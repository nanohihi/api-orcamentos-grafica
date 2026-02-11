from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

# ================= 🔐 CREDENCIAIS =================
# O script tenta ler do Coolify. Se não encontrar, usa o valor fixo.
USERNAME = os.getenv("BMG_USER", "dbasilio")
PASSWORD = os.getenv("BMG_PASS", "20032025") 
ID_PONTO_ENTREGA_ESTATICO = 6909
BASE_URL = "https://apicotizadorespanya.bibliomanager.com"

# ================= 📚 DICIONÁRIO DE TRADUÇÃO =================
# Mapeia os nomes que vêm do n8n/Lovable para os IDs da API
MATERIAIS = {
    "encadernacao": {
        "Capa Mole": 45,  
        "Tapa Blanda": 45
    },
    "laminado": {
        "Mate": 47,
        "Brilho": 48,
        "Sem Laminar": 1118,
        "Antirisco": 949,
        "Soft Touch": 948
    },
    "papel_miolo": {
        "Ahuesado 80 gr": 141,
        "Ahuesado 90 gr": 142,
        "Estucado Mate 115 gr": 149,
        "Offset 80 gr": 160,
        "Offset 90 gr": 161,
        "Offset 100 gr": 382,
        "Reciclado 90 gr": 1251
    },
    "papel_capa": {
        "Cartolina Gráfica 240 gr": 35,
        "Cartolina Gráfica 260 gr": 83,
        "Estucado Mate 300 gr": 50,
        "Verjurado Branco 300 gr": 1145,
        "Reciclado 300 gr": 1143
    }
}

# Configuração Padrão
DEFAULT_SPECS = {
    "coleccion": 11, "sangre": 13, "encuadernado": 45, "tinta": 29, 
    "papel_miolo": 161, "contiene_imagenes": 7, "tipo_trabalho_web": 853, 
    "impresion_tapa": 22, "tipo_tapa": 162, "papel_capa": 50, 
    "laminado": 47, "solapa": 9
}

# ================= ⚙️ LÓGICA TÉCNICA =================

def obter_token_de_sessao(username, password):
    try:
        url_acesso = f"{BASE_URL}/Acceso"
        headers = {"User-Agent": "My-API-Client/1.0", "Origin": "https://editores.bibliomanager.com"}
        response = requests.get(url_acesso, auth=(username, password), headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Erro login: {e}")
        return None

def calcular_orcamento(token, quantidade, paginas, specs, id_morada):
    headers = {"Authorization": f"Bearer {token}"}
    headers_com_dados = {**headers, "Content-Type": "text/plain;charset=UTF-8"}
    
    try:
        # 1. CRIAR COTAÇÃO
        url_guardar = f"{BASE_URL}/POD/guardarCotizacion"
        payload_producao = { 
            "informacion": { "titulo": f"Auto {quantidade}ex", "cantidad": quantidade, "coleccion": specs["coleccion"], "isbn": "", "sku": 0, "nombreColeccion": "", "editorial": 0, "referenciaCliente": "AUTO-API" }, 
            "formato": { "ancho": 150, "alto": 230, "sangre": specs["sangre"] }, 
            "acabado": { "encuadernado": specs["encuadernado"] }, 
            "interior": { "tinta": specs["tinta"], "paginas": { "paginasColor": 0, "paginasBN": paginas }, "papelBn": specs["papel_miolo"], "papelColor": 0, "contieneImagenes": specs["contiene_imagenes"], "tipoTrabajoWeb": specs["tipo_trabalho_web"] }, 
            "cubierta": { "impresionTapa": specs["impresion_tapa"], "tipoTapa": specs["tipo_tapa"], "tipoPapel": specs["papel_capa"], "laminado": specs["laminado"], "solapa": {"solapa": specs["solapa"]}, "papelSobrecubierta": 0, "laminadoSobrecubierta": 0 }, 
            "tapadura": {}, "inserciones": {}, "adicionales": {}, "observaciones": "", "idNegocio": 1, "idFilialProduccion": 1 
        }
        
        res = requests.post(url_guardar, data=json.dumps(payload_producao), headers=headers_com_dados)
        res.raise_for_status()
        id_cotacao = res.json()["oResultado"]["idTrabajoRelacion"]

        # 2. AQUECIMENTO
        requests.get(f"{BASE_URL}/POD/dameCotizacion?idCotizacionCabecera={id_cotacao}&idFilialProduccion=1", headers=headers)
        requests.get(f"{BASE_URL}/Utilidades/validarPuntoEntrega?idPuntoEntrega={id_morada}&idFilialProduccion=1", headers=headers)

        # 3. OPÇÕES DE ENVIO
        url_opt_envio = f"{BASE_URL}/POD/distribucionEnvio"
        payload_opt = {"id_dir": id_morada, "id_cotizacion": id_cotacao, "und": quantidade, "termoempaque": 15, "undTermoempaque": 0, "idFilialProduccion": "1"}
        res_opt = requests.post(url_opt_envio, data=json.dumps(payload_opt), headers=headers_com_dados)
        
        # Pega a primeira opção
        id_dist_envio = res_opt.json()["oResultado"][0]["gastos"][0]["id_distribucion_envio"]

        # 4. CONFIRMAR ENVIO (ID Dinâmico)
        url_conf = f"{BASE_URL}/POD/confirmaDistribucionEnvio"
        payload_conf = {"id_distribucion_envio": id_dist_envio, "idFilialProduccion": "1"}
        res_conf = requests.patch(url_conf, data=json.dumps(payload_conf), headers=headers_com_dados)
        id_dinamico = res_conf.json()["oResultado"]["id_diccionario_punto_entrega"]

        # 5. TOTAL FINAL
        url_total = f"{BASE_URL}/POD/dameTotalIva"
        payload_total = {"id_cotizacion_cabecera": id_cotacao, "numTrab": 1, "puntosEntrega": [{"id_diccionario_punto_entrega": id_dinamico}], "idFilialProduccion": "1"}
        res_total = requests.post(url_total, data=json.dumps(payload_total), headers=headers_com_dados)
        data = res_total.json()["oResultado"]

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
        return {"success": False, "error": str(e)}

# ================= ROTA API =================

@app.route('/orcamento', methods=['POST'])
def endpoint_orcamento():
    data = request.json
    quantidade = data.get('quantidade')
    paginas = data.get('paginas')
    
    if not quantidade or not paginas:
        return jsonify({"error": "Faltam dados obrigatórios (quantidade, paginas)"}), 400

    # Configurar specs com base nos nomes enviados
    specs = DEFAULT_SPECS.copy()
    
    mapeamentos = [
        ('papel_miolo', 'papel_miolo'),
        ('papel_capa', 'papel_capa'),
        ('laminado', 'laminado'),
        ('encadernacao', 'encadernado') # Nome no JSON -> Nome no dicionário
    ]

    for campo_json, campo_specs in mapeamentos:
        if campo_json in data:
            nome = data[campo_json]
            # Procura no dicionário MATERIAIS
            categoria = 'encadernacao' if campo_json == 'encadernacao' else campo_json
            
            if nome in MATERIAIS[categoria]:
                specs[campo_specs] = MATERIAIS[categoria][nome]
            else:
                return jsonify({"error": f"Material desconhecido: '{nome}' em '{campo_json}'. Opções: {list(MATERIAIS[categoria].keys())}"}), 400

    # Executar
    token = obter_token_de_sessao(USERNAME, PASSWORD)
    if not token:
        return jsonify({"error": "Falha login gráfica"}), 500

    resultado = calcular_orcamento(token, quantidade, paginas, specs, ID_PONTO_ENTREGA_ESTATICO)
    
    if resultado["success"]:
        return jsonify(resultado)
    else:
        return jsonify(resultado), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)