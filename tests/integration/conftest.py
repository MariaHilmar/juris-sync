"""
Fixtures de integração que sobem um PostgreSQL real via Testcontainers.

As migrations reais do Alembic são executadas contra o container, validando
o dialeto de produção (PostgreSQL) - algo que o SQLite in-memory usado nos
testes unitários não garante (ex: tipos, defaults, constraints).

Se o Docker não estiver disponível (ex: máquina local sem o daemon rodando),
os testes desta pasta são pulados automaticamente. No CI (GitHub Actions),
o Docker já vem disponível por padrão nos runners ubuntu-latest.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.core.config import settings
from app.core.database import get_db
from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_container():
    if not _docker_available():
        pytest.skip(
            "Docker não está disponível localmente - testes de integração com "
            "Testcontainers (PostgreSQL real) foram pulados. Eles rodam "
            "normalmente no job de integração do CI."
        )

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def postgres_url(postgres_container) -> str:
    return postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def apply_migrations(postgres_url: str) -> None:
    """Aplica as migrations reais do Alembic contra o PostgreSQL do container."""
    original_url = settings.DATABASE_URL
    settings.DATABASE_URL = postgres_url
    try:
        cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        command.upgrade(cfg, "head")
    finally:
        settings.DATABASE_URL = original_url


@pytest.fixture(scope="session")
async def postgres_engine(postgres_url: str, apply_migrations: None):
    engine = create_async_engine(postgres_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_session(postgres_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Sessão isolada por teste com savepoints, no mesmo padrão do db_session
    usado nos testes unitários com SQLite, mas contra o PostgreSQL real.
    """
    async with postgres_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        yield session

        await session.close()
        await transaction.rollback()


@pytest.fixture
async def pg_api_client(pg_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield pg_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
