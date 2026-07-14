"""
Utilitários de parsing do número CNJ (padrão NNNNNNN-DD.YYYY.J.TR.OOOO).

Centraliza o mapa de tribunais e a extração de segmentos do CNJ para evitar
duplicação da mesma lógica de `split(".")` espalhada entre o cliente DataJud
e o enriquecedor RAG.
"""

# Mapa J.TR -> (sigla, nome completo, alias da API pública do DataJud).
TRIBUNAIS_MAP: dict[str, tuple[str, str, str]] = {
    "8.15": ("TJPB", "Tribunal de Justiça da Paraíba", "tjpb"),
    "8.26": ("TJSP", "Tribunal de Justiça de São Paulo", "tjsp"),
    "8.19": ("TJRJ", "Tribunal de Justiça do Rio de Janeiro", "tjrj"),
    "8.06": ("TJCE", "Tribunal de Justiça do Ceará", "tjce"),
    "4.01": ("TRF1", "Tribunal Regional Federal da 1ª Região", "trf1"),
    "4.02": ("TRF2", "Tribunal Regional Federal da 2ª Região", "trf2"),
    "5.01": ("TRT1", "Tribunal Regional do Trabalho da 1ª Região", "trt1"),
}


def segmento_jtr(numero_cnj: str) -> str | None:
    """
    Retorna o segmento "J.TR" (justiça + tribunal) do CNJ, ex: "8.15".
    Retorna None se o número não tiver segmentos suficientes.
    """
    parts = numero_cnj.split(".")
    if len(parts) >= 4:
        return f"{parts[2]}.{parts[3]}"
    return None


def tribunal_info_from_cnj(numero_cnj: str) -> tuple[str, str, str] | None:
    """
    Resolve a tupla (sigla, nome, alias) do tribunal a partir do CNJ.
    Retorna None se o segmento J.TR não estiver mapeado em TRIBUNAIS_MAP.
    """
    codigo = segmento_jtr(numero_cnj)
    if codigo is None:
        return None
    return TRIBUNAIS_MAP.get(codigo)


def tribunal_sigla_from_cnj(numero_cnj: str) -> str | None:
    """Retorna apenas a sigla do tribunal (ex: "TJPB") ou None se não mapeado."""
    info = tribunal_info_from_cnj(numero_cnj)
    return info[0] if info else None


def tribunal_alias_from_cnj(numero_cnj: str) -> str | None:
    """Retorna o alias da API pública (ex: "tjpb") ou None se não mapeado."""
    info = tribunal_info_from_cnj(numero_cnj)
    return info[2] if info else None
