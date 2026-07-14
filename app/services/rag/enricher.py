import json
import re
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.core.cnj import tribunal_sigla_from_cnj
from app.core.config import settings
from app.services.rag.knowledge_base import KnowledgeChunk
from app.services.rag.vector_store import InMemoryVectorStore

logger = structlog.get_logger()

CANONICAL_ASSUNTOS = {
    "dano moral": "Indenização por Dano Moral",
    "consumidor": "Práticas Abusivas / Direito do Consumidor",
    "cadastro": "Inclusão Indevida em Cadastro de Inadimplentes",
    "contrato": "Prestação de Serviços - Contratos",
    "fiduciária": "Alienação Fiduciária",
    "fiduciaria": "Alienação Fiduciária",
}

CANONICAL_CLASSES = {
    "procedimento comum": "Procedimento Comum Cível",
    "execução": "Execução de Título Extrajudicial",
    "cumprimento": "Cumprimento de Sentença",
    "ação penal": "Ação Penal - Procedimento Ordinário",
    "recurso inominado": "Recurso Inominado Cível",
}


class DataJudRAGEnricher:
    """
    Camada RAG que recupera contexto jurídico e enriquece dados brutos do DataJud
    antes da validação estrita via Pydantic v2.
    """

    def __init__(self, vector_store: InMemoryVectorStore | None = None):
        self.vector_store = vector_store or InMemoryVectorStore()

    async def enrich(
        self,
        raw_data: dict[str, Any],
        numero_cnj: str,
        grau: int,
    ) -> dict[str, Any]:
        query = self._build_query(raw_data, numero_cnj)
        retrieved = self.vector_store.search(query, top_k=settings.RAG_TOP_K)
        context_chunks = [chunk.texto for chunk, _ in retrieved]

        logger.info(
            "rag_retrieval_completed",
            numero_cnj=numero_cnj,
            chunks_retrieved=len(context_chunks),
            top_score=retrieved[0][1] if retrieved else 0.0,
        )

        normalized = self._normalize_raw_payload(raw_data, numero_cnj, grau)
        enriched = self._apply_context(normalized, retrieved)

        if settings.OPENAI_API_KEY:
            enriched = await self._llm_refine(enriched, context_chunks)

        enriched["contexto_rag"] = context_chunks
        return enriched

    def _build_query(self, raw_data: dict[str, Any], numero_cnj: str) -> str:
        parts = [
            numero_cnj,
            str(raw_data.get("classe", "")),
            str(raw_data.get("assunto", "")),
            str(raw_data.get("tribunal", "")),
            str(raw_data.get("orgao_julgador", "")),
        ]
        return " ".join(part for part in parts if part)

    def _normalize_raw_payload(
        self,
        raw_data: dict[str, Any],
        numero_cnj: str,
        grau: int,
    ) -> dict[str, Any]:
        movimentacoes = []
        for mov in raw_data.get("movimentacoes", []):
            movimentacoes.append(
                {
                    "data_hora": mov["data_hora"],
                    "descricao": mov.get("descricao", "").strip(),
                    "complemento": mov.get("complemento"),
                    "codigo_movimento": mov.get("codigo_movimento"),
                }
            )

        data_distribuicao = raw_data.get("data_distribuicao")
        if isinstance(data_distribuicao, str):
            data_distribuicao = datetime.fromisoformat(data_distribuicao)

        return {
            "numero_cnj": raw_data.get("numeroProcesso")
            or raw_data.get("numero_cnj")
            or numero_cnj,
            "classe": raw_data.get("classe"),
            "assunto": raw_data.get("assunto"),
            "tribunal": raw_data.get("tribunal", ""),
            "orgao_julgador": raw_data.get("orgao_julgador"),
            "data_distribuicao": data_distribuicao,
            "grau": raw_data.get("grau", grau),
            "movimentacoes": movimentacoes,
        }

    def _apply_context(
        self,
        payload: dict[str, Any],
        retrieved: list[tuple[KnowledgeChunk, float]],
    ) -> dict[str, Any]:
        enriched = dict(payload)

        cnj_tribunal = self._tribunal_from_cnj(enriched["numero_cnj"])
        if cnj_tribunal:
            enriched["tribunal"] = cnj_tribunal
        elif not self._is_valid_tribunal_sigla(enriched.get("tribunal", "")):
            tribunal_chunk = next(
                (chunk for chunk, _ in retrieved if chunk.categoria == "tribunal"),
                None,
            )
            if tribunal_chunk and tribunal_chunk.tribunal:
                enriched["tribunal"] = tribunal_chunk.tribunal

        if enriched.get("classe"):
            enriched["classe"] = (
                self._canonicalize(enriched["classe"], CANONICAL_CLASSES)
                or enriched["classe"]
            )
        if enriched.get("assunto"):
            enriched["assunto"] = (
                self._canonicalize(enriched["assunto"], CANONICAL_ASSUNTOS)
                or enriched["assunto"]
            )

        return enriched

    def _tribunal_from_cnj(self, numero_cnj: str) -> str | None:
        return tribunal_sigla_from_cnj(numero_cnj)

    def _is_valid_tribunal_sigla(self, tribunal: str) -> bool:
        return bool(re.match(r"^[A-Z]{2,5}\d?$", tribunal or ""))

    def _canonicalize(self, value: str, mapping: dict[str, str]) -> str | None:
        lowered = value.lower()
        for needle, canonical in mapping.items():
            if needle in lowered:
                return canonical
        return None

    async def _llm_refine(
        self,
        payload: dict[str, Any],
        context_chunks: list[str],
    ) -> dict[str, Any]:
        prompt = {
            "contexto_juridico": context_chunks,
            "dados_brutos": payload,
            "instrucao": (
                "Normalize classe, assunto e tribunal com base no contexto jurídico. "
                "Retorne apenas JSON compatível com o schema de processo."
            ),
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{settings.OPENAI_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.OPENAI_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Você normaliza dados jurídicos brasileiros e responde somente em JSON.",
                            },
                            {
                                "role": "user",
                                "content": json.dumps(prompt, default=str),
                            },
                        ],
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                refined = json.loads(content)
                payload.update({k: v for k, v in refined.items() if k in payload})
                logger.info("rag_llm_refinement_applied")
        except Exception as error:
            logger.warning("rag_llm_refinement_skipped", error=str(error))

        return payload
