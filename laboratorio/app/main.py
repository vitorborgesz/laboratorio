"""
Laboratório: Upload de arquivos com FastAPI, PostgreSQL e RustFS (S3)

Casos:
  1 - API recebe o arquivo e salva no banco (BYTEA) e no RustFS
  2 - Cliente envia direto ao RustFS (sem API) -> ver clientes/caso2_direto_rustfs.py
  3 - API gera link assinado (presigned PUT); cliente envia direto ao RustFS;
      API guarda só os metadados no Postgres
  4 - API gera link assinado de DOWNLOAD (presigned GET) com validade curta
  5 - Auditoria: compara o que existe no banco com o que existe no bucket

Extras: validação de tipo no caso 3, DELETE /arquivos/{id}, limpeza de
pendentes expirados e uma página HTML (GET /pagina) que usa o fluxo do caso 3.
"""
import hashlib
import os
import uuid
from contextlib import asynccontextmanager

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuração (valores padrão batem com o docker-compose.yml)
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lab:lab@localhost:5432/lab_upload")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "labaluno")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "labaluno-segredo-123")
BUCKET = os.getenv("S3_BUCKET", "uploads")
TAMANHO_MAXIMO = int(os.getenv("TAMANHO_MAXIMO_MB", "10")) * 1024 * 1024  # limite do caso 1
TIPOS_PERMITIDOS_CASO3 = {"image/png", "image/jpeg", "application/pdf"}
MINUTOS_PARA_EXPIRAR_PENDENTE = 10
PAGINA_HTML = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name="us-east-1",
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        # evita cabeçalhos de checksum novos do boto3 que alguns servidores S3-compatíveis não aceitam
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    ),
)

# A tabela "arquivos" NÃO é criada aqui: quem cuida do esquema do banco é o
# Alembic (pasta migrations/). Rode "alembic upgrade head" antes de subir a API.


def db():
    return psycopg.connect(DATABASE_URL, autocommit=True)


def nova_chave(caso: str, nome: str) -> str:
    """Gera um nome único no bucket: caso1/3f2a..._relatorio.pdf"""
    return f"{caso}/{uuid.uuid4().hex}_{os.path.basename(nome)}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with db() as conn:
        (tabela,) = conn.execute("SELECT to_regclass('public.arquivos')").fetchone()
    if tabela is None:
        raise RuntimeError(
            "Tabela 'arquivos' não existe. Rode as migrações antes: alembic upgrade head"
        )
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=BUCKET)
    # CORS no bucket: sem isso o navegador bloqueia o PUT da página /pagina
    try:
        s3.put_bucket_cors(
            Bucket=BUCKET,
            CORSConfiguration={"CORSRules": [{
                "AllowedOrigins": ["http://localhost:8000", "http://127.0.0.1:8000"],
                "AllowedMethods": ["PUT", "GET"],
                "AllowedHeaders": ["*"],
                "MaxAgeSeconds": 3000,
            }]},
        )
    except ClientError as erro:
        print(f"Aviso: não foi possível configurar CORS no bucket ({erro})")
    yield


app = FastAPI(title="Lab Upload - Desenvolvimento Web", lifespan=lifespan)


@app.get("/")
def raiz():
    return {"status": "ok", "docs": "/docs", "bucket": BUCKET, "rustfs": S3_ENDPOINT}


@app.get("/arquivos")
def listar_arquivos():
    """Lista os metadados (nunca os bytes) de tudo que está no banco."""
    with db() as conn:
        linhas = conn.execute(
            "SELECT id, caso, nome, content_type, tamanho, chave_objeto, status, "
            "conteudo IS NOT NULL AS tem_bytes_no_banco, criado_em "
            "FROM arquivos ORDER BY id"
        ).fetchall()
    campos = ["id", "caso", "nome", "content_type", "tamanho", "chave_objeto",
              "status", "tem_bytes_no_banco", "criado_em"]
    return [dict(zip(campos, linha)) for linha in linhas]


# ---------------------------------------------------------------------------
# CASO 1 - o arquivo passa pela API e é salvo no banco E no RustFS
# ---------------------------------------------------------------------------
@app.post("/caso1/upload")
def caso1_upload(arquivo: UploadFile = File(...)):
    conteudo = arquivo.file.read()
    if len(conteudo) > TAMANHO_MAXIMO:
        raise HTTPException(413, f"Arquivo maior que {TAMANHO_MAXIMO // (1024 * 1024)} MB")
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    chave = nova_chave("caso1", arquivo.filename)
    content_type = arquivo.content_type or "application/octet-stream"

    # 1) grava no RustFS
    s3.put_object(Bucket=BUCKET, Key=chave, Body=conteudo, ContentType=content_type)

    # 2) grava no Postgres (metadados + os próprios bytes)
    with db() as conn:
        (novo_id,) = conn.execute(
            "INSERT INTO arquivos (caso, nome, content_type, tamanho, chave_objeto, conteudo, hash_sha256) "
            "VALUES ('caso1', %s, %s, %s, %s, %s, %s) RETURNING id",
            (arquivo.filename, content_type, len(conteudo), chave, conteudo, hash_sha256),
        ).fetchone()

    return {"id": novo_id, "nome": arquivo.filename, "tamanho": len(conteudo),
            "chave_objeto": chave, "hash_sha256": hash_sha256}


@app.get("/caso1/arquivos/{arquivo_id}/do-banco")
def caso1_baixar_do_banco(arquivo_id: int):
    """Devolve o arquivo lendo os bytes direto do Postgres."""
    with db() as conn:
        linha = conn.execute(
            "SELECT nome, content_type, conteudo FROM arquivos WHERE id = %s AND conteudo IS NOT NULL",
            (arquivo_id,),
        ).fetchone()
    if not linha:
        raise HTTPException(404, "Arquivo não encontrado no banco")
    nome, content_type, conteudo = linha
    return Response(
        content=bytes(conteudo),
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ---------------------------------------------------------------------------
# CASO 2 - não tem endpoint! O cliente fala direto com o RustFS.
#          Veja clientes/caso2_direto_rustfs.py e depois rode /caso5/auditoria
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CASO 3 - API gera link assinado; os bytes NÃO passam pela API
# ---------------------------------------------------------------------------
class PedidoLink(BaseModel):
    nome: str
    content_type: str = "application/octet-stream"
    expira_em_segundos: int = 300


@app.post("/caso3/gerar-link")
def caso3_gerar_link(pedido: PedidoLink):
    if pedido.content_type not in TIPOS_PERMITIDOS_CASO3:
        raise HTTPException(
            415, f"Tipo não permitido. Aceitos: {', '.join(sorted(TIPOS_PERMITIDOS_CASO3))}"
        )
    chave = nova_chave("caso3", pedido.nome)

    with db() as conn:
        (novo_id,) = conn.execute(
            "INSERT INTO arquivos (caso, nome, content_type, chave_objeto, status) "
            "VALUES ('caso3', %s, %s, %s, 'pendente') RETURNING id",
            (pedido.nome, pedido.content_type, chave),
        ).fetchone()

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": chave, "ContentType": pedido.content_type},
        ExpiresIn=pedido.expira_em_segundos,
    )
    return {
        "id": novo_id,
        "metodo": "PUT",
        "url_upload": url,
        "headers_obrigatorios": {"Content-Type": pedido.content_type},
        "expira_em_segundos": pedido.expira_em_segundos,
        "proximo_passo": f"Após o PUT, chame POST /caso3/confirmar/{novo_id}",
    }


@app.post("/caso3/confirmar/{arquivo_id}")
def caso3_confirmar(arquivo_id: int):
    """Confere no RustFS se o objeto chegou e atualiza os metadados."""
    with db() as conn:
        linha = conn.execute(
            "SELECT chave_objeto FROM arquivos WHERE id = %s AND caso = 'caso3'", (arquivo_id,)
        ).fetchone()
        if not linha:
            raise HTTPException(404, "Registro não encontrado")
        try:
            info = s3.head_object(Bucket=BUCKET, Key=linha[0])
        except ClientError:
            raise HTTPException(409, "O arquivo ainda não foi enviado ao RustFS")
        conn.execute(
            "UPDATE arquivos SET status = 'concluido', tamanho = %s WHERE id = %s",
            (info["ContentLength"], arquivo_id),
        )
    return {"id": arquivo_id, "status": "concluido", "tamanho": info["ContentLength"]}


@app.delete("/caso3/pendentes-expirados")
def caso3_remover_pendentes_expirados():
    """Remove registros 'pendente' com mais de 10 minutos (e o objeto, se o PUT chegou a ser feito)."""
    with db() as conn:
        with conn.transaction():
            linhas = conn.execute(
                "DELETE FROM arquivos WHERE status = 'pendente' "
                "AND criado_em < now() - make_interval(mins => %s) "
                "RETURNING id, chave_objeto",
                (MINUTOS_PARA_EXPIRAR_PENDENTE,),
            ).fetchall()
            for _, chave in linhas:
                s3.delete_object(Bucket=BUCKET, Key=chave)
    return {"removidos": [l[0] for l in linhas]}


@app.get("/pagina")
def pagina_caso3():
    """Página HTML que faz o fluxo do caso 3 pelo navegador."""
    return FileResponse(PAGINA_HTML)


# ---------------------------------------------------------------------------
# Limpeza - apaga do banco E do RustFS
# ---------------------------------------------------------------------------
@app.delete("/arquivos/{arquivo_id}")
def apagar_arquivo(arquivo_id: int):
    # A transação garante que, se o RustFS falhar, o registro volta (rollback).
    with db() as conn:
        with conn.transaction():
            linha = conn.execute(
                "DELETE FROM arquivos WHERE id = %s RETURNING chave_objeto", (arquivo_id,)
            ).fetchone()
            if not linha:
                raise HTTPException(404, "Registro não encontrado")
            s3.delete_object(Bucket=BUCKET, Key=linha[0])
    return {"id": arquivo_id, "apagado": True}


# ---------------------------------------------------------------------------
# CASO 4 - link assinado de DOWNLOAD com validade curta
# ---------------------------------------------------------------------------
@app.get("/caso4/link-download/{arquivo_id}")
def caso4_link_download(arquivo_id: int, expira_em_segundos: int = 60):
    with db() as conn:
        linha = conn.execute(
            "SELECT nome, chave_objeto, status FROM arquivos WHERE id = %s", (arquivo_id,)
        ).fetchone()
    if not linha or linha[2] != "concluido":
        raise HTTPException(404, "Arquivo não encontrado ou upload não confirmado")
    nome, chave, _ = linha
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": chave,
                "ResponseContentDisposition": f'attachment; filename="{nome}"'},
        ExpiresIn=expira_em_segundos,
    )
    return {"id": arquivo_id, "url_download": url, "expira_em_segundos": expira_em_segundos}


# ---------------------------------------------------------------------------
# CASO 5 - auditoria: o banco e o bucket concordam?
# ---------------------------------------------------------------------------
@app.get("/caso5/auditoria")
def caso5_auditoria():
    objetos = s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    chaves_bucket = {o["Key"] for o in objetos}

    with db() as conn:
        linhas = conn.execute("SELECT id, chave_objeto, status FROM arquivos").fetchall()
    chaves_banco = {l[1] for l in linhas}

    return {
        "total_no_bucket": len(chaves_bucket),
        "total_no_banco": len(linhas),
        "orfaos_no_bucket (existem no RustFS, mas o banco não conhece)": sorted(chaves_bucket - chaves_banco),
        "fantasmas_no_banco (registro sem objeto no RustFS)": sorted(
            {l[1] for l in linhas if l[1] not in chaves_bucket and l[2] != "pendente"}
        ),
        "pendentes (link gerado, upload não confirmado)": [l[0] for l in linhas if l[2] == "pendente"],
    }
