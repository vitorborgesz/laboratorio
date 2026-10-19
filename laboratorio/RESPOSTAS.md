# Respostas: Laboratório de Upload de Arquivos

## Atividade 1: Upload via API

**Os bytes passaram por quantos lugares?**

Passam pelo cliente, pela API, pelo RustFS e pelo PostgreSQL. Como o arquivo é salvo nos dois últimos, ficam duas cópias e a API precisa enviá-lo duas vezes.

**E se 100 alunos enviarem vídeos de 1 GB ao mesmo tempo?**

O código carrega os arquivos inteiros na memória. Isso poderia consumir cerca de 100 GB de RAM, causando lentidão, travamentos ou falta de memória no servidor.

**Por que o backup do banco fica pesado?**

Porque os arquivos também são armazenados no PostgreSQL e entram nos backups. O ideal é guardar os arquivos no storage e deixar no banco apenas seus metadados.

**Se o `put_object` funcionar e o `INSERT` falhar, o que sobra?**

Um objeto órfão no RustFS, pois o arquivo existe no storage, mas não possui registro correspondente no banco.

---

## Atividade 2: Upload direto no storage

**Quem teria acesso à chave e ao segredo num app web ou mobile?**

Qualquer pessoa que conseguisse analisar o código do aplicativo. Por isso, as credenciais não devem ficar expostas no cliente.

**O cliente poderia apagar arquivos dos outros ou listar o bucket inteiro?**

Sim, caso as credenciais tenham acesso total ao storage. Seria possível listar, baixar, sobrescrever e apagar arquivos de outros usuários.

**Como a aplicação saberia de quem é o arquivo ou que ele existe?**

Não saberia pelo banco, pois o upload não cria nenhum registro na aplicação. Seria necessário consultar o storage ou utilizar notificações para identificar os arquivos enviados.

---

## Atividade 3: Link assinado para upload

**O que acontece quando tentamos usar o link de forma incorreta?**

- **Sem o `Content-Type` correto:** a assinatura pode ser rejeitada, retornando erro 403.
- **Link expirado:** o upload é recusado porque o prazo terminou.
- **Assinatura alterada:** o servidor rejeita a requisição por assinatura inválida.
- **Confirmação sem upload:** a API retorna erro 409 porque o objeto não foi encontrado.

**Que informação o cliente recebeu? Ele consegue usar o link para outro arquivo ou outro nome?**

O cliente recebe uma URL temporária, sem acesso à chave secreta. O link permite enviar conteúdo apenas para o destino autorizado, enquanto estiver válido.

**Por que esse é o padrão do S3, GCS, Azure e outros serviços?**

Porque o arquivo vai diretamente para o storage, reduzindo a carga na API. Ao mesmo tempo, a aplicação controla a geração dos links e registra os metadados no banco.

---

## Atividade 4: Link temporário para download

**Por que não deixar o bucket público e devolver a URL direta?**

Porque qualquer pessoa com acesso ao endereço poderia baixar o arquivo sem uma verificação de permissão. O link temporário permite controlar o acesso e expira automaticamente, mantendo o download direto pelo storage.

---

## Atividade 5: Auditoria

**O endpoint `/do-banco` do arquivo fantasma ainda funciona? Por quê?**

Sim, porque o caso 1 também salva o arquivo no PostgreSQL. O endpoint recupera essa cópia sem consultar o RustFS, mostrando que os dois armazenamentos podem ficar inconsistentes.

**Com dois sistemas de armazenamento, como garantir que eles concordem?**

É possível controlar o status dos arquivos, tratar falhas nas operações, remover objetos órfãos e executar auditorias periódicas. Também é recomendável evitar duplicar os arquivos no banco e manter ali apenas os metadados.

---

## Atividade 6: Alembic

**6.4: O que aconteceu com a coluna e com os hashes?**

O `downgrade` remove o índice e a coluna `hash_sha256`. Os hashes armazenados são perdidos e, se a coluna for recriada, ela estará vazia.

**6.4: O que acontece ao enviar um arquivo pelo caso 1 depois do downgrade?**

A API retorna erro 500 porque tenta inserir dados em uma coluna que não existe. Como o upload no RustFS acontece antes da inserção, pode sobrar um objeto órfão.

**Por que não basta editar o `CREATE TABLE` e recriar o banco?**

Porque isso apagaria os dados existentes. As migrações permitem alterar a estrutura do banco sem precisar recriá-lo.

**Por que a migração vai para o Git junto com o código?**

Porque o código e o banco precisam estar compatíveis. Versionar as migrações permite que outras pessoas apliquem as mesmas alterações no banco.

**E se dois alunos criarem migrações a partir da `0001` e depois juntarem o código?**

O histórico terá duas heads. O comando `alembic upgrade head` pode falhar, sendo possível resolver o problema com `alembic merge heads`.

**Por que o `downgrade()` desfaz as operações em ordem inversa?**

Porque algumas operações dependem de outras. Por exemplo, o índice precisa ser removido antes da coluna utilizada por ele.

**Desafio `0003`:**

Foi criada uma restrição para permitir apenas os status `pendente` e `concluido` na tabela `arquivos`.

Teste:

```sql
UPDATE arquivos SET status = 'outro' WHERE id = 1;
```

O PostgreSQL rejeita a alteração porque o status viola a restrição `ck_arquivos_status`.
