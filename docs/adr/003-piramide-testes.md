# ADR-003: Pirâmide de testes em cinco camadas

## Status

Aceito

## Contexto

O valor do portfólio não é só o endpoint. É provar que sync, contrato e dados
não mentem. Uma suíte só de happy path na API deixaria RN de idempotência e
OpenAPI sem rede de segurança.

## Decisão

Cinco camadas, com cobertura mínima de 85% na suíte padrão:

1. Unitário / schemas (Pydantic, regras isoladas)
2. API ASGI (httpx contra FastAPI)
3. Mock HTTP da origem (respx) + reconciliação
4. Integração com PostgreSQL real (Testcontainers)
5. Contrato OpenAPI (Schemathesis)

A suíte padrão no CI exclui `integration` e `contract` por marcador; jobs
separados rodam essas camadas.

## Consequências

- Refatorações de sync quebram testes antes de quebrar o dashboard.
- Fuzzing OpenAPI pega drift de schema (`response_model` em `/stats`, datas UTC).
- Integração Postgres é mais lenta e fica em job próprio.
