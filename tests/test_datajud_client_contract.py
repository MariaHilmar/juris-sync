"""
Testes de mock da API externa DataJud usando respx.

Diferente do monkeypatch manual em test_datajud_client.py, aqui interceptamos
a camada HTTP real (httpx) e validamos o contrato exato da requisição (URL,
headers, payload) além dos cenários de falha (404 vazio, 5xx, timeout), que
devem sempre acionar o fallback determinístico para o mock local.
"""

import json
import re

import httpx
import pytest
import respx

from app.services.datajud_client import DataJudClient

DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"


@pytest.fixture
def client_with_key() -> DataJudClient:
    client = DataJudClient()
    client.api_key = "chave-de-teste"
    client.base_url = DATAJUD_BASE_URL
    return client


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_api_sends_expected_request_contract(
    client_with_key: DataJudClient,
):
    cnj = "0001234-56.2023.8.15.0001"
    route = respx.post(f"{DATAJUD_BASE_URL}/api_publica_tjpb/_search").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "numeroProcesso": "00012345620238150001",
                                "classe": {"nome": "Procedimento Comum Cível"},
                                "assuntos": [{"nome": "Dano Moral"}],
                                "orgaoJulgador": {"nome": "1ª Vara Cível"},
                                "dataAjuizamento": "2023-05-10T10:00:00",
                                "movimentos": [
                                    {
                                        "dataHora": "2023-05-10T10:00:00",
                                        "nome": "Distribuído por Sorteio",
                                        "codigo": 1,
                                    }
                                ],
                            }
                        }
                    ]
                }
            },
        )
    )

    data = await client_with_key.fetch_process_data(cnj, grau=1)

    assert route.called
    sent_request = route.calls.last.request

    # Contrato de autenticação e content-type exigido pela API pública do DataJud
    assert sent_request.headers["Authorization"] == "APIKey chave-de-teste"
    assert sent_request.headers["Content-Type"] == "application/json"

    body = json.loads(sent_request.content)
    assert body["size"] == 1
    assert body["query"]["term"]["numeroProcesso"] == "00012345620238150001"

    assert data["classe"] == "Procedimento Comum Cível"
    assert data["assunto"] == "Dano Moral"
    assert data["tribunal"] == "TJPB"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_api_with_empty_hits_falls_back_to_mock(
    client_with_key: DataJudClient,
):
    cnj = "0001234-56.2023.8.15.0001"
    respx.post(re.compile(r".*api_publica_tjpb/_search")).mock(
        return_value=httpx.Response(200, json={"hits": {"hits": []}})
    )

    data = await client_with_key.fetch_process_data(cnj, grau=1)

    # Processo não encontrado na origem não deve propagar erro ao chamador:
    # o cliente deve degradar graciosamente para o mock determinístico.
    assert data["numeroProcesso"] == cnj
    assert data["tribunal"] == "TJPB"
    assert len(data["movimentacoes"]) > 0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_api_http_server_error_falls_back_to_mock(
    client_with_key: DataJudClient,
):
    cnj = "0001234-56.2023.8.15.0001"
    client_with_key.retry_base_delay = 0  # evita esperas reais de backoff no teste
    respx.post(re.compile(r".*api_publica_tjpb/_search")).mock(
        return_value=httpx.Response(500, json={"error": "internal_server_error"})
    )

    data = await client_with_key.fetch_process_data(cnj, grau=1)

    assert data["tribunal"] == "TJPB"
    assert len(data["movimentacoes"]) > 0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_api_network_timeout_falls_back_to_mock(
    client_with_key: DataJudClient,
):
    cnj = "0001234-56.2023.8.15.0001"
    client_with_key.retry_base_delay = 0  # evita esperas reais de backoff no teste
    respx.post(re.compile(r".*api_publica_tjpb/_search")).mock(
        side_effect=httpx.ConnectTimeout("timeout simulado")
    )

    data = await client_with_key.fetch_process_data(cnj, grau=1)

    assert data["tribunal"] == "TJPB"
    assert len(data["movimentacoes"]) > 0
