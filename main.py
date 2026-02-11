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

# ================= 📚 DICIONÁRIO DE TRADUÇÃO BASE =================
# Valores fixos que não dependem de chamadas dinâmicas
FIXOS = {
    "tinta": {
        "Preto": 29, 
        "Cor": 30, # Assumindo 30 (tens de confirmar se é 30 ou outro ID para "Color")
    },
    "imagens": {
        True: 23,  # Assumindo 23 para Sim (com base no código antigo)
        False: 7   # Não
    }
}

DEFAULT_SPECS = {
    "coleccion": 11, "sangre": 13, "encuadernado": 45, "tinta": 29, 
    "papel_miolo": 161, "contiene_imagenes": 7, "tipo_trabalho_web": 853, 
    "impresion_tapa": 22, "tipo_tapa": 162, "papel_capa": 50, "laminado": 47, "solapa": 9,
    "ancho": 150, "alto": 230
}

# ================= ⚙️ LÓGICA =================

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

def carregar_metadados(token):
    """Carrega dinamicamente os papéis de Preto e de Cor."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "text/plain;charset=UTF-8"}
    metadados = {"papel_miolo_preto": {}, "papel_miolo_cor": {}, "papel_capa": {}, "laminado": {}, "encadernado": {}}
    
    try:
        # Papel Miolo PRETO (id_metadato=3)
        res_preto = requests.get(f"{BASE_URL}/Metadatos/dameRelacionesMetadatosCompuestos?id_tipo=1&id_metadato=3&idFilial=1&idTrabajoWeb=853", headers=headers).json()
        metadados['papel_miolo_preto'] = {item['nombre'].strip().replace('  ', ' '): item['id_rel'] for item in res_preto['oResultado']}

        # Papel Miolo COR (id_metadato=4) - A tua descoberta!
        res_cor = requests.get(f"{BASE_URL}/Metadatos/dameRelacionesMetadatosCompuestos?id_tipo=1&id_metadato=4&idFilial=1&tieneRangoPaginas=1&idTrabajoWeb=853", headers=headers).json()
        metadados['papel_miolo_cor'] = {item['nombre'].strip().replace('  ', ' '): item['id_rel'] for item in res_cor['oResultado']}

        # Papel Capa
        res_capa = requests.get(f"{BASE_URL}/Metadatos/dameRelacionesMetadatosCompuestos?id_tipo=1&id_metadato=5&idFilial=1", headers=headers).json()
        metadados['papel_capa'] = {item['nombre'].strip().replace('  ', ' '): item['id_rel'] for item in res_capa['oResultado']}

        # Laminado
        res_lam = requests.get(f"{BASE_URL}/Metadatos/dameRelacionesMetadatosCompuestos?id_tipo=11&id_metadato=5&idFilial=1", headers=headers).json()
        metadados['laminado'] = {item['nombre'].strip(): item['id_rel'] for item in res_lam['oResultado']}

        # Encadernação
        res_enc = requests.get(f"{BASE_URL}/Metadatos/dameRelacionesMetadatos?id_tipo=4&idFilial=1", headers=headers).json()
        metadados['encadernado'] = {item['nombre'].strip(): item['id_rel'] for item in res_enc['oResultado']}

        return metadados
    except Exception as e:
        print(f"Erro metadados: {e}")
        return None

def calcular_orcamento(token, quantidade, paginas, specs, id_morada):
    headers = {"Authorization": f"Bearer {token}"}
    headers_com_dados = {**headers, "Content-Type": "text/plain;charset=UTF-8"}
    
    try:
        # Lógica para cor: Se for cor, paginasColor = total, paginasBN = 0
        paginas_bn = paginas
        paginas_cor = 0
        
        # Se a tinta não for a padrão (29=Preto), assumimos que é tudo a cores
        # Nota: Ajusta esta lógica se quiseres misturar preto e cor
        if specs['tinta'] != 29:
            paginas_bn = 0
            paginas_cor = paginas

        payload_producao = { 
            "informacion": { "titulo": f"Auto {quantidade}ex", "cantidad": quantidade, "coleccion": specs["coleccion"], "isbn": "", "sku": 0, "nombreColeccion": "", "editorial": 0, "referenciaCliente": "AUTO-API" }, 
            "formato": { "ancho": specs["ancho"], "alto": specs["alto"], "sangre": specs["sangre"] }, 
            "acabado": { "encuadernado": specs["encuadernado"] }, 
            "interior": { 
                "tinta": specs["tinta"], 
                "paginas": { "paginasColor": paginas_cor, "paginasBN": paginas_bn }, 
                # Papel depende se é cor ou preto. Se tiveres papelBn e papelColor definidos nas specs, usa-os.
                # Aqui simplificamos: se for cor, usa o ID no campo papelColor.
                "papelBn": specs["papel_miolo"] if paginas_bn > 0 else 0,
                "papelColor": specs["papel_miolo"] if paginas_cor > 0 else 0,
                "contieneImagenes": specs["contiene_imagenes"], 
                "tipoTrabajoWeb": specs["tipo_trabalho_web"] 
            }, 
            "cubierta": { "impresionTapa": specs["impresion_tapa"], "tipoTapa": specs["tipo_tapa"], "tipoPapel": specs["papel_capa"], "laminado": specs["laminado"], "solapa": {"solapa": specs["solapa"]}, "papelSobrecubierta": 0, "laminadoSobrecubierta": 0 }, 
            "tapadura": {}, "inserciones": {}, "adicionales": {}, "observaciones": "", "idNegocio": 1, "idFilialProduccion": 1 
        }
        
        res = requests.post(f"{BASE_URL}/POD/guardarCotizacion", data=json.dumps(payload_producao), headers=headers_com_dados)
        res.raise_for_status()
        id_cotacao = res.json()["oResultado"]["idTrabajoRelacion"]

        requests.get(f"{BASE_URL}/POD/dameCotizacion?idCotizacionCabecera={id_cotacao}&idFilialProduccion=1", headers=headers)
        requests.get(f"{BASE_URL}/Utilidades/validarPuntoEntrega?idPuntoEntrega={id_morada}&idFilialProduccion=1", headers=headers)

        payload_opt = {"id_dir": id_morada, "id_cotizacion": id_cotacao, "und": quantidade, "termoempaque": 15, "undTermoempaque": 0, "idFilialProduccion": "1"}
        res_opt = requests.post(f"{BASE_URL}/POD/distribucionEnvio", data=json.dumps(payload_opt), headers=headers_com_dados)
        id_dist_envio = res_opt.json()["oResultado"][0]["gastos"][0]["id_distribucion_envio"]

        payload_conf = {"id_distribucion_envio": id_dist_envio, "idFilialProduccion": "1"}
        res_conf = requests.patch(f"{BASE_URL}/POD/confirmaDistribucionEnvio", data=json.dumps(payload_conf), headers=headers_com_dados)
        id_dinamico = res_conf.json()["oResultado"]["id_diccionario_punto_entrega"]

        payload_total = {"id_cotizacion_cabecera": id_cotacao, "numTrab": 1, "puntosEntrega": [{"id_diccionario_punto_entrega": id_dinamico}], "idFilialProduccion": "1"}
        res_total = requests.post(f"{BASE_URL}/POD/dameTotalIva", data=json.dumps(payload_total), headers=headers_com_dados)
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

@app.route('/orcamento', methods=['POST'])
def endpoint_orcamento():
    data = request.json
    quantidade = data.get('quantidade')
    paginas = data.get('paginas')
    
    if not quantidade or not paginas:
        return jsonify({"error": "Faltam dados"}), 400

    token = obter_token_de_sessao(USERNAME, PASSWORD)
    if not token:
        return jsonify({"error": "Falha login"}), 500

    # Carregar metadados dinâmicos
    metadados = carregar_metadados(token)
    if not metadados:
        return jsonify({"error": "Falha metadados"}), 500

    specs = DEFAULT_SPECS.copy()
    
    # 1. Configurar Tinta e Imagens
    impressao_nome = data.get('impressao', 'Preto') # Padrão Preto
    if impressao_nome in FIXOS['tinta']:
        specs['tinta'] = FIXOS['tinta'][impressao_nome]
    
    tem_imagens = data.get('imagens', False) # Padrão False
    specs['contiene_imagenes'] = FIXOS['imagens'][bool(tem_imagens)]

    # 2. Configurar Papel MIOLO (Lógica Inteligente)
    # Se for "Cor", procura no dicionário de cor. Se for "Preto", no de preto.
    nome_papel_miolo = data.get('papel_miolo')
    if nome_papel_miolo:
        dicionario_alvo = metadados['papel_miolo_cor'] if impressao_nome == 'Cor' else metadados['papel_miolo_preto']
        
        if nome_papel_miolo in dicionario_alvo:
            specs['papel_miolo'] = dicionario_alvo[nome_papel_miolo]
        else:
            return jsonify({"error": f"Papel '{nome_papel_miolo}' indisponível para impressão '{impressao_nome}'"}), 400

    # 3. Configurar Restante (Capa, Laminado, etc.)
    if 'papel_capa' in data and data['papel_capa'] in metadados['papel_capa']:
        specs['papel_capa'] = metadados['papel_capa'][data['papel_capa']]
        
    if 'laminado' in data and data['laminado'] in metadados['laminado']:
        specs['laminado'] = metadados['laminado'][data['laminado']]
        
    if 'encadernacao' in data and data['encadernacao'] in metadados['encadernado']:
        specs['encadernado'] = metadados['encadernado'][data['encadernacao']]

    # Tamanho
    if 'largura' in data: specs['ancho'] = int(data['largura'])
    if 'altura' in data: specs['alto'] = int(data['altura'])

    resultado = calcular_orcamento(token, quantidade, paginas, specs, ID_PONTO_ENTREGA_ESTATICO)
    
    status_code = 200 if resultado["success"] else 500
    return jsonify(resultado), status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
