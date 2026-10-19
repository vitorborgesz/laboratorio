"""CASO 4 - link de download temporário.

Uso: python clientes/caso4_link_download.py <id> [segundos_validade]
Ex.: python clientes/caso4_link_download.py 2 10
"""
import sys
import time

import requests

API = "http://localhost:8000"
arquivo_id = sys.argv[1]
validade = int(sys.argv[2]) if len(sys.argv) > 2 else 10

link = requests.get(f"{API}/caso4/link-download/{arquivo_id}",
                    params={"expira_em_segundos": validade}).json()
url = link["url_download"]
print("Link:", url[:120], "...")

r = requests.get(url)
print(f"Download agora           -> HTTP {r.status_code}, {len(r.content)} bytes")

print(f"Esperando {validade + 2}s para o link expirar...")
time.sleep(validade + 2)

r = requests.get(url)
print(f"Download após expirar    -> HTTP {r.status_code}")
