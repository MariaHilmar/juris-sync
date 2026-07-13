import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.process import Movimentacao, Processo
from app.services.datajud_client import DataJudClient
from app.services.sync_service import JurisSyncService


@pytest.mark.asyncio
async def test_sync_new_process_creates_record(db_session: AsyncSession):
    """
    Testa que ao sincronizar um número CNJ inédito, um novo registro de Processo
    é persistido no banco com as respectivas movimentações correlatas.
    """
    # Usamos o CNJ 0801234-56.2023.8.15.0001 (8.15 -> TJPB)
    cnj = "0801234-56.2023.8.15.0001"
    service = JurisSyncService(db_session)

    resultado = await service.sync_process(cnj, grau=1)

    assert resultado["sucesso"] is True
    assert "Sincronização realizada com sucesso!" in resultado["mensagem"]
    assert resultado["movimentacoes_sincronizadas"] > 0

    # Valida persistência no banco
    stmt = select(Processo).where(Processo.numero_cnj == cnj)
    res = await db_session.execute(stmt)
    processo = res.scalar_one_or_none()

    assert processo is not None
    assert processo.numero_cnj == cnj
    assert processo.tribunal == "TJPB"
    assert len(processo.movimentacoes) == resultado["movimentacoes_sincronizadas"]


@pytest.mark.asyncio
async def test_sync_process_is_idempotent(db_session: AsyncSession):
    """
    Testa a Idempotência do motor de sincronização: ao re-sincronizar um processo já existente,
    não deve duplicar o registro do Processo nem de suas Movimentações.
    """
    cnj = "0805555-22.2023.8.26.0001"  # 8.26 -> TJSP
    service = JurisSyncService(db_session)

    # Primeira sincronização (carga inicial)
    primeira_carga = await service.sync_process(cnj, grau=1)
    movs_carregadas = primeira_carga["movimentacoes_sincronizadas"]
    assert movs_carregadas > 0

    # Segunda sincronização (carga repetida de dados idênticos)
    segunda_carga = await service.sync_process(cnj, grau=1)

    assert segunda_carga["sucesso"] is True
    # Devem ser importadas 0 novas movimentações já que todas já estão localmente salvas
    assert segunda_carga["movimentacoes_sincronizadas"] == 0

    # Valida no banco que existe apenas 1 registro do processo
    stmt_processos = select(Processo).where(Processo.numero_cnj == cnj)
    res_proc = await db_session.execute(stmt_processos)
    processos = res_proc.scalars().all()
    assert len(processos) == 1

    # Valida no banco que as movimentações se mantiveram intactas sem duplicidade
    stmt_movs = select(Movimentacao).where(Movimentacao.processo_id == processos[0].id)
    res_movs = await db_session.execute(stmt_movs)
    movimentacoes = res_movs.scalars().all()
    assert len(movimentacoes) == movs_carregadas


@pytest.mark.asyncio
async def test_sync_new_movement_adds_only_the_new_one(db_session: AsyncSession):
    """
    Testa que se novas movimentações aparecerem na origem, apenas os andamentos adicionais
    devem ser inseridos na nossa base (comportamento incremental).
    """
    cnj = "0801111-33.2024.8.19.0002"  # 8.19 -> TJRJ

    # Criamos um mock personalizado do DataJudClient para simular o recebimento incremental
    class MockClient(DataJudClient):
        def __init__(self):
            super().__init__()
            self.chamadas = 0

        async def fetch_process_data(self, numero_cnj: str, grau: int = 1):
            self.chamadas += 1
            data = self._generate_mock_data(numero_cnj, grau)
            # Na primeira chamada devolve as 3 primeiras movimentações
            if self.chamadas == 1:
                data["movimentacoes"] = data["movimentacoes"][-3:]
            # Na segunda chamada devolve todas (incluindo as novas)
            return data

    mock_client = MockClient()
    service = JurisSyncService(db_session, client=mock_client)

    # Executa primeira carga
    carga_1 = await service.sync_process(cnj)
    assert carga_1["movimentacoes_sincronizadas"] == 3

    # Executa segunda carga (contendo andamentos inéditos)
    carga_2 = await service.sync_process(cnj)
    # Deve carregar apenas a diferença de andamentos
    assert carga_2["movimentacoes_sincronizadas"] > 0
    assert carga_2["movimentacoes_sincronizadas"] < len(
        carga_2["processo"].movimentacoes
    )
