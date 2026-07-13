import pytest

from app.schemas.datajud import DataJudProcessoSchema
from app.services.rag.enricher import DataJudRAGEnricher
from app.services.rag.vector_store import InMemoryVectorStore


@pytest.mark.asyncio
async def test_rag_enricher_retrieves_context_and_normalizes_fields():
    enricher = DataJudRAGEnricher()
    raw_data = {
        "numeroProcesso": "0801234-56.2023.8.15.0001",
        "classe": "procedimento comum cível",
        "assunto": "dano moral por negativação indevida",
        "tribunal": "paraíba",
        "orgao_julgador": "1ª Vara Cível",
        "data_distribuicao": "2023-05-10T10:00:00",
        "grau": 1,
        "movimentacoes": [
            {
                "data_hora": "2023-05-10T10:00:00",
                "descricao": "Distribuído por Sorteio",
                "complemento": "Autuação inicial",
                "codigo_movimento": 1,
            }
        ],
    }

    enriched = await enricher.enrich(raw_data, "0801234-56.2023.8.15.0001", grau=1)
    validated = DataJudProcessoSchema.from_enriched(enriched)

    assert validated.tribunal == "TJPB"
    assert validated.classe == "Procedimento Comum Cível"
    assert validated.assunto == "Indenização por Dano Moral"
    assert len(validated.contexto_rag) > 0
    assert len(validated.movimentacoes) == 1


@pytest.mark.asyncio
async def test_rag_pipeline_rejects_invalid_cnj_after_enrichment():
    enricher = DataJudRAGEnricher()
    raw_data = {
        "numeroProcesso": "numero-invalido",
        "tribunal": "TJSP",
        "movimentacoes": [],
    }

    enriched = await enricher.enrich(raw_data, "numero-invalido", grau=1)

    with pytest.raises(ValueError):
        DataJudProcessoSchema.from_enriched(enriched)


def test_vector_store_returns_relevant_chunks_for_legal_query():
    store = InMemoryVectorStore()
    results = store.search("dano moral tjsp consumidor", top_k=2)

    assert len(results) > 0
    categories = {chunk.categoria for chunk, _ in results}
    assert "assunto" in categories or "tribunal" in categories
