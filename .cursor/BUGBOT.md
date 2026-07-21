# JurisSync API - Regras de code review

Projeto de portfólio: API FastAPI para sincronização idempotente de processos judiciais com DataJud (ou mock).

## Prioridades de revisão

1. **Idempotência e reconciliação** - sincronizações repetidas não podem duplicar processos nem movimentações (`RN02`, `RN03`). Verifique `app/services/sync_service.py`.
2. **Atomicidade** - falha em qualquer etapa do pipeline deve fazer rollback completo (`RN04`). Não persistir dados parciais.
3. **Contrato DataJud** - alterações em `datajud_client.py` devem manter fallback para mock quando a chave não está configurada ou a chamada falha (`RN05`, `RN09`).
4. **Validação CNJ** - número CNJ deve seguir o padrão nacional; rejeitar formatos inválidos com 422.
5. **Testes obrigatórios** - toda nova regra de negócio precisa de teste em `tests/` e entrada na matriz de rastreabilidade em `docs/requisitos.md`.
6. **Cobertura** - a suíte padrão não pode ficar abaixo de 85% (`pyproject.toml`).

## Bloquear (bug de severidade alta)

- Inserção de movimentação sem verificar duplicidade `(data_hora, descricao)`.
- `commit` sem `try/except` + `rollback` em operações multi-etapa de sync.
- Remoção ou bypass do fallback mock sem justificativa documentada.
- Credenciais ou chaves de API hardcoded (devem vir de `app/core/config.py` / `.env`).
- Alteração de schema sem migration Alembic correspondente.

## Avisar (melhoria ou risco médio)

- Novo endpoint sem cenário BDD ou história de usuário em `docs/requisitos.md`.
- Mudança em schema Pydantic sem atualizar testes de contrato OpenAPI (`tests/contract/`).
- Uso de `datetime` sem timezone awareness em campos persistidos.
- Log sem contexto estruturado (`structlog`) em fluxos de sync.

## Fora de escopo (não exigir)

- Autenticação de usuários finais (fora de escopo v1).
- Deploy público ou hardening de produção.
