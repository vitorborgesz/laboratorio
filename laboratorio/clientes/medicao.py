"""DESAFIO 5 - compara o tempo de upload pelo caso 1 (via API) e pelo caso 3 (link assinado).

Gera um arquivo PDF "falso" de N MB e envia pelos dois caminhos.
O caso 1 tem limite de 10 MB: para testar 50 MB, suba a API com
    TAMANHO_MAXIMO_MB=100 uvicorn app.main:app --reload

Para ver a memória da API enquanto o script roda, em outro terminal:
    top -p $(pgrep -f "uvicorn app.main:app" | tr '\\n' ',' | sed 's/,$//')

Uso: python clientes/medicao.py [tamanho_em_MB]
"""
import os
import sys
import time

import requests

API = "http://localhost:8000"
tamanho_mb = int(sys.argv[1]) if len(sys.argv) > 1 else 50
caminho = f"arquivos-teste/grande_{tamanho_mb}mb.pdf"

if not os.path.exists(caminho):
    with open(caminho, "wb") as f:
        f.write(os.urandom(tamanho_mb * 1024 * 1024))

# Caso 1: os bytes passam pela API
inicio = time.perf_counter()
with open(caminho, "rb") as f:
    r = requests.post(f"{API}/caso1/upload",
                      files={"arquivo": (os.path.basename(caminho), f, "application/pdf")})
tempo1 = time.perf_counter() - inicio
print(f"Caso 1 (via API):       HTTP {r.status_code}  {tempo1:6.2f} s")

# Caso 3: a API só gera o link e confirma
inicio = time.perf_counter()
link = requests.post(f"{API}/caso3/gerar-link",
                     json={"nome": os.path.basename(caminho), "content_type": "application/pdf"}).json()
with open(caminho, "rb") as f:
    put = requests.put(link["url_upload"], data=f, headers=link["headers_obrigatorios"])
conf = requests.post(f"{API}/caso3/confirmar/{link['id']}")
tempo3 = time.perf_counter() - inicio
print(f"Caso 3 (link assinado): HTTP {put.status_code}/{conf.status_code}  {tempo3:6.2f} s")
