"""Configuração do Alembic para o laboratório.

Usamos migrações escritas à mão (op.create_table, op.add_column...),
sem ORM e sem autogenerate, para o aluno ver exatamente o que muda no banco.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Mesma variável usada pela API. O SQLAlchemy precisa saber o driver (psycopg 3).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lab:lab@localhost:5432/lab_upload")
URL_SQLALCHEMY = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

target_metadata = None  # sem modelos ORM -> sem autogenerate


def run_migrations_offline():
    """Gera o SQL sem conectar no banco:  alembic upgrade head --sql"""
    context.configure(url=URL_SQLALCHEMY, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(URL_SQLALCHEMY, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
