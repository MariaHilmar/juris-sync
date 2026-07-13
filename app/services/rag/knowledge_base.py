from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    categoria: str
    tribunal: str | None
    texto: str
    termos_chave: tuple[str, ...]


LEGAL_KNOWLEDGE_BASE: list[KnowledgeChunk] = [
    KnowledgeChunk(
        id="tribunal-tjpb",
        categoria="tribunal",
        tribunal="TJPB",
        texto=(
            "TJPB - Tribunal de Justiça da Paraíba. Competência cível, criminal e "
            "especial nas comarcas do estado da Paraíba."
        ),
        termos_chave=("tjpb", "paraíba", "paraiba", "8.15"),
    ),
    KnowledgeChunk(
        id="tribunal-tjsp",
        categoria="tribunal",
        tribunal="TJSP",
        texto=(
            "TJSP - Tribunal de Justiça de São Paulo. Alto volume processual em "
            "varas cíveis, criminais e especializadas."
        ),
        termos_chave=("tjsp", "são paulo", "sao paulo", "8.26"),
    ),
    KnowledgeChunk(
        id="tribunal-tjrj",
        categoria="tribunal",
        tribunal="TJRJ",
        texto=(
            "TJRJ - Tribunal de Justiça do Rio de Janeiro. Atua em processos "
            "cíveis, criminais e fazendários do estado do Rio."
        ),
        termos_chave=("tjrj", "rio de janeiro", "8.19"),
    ),
    KnowledgeChunk(
        id="classe-procedimento-comum",
        categoria="classe",
        tribunal=None,
        texto=(
            "Procedimento Comum Cível: rito ordinário para demandas sem rito "
            "específico previsto no CPC."
        ),
        termos_chave=("procedimento comum", "cível", "cpc", "rito ordinário"),
    ),
    KnowledgeChunk(
        id="classe-execucao-titulo",
        categoria="classe",
        tribunal=None,
        texto=(
            "Execução de Título Extrajudicial: cobrança de dívida líquida e "
            "certa com base em título executivo extrajudicial."
        ),
        termos_chave=("execução", "título extrajudicial", "cobrança"),
    ),
    KnowledgeChunk(
        id="assunto-dano-moral",
        categoria="assunto",
        tribunal=None,
        texto=(
            "Indenização por Dano Moral: reparação por violação a direitos da "
            "personalidade, como honra, imagem e dignidade."
        ),
        termos_chave=("dano moral", "indenização", "personalidade", "honra"),
    ),
    KnowledgeChunk(
        id="assunto-cdc",
        categoria="assunto",
        tribunal=None,
        texto=(
            "Práticas Abusivas / Direito do Consumidor: relações de consumo "
            "regidas pelo CDC, incluindo vícios e defeitos de serviço."
        ),
        termos_chave=("consumidor", "cdc", "práticas abusivas", "fornecedor"),
    ),
    KnowledgeChunk(
        id="assunto-cadastro-inadimplentes",
        categoria="assunto",
        tribunal=None,
        texto=(
            "Inclusão Indevida em Cadastro de Inadimplentes: negativação "
            "indevida em órgãos de proteção ao crédito (SPC/Serasa)."
        ),
        termos_chave=("cadastro", "inadimplentes", "negativação", "spc", "serasa"),
    ),
    KnowledgeChunk(
        id="movimento-distribuicao",
        categoria="movimentacao",
        tribunal=None,
        texto=(
            "Distribuído por Sorteio: ato inicial de autuação e encaminhamento "
            "do processo a uma vara competente."
        ),
        termos_chave=("distribuído", "sorteio", "autuação"),
    ),
    KnowledgeChunk(
        id="movimento-despacho",
        categoria="movimentacao",
        tribunal=None,
        texto=(
            "Despacho Proferido: manifestação judicial de mero expediente, sem "
            "conteúdo decisório de mérito."
        ),
        termos_chave=("despacho", "conclusos", "expediente"),
    ),
]
