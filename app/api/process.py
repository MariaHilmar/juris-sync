import uuid
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.process import Processo
from app.schemas.process import (
    ProcessoDetailRead,
    ProcessoRead,
    ProcessoSyncRequest,
    ProcessoSyncResponse,
)
from app.services.sync_service import JurisSyncService

logger = structlog.get_logger()
router = APIRouter(prefix="/processos", tags=["Processos Judiciais"])


@router.post(
    "/sync",
    response_model=ProcessoSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar Processo com o DataJud",
)
async def sincronizar_processo(
    request: ProcessoSyncRequest, db: AsyncSession = Depends(get_db)
):
    """
    Aciona o motor de sincronização para buscar dados atualizados de um processo judicial
    diretamente no DataJud (ou gerar dados simulados realistas caso não configurado).
    Salva e atualiza o histórico de movimentações local de forma idempotente.
    """
    logger.info("api_sync_endpoint_called", numero_cnj=request.numero_cnj)
    service = JurisSyncService(db)
    try:
        resultado = await service.sync_process(request.numero_cnj, request.grau)

        # Converte o modelo do banco para o schema Pydantic de resposta
        processo_read = ProcessoRead.model_validate(resultado["processo"])

        return ProcessoSyncResponse(
            sucesso=resultado["sucesso"],
            mensagem=resultado["mensagem"],
            processo=processo_read,
            movimentacoes_sincronizadas=resultado["movimentacoes_sincronizadas"],
        )
    except Exception as e:
        logger.error("api_sync_endpoint_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao sincronizar processo: {str(e)}",
        ) from e


@router.get("/", response_model=List[ProcessoRead], summary="Listar Processos Locais")
async def listar_processos(
    tribunal: Optional[str] = Query(
        None, description="Filtrar por sigla do tribunal (ex: TJPB, TJSP)"
    ),
    classe: Optional[str] = Query(None, description="Filtrar por classe processual"),
    limit: int = Query(
        20, ge=1, le=100, description="Número máximo de registros por página"
    ),
    offset: int = Query(
        0, ge=0, description="Número de registros a pular para paginação"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista todos os processos armazenados localmente na nossa base de dados.
    Suporta paginação e filtros opcionais por tribunal ou classe.
    """
    logger.info("api_list_processes_called", tribunal=tribunal, classe=classe)

    query = select(Processo)
    if tribunal:
        query = query.where(Processo.tribunal == tribunal.upper())
    if classe:
        query = query.where(Processo.classe.ilike(f"%{classe}%"))

    query = (
        query.order_by(desc(Processo.data_ultima_atualizacao))
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    processos = result.scalars().all()
    return processos


@router.get(
    "/stats/por-tribunal", summary="Jurimetria: Distribuição de Processos por Tribunal"
)
async def estatisticas_por_tribunal(db: AsyncSession = Depends(get_db)):
    """
    Módulo de Jurimetria Básica: Agrupa os processos cadastrados na nossa base de dados
    por Tribunal de origem, contabilizando o volume. Demonstra competência analítica integrada.
    """
    logger.info("api_stats_tribunal_called")

    query = (
        select(Processo.tribunal, func.count(Processo.id).label("total_processos"))
        .group_by(Processo.tribunal)
        .order_by(desc("total_processos"))
    )

    result = await db.execute(query)
    rows = result.all()
    return [{"tribunal": row[0], "total_processos": row[1]} for row in rows]


@router.get(
    "/stats/por-assunto", summary="Jurimetria: Distribuição de Processos por Assunto"
)
async def estatisticas_por_assunto(db: AsyncSession = Depends(get_db)):
    """
    Módulo de Jurimetria Básica: Agrupa os processos por Assunto jurídico,
    identificando os temas mais comuns na base de dados.
    """
    logger.info("api_stats_assunto_called")

    query = (
        select(Processo.assunto, func.count(Processo.id).label("total_processos"))
        .group_by(Processo.assunto)
        .order_by(desc("total_processos"))
    )

    result = await db.execute(query)
    rows = result.all()
    return [
        {"assunto": row[0] or "Não Informado", "total_processos": row[1]}
        for row in rows
    ]


@router.get(
    "/{process_id}",
    response_model=ProcessoDetailRead,
    summary="Obter Detalhes do Processo com Movimentações",
)
async def obter_processo(process_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Obtém a ficha completa de um processo cadastrado localmente no banco,
    incluindo seu histórico completo de movimentações ordenadas cronologicamente de forma decrescente.
    """
    logger.info("api_get_process_called", process_id=process_id)

    # Executa a busca trazendo o processo com join carregando suas movimentações
    # para evitar problemas de N+1 queries.
    query = (
        select(Processo)
        .options(selectinload(Processo.movimentacoes))
        .where(Processo.id == process_id)
    )
    result = await db.execute(query)
    processo = result.scalar_one_or_none()

    if not processo:
        logger.warning("api_get_process_not_found", process_id=process_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processo judicial não encontrado na base de dados.",
        )

    return processo
