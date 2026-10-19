"""CASO 1 - o arquivo passa pela API, que salva no Postgres e no RustFS.

Uso: python clientes/caso1_via_api.py arquivos-teste/exemplo.txt
"""
import mimetypes
import os
import sys

import requests

API = "http://localhost:8000"
caminho = sys.argv[1] if len(sys.argv) > 1 else "arquivos-teste/exemplo.txt"
content_type = mimetypes.guess_type(caminho)[0] or "application/octet-stream"

with open(caminho, "rb") as f:
    resp = requests.post(f"{API}/caso1/upload",
                         files={"arquivo": (os.path.basename(caminho), f, content_type)})

print(resp.status_code, resp.json())
arquivo_id = resp.json()["id"]
print(f"\nBaixe do banco em: {API}/caso1/arquivos/{arquivo_id}/do-banco")
