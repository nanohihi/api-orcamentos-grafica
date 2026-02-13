from flask import Flask, request, jsonify
import requests
import json
import os
import sys # Para logs

app = Flask(__name__)

# ================= 🔐 CREDENCIAIS =================
USERNAME = os.getenv("BMG_USER", "dbasilio")
PASSWORD = os.getenv("BMG_PASS", "20032025") 
ID_PONTO_ENTREGA_ESTATICO = 12943 # Confirma se este ID ainda é válido na tua conta
BASE_URL = "https://apicotizadorespanya.bibliomanager.com"

# ================= 📚 DICIONÁRIO DE TRADUÇÃO =================
MATERIAIS = {
    "encadernacao": { "Capa Mole": 45, "Tapa Blanda": 45 },
    "laminado": { "Mate": 47, "Brilho": 48, "Sem Laminar": 1118, "Antirisco": 949, "Soft Touch": 948 },
    "papel_miolo": { "Ahuesado 80 gr": 141, "Ahuesado 90 gr": 142, "Estucado Mate 115 gr": 149, "Offset 80 gr": 160, "Offset 90 gr": 161, "Offset 100 gr": 382, "Reciclado 90 gr": 1251 },
    "papel_capa": { "Cartolina Gráfica 240 gr": 35, "Cartolina Gráfica 260 gr": 83, "Estucado Mate 300 gr": 50, "Verjurado Branco 300 gr": 1145, "Reciclado 300 gr": 1143 }
}

DEFAULT_SPECS = {
    "coleccion": 11, "sangre": 13, "encuadernado": 45, "tinta": 29, 
    "papel_miolo": 161, "contiene_imagenes": 7, "tipo_trabalho_web": 853, 
    "impresion_tapa": 22, "tipo_tapa": 162, "papel_capa": 50, "laminado": 47, "solapa": 9,
    "ancho": 150, "alto": 230
}

# ================= 🛠️ HELPER =================
def safe_request(method, url, **kwargs):
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        
        try:
            return response.json()
        except json.JSONDecodeError:
            # Se não for JSON, imprime o erro no log do Coolify
            print(f"❌ [ERRO API] Não é JSON. Resposta: {response.text}", file=sys.stderr)
            raise Exception(f"A API não devolveu JSON. Resposta: {response.text[:200]}")
            
    except requests.exceptions.HTTPError as e:
        print(f"❌ [ERRO HTTP] {e.response.status_code} em {url}: {e.response.text}", file=sys.stderr)
        raise Exception(f"Erro HTTP {e.response.status_code} em {url}")
    except Exception as e:
        print(f"❌ [ERRO GERAL] {str(e)}", file=sys.stderr)
        raise e

# ================= ⚙️ LÓGICA =================

def obter_token_de_sessao(username, password):
    try:
        url = f"{BASE_URL}/Acceso"
        headers = {"User-Agent": "My-API-Client/1.0", "Origin": "https://editores.bibliomanager.com"}
        response = requests.get(url, auth=(username, password), headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ [LOGIN] Erro ao fazer login: {e}", file=sys.stderr)
        return None

def calcular_orcamento(token, quantidade, paginas, specs, id_morada):
    headers = {"Authorization": f"Bearer {token}"}
    headers_com_dados = {**headers, "Content-Type": "text/plain;charset=UTF-8"}
    
    try:
        # 1. CRIAR COTAÇÃO
        print(f"🔹 1. Criar Cotação para {quantidade}ex...", file=sys.stdout)
        payload_producao = { 
            "informacion": { "titulo": f"Auto {quantidade}ex", "cantidad": quantidade, "coleccion": specs["coleccion"], "isbn": "", "sku": 0, "nombreColeccion": "", "editorial": 0, "referenciaCliente": "AUTO-API" }, 
            "formato": { "ancho": specs["ancho"], "alto": specs["alto"], "sangre": specs["sangre"] }, 
            "acabado": { "encuadernado": specs["encuadernado"] }, 
            "interior": { "tinta": specs["tinta"], "paginas": { "paginasColor": 0, "paginasBN": paginas }, "papelBn": specs["papel_miolo"], "papelColor": 0, "contieneImagenes": specs["contiene_imagenes"], "tipoTrabajoWeb": specs["tipo_trabalho_web"] }, 
            "cubierta": { "impresionTapa": specs["impresion_tapa"], "tipoTapa": specs["tipo_tapa"], "tipoPapel": specs["papel_capa"], "laminado": specs["laminado"], "solapa": {"solapa": specs["solapa"]}, "papelSobrecubierta": 0, "laminadoSobrecubierta": 0 }, 
            "tapadura": {}, "inserciones": {}, "adicionales": {}, "observaciones": "", "idNegocio": 1, "idFilialProduccion": 1 
        }
        
        data_cot = safe_request('POST', f"{BASE_URL}/POD/guardarCotizacion", data=json.dumps(payload_producao), headers=headers_com_dados)
        
        # DEBUG: Verifica se oResultado existe
        if not data_cot.get("oResultado"):
            print(f"❌ [ERRO COTAÇÃO] Resposta vazia da API: {data_cot}", file=sys.stderr)
            raise Exception("A API não criou a cotação (oResultado vazio).")
            
        id_cotacao = data_cot["oResultado"]["idTrabajoRelacion"]
        print(f"✅ Cotação criada: {id_cotacao}", file=sys.stdout)

        # 2. AQUECIMENTO
        print(f"🔹 2. Aquecimento...", file=sys.stdout)
        safe_request('GET', f"{BASE_URL}/POD/dameCotizacion?idCotizacionCabecera={id_cotacao}&idFilialProduccion=1", headers=headers)
        safe_request('GET', f"{BASE_URL}/Utilidades/validarPuntoEntrega?idPuntoEntrega={id_morada}&idFilialProduccion=1", headers=headers)

        # 3. OPÇÕES DE ENVIO
        print(f"🔹 3. Opções de Envio...", file=sys.stdout)
        payload_opt = {"id_dir": id_morada, "id_cotizacion": id_cotacao, "und": quantidade, "termoempaque": 15, "undTermoempaque": 0, "idFilialProduccion": "1"}
        data_opt = safe_request('POST', f"{BASE_URL}/POD/distribucionEnvio", data=json.dumps(payload_opt), headers=headers_com_dados)
        
        # DEBUG: Verifica se devolveu opções
        if not data_opt.get("oResultado") or len(data_opt["oResultado"]) == 0:
             print(f"❌ [ERRO ENVIO] Sem opções de envio. Payload enviado: {payload_opt}. Resposta: {data_opt}", file=sys.stderr)
             raise Exception("A API não devolveu opções de envio. Verifica o ID da morada ou a quantidade.")
             
        id_dist_envio = data_opt["oResultado"][0]["gastos"][0]["id_distribucion_envio"]

        # 4. CONFIRMAR ENVIO
        print(f"🔹 4. Confirmar Envio {id_dist_envio}...", file=sys.stdout)
        payload_conf = {"id_distribucion_envio": id_dist_envio, "idFilialProduccion": "1"}
        data_conf = safe_request('PATCH', f"{BASE_URL}/POD/confirmaDistribucionEnvio", data=json.dumps(payload_conf), headers=headers_com_dados)
        
        if not data_conf.get("oResultado"):
             print(f"❌ [ERRO CONFIRMAÇÃO] Falha ao confirmar. Resposta: {data_conf}", file=sys.stderr)
             raise Exception("Falha ao confirmar envio.")

        id_dinamico = data_conf["oResultado"]["id_diccionario_punto_entrega"]

        # 5. TOTAL FINAL
        print(f"🔹 5. Total Final...", file=sys.stdout)
        payload_total = {"id_cotizacion_cabecera": id_cotacao, "numTrab": 1, "puntosEntrega": [{"id_diccionario_punto_entrega": id_dinamico}], "idFilialProduccion": "1"}
        data_total = safe_request('POST', f"{BASE_URL}/POD/dameTotalIva", data=json.dumps(payload_total), headers=headers_com_dados)
        data = data_total["oResultado"]

        # 6. RESULTADO
        preco_unit = float(data["precios_unitarios"][0]["precio_unidad"])
        total_prod = preco_unit * quantidade
        envio = float(data["precio_distribución"])
        iva = float(data["IVA_productivo"]) + float(data["IVA_logistica"])
        total_final = total_prod + envio + iva

        return {
            "success": True,
            "dados": {
                "qtd": quantidade,
                "paginas": paginas,
                "producao": round(total_prod, 2),
                "envio": round(envio, 2),
                "iva": round(iva, 2),
                "total_final": round(total_final, 2)
            }
        }

    except Exception as e:
        print(f"❌ [EXCEPTION] {str(e)}", file=sys.stderr)
        return {"success": False, "error": str(e)}

# ================= ROTA API =================

@app.route('/orcamento', methods=['POST'])
def endpoint_orcamento():
    data = request.json
    print(f"📥 Pedido Recebido: {data}", file=sys.stdout)
    
    quantidade = data.get('quantidade')
    paginas = data.get('paginas')
    
    if not quantidade or not paginas:
        return jsonify({"error": "Faltam dados (quantidade, paginas)"}), 400

    specs = DEFAULT_SPECS.copy()
    
    # Mapeamento
    mapeamentos = [('papel_miolo', 'papel_miolo'), ('papel_capa', 'papel_capa'), ('laminado', 'laminado'), ('encadernacao', 'encadernado')]
    for json_key, dict_key in mapeamentos:
        if json_key in data:
            nome = data[json_key]
            cat = 'encadernacao' if json_key == 'encadernacao' else json_key
            if nome in MATERIAIS[cat]:
                specs[dict_key] = MATERIAIS[cat][nome]
            else:
                return jsonify({"error": f"Material inválido: '{nome}' em '{json_key}'"}), 400

    # Lógica de Cor / Tamanho (Simplificada para debug)
    if 'largura' in data: specs['ancho'] = int(data['largura'])
    if 'altura' in data: specs['alto'] = int(data['altura'])
    
    # Autenticação
    token = obter_token_de_sessao(USERNAME, PASSWORD)
    if not token:
        return jsonify({"error": "Falha login gráfica"}), 500

    resultado = calcular_orcamento(token, quantidade, paginas, specs, ID_PONTO_ENTREGA_ESTATICO)
    
    status_code = 200 if resultado["success"] else 500
    return jsonify(resultado), status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
