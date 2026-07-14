"""
Testes de reconciliação do motor de sincronização.

Diferente dos testes de idempotência em test_sync_service.py, aqui validamos
que os dados persistidos localmente são um espelho fiel e auditável da fonte
externa (DataJud): sem movimentações órfãs, sem divergência de conteúdo, com
atualização quando a fonte muda e com atomicidade total em caso de falha.
"""

import pytest
from sqlalchemy import select

from app.models.process import Movimentacao, Processo
from app.services.datajud_client import DataJudClient
from app.services.sync_service import JurisSyncService


@pytest.mark.asyncio
async def test_reconciliation_matches_source_movement_count_and_content(db_session):
    """
    O conjunto de movimentações persistidas deve corresponder exatamente
    (mesma chave data_hora + descricao) ao que a fonte externa retornou.
    """
    cnj = "0812345-11.2023.8.26.0005"
    client = DataJudClient()
    source_data = client._generate_mock_data(cnj, grau=1)

    service = JurisSyncService(db_session, client=client)
    resultado = await service.sync_process(cnj, grau=1)

    stmt = select(Movimentacao).where(
        Movimentacao.processo_id == resultado["processo"].id
    )
    persisted = (await db_session.execute(stmt)).scalars().all()

    source_keys = {
        (mov["data_hora"], mov["descricao"]) for mov in source_data["movimentacoes"]
    }
    persisted_keys = {(mov.data_hora.isoformat(), mov.descricao) for mov in persisted}

    assert persisted_keys == source_keys
    assert len(persisted) == len(source_data["movimentacoes"])


@pytest.mark.asyncio
async def test_reconciliation_reflects_source_updates_on_resync(db_session):
    """
    Quando a origem muda um campo (ex: classe processual), a reconciliação deve
    sobrescrever o valor local com o da fonte de verdade no próximo sync.
    """
    cnj = "0812346-22.2023.8.26.0005"

    class ChangingClient(DataJudClient):
        def __init__(self) -> None:
            super().__init__()
            self.chamadas = 0

        async def fetch_process_data(self, numero_cnj: str, grau: int = 1):
            self.chamadas += 1
            data = self._generate_mock_data(numero_cnj, grau)
            data["classe"] = (
                "Procedimento Comum Cível"
                if self.chamadas == 1
                else "Execução de Título Extrajudicial"
            )
            return data

    client = ChangingClient()
    service = JurisSyncService(db_session, client=client)

    primeira = await service.sync_process(cnj, grau=1)
    assert primeira["processo"].classe == "Procedimento Comum Cível"

    segunda = await service.sync_process(cnj, grau=1)
    assert segunda["processo"].classe == "Execução de Título Extrajudicial"

    stmt = select(Processo).where(Processo.numero_cnj == cnj)
    processo = (await db_session.execute(stmt)).scalar_one()
    assert processo.classe == "Execução de Título Extrajudicial"


@pytest.mark.asyncio
async def test_reconciliation_rolls_back_completely_on_partial_failure(db_session):
    """
    Se o pipeline falhar após a extração (ex: erro no enriquecimento RAG),
    nenhum dado parcial pode permanecer no banco. Reconciliação exige
    atomicidade: tudo ou nada.
    """
    cnj = "0812347-33.2023.8.26.0005"

    class FailingEnricher:
        async def enrich(self, raw_data, numero_cnj, grau):
            raise RuntimeError("Falha simulada no pipeline de enriquecimento RAG")

    movimentacoes_antes = len(
        (await db_session.execute(select(Movimentacao))).scalars().all()
    )

    service = JurisSyncService(db_session, rag_enricher=FailingEnricher())

    with pytest.raises(RuntimeError):
        await service.sync_process(cnj, grau=1)

    stmt = select(Processo).where(Processo.numero_cnj == cnj)
    processo = (await db_session.execute(stmt)).scalar_one_or_none()
    assert processo is None

    movimentacoes_depois = len(
        (await db_session.execute(select(Movimentacao))).scalars().all()
    )
    # Nenhuma movimentação nova pode ter sido persistida por esta tentativa falha
    assert movimentacoes_depois == movimentacoes_antes


@pytest.mark.asyncio
async def test_reconciliation_detects_no_orphan_movements(db_session):
    """
    Toda movimentação persistida deve pertencer a um processo existente -
    não pode haver órfãos após ciclos de sincronização.
    """
    cnj = "0812348-44.2023.8.15.0002"
    service = JurisSyncService(db_session)
    await service.sync_process(cnj, grau=1)

    movimentacoes = (await db_session.execute(select(Movimentacao))).scalars().all()
    processo_ids = {
        row[0] for row in (await db_session.execute(select(Processo.id))).all()
    }

    orfas = [mov for mov in movimentacoes if mov.processo_id not in processo_ids]
    assert orfas == []


@pytest.mark.asyncio
async def test_reconciliation_incremental_sync_adds_only_the_delta(db_session):
    """
    Reconciliação incremental: se a origem retornar apenas parte do histórico
    numa primeira carga e o restante depois, o total final persistido deve
    igualar exatamente o total da fonte - sem duplicar o que já existia.
    """
    cnj = "0812349-55.2023.8.19.0002"

    class IncrementalClient(DataJudClient):
        def __init__(self) -> None:
            super().__init__()
            self.chamadas = 0

        async def fetch_process_data(self, numero_cnj: str, grau: int = 1):
            self.chamadas += 1
            data = self._generate_mock_data(numero_cnj, grau)
            if self.chamadas == 1:
                data["movimentacoes"] = data["movimentacoes"][-3:]
            return data

    client = IncrementalClient()
    service = JurisSyncService(db_session, client=client)

    await service.sync_process(cnj)
    resultado_final = await service.sync_process(cnj)

    total_fonte = len(client._generate_mock_data(cnj, 1)["movimentacoes"])
    total_persistido = len(resultado_final["processo"].movimentacoes)

    assert total_persistido == total_fonte
