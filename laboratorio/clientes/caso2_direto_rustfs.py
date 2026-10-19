"""CASO 2 - o cliente envia direto ao RustFS, sem passar pela API.

Repare: este script precisa conhecer a CHAVE e o SEGREDO do storage.
E o banco de dados nunca fica sabendo que o arquivo existe.

Uso: python clientes/caso2_direto_rustfs.py arquivos-teste/exemplo.txt
"""
import os
import sys

import boto3
from botocore.config import Config

caminho = sys.argv[1] if len(sys.argv) > 1 else "arquivos-teste/exemplo.txt"

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="labaluno",              # credencial exposta no cliente!
    aws_secret_access_key="labaluno-segredo-123",
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                  request_checksum_calculation="when_required",
                  response_checksum_validation="when_required"),
)

chave = f"caso2/{os.path.basename(caminho)}"
s3.upload_file(caminho, "uploads", chave)
print(f"Enviado para s3://uploads/{chave}")

print("\nObjetos no bucket agora:")
for obj in s3.list_objects_v2(Bucket="uploads").get("Contents", []):
    print(f"  {obj['Key']:60} {obj['Size']:>8} bytes")
