# ADR-002: Idempotência incremental no sync

## Status

Aceito

## Contexto

Re-sincronizar o mesmo processo é o caminho feliz (atualizar andamentos).
Inserir de novo o processo ou as movimentações já vistas quebraria jurimetria
e a confiança no histórico local.

## Decisão

- Processo: upsert por `numero_cnj` (único).
- Movimentação: identidade `(data_hora em UTC, descricao)`. Só entra o que ainda não existe.
- Pipeline atômico: qualquer falha faz rollback da transação.

## Consequências

- Re-sync do mesmo CNJ não duplica linhas.
- Andamentos novos na origem entram de forma incremental.
- Testes de reconciliação podem afirmar "espelho fiel da fonte".
