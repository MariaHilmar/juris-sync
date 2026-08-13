# ADR-004: Enriquecimento por glossário, não RAG de produção

## Status

Aceito

## Contexto

A pasta `app/services/rag/` sugeria Retrieval-Augmented Generation (embeddings,
banco vetorial, geração de resposta). O código real canonicaliza classe, assunto
e tribunal com um glossário em memória e similaridade lexical. O nome inflado
enfraquecia a leitura técnica do portfólio.

JWT (`SECRET_KEY`) existe na config, mas não há login. Deixar isso implícito
também infla o produto.

## Decisão

- Pacote `app/services/enrichment/`: `DataJudEnricher` + `InMemoryGlossaryIndex`.
- Campo `contexto_enriquecimento` no schema interno e na resposta de sync.
- LLM opcional (`OPENAI_API_KEY`) só polimento de campos; falha não aborta o sync.
- Auth de usuário final permanece **fora de escopo** (documentado). `SECRET_KEY`
  não autentica nenhum endpoint.

## Consequências

- Recrutador lê o que o código faz.
- Evoluir para RAG de verdade (pgvector, embeddings) seria um ADR novo, não um rename.
- Dashboard pode ignorar `contexto_enriquecimento`; campo extra não quebra clientes.
