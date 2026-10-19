"""restringe status a pendente/concluido

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_arquivos_status",
        "arquivos",
        "status IN ('pendente', 'concluido')",
    )


def downgrade():
    op.drop_constraint("ck_arquivos_status", "arquivos", type_="check")
