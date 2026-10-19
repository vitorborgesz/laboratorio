"""cria tabela arquivos

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "arquivos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("caso", sa.Text, nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text),
        sa.Column("tamanho", sa.BigInteger),
        sa.Column("chave_objeto", sa.Text),        # caminho do objeto no RustFS
        sa.Column("conteudo", sa.LargeBinary),     # BYTEA - bytes do arquivo (só no caso 1)
        sa.Column("status", sa.Text, nullable=False, server_default="concluido"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("arquivos")
