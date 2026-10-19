# Laboratório — Upload de Arquivos (FastAPI + PostgreSQL + RustFS)

Disciplina: Desenvolvimento Web

**Objetivo:** comparar 4 formas de lidar com upload de arquivos e entender o que cada uma implica em segurança, desempenho e consistência dos dados.

| Caso | Quem recebe os bytes | Onde ficam os bytes | O banco sabe? |
|---|---|---|---|
| 1 — Upload via API | API | Postgres (BYTEA) **e** RustFS | Sim |
| 2 — Direto no storage | RustFS | RustFS | **Não** |
| 3 — Link assinado (upload) | RustFS | RustFS | Sim (só metadados) |
| 4 — Link assinado (download) | RustFS | — | Sim |
| 5 — Auditoria | — | — | Compara banco × bucket |

Além dos casos de upload, a **Atividade 6** usa o **Alembic** para versionar o esquema do banco (migrations).

**RustFS** é um armazenamento de objetos compatível com a API S3 da AWS. Tudo que funciona com S3 (boto3, presigned URLs) funciona com ele.

```
lab-upload/
├── docker-compose.yml        # Postgres + RustFS
├── requirements.txt
├── alembic.ini               # configuração do Alembic
├── migrations/               # migrações do banco
│   ├── env.py
│   └── versions/0001_cria_tabela_arquivos.py
├── app/main.py               # API FastAPI (todos os casos)
├── clientes/                 # scripts que simulam o "front-end"
│   ├── caso1_via_api.py
│   ├── caso2_direto_rustfs.py
│   ├── caso3_link_assinado.py
│   └── caso4_link_download.py
└── arquivos-teste/exemplo.txt
```

---

## 0. Preparação (10 min)

Pré-requisitos: Docker (com Compose) e Python 3.10+.

```bash
# 1) subir a infraestrutura
docker compose up -d
docker compose ps                     # os dois serviços devem estar "running"
curl http://localhost:9000/health     # RustFS respondendo

# 2) ambiente Python
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3) criar as tabelas com o Alembic
alembic upgrade head

# 4) subir a API (deixe este terminal aberto)
uvicorn app.main:app --reload
```

Se você esquecer o passo 3, a API não sobe e avisa: `Tabela 'arquivos' não existe. Rode as migrações antes: alembic upgrade head`.

Abra em abas do navegador:

- Swagger da API: http://localhost:8000/docs
- Console do RustFS: http://localhost:9001 — usuário `labaluno`, senha `labaluno-segredo-123`

A tabela `arquivos` é criada pela migração `0001` do Alembic. A API apenas cria o bucket `uploads` no RustFS ao subir.

Para olhar o banco a qualquer momento:

```bash
docker exec -it lab_postgres psql -U lab -d lab_upload
```

> A API roda **fora** do Docker de propósito: assim os links assinados apontam para `localhost:9000`, que o seu computador consegue acessar.

---

## Atividade 1 — Upload via API (banco + storage)

Em um **segundo terminal** (com o venv ativo):

```bash
python clientes/caso1_via_api.py arquivos-teste/exemplo.txt
```

Ou pelo Swagger: `POST /caso1/upload` → *Try it out* → escolha um arquivo.

**Verifique:**

1. No console do RustFS, abra o bucket `uploads` → pasta `caso1/`. O arquivo está lá.
2. No psql:
   ```sql
   SELECT id, nome, tamanho, chave_objeto, length(conteudo) AS bytes_no_banco FROM arquivos;
   ```
3. Baixe o arquivo **direto do banco**: `http://localhost:8000/caso1/arquivos/1/do-banco`

**Experimente:** envie uma imagem de uns 5 MB e depois rode:
```sql
SELECT pg_size_pretty(pg_total_relation_size('arquivos'));
```

**Discuta:**
- Os bytes passaram por quantos lugares? (cliente → API → banco **e** storage)
- O que acontece com a memória da API se 100 alunos enviarem vídeos de 1 GB ao mesmo tempo?
- Por que o backup do banco fica pesado quando guardamos arquivos nele?
- Se o `put_object` funcionar e o `INSERT` falhar, o que sobra? (Dica: Atividade 5.)

---

## Atividade 2 — Direto no storage (sem API)

```bash
python clientes/caso2_direto_rustfs.py arquivos-teste/exemplo.txt
```

**Verifique:**

1. O arquivo aparece no console do RustFS em `caso2/`.
2. Agora chame `GET /arquivos` no Swagger. **O arquivo não aparece.**

**Discuta:**
- Abra o script: a chave e o segredo do storage estão no código do cliente. Se isso fosse um app web ou mobile, quem teria acesso a eles?
- Com essas credenciais, o cliente poderia apagar arquivos dos outros? Listar o bucket inteiro?
- Como a aplicação saberia de quem é esse arquivo, ou que ele existe?

---

## Atividade 3 — Link assinado (presigned URL)

```bash
python clientes/caso3_link_assinado.py arquivos-teste/exemplo.txt
```

O script faz três passos, imprimindo cada um:

1. `POST /caso3/gerar-link` → a API registra os metadados com status `pendente` e devolve uma URL de upload válida por 5 minutos.
2. `PUT <url>` → os bytes vão **direto para o RustFS**. A API não participa.
3. `POST /caso3/confirmar/{id}` → a API confere no RustFS que o objeto chegou e marca como `concluido`.

**Faça na mão também (com o Swagger + terminal):**

1. No Swagger, chame `POST /caso3/gerar-link` com:
   ```json
   {"nome": "manual.txt", "content_type": "text/plain", "expira_em_segundos": 60}
   ```
2. Copie a `url_upload` e envie com curl:
   ```bash
   curl -X PUT -H "Content-Type: text/plain" --upload-file arquivos-teste/exemplo.txt "COLE_A_URL_AQUI"
   ```
3. Antes de confirmar, olhe `GET /arquivos`: status `pendente`, tamanho vazio.
4. Chame `POST /caso3/confirmar/{id}` e olhe de novo.

**Quebre de propósito:**
- Repita o curl **sem** o cabeçalho `Content-Type` (ou com outro valor). O que o RustFS responde? Por quê?
- Gere um link com `expira_em_segundos: 10`, espere 15 s e tente o PUT.
- Altere um caractere do parâmetro `X-Amz-Signature` na URL e tente de novo.
- Chame `confirmar` para um id cujo PUT você nunca fez.

**Discuta:**
- Que informação o cliente recebeu? Ele consegue usar esse link para outro arquivo ou outro nome?
- Por que esse padrão é o usado por S3, Google Cloud Storage, Azure etc. em aplicações reais?

---

## Atividade 4 — Link de download temporário

Use o id de um arquivo concluído (veja em `GET /arquivos`):

```bash
python clientes/caso4_link_download.py 1 10
```

O script baixa o arquivo com o link, espera ele expirar e tenta de novo.

**Discuta:** por que não deixar o bucket público e simplesmente devolver `http://localhost:9000/uploads/<chave>`?

---

## Atividade 5 — Auditoria: banco × storage

Chame `GET /caso5/auditoria` no Swagger.

Você deve ver:
- **Órfãos no bucket**: o arquivo do caso 2 (existe no RustFS, mas o banco não conhece).
- **Pendentes**: links do caso 3 gerados mas nunca confirmados.

**Crie um "fantasma":** no console do RustFS, apague manualmente um objeto da pasta `caso1/` e rode a auditoria de novo. O registro continua no banco, mas o arquivo sumiu. E o `/do-banco` desse id — ainda funciona? Por quê?

**Discuta:** quando temos dois sistemas de armazenamento, como garantir que eles concordem? (transações, rotina de limpeza, eventos/notificações do bucket, status `pendente`).

---

## Atividade 6 — Evoluindo o banco com Alembic (migrations)

Até agora a tabela foi criada pela migração `0001`. Nesta atividade você vai **mudar o esquema** do banco sem apagar nada, do jeito que se faz em produção.

**Objetivo:** guardar o hash SHA-256 de cada arquivo enviado pelo caso 1, para detectar arquivos duplicados ou corrompidos.

### 6.1 Explorando o estado atual

```bash
alembic current        # qual versão está aplicada no banco
alembic history        # todas as migrações conhecidas
```

No psql, veja onde o Alembic guarda essa informação:

```sql
SELECT * FROM alembic_version;
\d arquivos
```

Abra `migrations/versions/0001_cria_tabela_arquivos.py` e compare com o `\d arquivos`.

### 6.2 Criando a migração

```bash
alembic revision -m "adiciona hash_sha256"
```

O Alembic cria um arquivo novo em `migrations/versions/` com `upgrade()` e `downgrade()` vazios. Repare que `down_revision` já aponta para `"0001"`. Preencha:

```python
def upgrade():
    op.add_column("arquivos", sa.Column("hash_sha256", sa.String(64)))
    op.create_index("ix_arquivos_hash_sha256", "arquivos", ["hash_sha256"])


def downgrade():
    op.drop_index("ix_arquivos_hash_sha256", table_name="arquivos")
    op.drop_column("arquivos", "hash_sha256")
```

Antes de aplicar, veja o SQL que será executado (sem tocar no banco):

```bash
alembic upgrade 0001:head --sql
```

> No modo `--sql` o Alembic não consulta o banco, por isso informamos o ponto de partida (`0001:`). Sem ele, o SQL sairia desde a primeira migração.

Aplique e confira:

```bash
alembic upgrade head
alembic current
```

```sql
\d arquivos
SELECT id, nome, hash_sha256 FROM arquivos;   -- registros antigos ficam com NULL
```

### 6.3 Usando a coluna nova na API

Em `app/main.py`, no `caso1_upload`:

```python
import hashlib   # no topo do arquivo

# logo depois de ler o conteúdo:
hash_sha256 = hashlib.sha256(conteudo).hexdigest()
```

E inclua `hash_sha256` no `INSERT` (coluna + valor). Envie o mesmo arquivo duas vezes e rode:

```sql
SELECT hash_sha256, count(*) FROM arquivos GROUP BY hash_sha256 HAVING count(*) > 1;
```

### 6.4 Voltando atrás (rollback)

```bash
alembic downgrade -1
alembic current
```

- O que aconteceu com a coluna e com os hashes salvos?
- Envie um arquivo pelo caso 1 agora. O que a API responde? Por quê?
- Rode `alembic upgrade head` de novo para voltar ao estado correto.

### Discuta

- Por que não basta editar o `CREATE TABLE` e recriar o banco? (Pense em um banco de produção com milhões de registros.)
- Por que a migração vai para o Git junto com o código?
- O que aconteceria se dois alunos criassem migrações diferentes a partir da `0001` e juntassem o código? Rode `alembic heads` para investigar.
- Por que o `downgrade()` precisa desfazer as operações na ordem inversa?

**Desafio:** crie uma migração `0003` que impeça `status` de receber valores diferentes de `pendente` e `concluido` (`op.create_check_constraint`). Teste o `upgrade` e o `downgrade`.

---

## Desafios extras (para quem terminar)

1. **Validação:** no caso 3, recuse tipos diferentes de `image/png`, `image/jpeg` e `application/pdf` (retorne 415).
2. **Limpeza:** crie `DELETE /arquivos/{id}` que apague do banco **e** do RustFS.
3. **Expiração de pendentes:** crie um endpoint que remova registros `pendente` com mais de 10 minutos.
4. **Front-end:** faça uma página HTML com `fetch` que use o fluxo do caso 3 no navegador. (Vai esbarrar em CORS no RustFS — investigue como configurar.)
5. **Medição:** envie o mesmo arquivo de ~50 MB pelos casos 1 e 3 e compare o tempo e o uso de memória da API (`docker stats` não pega a API, use o Gerenciador de Tarefas / `top`).

---

## Encerrando

```bash
docker compose down        # para os containers, mantém os dados
docker compose down -v     # para e APAGA os dados (recomeçar do zero)
```

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `connection refused` na porta 5432 ou 9000 | containers não subiram: `docker compose ps` / `docker compose logs rustfs` |
| porta 5432 já em uso | há um Postgres local; troque para `"5433:5432"` no compose e rode `DATABASE_URL=postgresql://lab:lab@localhost:5433/lab_upload uvicorn app.main:app --reload` |
| `SignatureDoesNotMatch` no PUT | `Content-Type` diferente do informado ao gerar o link |
| `AccessDenied` / `Request has expired` | link expirou |
| 409 no `confirmar` | o PUT não foi feito ou falhou |
| API não sobe: `Tabela 'arquivos' não existe` | faltou rodar `alembic upgrade head` |
| `alembic: command not found` | venv não está ativo; ative ou use `python -m alembic ...` |
| `Multiple head revisions` | duas migrações com o mesmo `down_revision`; ajuste um deles ou use `alembic merge heads` |
| `docker-credential-desktop: executable file not found` (Windows / Rancher Desktop) | em `%USERPROFILE%\.docker\config.json`, troque `"credsStore": "desktop"` por `"credsStore": "wincred"` (ou remova a linha) |

> As credenciais deste laboratório são fixas e fracas **apenas para fins didáticos**. Nunca exponha um RustFS com elas em rede.
