"""
Utilitários de parsing do número CNJ (padrão NNNNNNN-DD.YYYY.J.TR.OOOO).

Centraliza o mapa de tribunais e a extração de segmentos do CNJ para evitar
duplicação da mesma lógica de `split(".")` espalhada entre o cliente DataJud
e o enriquecedor RAG.
"""

# Mapa J.TR -> (sigla, nome completo, alias da API pública do DataJud).
# Justiça Estadual (8.xx): coberta para demo de jurimetria por UF.
TRIBUNAIS_MAP: dict[str, tuple[str, str, str]] = {
    "8.01": ("TJAC", "Tribunal de Justiça do Acre", "tjac"),
    "8.02": ("TJAL", "Tribunal de Justiça de Alagoas", "tjal"),
    "8.03": ("TJAP", "Tribunal de Justiça do Amapá", "tjap"),
    "8.04": ("TJAM", "Tribunal de Justiça do Amazonas", "tjam"),
    "8.05": ("TJBA", "Tribunal de Justiça da Bahia", "tjba"),
    "8.06": ("TJCE", "Tribunal de Justiça do Ceará", "tjce"),
    "8.07": ("TJDFT", "Tribunal de Justiça do Distrito Federal e Territórios", "tjdft"),
    "8.08": ("TJES", "Tribunal de Justiça do Espírito Santo", "tjes"),
    "8.09": ("TJGO", "Tribunal de Justiça de Goiás", "tjgo"),
    "8.10": ("TJMA", "Tribunal de Justiça do Maranhão", "tjma"),
    "8.11": ("TJMT", "Tribunal de Justiça de Mato Grosso", "tjmt"),
    "8.12": ("TJMS", "Tribunal de Justiça de Mato Grosso do Sul", "tjms"),
    "8.13": ("TJMG", "Tribunal de Justiça de Minas Gerais", "tjmg"),
    "8.14": ("TJPA", "Tribunal de Justiça do Pará", "tjpa"),
    "8.15": ("TJPB", "Tribunal de Justiça da Paraíba", "tjpb"),
    "8.16": ("TJPR", "Tribunal de Justiça do Paraná", "tjpr"),
    "8.17": ("TJPE", "Tribunal de Justiça de Pernambuco", "tjpe"),
    "8.18": ("TJPI", "Tribunal de Justiça do Piauí", "tjpi"),
    "8.19": ("TJRJ", "Tribunal de Justiça do Rio de Janeiro", "tjrj"),
    "8.20": ("TJRN", "Tribunal de Justiça do Rio Grande do Norte", "tjrn"),
    "8.21": ("TJRS", "Tribunal de Justiça do Rio Grande do Sul", "tjrs"),
    "8.22": ("TJRO", "Tribunal de Justiça de Rondônia", "tjro"),
    "8.23": ("TJRR", "Tribunal de Justiça de Roraima", "tjrr"),
    "8.24": ("TJSC", "Tribunal de Justiça de Santa Catarina", "tjsc"),
    "8.25": ("TJSE", "Tribunal de Justiça de Sergipe", "tjse"),
    "8.26": ("TJSP", "Tribunal de Justiça de São Paulo", "tjsp"),
    "8.27": ("TJTO", "Tribunal de Justiça do Tocantins", "tjto"),
    "4.01": ("TRF1", "Tribunal Regional Federal da 1ª Região", "trf1"),
    "4.02": ("TRF2", "Tribunal Regional Federal da 2ª Região", "trf2"),
    "5.01": ("TRT1", "Tribunal Regional do Trabalho da 1ª Região", "trt1"),
}

# Sigla do tribunal estadual -> UF (para mapa de jurimetria).
# Tribunais federais/trabalhistas ficam de fora do mapa por UF.
TRIBUNAL_TO_UF: dict[str, str] = {
    "TJAC": "AC",
    "TJAL": "AL",
    "TJAP": "AP",
    "TJAM": "AM",
    "TJBA": "BA",
    "TJCE": "CE",
    "TJDFT": "DF",
    "TJES": "ES",
    "TJGO": "GO",
    "TJMA": "MA",
    "TJMT": "MT",
    "TJMS": "MS",
    "TJMG": "MG",
    "TJPA": "PA",
    "TJPB": "PB",
    "TJPR": "PR",
    "TJPE": "PE",
    "TJPI": "PI",
    "TJRJ": "RJ",
    "TJRN": "RN",
    "TJRS": "RS",
    "TJRO": "RO",
    "TJRR": "RR",
    "TJSC": "SC",
    "TJSE": "SE",
    "TJSP": "SP",
    "TJTO": "TO",
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


def uf_from_tribunal(sigla_tribunal: str) -> str | None:
    """Retorna a UF do tribunal estadual, ou None se não for TJ de estado."""
    return TRIBUNAL_TO_UF.get(sigla_tribunal.upper())
