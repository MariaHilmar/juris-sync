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


def _movement_identity_key(data_hora: datetime, descricao: str) -> tuple[str, str]:
    """
    Chave estável para idempotência de movimentações.

    Normaliza datetimes naive/aware para UTC antes de comparar, evitando
    duplicatas quando o PostgreSQL devolve timestamptz com offset e a origem
    envia valores naive (comum no mock e em alguns tribunais).
    """
    if data_hora.tzinfo is None:
        normalized = data_hora.replace(tzinfo=UTC)
    else:
        normalized = data_hora.astimezone(UTC)
    return normalized.isoformat(), descricao


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

        Orquestra as etapas atômicas: em qualquer falha, faz rollback da
        transação e propaga o erro ao chamador.
        """
        logger.info("process_sync_started", numero_cnj=numero_cnj, grau=grau)

        try:
            validated = await self._extrair_e_validar(numero_cnj, grau)

            processo, is_new = await self._upsert_processo(numero_cnj, validated)
            await self.db.flush()

            new_movs_count = await self._sync_movimentacoes(
                processo, validated.movimentacoes
            )

            await self.db.commit()

            processo = await self._reload_com_movimentacoes(processo.id)

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

    async def _extrair_e_validar(
        self, numero_cnj: str, grau: int
    ) -> DataJudProcessoSchema:
        """Extrai da origem externa, enriquece via RAG e valida com Pydantic v2."""
        raw_data = await self.client.fetch_process_data(numero_cnj, grau)
        enriched_data = await self.rag_enricher.enrich(raw_data, numero_cnj, grau)

        validated = DataJudProcessoSchema.from_enriched(enriched_data)
        logger.info(
            "pydantic_validation_completed",
            numero_cnj=validated.numero_cnj,
            rag_context_chunks=len(validated.contexto_rag),
        )
        return validated

    async def _upsert_processo(
        self, numero_cnj: str, validated: DataJudProcessoSchema
    ) -> tuple[Processo, bool]:
        """Cria ou atualiza o processo de forma idempotente. Retorna (processo, is_new)."""
        stmt = select(Processo).where(Processo.numero_cnj == numero_cnj)
        result = await self.db.execute(stmt)
        processo: Optional[Processo] = result.scalar_one_or_none()

        if not processo:
            logger.info("process_not_found_creating_new_record", numero_cnj=numero_cnj)
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
            return processo, True

        logger.info("process_found_updating_record", numero_cnj=numero_cnj)
        processo.classe = validated.classe
        processo.assunto = validated.assunto
        processo.orgao_julgador = validated.orgao_julgador
        processo.grau = validated.grau
        processo.data_ultima_atualizacao = datetime.now(UTC)
        return processo, False

    async def _sync_movimentacoes(
        self, processo: Processo, movimentacoes: list[Any]
    ) -> int:
        """Insere apenas movimentações inéditas (idempotência por data_hora + descrição)."""
        stmt_movs = select(Movimentacao).where(Movimentacao.processo_id == processo.id)
        result_movs = await self.db.execute(stmt_movs)
        existing_movs = result_movs.scalars().all()

        existing_set = {
            _movement_identity_key(mov.data_hora, mov.descricao)
            for mov in existing_movs
        }

        new_movs_count = 0
        for mov in movimentacoes:
            key = _movement_identity_key(mov.data_hora, mov.descricao)
            if key not in existing_set:
                self.db.add(
                    Movimentacao(
                        processo_id=processo.id,
                        data_hora=mov.data_hora,
                        descricao=mov.descricao,
                        complemento=mov.complemento,
                        codigo_movimento=mov.codigo_movimento,
                    )
                )
                new_movs_count += 1

        return new_movs_count

    async def _reload_com_movimentacoes(self, processo_id: Any) -> Processo:
        """Recarrega o processo com as movimentações já materializadas (evita N+1)."""
        stmt_reload = (
            select(Processo)
            .execution_options(populate_existing=True)
            .options(selectinload(Processo.movimentacoes))
            .where(Processo.id == processo_id)
        )
        result_reload = await self.db.execute(stmt_reload)
        return result_reload.scalar_one()
