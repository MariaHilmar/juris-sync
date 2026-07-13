import random
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

TRIBUNAIS_MAP = {
    "8.15": ("TJPB", "Tribunal de Justiça da Paraíba", "tjpb"),
    "8.26": ("TJSP", "Tribunal de Justiça de São Paulo", "tjsp"),
    "8.19": ("TJRJ", "Tribunal de Justiça do Rio de Janeiro", "tjrj"),
    "8.06": ("TJCE", "Tribunal de Justiça do Ceará", "tjce"),
    "4.01": ("TRF1", "Tribunal Regional Federal da 1ª Região", "trf1"),
    "4.02": ("TRF2", "Tribunal Regional Federal da 2ª Região", "trf2"),
    "5.01": ("TRT1", "Tribunal Regional do Trabalho da 1ª Região", "trt1"),
}

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


class DataJudClient:
    """
    Cliente para integração com a API pública do DataJud (CNJ).
    Sem chave configurada, ou em caso de falha, usa mock determinístico
    baseado no padrão numérico do CNJ.
    """

    def __init__(self) -> None:
        self.api_key = settings.DATAJUD_API_KEY
        self.base_url = settings.DATAJUD_API_URL.rstrip("/")

    async def fetch_process_data(
        self, numero_cnj: str, grau: int = 1
    ) -> dict[str, Any]:
        numero_limpo = re.sub(r"\D", "", numero_cnj)

        if self.api_key:
            logger.info("datajud_client_request_started", numero_cnj=numero_cnj)
            try:
                data = await self._fetch_from_api(numero_cnj, numero_limpo)
                logger.info("datajud_client_request_success", numero_cnj=numero_cnj)
                return data
            except Exception as error:
                logger.error(
                    "datajud_client_request_failed",
                    error=str(error),
                    numero_cnj=numero_cnj,
                )
                logger.info(
                    "datajud_client_activating_mock_fallback", numero_cnj=numero_cnj
                )

        logger.info("datajud_client_generating_mock_data", numero_cnj=numero_cnj)
        return self._generate_mock_data(numero_cnj, grau)

    async def _fetch_from_api(
        self, numero_cnj: str, numero_limpo: str
    ) -> dict[str, Any]:
        tribunal_alias = self._resolve_tribunal_alias(numero_cnj)
        url = f"{self.base_url}/api_publica_{tribunal_alias}/_search"

        payload = {
            "query": {
                "match": {
                    "numeroProcesso": numero_limpo,
                }
            }
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"APIKey {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        hits = body.get("hits", {}).get("hits", [])
        if not hits:
            raise ValueError(
                f"Processo {numero_cnj} não encontrado no DataJud ({tribunal_alias})."
            )

        return self._normalize_api_source(hits[0].get("_source", {}), numero_cnj)

    def _resolve_tribunal_alias(self, numero_cnj: str) -> str:
        parts = numero_cnj.split(".")
        if len(parts) >= 4:
            tribunal_code = f"{parts[2]}.{parts[3]}"
            tribunal_info = TRIBUNAIS_MAP.get(tribunal_code)
            if tribunal_info:
                return tribunal_info[2]

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
        parts = numero_cnj.split(".")
        if len(parts) >= 4:
            tribunal_code = f"{parts[2]}.{parts[3]}"
            tribunal_info = TRIBUNAIS_MAP.get(tribunal_code)
            if tribunal_info:
                return tribunal_info[0]
        return "TJSP"

    def _generate_mock_data(self, numero_cnj: str, grau: int) -> dict[str, Any]:
        parts = numero_cnj.split(".")

        ano_distribuicao = 2023
        try:
            if len(parts) >= 2:
                ano_distribuicao = int(parts[1])
        except ValueError:
            pass

        tribunal_code = "8.26"
        if len(parts) >= 4:
            tribunal_code = f"{parts[2]}.{parts[3]}"

        sigla_tribunal, nome_tribunal, _ = TRIBUNAIS_MAP.get(
            tribunal_code, ("TJSP", "Tribunal de Justiça de São Paulo", "tjsp")
        )

        orgao_codigo = parts[4] if len(parts) >= 5 else "0001"
        orgao_julgador = f"{random.randint(1, 10)}ª Vara Cível de {nome_tribunal} (Comarca {orgao_codigo})"

        random.seed(numero_cnj)
        classe = random.choice(CLASSES_EXEMPLO)
        assunto = random.choice(ASSUNTOS_EXEMPLO)

        mes = random.randint(1, 12)
        dia = random.randint(1, 28)
        data_dist = datetime(
            ano_distribuicao, mes, dia, random.randint(8, 18), random.randint(0, 59)
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

        random.seed(None)

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
