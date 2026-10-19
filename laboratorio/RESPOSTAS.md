# Respostas — Laboratório de Upload de Arquivos

## Atividade 1 — Upload via API

**Os bytes passaram por quantos lugares?**
Por quatro: cliente → API (memória do processo) → RustFS **e** Postgres (coluna BYTEA). O arquivo fica guardado duas vezes e a API faz duas escritas de rede com o arquivo inteiro.

**E se 100 alunos enviarem vídeos de 1 GB ao mesmo tempo?**
`arquivo.file.read()` carrega o arquivo inteiro na memória. Seriam cerca de 100 GB de RAM ao mesmo tempo, sem contar as cópias feitas pelo driver do banco e pelo boto3. O processo é morto por falta de memória (OOM) ou o servidor trava, e todos os outros usuários são afetados. A banda da API também vira o gargalo: tudo passa por ela duas vezes.

**Por que o backup do banco fica pesado?**
Os arquivos passam a fazer parte do banco. O `pg_dump` exporta todos os bytes, e backups, restaurações e réplicas ficam enormes e lentos. A tabela incha (TOAST) e o `VACUUM` fica mais caro. Arquivos são dados grandes e imutáveis, e cabem melhor num storage de objetos, que é barato e escala. O banco deveria guardar só os metadados.

**Se o `put_object` funcionar e o `INSERT` falhar, o que sobra?**
Um **objeto órfão** no RustFS: ele existe no bucket, mas nenhum registro no banco aponta para ele. Ninguém o encontra pela aplicação e ele ocupa espaço para sempre. É exatamente o que a auditoria da Atividade 5 detecta.

---

## Atividade 2 — Direto no storage

**Quem teria acesso à chave e ao segredo num app web ou mobile?**
Qualquer pessoa. Num app web basta abrir o DevTools ou ver o código JavaScript. Num app mobile basta descompilar o APK/IPA. Credenciais embutidas no cliente são públicas.

**O cliente poderia apagar arquivos dos outros? Listar o bucket inteiro?**
Sim. Essas credenciais são de acesso total ao storage: dá para listar, baixar, sobrescrever e apagar qualquer objeto de qualquer usuário, e até criar ou remover buckets. O próprio script lista o bucket inteiro no final.

**Como a aplicação saberia de quem é o arquivo, ou que ele existe?**
Não saberia. O banco nunca é avisado (`GET /arquivos` não mostra o arquivo), então não há dono, data, status nem controle de acesso. A única forma de descobrir seria varrer o bucket (como faz a auditoria) ou configurar notificações de eventos do bucket. Mesmo assim, não daria para saber quem enviou.

---

## Atividade 3 — Link assinado (upload)

**Quebrando de propósito:**
- **Sem `Content-Type`, ou com outro valor:** o RustFS responde **403 `SignatureDoesNotMatch`**. O `Content-Type` fez parte do que foi assinado na hora de gerar o link (`Params={"ContentType": ...}`). Se o cabeçalho enviado for diferente, a assinatura recalculada pelo servidor não bate.
- **Link expirado (10 s, PUT depois de 15 s):** **403 `AccessDenied` / `Request has expired`**. A data e a validade (`X-Amz-Date`, `X-Amz-Expires`) também são assinadas.
- **Um caractere da `X-Amz-Signature` alterado:** **403 `SignatureDoesNotMatch`**. A assinatura é um HMAC calculado com a chave secreta. Sem a chave, não dá para forjar uma válida.
- **`confirmar` de um id sem PUT:** **409** "O arquivo ainda não foi enviado ao RustFS". O `head_object` não encontra o objeto e o registro continua `pendente`.

**Que informação o cliente recebeu? Ele consegue usar o link para outro arquivo ou outro nome?**
Ele recebeu só uma URL com a assinatura e o prazo de validade, nunca a chave secreta. A assinatura cobre o método (PUT), o bucket, a chave do objeto (`caso3/<uuid>_nome`), o `Content-Type` e o prazo. Não dá para mudar o nome nem o destino, nem usar o link para ler, listar ou apagar outros objetos. Ele **consegue** enviar qualquer conteúdo para aquela chave específica enquanto o link valer. Por isso a API confere o objeto no `confirmar`, e por isso existe a validação de tipo do extra 1.

**Por que esse é o padrão do S3, GCS, Azure etc.?**
Ele junta o melhor dos casos 1 e 2. Os bytes vão direto para o storage, então a API não gasta memória nem banda e escala para arquivos enormes. Ao mesmo tempo, a API continua no controle: ela decide quem pode enviar, o quê, para onde e por quanto tempo, e registra os metadados no banco. As credenciais ficam só no servidor.

---

## Atividade 4 — Link de download temporário

**Por que não deixar o bucket público e devolver a URL direta?**
- Qualquer pessoa com a URL (ou que adivinhe ou liste as chaves) baixaria o arquivo para sempre, sem verificação de permissão.
- Não dá para revogar: uma URL pública vazada continua funcionando.
- Com o link assinado, a API verifica permissão e status (`concluido`) **antes** de gerar o link. O link expira sozinho e pode até forçar o nome do download (`ResponseContentDisposition`).
- O download continua indo direto do storage, sem passar pela API. Ganhamos segurança sem perder desempenho.

---

## Atividade 5 — Auditoria

**O `/do-banco` do "fantasma" ainda funciona? Por quê?**
Sim. O caso 1 guarda uma cópia dos bytes no Postgres (BYTEA) e o `/do-banco` lê dessa cópia, sem consultar o RustFS. O banco e o storage já discordam: o caso 4 (que usa o RustFS) falharia para esse mesmo id. Duas cópias do mesmo dado acabam divergindo.

**Com dois sistemas de armazenamento, como garantir que eles concordem?**
Não existe uma transação única entre Postgres e RustFS, então combinamos técnicas:
- **Status `pendente` → `concluido`:** registra a intenção antes e confirma depois (caso 3). O que nunca foi confirmado é identificável.
- **Ordem das operações e compensação:** por exemplo, abrir a transação do banco, gravar no storage e só então fazer commit. Se o storage falhar, faz rollback. Se o commit falhar depois do upload, apaga o objeto (o `DELETE /arquivos/{id}` usa esse princípio).
- **Rotinas de limpeza / reconciliação:** um job periódico como a auditoria remove órfãos e pendentes expirados (extra 3).
- **Eventos/notificações do bucket:** o storage avisa a aplicação (webhook ou fila) quando um objeto é criado ou removido, e a aplicação atualiza o banco.
- **Uma única fonte da verdade:** não duplicar os bytes no banco (o problema do caso 1).

---

## Atividade 6 — Alembic

**6.4 — O que aconteceu com a coluna e com os hashes?**
O `downgrade` executa `DROP INDEX` e `DROP COLUMN hash_sha256`. A coluna some e **os hashes salvos são perdidos de vez**. Um `upgrade` posterior recria a coluna vazia (`NULL`).

**6.4 — Enviando pelo caso 1 depois do downgrade:**
A API responde **500 Internal Server Error**. O código faz `INSERT ... hash_sha256`, mas a coluna não existe mais (`psycopg.errors.UndefinedColumn`). O código e o esquema do banco ficaram fora de sincronia. Pior: o `put_object` acontece antes do `INSERT`, então cada tentativa deixa um **objeto órfão** no bucket (aparece na auditoria).

**Por que não basta editar o `CREATE TABLE` e recriar o banco?**
Recriar significa apagar a tabela e **todos os dados**. Em produção, com milhões de registros, isso é inaceitável. A migração altera o esquema que já existe (`ALTER TABLE`) e preserva os dados. Ela também registra em que versão cada banco está (`alembic_version`), então desenvolvimento, homologação e produção são atualizados do mesmo jeito, de forma repetível.

**Por que a migração vai para o Git junto com o código?**
O código depende do esquema. O commit que passa a usar `hash_sha256` precisa vir junto com a migração que cria a coluna. Assim, quem faz checkout de qualquer versão roda `alembic upgrade head` e tem o banco certo para aquele código. Isso também dá histórico e revisão (code review) das mudanças no banco, e permite rollback.

**E se dois alunos criarem migrações a partir da `0001` e juntarem o código?**
As duas terão `down_revision = "0001"`, e o histórico se divide em dois ramos. `alembic heads` mostra **duas heads**, e `alembic upgrade head` falha com `Multiple head revisions`. Para resolver, rode `alembic merge heads` (cria uma migração que depende das duas) ou faça uma delas apontar para a outra no `down_revision`.

**Por que o `downgrade()` desfaz as operações em ordem inversa?**
As operações dependem umas das outras. O índice foi criado *sobre* a coluna, então precisa ser removido antes dela (é como desempilhar). Na ordem inversa, cada passo encontra o banco exatamente como estava logo depois do passo correspondente do `upgrade`. Um exemplo: não dá para remover uma tabela que ainda é referenciada por uma chave estrangeira criada depois dela.

**Desafio `0003`:** `op.create_check_constraint("ck_arquivos_status", "arquivos", "status IN ('pendente', 'concluido')")`, desfeita com `op.drop_constraint(..., type_="check")`. Teste:
```sql
UPDATE arquivos SET status = 'outro' WHERE id = 1;
-- ERROR: new row for relation "arquivos" violates check constraint "ck_arquivos_status"
```
