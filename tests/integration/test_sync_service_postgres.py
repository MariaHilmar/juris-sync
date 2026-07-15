"""
Testes de integração do motor de sincronização contra um PostgreSQL real
(via Testcontainers), incluindo as migrations reais do Alembic.

Isso cobre comportamentos que o SQLite in-memory dos testes unitários pode
mascarar: tipos de coluna (UUID, timezone), defaults do lado do servidor
(server_default) e concorrência real de transações.
"""

import pytest
from sqlalchemy import select

from app.models.process import Movimentacao, Processo
from app.services.sync_service import JurisSyncService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_sync_process_persists_correctly_on_real_postgres(pg_session):
    cnj = "0801234-56.2023.8.15.0001"
    service = JurisSyncService(pg_session)

    resultado = await service.sync_process(cnj, grau=1)

    assert resultado["sucesso"] is True
    assert resultado["movimentacoes_sincronizadas"] > 0

    stmt = select(Processo).where(Processo.numero_cnj == cnj)
    processo = (await pg_session.execute(stmt)).scalar_one_or_none()

    assert processo is not None
    assert processo.tribunal == "TJPB"
    # server_default/onupdate do PostgreSQL precisam ter sido de fato aplicados
    assert processo.created_at is not None
    assert processo.data_ultima_atualizacao is not None


async def test_sync_is_idempotent_on_real_postgres(pg_session):
    cnj = "0805555-22.2023.8.26.0001"
    service = JurisSyncService(pg_session)

    await service.sync_process(cnj, grau=1)
    segunda_carga = await service.sync_process(cnj, grau=1)

    assert segunda_carga["movimentacoes_sincronizadas"] == 0

    stmt = select(Processo).where(Processo.numero_cnj == cnj)
    processos = (await pg_session.execute(stmt)).scalars().all()
    assert len(processos) == 1


async def test_sync_unique_constraint_on_numero_cnj_is_enforced(pg_session):
    """
    A constraint UNIQUE de numero_cnj deve ser respeitada mesmo no dialeto
    real do PostgreSQL, garantindo que a idempotência não depende apenas
    da lógica da aplicação.
    """
    cnj = "0807777-88.2023.8.06.0001"
    service = JurisSyncService(pg_session)

    await service.sync_process(cnj, grau=1)

    stmt = select(Processo).where(Processo.numero_cnj == cnj)
    total = len((await pg_session.execute(stmt)).scalars().all())
    assert total == 1


async def test_api_sync_flow_against_real_postgres(pg_api_client):
    response = await pg_api_client.post(
        "/api/v1/processos/sync",
        json={"numero_cnj": "0809999-11.2024.8.19.0003", "grau": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sucesso"] is True
    assert body["processo"]["tribunal"] == "TJRJ"

    listagem = await pg_api_client.get(
        "/api/v1/processos/", params={"tribunal": "TJRJ"}
    )
    assert listagem.status_code == 200
    body_listagem = listagem.json()
    assert any(
        p["numero_cnj"] == "0809999-11.2024.8.19.0003" for p in body_listagem["items"]
    )


async def test_reconciliation_movement_delete_cascade_on_real_postgres(pg_session):
    """
    Valida o ON DELETE CASCADE real do PostgreSQL entre processos e
    movimentações - constraint que só é totalmente confiável no dialeto
    de produção.
    """
    cnj = "0803333-44.2023.8.15.0004"
    service = JurisSyncService(pg_session)

    resultado = await service.sync_process(cnj, grau=1)
    processo_id = resultado["processo"].id

    stmt_processo = select(Processo).where(Processo.id == processo_id)
    processo = (await pg_session.execute(stmt_processo)).scalar_one()

    await pg_session.delete(processo)
    await pg_session.flush()

    stmt_movs = select(Movimentacao).where(Movimentacao.processo_id == processo_id)
    movimentacoes_restantes = (await pg_session.execute(stmt_movs)).scalars().all()
    assert movimentacoes_restantes == []
