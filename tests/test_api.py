import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_health_endpoint(api_client: AsyncClient):
    """Testa que o endpoint de saúde /health está online e respondendo status healthy."""
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["database"] == "healthy"


@pytest.mark.asyncio
async def test_api_sync_process_endpoint(api_client: AsyncClient):
    """Testa o endpoint de sincronização via POST."""
    cnj = "0004444-11.2023.8.26.0001"

    response = await api_client.post(
        "/api/v1/processos/sync", json={"numero_cnj": cnj, "grau": 1}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["sucesso"] is True
    assert data["processo"]["numero_cnj"] == cnj
    assert data["processo"]["tribunal"] == "TJSP"
    assert data["movimentacoes_sincronizadas"] > 0


@pytest.mark.asyncio
async def test_api_sync_invalid_cnj_returns_422(api_client: AsyncClient):
    """Testa que o validador do Pydantic rejeita números de processo fora do padrão CNJ."""
    response = await api_client.post(
        "/api/v1/processos/sync", json={"numero_cnj": "invalid-cnj-number", "grau": 1}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_list_and_detail_processes(api_client: AsyncClient):
    """Testa a listagem e detalhamento de processos sincronizados."""
    cnj_1 = "0101111-22.2023.8.15.0001"  # TJPB
    cnj_2 = "0202222-33.2023.8.19.0001"  # TJRJ

    # Sincroniza dois processos para ter massa de dados
    await api_client.post("/api/v1/processos/sync", json={"numero_cnj": cnj_1})
    await api_client.post("/api/v1/processos/sync", json={"numero_cnj": cnj_2})

    # 1. Testa Listagem Geral
    list_response = await api_client.get("/api/v1/processos/")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] >= 2
    assert len(list_data["items"]) >= 2
    assert list_data["limit"] == 20
    assert list_data["offset"] == 0

    # 2. Testa Listagem com Filtro por Tribunal
    list_filtered = await api_client.get("/api/v1/processos/?tribunal=TJPB")
    assert list_filtered.status_code == 200
    filtered_data = list_filtered.json()
    assert all(p["tribunal"] == "TJPB" for p in filtered_data["items"])

    # 3. Testa Detalhe de Processo Específico
    proc_id = list_data["items"][0]["id"]
    detail_response = await api_client.get(f"/api/v1/processos/{proc_id}")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()
    assert detail_data["id"] == proc_id
    assert len(detail_data["movimentacoes"]) > 0


@pytest.mark.asyncio
async def test_api_detail_returns_404_for_not_found(api_client: AsyncClient):
    """Testa retorno 404 para detalhe de processo com UUID inexistente."""
    fake_id = uuid.uuid4()
    response = await api_client.get(f"/api/v1/processos/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_jurimetria_stats_endpoints(api_client: AsyncClient):
    """Testa os endpoints de Jurimetria e Métricas Estatísticas."""
    # Sincroniza processos de tribunais diferentes
    await api_client.post(
        "/api/v1/processos/sync", json={"numero_cnj": "0001111-11.2023.8.15.0001"}
    )  # TJPB
    await api_client.post(
        "/api/v1/processos/sync", json={"numero_cnj": "0002222-22.2023.8.15.0002"}
    )  # TJPB
    await api_client.post(
        "/api/v1/processos/sync", json={"numero_cnj": "0003333-33.2023.8.26.0001"}
    )  # TJSP

    # 1. Estatísticas por Tribunal
    stats_tribunal = await api_client.get("/api/v1/processos/stats/por-tribunal")
    assert stats_tribunal.status_code == 200
    data_tribunal = stats_tribunal.json()

    # Deve conter registros de TJPB e TJSP
    tribunais = [item["tribunal"] for item in data_tribunal]
    assert "TJPB" in tribunais
    assert "TJSP" in tribunais

    # O TJPB deve possuir mais processos cadastrados na estatística
    tjpb_stat = next(item for item in data_tribunal if item["tribunal"] == "TJPB")
    assert tjpb_stat["total_processos"] >= 2

    # 2. Estatísticas por Assunto
    stats_assunto = await api_client.get("/api/v1/processos/stats/por-assunto")
    assert stats_assunto.status_code == 200
    data_assunto = stats_assunto.json()
    assert len(data_assunto) > 0
    assert "total_processos" in data_assunto[0]
