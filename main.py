from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

# ================= 🔐 CREDENCIAIS =================
USERNAME = os.getenv("BMG_USER", "dbasilio")
PASSWORD = os.getenv("BMG_PASS", "20032025") 
ID_PONTO_ENTREGA_ESTATICO = 12943
BASE_URL = "https://apicotizadorespanya.bibliomanager.com"

# ================= 📚 DICIONÁRIO DE TRADUÇÃO =================
MATERIAIS = {
    "encadernacao": { "Capa Mole": 45, "Tapa Blanda": 45 },
    "laminado": { "Mate": 47, "Brilho": 48, "Sem Laminar": 1118, "Antirisco": 949, "Soft Touch": 948 },
    "papel_miolo": { "Ahuesado 80 gr": 141, "Ahuesado 90 gr": 142, "Estucado Mate 115 gr": 149, "Offset 80 gr": 160, "Offset 90 gr": 161, "Offset 100 gr": 382, "Reciclado 90 gr": 1251 },
    "papel_capa": { "Cartolina Gráfica 240 gr": 35, "Cartolina Gráfica 260 gr": 83, "Estucado Mate 300 gr": 50, "Verjurado Branco 300 gr": 1145, "Reciclado 300 gr": 1143 }
}

# ⭐️ MUDANÇA 1: Adicionei largura (ancho) e altura (alto) aos padrões
DEFAULT_SPECS = {
    "coleccion": 11, "sangre": 13, "encuadernado": 45, "tinta": 29, 
    "papel_miolo": 161, "contiene_imagenes": 7, "tipo_trabalho_web": 853, 
    "impresion_tapa": 22, "tipo_tapa": 162, "papel_capa": 50, "laminado": 47, "solapa": 9,
    "ancho": 150, # Largura padrão em mm
    "alto": 230   # Altura padrão em mm
}

# ================= 🛠️ HELPER PARA PEDIDOS SEGUROS =================
def safe_request(method, url, **kwargs):
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        try:
            return response.json()
        except json.JSONDecodeError:
            raise Exception(f"A API não devolveu JSON. Resposta: {response.text[:200]}")
    except requests.exceptions.HTTPError as e:
        raise Exception(f"Erro HTTP {e.response.status_code} em {url}: {e.response.text[:200]}")
    except Exception as e:
        raise e

# ================= ⚙️ LÓGICA DO ORÇAMENTO =================

def obter_token_de_sessao(username, password):
    try:
        url = f"{BASE_URL}/Acceso"
        headers = {"User-Agent": "My-API-Client/1.0", "Origin": "https://editores.bibliomanager.com"}
        response = requests.get(url, auth=(username, password), headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Erro login: {e}")
        return None

def calcular_orcamento(token, quantidade, paginas, specs, id_morada):
    headers = {"Authorization": f"Bearer {token}"}
    headers_com_dados = {**headers, "Content-Type": "text/plain;charset=UTF-8"}
    
    try:
        # ⭐️ MUDANÇA 2: Usar specs['ancho'] e specs['alto'] em vez de números fixos
        payload_producao = { 
            "informacion": { "titulo": f"Auto {quantidade}ex", "cantidad": quantidade, "coleccion": specs["coleccion"], "isbn": "", "sku": 0, "nombreColeccion": "", "editorial": 0, "referenciaCliente": "AUTO-API" }, 
            "formato": { "ancho": specs["ancho"], "alto": specs["alto"], "sangre": specs["sangre"] }, 
            "acabado": { "encuadernado": specs["encuadernado"] }, 
            "interior": { "tinta": specs["tinta"], "paginas": { "paginasColor": 0, "paginasBN": paginas }, "papelBn": specs["papel_miolo"], "papelColor": 0, "contieneImagenes": specs["contiene_imagenes"], "tipoTrabajoWeb": specs["tipo_trabalho_web"] }, 
            "cubierta": { "impresionTapa": specs["impresion_tapa"], "tipoTapa": specs["tipo_tapa"], "tipoPapel": specs["papel_capa"], "laminado": specs["laminado"], "solapa": {"solapa": specs["solapa"]}, "papelSobrecubierta": 0, "laminadoSobrecubierta": 0 }, 
            "tapadura": {}, "inserciones": {}, "adicionales": {}, "observaciones": "", "idNegocio": 1, "idFilialProduccion": 1 
        }
        
        data_cot = safe_request('POST', f"{BASE_URL}/POD/guardarCotizacion", data=json.dumps(payload_producao), headers=headers_com_dados)
        id_cotacao = data_cot["oResultado"]["idTrabajoRelacion"]

        # Aquecimento
        safe_request('GET', f"{BASE_URL}/POD/dameCotizacion?idCotizacionCabecera={id_cotacao}&idFilialProduccion=1", headers=headers)
        safe_request('GET', f"{BASE_URL}/Utilidades/validarPuntoEntrega?idPuntoEntrega={id_morada}&idFilialProduccion=1", headers=headers)

        # Opções Envio
        payload_opt = {"id_dir": id_morada, "id_cotizacion": id_cotacao, "und": quantidade, "termoempaque": 15, "undTermoempaque": 0, "idFilialProduccion": "1"}
        data_opt = safe_request('POST', f"{BASE_URL}/POD/distribucionEnvio", data=json.dumps(payload_opt), headers=headers_com_dados)
        
        if not data_opt.get("oResultado") or len(data_opt["oResultado"]) == 0:
             raise Exception("A API não devolveu opções de envio.")
        id_dist_envio = data_opt["oResultado"][0]["gastos"][0]["id_distribucion_envio"]

        # Confirmar Envio
        payload_conf = {"id_distribucion_envio": id_dist_envio, "idFilialProduccion": "1"}
        data_conf = safe_request('PATCH', f"{BASE_URL}/POD/confirmaDistribucionEnvio", data=json.dumps(payload_conf), headers=headers_com_dados)
        id_dinamico = data_conf["oResultado"]["id_diccionario_punto_entrega"]

        # Total Final
        payload_total = {"id_cotizacion_cabecera": id_cotacao, "numTrab": 1, "puntosEntrega": [{"id_diccionario_punto_entrega": id_dinamico}], "idFilialProduccion": "1"}
        data_total = safe_request('POST', f"{BASE_URL}/POD/dameTotalIva", data=json.dumps(payload_total), headers=headers_com_dados)
        data = data_total["oResultado"]

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
                "formato": f"{specs['ancho']}x{specs['alto']}mm", # Adicionei info do formato na resposta
                "producao": round(total_prod, 2),
                "envio": round(envio, 2),
                "iva": round(iva, 2),
                "total_final": round(total_final, 2)
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

# ================= ROTA API =================

@app.route('/orcamento', methods=['POST'])
def endpoint_orcamento():
    data = request.json
    quantidade = data.get('quantidade')
    paginas = data.get('paginas')
    
    if not quantidade or not paginas:
        return jsonify({"error": "Faltam dados (quantidade, paginas)"}), 400

    specs = DEFAULT_SPECS.copy()
    
    # ⭐️ MUDANÇA 3: Ler largura e altura do JSON (se existirem)
    if 'largura' in data:
        try:
            specs['ancho'] = int(data['largura'])
        except:
            return jsonify({"error": "Largura tem de ser um número inteiro (mm)"}), 400
            
    if 'altura' in data:
        try:
            specs['alto'] = int(data['altura'])
        except:
            return jsonify({"error": "Altura tem de ser um número inteiro (mm)"}), 400

    # Mapeamento materiais
    mapeamentos = [('papel_miolo', 'papel_miolo'), ('papel_capa', 'papel_capa'), ('laminado', 'laminado'), ('encadernacao', 'encadernado')]
    for json_key, dict_key in mapeamentos:
        if json_key in data:
            nome = data[json_key]
            cat = 'encadernacao' if json_key == 'encadernacao' else json_key
            if nome in MATERIAIS[cat]:
                specs[dict_key] = MATERIAIS[cat][nome]
            else:
                return jsonify({"error": f"Material inválido: '{nome}' em '{json_key}'"}), 400

    token = obter_token_de_sessao(USERNAME, PASSWORD)
    if not token:
        return jsonify({"error": "Falha login gráfica"}), 500

    resultado = calcular_orcamento(token, quantidade, paginas, specs, ID_PONTO_ENTREGA_ESTATICO)
    
    status_code = 200 if resultado["success"] else 500
    return jsonify(resultado), status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
