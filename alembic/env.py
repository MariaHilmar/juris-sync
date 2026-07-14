import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Adiciona o diretório raiz ao sys.path para permitir importações do pacote 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.database import Base
from app.models import Processo, Movimentacao  # noqa: F401 - registra metadados

# Este é o objeto de configuração do Alembic
config = context.config

# Sobrescreve dinamicamente a URL do banco com a URL definida na nossa configuração central
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configura logs a partir do alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Registra os metadados dos nossos modelos para habilitar a autogeração (autogenerate)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Executa migrações em modo offline (geração de scripts SQL simples)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Executa migrações em modo online utilizando engine assíncrono."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Executa migrações no modo online."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
