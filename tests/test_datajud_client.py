import pytest

from app.services.datajud_client import TRIBUNAIS_MAP, DataJudClient


@pytest.mark.asyncio
async def test_mock_client_generates_consistent_data():
    client = DataJudClient()
    cnj = "0001234-56.2023.8.15.0001"

    first = await client.fetch_process_data(cnj, grau=1)
    second = await client.fetch_process_data(cnj, grau=1)

    assert first["numeroProcesso"] == cnj
    assert first["tribunal"] == "TJPB"
    assert len(first["movimentacoes"]) > 0
    assert first["classe"] == second["classe"]
    assert first["assunto"] == second["assunto"]
    assert first["orgao_julgador"] == second["orgao_julgador"]
    assert first["data_distribuicao"] == second["data_distribuicao"]
    assert len(first["movimentacoes"]) == len(second["movimentacoes"])


@pytest.mark.asyncio
async def test_mock_client_is_deterministic_and_isolated_from_global_random():
    """
    Garante determinismo total do mock (RN06) mesmo quando o estado global
    do módulo `random` é alterado entre chamadas. Protege contra regressão
    do bug em que o número da vara era sorteado antes de semear o gerador.
    """
    import random

    client = DataJudClient()
    cnj = "0009876-54.2023.8.26.0100"

    random.seed(1)
    first = await client.fetch_process_data(cnj, grau=1)

    random.seed(999)
    _ = [random.random() for _ in range(50)]
    second = await client.fetch_process_data(cnj, grau=1)

    assert first["orgao_julgador"] == second["orgao_julgador"]
    assert first["classe"] == second["classe"]
    assert first["assunto"] == second["assunto"]
    assert first["data_distribuicao"] == second["data_distribuicao"]


@pytest.mark.asyncio
async def test_mock_client_maps_tribunal_from_cnj_segment():
    client = DataJudClient()

    tjsp = await client.fetch_process_data("0001111-11.2023.8.26.0001")
    tjrj = await client.fetch_process_data("0002222-22.2023.8.19.0001")

    assert tjsp["tribunal"] == "TJSP"
    assert tjrj["tribunal"] == "TJRJ"


def test_resolve_tribunal_alias_from_cnj():
    client = DataJudClient()

    assert client._resolve_tribunal_alias("0001234-56.2023.8.15.0001") == "tjpb"
    assert client._resolve_tribunal_alias("0001234-56.2023.8.26.0001") == "tjsp"


def test_resolve_tribunal_alias_raises_for_unknown_cnj():
    client = DataJudClient()

    with pytest.raises(ValueError, match="Tribunal não mapeado"):
        client._resolve_tribunal_alias("0001234-56.2023.9.99.0001")


def test_normalize_api_source_maps_nested_fields():
    client = DataJudClient()
    cnj = "0001234-56.2023.8.15.0001"

    normalized = client._normalize_api_source(
        {
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
        },
        cnj,
    )

    assert normalized["classe"] == "Procedimento Comum Cível"
    assert normalized["assunto"] == "Dano Moral"
    assert normalized["orgao_julgador"] == "1ª Vara Cível"
    assert normalized["tribunal"] == "TJPB"
    assert len(normalized["movimentacoes"]) == 1


@pytest.mark.asyncio
async def test_fetch_with_api_key_calls_http_and_parses_response(monkeypatch):
    client = DataJudClient()
    client.api_key = "test-key"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "numeroProcesso": "00012345620238150001",
                                "classe": {"nome": "Procedimento Comum Cível"},
                                "assuntos": [{"nome": "Dano Moral"}],
                                "orgaoJulgador": {"nome": "1ª Vara Cível"},
                                "dataAjuizamento": "2023-05-10T10:00:00",
                                "movimentos": [],
                            }
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            assert "api_publica_tjpb/_search" in url
            assert headers["Authorization"] == "APIKey test-key"
            assert json["query"]["match"]["numeroProcesso"] == "00012345620238150001"
            return FakeResponse()

    monkeypatch.setattr("app.services.datajud_client.httpx.AsyncClient", FakeClient)

    data = await client.fetch_process_data("0001234-56.2023.8.15.0001", grau=1)

    assert data["classe"] == "Procedimento Comum Cível"
    assert data["tribunal"] == "TJPB"


@pytest.mark.asyncio
async def test_fetch_with_api_key_falls_back_to_mock_on_http_error(monkeypatch):
    client = DataJudClient()
    client.api_key = "test-key"

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            raise ConnectionError("API indisponível")

    monkeypatch.setattr("app.services.datajud_client.httpx.AsyncClient", FailingClient)

    data = await client.fetch_process_data("0001234-56.2023.8.15.0001", grau=1)

    assert data["numeroProcesso"] == "0001234-56.2023.8.15.0001"
    assert data["tribunal"] == "TJPB"
    assert len(data["movimentacoes"]) > 0


def test_tribunais_map_contains_expected_aliases():
    assert TRIBUNAIS_MAP["8.15"][2] == "tjpb"
    assert TRIBUNAIS_MAP["8.26"][2] == "tjsp"


@pytest.mark.asyncio
async def test_datajud_client_reuses_shared_http_client(monkeypatch):
    """
    Garante que múltiplas chamadas HTTP reutilizam o mesmo AsyncClient,
    evitando abrir conexões TCP a cada requisição ao DataJud.
    """
    from app.services import datajud_client as mod

    mod._module_http_client = None
    created_clients: list[object] = []

    class TrackingClient:
        is_closed = False

        def __init__(self, *args, **kwargs):
            created_clients.append(self)

        async def post(self, url, headers=None, json=None):
            class FakeResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"hits": {"hits": []}}

            return FakeResponse()

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr("app.services.datajud_client.httpx.AsyncClient", TrackingClient)

    client = DataJudClient()
    client.api_key = "test-key"

    await client.fetch_process_data("0001234-56.2023.8.15.0001", grau=1)
    await client.fetch_process_data("0005678-90.2023.8.26.0001", grau=1)

    assert len(created_clients) == 1
