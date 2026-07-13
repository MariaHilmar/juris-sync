import pytest
from httpx import AsyncClient

from app.schemas.datajud import DataJudProcessoSchema
from app.schemas.process import ProcessoSyncRequest


def test_processo_sync_request_rejects_invalid_cnj():
    with pytest.raises(ValueError):
        ProcessoSyncRequest(numero_cnj="123", grau=1)


def test_datajud_schema_accepts_valid_payload():
    payload = {
        "numero_cnj": "0001234-56.2023.8.15.0001",
        "classe": "Procedimento Comum Cível",
        "assunto": "Dano Moral",
        "tribunal": "TJPB",
        "orgao_julgador": "1ª Vara Cível",
        "data_distribuicao": "2023-05-10T10:00:00",
        "grau": 1,
        "movimentacoes": [
            {
                "data_hora": "2023-05-10T10:00:00",
                "descricao": "Distribuído por Sorteio",
                "complemento": None,
                "codigo_movimento": 1,
            }
        ],
        "contexto_rag": ["contexto"],
    }

    schema = DataJudProcessoSchema.model_validate(payload)

    assert schema.numero_cnj == payload["numero_cnj"]
    assert schema.tribunal == "TJPB"
    assert len(schema.movimentacoes) == 1


@pytest.mark.asyncio
async def test_health_reports_datajud_mock_mode(api_client: AsyncClient):
    response = await api_client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["services"]["database"] == "healthy"
    assert data["services"]["datajud_api"] == "mock_mode"
