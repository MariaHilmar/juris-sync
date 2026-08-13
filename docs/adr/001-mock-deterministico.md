# ADR-001: Mock determinístico do DataJud

## Status

Aceito

## Contexto

A API Pública do DataJud exige chave. Quem avalia o portfólio (e o CI) precisa
clonar e rodar sem credencial do CNJ. Dados inventados não podem variar a cada
execução, senão testes de jurimetria e reconciliação ficam flaky.

## Decisão

Sem `DATAJUD_API_KEY`, o cliente gera payload a partir do próprio número CNJ
(`random.Random(numero_cnj)`). Em `ENV=production`, falha real **não** cai para
mock: propaga o erro.

## Consequências

- Demo local e CI não dependem do CNJ.
- O mesmo CNJ sempre produz a mesma classe/assunto/movimentações-base.
- Em produção, 404/timeout do DataJud aparecem como erro HTTP, não como processo fictício.
