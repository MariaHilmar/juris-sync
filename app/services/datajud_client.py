import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from app.core.cnj import (
    TRIBUNAIS_MAP,
    tribunal_alias_from_cnj,
    tribunal_info_from_cnj,
    tribunal_sigla_from_cnj,
)
from app.core.config import settings

logger = structlog.get_logger()

__all__ = [
    "DataJudClient",
    "TRIBUNAIS_MAP",
    "close_shared_http_client",
    "DataJudError",
    "DataJudNotFoundError",
    "DataJudTransientError",
]

# Status HTTP que indicam falha transitória e valem retry (rate limit + 5xx).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DataJudError(Exception):
    """Erro base da integração com o DataJud."""


class DataJudNotFoundError(DataJudError):
    """Processo não encontrado na origem (não é falha transitória)."""


class DataJudTransientError(DataJudError):
    """Falha transitória (timeout, rede, 429, 5xx) - elegível a retry."""


CLASSES_EXEMPLO = [
    "Procedimento Comum Cível",
    "Execução de Título Extrajudicial",
    "Cumprimento de Sentença",
    "Ação Penal - Procedimento Ordinário",
    "Recurso Inominado Cível",
]

ASSUNTOS_EXEMPLO = [
    "Indenização por Dano Moral",
    "Inclusão Indevida em Cadastro de Inadimplentes",
    "Prestação de Serviços - Contratos",
    "Práticas Abusivas / Direito do Consumidor",
    "Alienação Fiduciária",
]

MOVIMENTACOES_EXEMPLO = [
    ("Distribuído por Sorteio", 0, 1),
    ("Conclusos para Despacho", 2, 22),
    ("Despacho Proferido", 5, 110),
    ("Expedida Notificação Citação", 8, 60),
    ("Juntada de Petição de Contestação", 15, 85),
    ("Conclusos para Decisão", 20, 22),
    ("Decisão Saneadora Proferida", 25, 110),
    ("Designada Audiência de Conciliação", 28, 120),
]

_module_http_client: httpx.AsyncClient | None = None


def _get_shared_http_client() -> httpx.AsyncClient:
    """Retorna um AsyncClient compartilhado (pool de conexões reutilizável)."""
    global _module_http_client
    if _module_http_client is None or _module_http_client.is_closed:
        _module_http_client = httpx.AsyncClient(timeout=20.0)
    return _module_http_client


async def close_shared_http_client() -> None:
    """Encerra o cliente HTTP compartilhado (chamado no shutdown da aplicação)."""
    global _module_http_client
    if _module_http_client is not None and not _module_http_client.is_closed:
        await _module_http_client.aclose()
    _module_http_client = None


class DataJudClient:
    """
    Cliente para integração com a API pública do DataJud (CNJ).
    Sem chave configurada, ou em caso de falha, usa mock determinístico
    baseado no padrão numérico do CNJ.
    """

    def __init__(self) -> None:
        self.api_key = settings.DATAJUD_API_KEY
        self.base_url = settings.DATAJUD_API_URL.rstrip("/")
        # Retry com backoff exponencial para falhas transitórias.
        # Expostos como atributos de instância para facilitar override em testes.
        self.max_retries = 2
        self.retry_base_delay = 0.5

    @property
    def _mock_fallback_enabled(self) -> bool:
        """
        O fallback para dados fictícios só é seguro fora de produção.
        Em produção, uma falha real deve propagar em vez de mascarar dados
        inventados como se fossem oficiais.
        """
        return settings.ENV != "production"

    async def fetch_process_data(
        self, numero_cnj: str, grau: int = 1
    ) -> dict[str, Any]:
        numero_limpo = re.sub(r"\D", "", numero_cnj)

        if self.api_key:
            logger.info("datajud_client_request_started", numero_cnj=numero_cnj)
            try:
                data = await self._fetch_with_retry(numero_cnj, numero_limpo)
                logger.info("datajud_client_request_success", numero_cnj=numero_cnj)
                return data
            except DataJudNotFoundError as error:
                logger.warning(
                    "datajud_client_process_not_found",
                    numero_cnj=numero_cnj,
                    error=str(error),
                )
                if not self._mock_fallback_enabled:
                    raise
            except Exception as error:
                logger.error(
                    "datajud_client_request_failed",
                    error=str(error),
                    numero_cnj=numero_cnj,
                )
                if not self._mock_fallback_enabled:
                    raise
            logger.info(
                "datajud_client_activating_mock_fallback", numero_cnj=numero_cnj
            )

        logger.info("datajud_client_generating_mock_data", numero_cnj=numero_cnj)
        return self._generate_mock_data(numero_cnj, grau)

    async def _fetch_with_retry(
        self, numero_cnj: str, numero_limpo: str
    ) -> dict[str, Any]:
        """Executa a chamada com retry + backoff exponencial em falhas transitórias."""
        attempt = 0
        while True:
            try:
                return await self._fetch_from_api(numero_cnj, numero_limpo)
            except DataJudTransientError as error:
                if attempt >= self.max_retries:
                    raise
                delay = self.retry_base_delay * (2**attempt)
                logger.warning(
                    "datajud_client_retrying",
                    numero_cnj=numero_cnj,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    delay_seconds=delay,
                    error=str(error),
                )
                await asyncio.sleep(delay)
                attempt += 1

    async def _fetch_from_api(
        self, numero_cnj: str, numero_limpo: str
    ) -> dict[str, Any]:
        tribunal_alias = self._resolve_tribunal_alias(numero_cnj)
        url = f"{self.base_url}/api_publica_{tribunal_alias}/_search"

        # `term` (não `match`) porque o número CNJ é um identificador exato:
        # evita análise full-text e o risco de recall indevido. `size: 1`
        # deixa explícito que só o hit correspondente interessa.
        payload = {
            "size": 1,
            "query": {
                "term": {
                    "numeroProcesso": numero_limpo,
                }
            },
        }

        client = _get_shared_http_client()
        try:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"APIKey {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise DataJudTransientError(
                f"Falha de rede ao consultar o DataJud ({tribunal_alias}): {error}"
            ) from error

        if response.status_code in RETRYABLE_STATUS:
            raise DataJudTransientError(
                f"DataJud retornou status {response.status_code} "
                f"({tribunal_alias}) para o processo {numero_cnj}."
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise DataJudError(
                f"Erro não recuperável do DataJud ({tribunal_alias}): {error}"
            ) from error

        body = response.json()

        hits = body.get("hits", {}).get("hits", [])
        if not hits:
            raise DataJudNotFoundError(
                f"Processo {numero_cnj} não encontrado no DataJud ({tribunal_alias})."
            )

        return self._normalize_api_source(hits[0].get("_source", {}), numero_cnj)

    def _resolve_tribunal_alias(self, numero_cnj: str) -> str:
        alias = tribunal_alias_from_cnj(numero_cnj)
        if alias:
            return alias

        raise ValueError(
            f"Tribunal não mapeado para o CNJ {numero_cnj}. "
            "Configure um número com segmento J.TR conhecido ou use o mock local."
        )

    def _normalize_api_source(
        self, source: dict[str, Any], numero_cnj: str
    ) -> dict[str, Any]:
        classe = source.get("classe")
        if isinstance(classe, dict):
            classe = classe.get("nome")

        assunto = source.get("assunto")
        if not assunto:
            assuntos = source.get("assuntos") or []
            if assuntos and isinstance(assuntos[0], dict):
                assunto = assuntos[0].get("nome")

        orgao = source.get("orgao_julgador") or source.get("orgaoJulgador")
        if isinstance(orgao, dict):
            orgao = orgao.get("nome")

        data_distribuicao = (
            source.get("data_distribuicao")
            or source.get("dataAjuizamento")
            or source.get("dataHoraUltimaAtualizacao")
        )

        movimentacoes = []
        for mov in source.get("movimentacoes") or source.get("movimentos") or []:
            if isinstance(mov, dict):
                movimentacoes.append(
                    {
                        "data_hora": mov.get("dataHora") or mov.get("data_hora"),
                        "descricao": mov.get("nome") or mov.get("descricao") or "",
                        "complemento": mov.get("complemento"),
                        "codigo_movimento": mov.get("codigo"),
                    }
                )

        return {
            "numeroProcesso": source.get("numeroProcesso") or numero_cnj,
            "classe": classe,
            "assunto": assunto,
            "tribunal": source.get("tribunal")
            or self._tribunal_sigla_from_cnj(numero_cnj),
            "orgao_julgador": orgao,
            "data_distribuicao": data_distribuicao,
            "grau": source.get("grau") or 1,
            "movimentacoes": movimentacoes,
        }

    def _tribunal_sigla_from_cnj(self, numero_cnj: str) -> str:
        return tribunal_sigla_from_cnj(numero_cnj) or "TJSP"

    def _generate_mock_data(self, numero_cnj: str, grau: int) -> dict[str, Any]:
        parts = numero_cnj.split(".")

        ano_distribuicao = 2023
        try:
            if len(parts) >= 2:
                ano_candidato = int(parts[1])
                # Protege contra segmentos de ano fora de um intervalo válido
                # para datetime (ex: "0000"), que passam pela regex do CNJ
                # mas não representam um ano real de distribuição.
                if 1900 <= ano_candidato <= 2100:
                    ano_distribuicao = ano_candidato
        except ValueError:
            pass

        sigla_tribunal, nome_tribunal, _ = tribunal_info_from_cnj(numero_cnj) or (
            "TJSP",
            "Tribunal de Justiça de São Paulo",
            "tjsp",
        )

        # Gerador local semeado pelo CNJ: garante determinismo (RN06) sem
        # tocar no estado global do módulo `random` (thread-safe).
        rng = random.Random(numero_cnj)

        orgao_codigo = parts[4] if len(parts) >= 5 else "0001"
        orgao_julgador = f"{rng.randint(1, 10)}ª Vara Cível de {nome_tribunal} (Comarca {orgao_codigo})"

        classe = rng.choice(CLASSES_EXEMPLO)
        assunto = rng.choice(ASSUNTOS_EXEMPLO)

        mes = rng.randint(1, 12)
        dia = rng.randint(1, 28)
        data_dist = datetime(
            ano_distribuicao, mes, dia, rng.randint(8, 18), rng.randint(0, 59)
        )

        movs = []
        for desc, dias_offset, cod in MOVIMENTACOES_EXEMPLO:
            data_mov = data_dist + timedelta(days=dias_offset)
            if data_mov < datetime.now():
                movs.append(
                    {
                        "data_hora": data_mov.isoformat(),
                        "descricao": desc,
                        "complemento": (
                            f"Movimentação registrada via integração com o tribunal {sigla_tribunal}."
                        ),
                        "codigo_movimento": cod,
                    }
                )

        return {
            "numeroProcesso": numero_cnj,
            "classe": classe,
            "assunto": assunto,
            "tribunal": sigla_tribunal,
            "orgao_julgador": orgao_julgador,
            "data_distribuicao": data_dist.isoformat(),
            "grau": grau,
            "movimentacoes": sorted(
                movs, key=lambda item: item["data_hora"], reverse=True
            ),
        }
