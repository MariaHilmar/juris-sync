from datetime import UTC, datetime
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.process import Movimentacao, Processo
from app.schemas.datajud import DataJudProcessoSchema
from app.services.datajud_client import DataJudClient
from app.services.rag.enricher import DataJudRAGEnricher

logger = structlog.get_logger()


class JurisSyncService:
    """
    Serviço central de Negócio responsável por orquestrar a busca de dados na API DataJud,
    enriquecimento via RAG, validação Pydantic e persistência idempotente.
    """

    def __init__(
        self,
        db: AsyncSession,
        client: Optional[DataJudClient] = None,
        rag_enricher: Optional[DataJudRAGEnricher] = None,
    ):
        self.db = db
        self.client = client or DataJudClient()
        self.rag_enricher = rag_enricher or DataJudRAGEnricher()

    async def sync_process(self, numero_cnj: str, grau: int = 1) -> dict[str, Any]:
        """
        Sincroniza um processo judicial com base em seu número CNJ e grau de jurisdição.
        Pipeline: DataJud -> RAG -> Pydantic v2 -> Persistência idempotente.
        """
        logger.info("process_sync_started", numero_cnj=numero_cnj, grau=grau)

        try:
            # 1. Extração na origem externa (DataJud ou Mock)
            raw_data = await self.client.fetch_process_data(numero_cnj, grau)

            # 2. Recuperação e enriquecimento via RAG (antes da validação Pydantic)
            enriched_data = await self.rag_enricher.enrich(raw_data, numero_cnj, grau)

            # 3. Validação estrita com Pydantic v2
            validated = DataJudProcessoSchema.from_enriched(enriched_data)
            logger.info(
                "pydantic_validation_completed",
                numero_cnj=validated.numero_cnj,
                rag_context_chunks=len(validated.contexto_rag),
            )

            # 4. Busca se o processo já existe na base local
            stmt = select(Processo).where(Processo.numero_cnj == numero_cnj)
            result = await self.db.execute(stmt)
            processo: Optional[Processo] = result.scalar_one_or_none()

            # 5. Criação ou atualização idempotente do processo
            is_new = False
            if not processo:
                logger.info(
                    "process_not_found_creating_new_record", numero_cnj=numero_cnj
                )
                processo = Processo(
                    numero_cnj=validated.numero_cnj,
                    classe=validated.classe,
                    assunto=validated.assunto,
                    tribunal=validated.tribunal,
                    orgao_julgador=validated.orgao_julgador,
                    data_distribuicao=validated.data_distribuicao,
                    grau=validated.grau,
                )
                self.db.add(processo)
                is_new = True
            else:
                logger.info("process_found_updating_record", numero_cnj=numero_cnj)
                processo.classe = validated.classe
                processo.assunto = validated.assunto
                processo.orgao_julgador = validated.orgao_julgador
                processo.grau = validated.grau
                processo.data_ultima_atualizacao = datetime.now(UTC)

            await self.db.flush()

            # 6. Sincronização idempotente de movimentações
            stmt_movs = select(Movimentacao).where(
                Movimentacao.processo_id == processo.id
            )
            result_movs = await self.db.execute(stmt_movs)
            existing_movs = result_movs.scalars().all()

            existing_set = {
                (
                    (
                        mov.data_hora.isoformat()
                        if hasattr(mov.data_hora, "isoformat")
                        else mov.data_hora
                    ),
                    mov.descricao,
                )
                for mov in existing_movs
            }

            new_movs_count = 0
            for mov in validated.movimentacoes:
                key = (mov.data_hora.isoformat(), mov.descricao)
                if key not in existing_set:
                    nova_mov = Movimentacao(
                        processo_id=processo.id,
                        data_hora=mov.data_hora,
                        descricao=mov.descricao,
                        complemento=mov.complemento,
                        codigo_movimento=mov.codigo_movimento,
                    )
                    self.db.add(nova_mov)
                    new_movs_count += 1

            await self.db.commit()

            stmt_reload = (
                select(Processo)
                .execution_options(populate_existing=True)
                .options(selectinload(Processo.movimentacoes))
                .where(Processo.id == processo.id)
            )
            result_reload = await self.db.execute(stmt_reload)
            processo = result_reload.scalar_one()

            logger.info(
                "process_sync_completed",
                numero_cnj=numero_cnj,
                is_new=is_new,
                new_movements_count=new_movs_count,
            )

            return {
                "sucesso": True,
                "mensagem": (
                    f"Sincronização realizada com sucesso! "
                    f"{'Processo criado' if is_new else 'Processo atualizado'}. "
                    f"{new_movs_count} novas movimentações adicionadas."
                ),
                "processo": processo,
                "movimentacoes_sincronizadas": new_movs_count,
                "contexto_rag": validated.contexto_rag,
            }

        except Exception as error:
            logger.error("process_sync_failed", numero_cnj=numero_cnj, error=str(error))
            await self.db.rollback()
            raise error
