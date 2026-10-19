"""CASO 3 - a API gera um link assinado; o cliente envia os bytes direto ao RustFS.

Fluxo: 1) pede o link à API   2) faz PUT no RustFS   3) confirma na API

Uso: python clientes/caso3_link_assinado.py arquivos-teste/exemplo.txt
"""
import mimetypes
import os
import sys

import requests

API = "http://localhost:8000"
caminho = sys.argv[1] if len(sys.argv) > 1 else "arquivos-teste/exemplo.txt"
content_type = mimetypes.guess_type(caminho)[0] or "application/octet-stream"

# 1) pedir o link
link = requests.post(f"{API}/caso3/gerar-link",
                     json={"nome": os.path.basename(caminho), "content_type": content_type}).json()
print("1) Link recebido (id", link["id"], ")")
print("  ", link["url_upload"][:120], "...")

# 2) enviar os bytes DIRETO para o RustFS (a API não vê este tráfego)
with open(caminho, "rb") as f:
    put = requests.put(link["url_upload"], data=f, headers=link["headers_obrigatorios"])
print("2) PUT no RustFS ->", put.status_code)
put.raise_for_status()

# 3) confirmar
conf = requests.post(f"{API}/caso3/confirmar/{link['id']}")
print("3) Confirmação ->", conf.status_code, conf.json())
