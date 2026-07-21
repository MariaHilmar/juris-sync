# Documentação Técnica e Funcional - JurisSync API

> Este documento complementa o [README.md](../README.md) (visão geral, stack, execução) com a análise de requisitos do sistema: domínio, regras de negócio, histórias de usuário, critérios de aceite e cenários BDD. Foi elaborado a partir da análise do código-fonte real (`app/`), migrations (`alembic/`) e suíte de testes (`tests/`) existentes, mantendo os mesmos termos e nomenclaturas já usados no projeto.

---

## Índice

1. [Visão do produto](#1-visão-do-produto)
2. [Glossário de domínio](#2-glossário-de-domínio)
3. [Atores e integrações](#3-atores-e-integrações)
4. [Regras de negócio](#4-regras-de-negócio)
5. [Histórias de usuário](#5-histórias-de-usuário)
6. [Cenários BDD (Gherkin)](#6-cenários-bdd-gherkin)
7. [Regras de validação de dados](#7-regras-de-validação-de-dados)
8. [Requisitos não funcionais](#8-requisitos-não-funcionais)
9. [Rastreabilidade requisito -> código -> teste](#9-rastreabilidade-requisito---código---teste)
10. [Metodologia de desenvolvimento](#10-metodologia-de-desenvolvimento)

---

## 1. Visão do produto

O **JurisSync** é uma API que sincroniza processos judiciais brasileiros com a **API Pública do DataJud (CNJ)**, enriquece os dados com contexto jurídico (RAG) e os disponibiliza localmente para consulta e análise de Jurimetria (distribuição de processos por tribunal e por assunto).

**Problema que resolve:** acompanhar processos judiciais exige consultar tribunais individualmente ou a API do DataJud repetidamente. O JurisSync centraliza, normaliza e mantém um histórico local consultável, evitando duplicidade de dados e permitindo análise agregada.

**Fora de escopo (não implementado):** autenticação/autorização de usuários finais (o `SECRET_KEY`/JWT existe na configuração mas não há endpoints de login), notificações de mudança de andamento, edição manual de processos, suporte a instâncias além de 1º, 2º e 3º grau.

---

## 2. Glossário de domínio

| Termo | Definição |
|---|---|
| **Número CNJ** | Identificador único de processo judicial no padrão nacional `NNNNNNN-DD.AAAA.J.TR.OOOO` (Resolução CNJ 65/2008) |
| **Processo** | Entidade central: uma ação judicial identificada por número CNJ, com classe, assunto, tribunal e grau |
| **Movimentação** | Um andamento/evento no histórico do processo (ex: "Distribuído por Sorteio"), com data/hora e descrição |
| **Grau de jurisdição** | Instância do processo: 1 (primeira instância), 2 (recurso/segunda instância) ou 3 (tribunais superiores) |
| **Sincronização (sync)** | Operação que busca o estado atual de um processo na fonte externa (DataJud ou mock) e reconcilia com o banco local |
| **DataJud** | API pública do CNJ que expõe dados processuais de tribunais brasileiros |
| **Modo mock** | Quando `DATAJUD_API_KEY` não está configurada (ou a chamada real falha), o sistema gera dados determinísticos e plausíveis a partir do próprio número CNJ |
| **RAG (Retrieval-Augmented Generation)** | Camada que recupera trechos de uma base de conhecimento jurídico em memória e usa esse contexto para normalizar/canonicalizar campos como classe, assunto e tribunal |
| **Jurimetria** | Análise estatística agregada dos processos armazenados (contagem por tribunal, por assunto) |
| **Idempotência** | Propriedade pela qual sincronizar o mesmo processo múltiplas vezes não gera duplicatas |
| **Reconciliação** | Processo de garantir que o dado local seja fiel (sem duplicar, sem perder, sem órfãos) ao dado da fonte externa |

---

## 3. Atores e integrações

| Ator | Tipo | Interação |
|---|---|---|
| **Cliente da API** | Ator humano/sistema | Consome os endpoints REST (`/api/v1/processos/*`, `/health`) |
| **API Pública DataJud (CNJ)** | Sistema externo | Fonte de dados processuais reais, consultada via HTTPS quando `DATAJUD_API_KEY` está configurada |
| **Motor de Mock** | Componente interno | Substitui o DataJud quando não há chave configurada ou quando a chamada real falha (fallback automático) |
| **LLM externo (OpenAI-compatível)** | Sistema externo opcional | Refina classe/assunto/tribunal via chat completion, apenas se `OPENAI_API_KEY` estiver configurada |
| **Banco de dados** | Infraestrutura | PostgreSQL (produção) ou SQLite (desenvolvimento/testes) via SQLAlchemy async |

Não há autenticação de usuário final nos endpoints hoje - qualquer cliente com acesso de rede à API pode chamar todos os endpoints.

---

## 4. Regras de negócio

As regras abaixo foram extraídas do comportamento real implementado em `app/services/sync_service.py`, `app/services/datajud_client.py`, `app/services/rag/enricher.py` e `app/api/process.py`.

### RN01 - Unicidade do processo por número CNJ
Cada processo é identificado de forma única pelo `numero_cnj` (constraint `UNIQUE` no banco). Não pode existir mais de um registro de `Processo` com o mesmo número CNJ.
> Código: `app/models/process.py` (`unique=True` em `numero_cnj`); migração `6f9ff010efb1`.

### RN02 - Sincronização é upsert (criar ou atualizar)
Ao sincronizar um número CNJ:
- Se **não existe** processo local com esse CNJ -> **cria** um novo registro.
- Se **já existe** -> **atualiza** `classe`, `assunto`, `orgao_julgador`, `grau` e `data_ultima_atualizacao` com os dados mais recentes da fonte.
> Código: `JurisSyncService.sync_process` (`app/services/sync_service.py`, linhas 60-83).

### RN03 - Movimentações são inseridas apenas se novas (idempotência incremental)
Uma movimentação é considerada "já existente" se a combinação `(data_hora, descricao)` já está persistida para aquele processo. Apenas movimentações com essa combinação **inédita** são inseridas. Re-sincronizar os mesmos dados não duplica nada.
> Código: `JurisSyncService.sync_process`, construção de `existing_set` e comparação por `key` (linhas 94-118).

### RN04 - Pipeline de sincronização é atômico (tudo ou nada)
O pipeline segue a ordem: **Extração (DataJud/mock) -> Enriquecimento RAG -> Validação Pydantic -> Persistência**. Se qualquer etapa falhar, a transação é revertida (`rollback`) e nenhum dado parcial (nem o processo, nem movimentações) é persistido.
> Código: bloco `try/except` com `await self.db.rollback()` em caso de erro (linhas 150-153); validado por `tests/test_sync_reconciliation.py::test_reconciliation_rolls_back_completely_on_partial_failure`.

### RN05 - Fallback automático para modo mock
Se `DATAJUD_API_KEY` não estiver configurada, **ou** se a chamada HTTP real ao DataJud falhar por qualquer motivo (timeout, 5xx, tribunal não encontrado, hits vazios), o sistema gera dados mock determinísticos a partir do número CNJ, sem interromper o fluxo do usuário.
> Código: `DataJudClient.fetch_process_data` (`app/services/datajud_client.py`, linhas 62-84).

### RN06 - Determinismo do mock por número CNJ
O gerador de mock usa o próprio número CNJ como seed (`random.seed(numero_cnj)`), garantindo que múltiplas chamadas para o mesmo CNJ produzam sempre a mesma classe, assunto e conjunto de movimentações-base. O ano de distribuição é extraído do segmento `AAAA` do CNJ (protegido para permanecer entre 1900-2100).
> Código: `DataJudClient._generate_mock_data` (linhas 189-248).

### RN07 - Resolução de tribunal pelo segmento J.TR do CNJ
O tribunal (sigla, nome e alias de API) é determinado pelos segmentos `J` (justiça) e `TR` (tribunal) do número CNJ, consultando o mapa `TRIBUNAIS_MAP`. Se o segmento não estiver mapeado, uma chamada real à API é rejeitada com erro; no mock, o tribunal cai para `TJSP` como padrão.
> Código: `DataJudClient._resolve_tribunal_alias`, `_tribunal_sigla_from_cnj` (linhas 120-131, 180-187).

### RN08 - Enriquecimento RAG antes da validação estrita
Antes de validar os dados com o schema Pydantic (`DataJudProcessoSchema`), o sistema recupera até `RAG_TOP_K` (padrão: 3) trechos de conhecimento jurídico relevantes e usa esse contexto para: (a) corrigir o tribunal quando a sigla informada é inválida, (b) canonicalizar `classe` e `assunto` para os termos padronizados da base de conhecimento.
> Código: `JurisSyncService.sync_process` (linhas 44-53); `DataJudRAGEnricher.enrich` (`app/services/rag/enricher.py`).

### RN09 - Refinamento opcional via LLM
Se `OPENAI_API_KEY` estiver configurada, uma chamada adicional a um endpoint compatível com OpenAI Chat Completions tenta refinar `classe`, `assunto` e `tribunal` usando o contexto RAG recuperado. Falhas nessa etapa são **toleradas** (log de warning) e não interrompem a sincronização - o dado normalizado pela regra RN08 permanece válido.
> Código: `DataJudRAGEnricher._llm_refine` (linhas 176-221).

### RN10 - Grau de jurisdição restrito a 1, 2 ou 3
O campo `grau` só aceita os valores 1 (primeira instância), 2 ou 3 (instâncias superiores/recursais). Qualquer valor fora desse intervalo é rejeitado na validação de entrada.
> Código: `Field(1, ge=1, le=3, ...)` em `ProcessoBase` e `ProcessoSyncRequest` (`app/schemas/process.py`).

### RN11 - Exclusão em cascata de movimentações
Se um processo for removido, todas as suas movimentações são removidas automaticamente (`ON DELETE CASCADE` no banco e `cascade="all, delete-orphan"` no ORM). Não é permitido existir uma movimentação "órfã" sem processo associado.
> Código: `app/models/process.py` (relationship `cascade`); migração (`ondelete='CASCADE'`).

### RN12 - Ordenação padrão de listagem e movimentações
- A listagem de processos (`GET /processos/`) é ordenada por `data_ultima_atualizacao` decrescente (mais recentes primeiro).
- As movimentações de um processo são sempre ordenadas por `data_hora` decrescente (andamento mais recente primeiro).
> Código: `app/api/process.py` (`order_by(desc(...))`); `app/models/process.py` (`order_by="desc(Movimentacao.data_hora)"`).

### RN13 - Filtros de listagem são opcionais e combináveis
A listagem de processos aceita filtro exato por `tribunal` (case-insensitive, normalizado para maiúsculas) e filtro parcial por `classe` (`ILIKE`), podendo ser usados isoladamente ou em conjunto. Sem filtros, retorna todos os processos (paginados).
> Código: `app/api/process.py`, função `listar_processos` (linhas 65-102).

### RN14 - Paginação obrigatória e limitada
A listagem sempre é paginada: `limit` entre 1 e 100 (padrão 20), `offset` entre 0 e 1.000.000 (padrão 0). Esses limites evitam sobrecarga de resposta e proteção contra valores extremos que quebrariam o driver do banco. A resposta inclui metadados de paginação: `items` (página atual), `total` (registros que atendem aos filtros), `limit` e `offset`.
> Código: `app/api/process.py` (`Query(20, ge=1, le=100, ...)`, `Query(0, ge=0, le=1_000_000, ...)`); schema `ProcessoListResponse` em `app/schemas/process.py`.

### RN15 - Jurimetria é sempre sobre a base local
Os endpoints de estatística (`/stats/por-tribunal`, `/stats/por-assunto`) agregam **somente** os processos já sincronizados e persistidos localmente - não consultam o DataJud em tempo real. Assuntos nulos são exibidos como "Não Informado".
> Código: `app/api/process.py`, funções `estatisticas_por_tribunal` e `estatisticas_por_assunto`.

### RN16 - Health check reflete dependências reais
O endpoint `/health` executa uma consulta real (`SELECT 1`) no banco para determinar `database: healthy/unhealthy`, e reporta `datajud_api: configured` (se há `DATAJUD_API_KEY`) ou `mock_mode` (se não há). O status geral é `healthy` apenas se o banco estiver saudável; caso contrário, `degraded`.
> Código: `app/main.py`, função `health_check` (linhas 45-69).

---

## 5. Histórias de usuário

Formato: `Como <ator>, quero <ação>, para <benefício>`, com critérios de aceite testáveis.

### US01 - Sincronizar um processo judicial

**Como** integrador de sistemas jurídicos,
**quero** sincronizar um processo pelo número CNJ,
**para** manter uma cópia local atualizada do andamento processual sem depender de consultas repetidas ao DataJud.

**Critérios de aceite:**
- Dado um número CNJ válido e inédito, ao sincronizar, um novo processo é criado e todas as movimentações da fonte são persistidas.
- Dado um número CNJ já sincronizado anteriormente, ao sincronizar novamente sem mudanças na fonte, nenhuma movimentação nova é criada (idempotência).
- Dado um número CNJ já sincronizado, se a fonte retornar novas movimentações, apenas as movimentações inéditas são adicionadas.
- Dado um número CNJ em formato inválido, a API responde `422 Unprocessable Entity` sem persistir nada.
- A resposta de sucesso informa se o processo foi criado ou atualizado, e quantas movimentações novas foram sincronizadas.

### US02 - Consultar processos sem credenciais do DataJud

**Como** desenvolvedor integrando com o JurisSync em ambiente local,
**quero** sincronizar processos mesmo sem uma chave de API do DataJud,
**para** desenvolver e testar a integração sem depender de credenciais externas.

**Critérios de aceite:**
- Sem `DATAJUD_API_KEY` configurada, a sincronização usa dados mock determinísticos e plausíveis, sem erro.
- O mock retorna sempre os mesmos dados-base para o mesmo número CNJ.
- O tribunal do processo mock corresponde ao segmento `J.TR` informado no CNJ, quando reconhecido.

### US03 - Resiliência a falhas do DataJud

**Como** operador da API em produção,
**quero** que falhas temporárias do DataJud não interrompam a sincronização,
**para** manter a disponibilidade do serviço mesmo com instabilidade externa.

**Critérios de aceite:**
- Se a API do DataJud retornar erro 5xx, timeout, ou nenhum resultado (`hits` vazio), o sistema recorre automaticamente ao mock e a sincronização é concluída com sucesso.
- A falha da chamada externa é registrada em log, mas não é exposta como erro ao cliente da API.

### US04 - Listar processos com filtros

**Como** analista jurídico,
**quero** listar os processos sincronizados filtrando por tribunal e/ou classe,
**para** localizar rapidamente processos de interesse dentro da base local.

**Critérios de aceite:**
- Sem filtros, a listagem retorna processos paginados, ordenados do mais recentemente atualizado para o mais antigo.
- Filtrar por `tribunal=TJSP` retorna apenas processos daquele tribunal, com correspondência exata (case-insensitive).
- Filtrar por `classe=dano moral` retorna processos cuja classe contenha esse texto, parcialmente e sem diferenciar maiúsculas/minúsculas.
- Parâmetros `limit` e `offset` controlam a paginação, com limites de segurança (`limit` até 100, `offset` até 1.000.000).

### US05 - Consultar detalhes e histórico de um processo

**Como** analista jurídico,
**quero** ver a ficha completa de um processo com todas as suas movimentações,
**para** entender a evolução completa do caso.

**Critérios de aceite:**
- Dado o ID de um processo existente, a API retorna seus dados e a lista de movimentações ordenada da mais recente para a mais antiga.
- Dado um ID que não existe na base, a API retorna `404 Not Found` com mensagem explicativa.

### US06 - Analisar Jurimetria básica

**Como** gestor/analista de dados jurídicos,
**quero** ver a distribuição de processos por tribunal e por assunto,
**para** identificar concentrações e tendências na carteira de processos monitorados.

**Critérios de aceite:**
- O endpoint de distribuição por tribunal retorna a contagem de processos agrupada por tribunal, ordenada da maior para a menor contagem.
- O endpoint de distribuição por assunto agrupa por assunto, exibindo "Não Informado" quando o assunto é nulo.
- Ambos os endpoentes refletem apenas dados já sincronizados localmente (sem chamar o DataJud).

### US07 - Verificar a saúde do sistema

**Como** operador de infraestrutura (SRE/DevOps),
**quero** consultar um endpoint de health check,
**para** monitorar automaticamente a disponibilidade da API e de suas dependências.

**Critérios de aceite:**
- O endpoint `/health` retorna o status geral (`healthy`/`degraded`), o status do banco de dados e o modo de operação do DataJud (`configured`/`mock_mode`).
- Se o banco estiver inacessível, o status geral é `degraded` e o status do banco é `unhealthy`, sem a API cair.

### US08 - Enriquecimento semântico dos dados processuais

**Como** consumidor dos dados sincronizados,
**quero** que classe, assunto e tribunal estejam normalizados para termos padronizados,
**para** conseguir agregar e comparar processos de fontes/tribunais diferentes de forma consistente.

**Critérios de aceite:**
- Dada uma classe processual com variações textuais (ex.: "execução" em qualquer caixa), o sistema a canonicaliza para o termo padrão da base de conhecimento (ex.: "Execução de Título Extrajudicial").
- Dado um tribunal inválido/ausente na origem, mas identificável pelo CNJ, o sistema corrige o tribunal automaticamente.
- O contexto jurídico recuperado (trechos usados na normalização) é exposto na resposta de sincronização (`contexto_rag`).

---

## 6. Cenários BDD (Gherkin)

Os cenários abaixo espelham o comportamento já coberto pela suíte automatizada (`tests/`), servindo como especificação executável e como referência para a rastreabilidade da seção 9.

```gherkin
Funcionalidade: Sincronização de processos judiciais
  Como integrador de sistemas jurídicos
  Quero sincronizar processos pelo número CNJ
  Para manter uma cópia local atualizada e idempotente

  Contexto:
    Dado que a API JurisSync está em execução
    E o banco de dados local está vazio para o número CNJ em teste

  Cenário: Sincronizar um processo inédito
    Dado um número CNJ válido "0801234-56.2023.8.15.0001" ainda não sincronizado
    Quando eu solicitar a sincronização desse processo com grau 1
    Então a resposta deve indicar sucesso
    E um novo processo deve ser criado na base local
    E o tribunal do processo criado deve ser "TJPB"
    E ao menos uma movimentação deve ter sido sincronizada

  Cenário: Re-sincronizar um processo sem alterações na fonte (idempotência)
    Dado um número CNJ "0805555-22.2023.8.26.0001" já sincronizado anteriormente
    Quando eu solicitar a sincronização desse mesmo processo novamente
    Então a resposta deve indicar sucesso
    E nenhuma movimentação nova deve ter sido sincronizada
    E deve existir exatamente um registro de processo para esse número CNJ

  Cenário: Sincronizar um processo com movimentações incrementais
    Dado um número CNJ já sincronizado com apenas as 3 movimentações mais recentes
    Quando a fonte externa passar a retornar o histórico completo de movimentações
    E eu solicitar uma nova sincronização
    Então apenas as movimentações inéditas devem ser adicionadas
    E o total de movimentações persistidas deve ser igual ao total da fonte

  Cenário: Rejeitar número CNJ em formato inválido
    Dado um número CNJ mal formatado "cnj-invalido"
    Quando eu solicitar a sincronização desse processo
    Então a API deve responder com status 422
    E nenhum processo deve ser criado na base local

  Cenário: Reverter completamente a sincronização em caso de falha no pipeline
    Dado um número CNJ inédito "0812347-33.2023.8.26.0005"
    E que o enriquecimento RAG irá falhar durante o processamento
    Quando eu solicitar a sincronização desse processo
    Então a API deve propagar o erro
    E nenhum processo deve ter sido criado na base local
    E nenhuma movimentação nova deve ter sido persistida

  Cenário: Usar dados mock quando não há chave do DataJud configurada
    Dado que a variável DATAJUD_API_KEY não está configurada
    Quando eu solicitar a sincronização de um número CNJ válido
    Então a resposta deve indicar sucesso
    E os dados retornados devem ser gerados de forma determinística a partir do CNJ

  Cenário: Cair para o modo mock quando o DataJud real falha
    Dado que a variável DATAJUD_API_KEY está configurada
    E a API do DataJud responde com erro 500 para o número CNJ solicitado
    Quando eu solicitar a sincronização desse processo
    Então a sincronização deve ser concluída com sucesso usando dados mock
    E o erro da chamada externa deve ser registrado em log, sem ser exposto ao cliente
```

```gherkin
Funcionalidade: Consulta e listagem de processos
  Como analista jurídico
  Quero consultar e filtrar processos sincronizados
  Para localizar informações relevantes rapidamente

  Cenário: Listar processos filtrando por tribunal
    Dado que existem processos sincronizados de tribunais "TJPB" e "TJSP"
    Quando eu listar processos filtrando por tribunal "TJSP"
    Então somente processos do tribunal "TJSP" devem ser retornados

  Cenário: Listar processos filtrando por classe parcial
    Dado que existe um processo com classe "Indenização por Dano Moral"
    Quando eu listar processos filtrando por classe "dano moral"
    Então esse processo deve constar no resultado, independente de maiúsculas/minúsculas

  Cenário: Consultar detalhes de um processo existente
    Dado um processo previamente sincronizado com 5 movimentações
    Quando eu consultar os detalhes desse processo pelo seu ID
    Então devo receber os dados do processo
    E a lista de 5 movimentações ordenada da mais recente para a mais antiga

  Cenário: Consultar um processo inexistente
    Dado um identificador de processo válido, porém não cadastrado
    Quando eu consultar os detalhes desse processo
    Então a API deve responder com status 404
    E uma mensagem informando que o processo não foi encontrado
```

```gherkin
Funcionalidade: Jurimetria básica
  Como gestor de dados jurídicos
  Quero visualizar a distribuição agregada dos processos
  Para identificar padrões e concentrações na carteira monitorada

  Cenário: Distribuição de processos por tribunal
    Dado que existem processos sincronizados de múltiplos tribunais
    Quando eu consultar a distribuição por tribunal
    Então devo receber a contagem de processos agrupada por tribunal
    E o resultado deve estar ordenado do tribunal com mais processos para o com menos

  Cenário: Distribuição de processos por assunto, incluindo assunto ausente
    Dado que existem processos com e sem assunto definido
    Quando eu consultar a distribuição por assunto
    Então processos sem assunto devem ser agrupados como "Não Informado"
```

```gherkin
Funcionalidade: Observabilidade e saúde do sistema
  Como operador de infraestrutura
  Quero monitorar a saúde da API e de suas dependências
  Para agir preventivamente em caso de degradação

  Cenário: Sistema saudável
    Dado que o banco de dados está acessível
    Quando eu consultar o endpoint de health check
    Então o status geral deve ser "healthy"
    E o status do banco deve ser "healthy"

  Cenário: Banco de dados indisponível
    Dado que o banco de dados está inacessível
    Quando eu consultar o endpoint de health check
    Então o status geral deve ser "degraded"
    E o status do banco deve ser "unhealthy"
    E a API não deve retornar erro 5xx para essa consulta
```

---

## 7. Regras de validação de dados

| Campo | Regra | Origem |
|---|---|---|
| `numero_cnj` | Deve seguir exatamente o padrão `NNNNNNN-DD.AAAA.J.TR.OOOO` (dígitos ASCII `0-9`) | `CNJ_PATTERN` em `app/schemas/process.py` |
| `grau` | Inteiro entre 1 e 3 (inclusive) | `Field(..., ge=1, le=3)` |
| `descricao` (movimentação) | Texto não vazio (mínimo 1 caractere) | `MovimentacaoBase.descricao` |
| `tribunal` | String obrigatória; validado contra `TRIBUNAIS_MAP` na resolução via CNJ | `DataJudClient` |
| `limit` (listagem) | Inteiro entre 1 e 100 (padrão 20) | `app/api/process.py` |
| `offset` (listagem) | Inteiro entre 0 e 1.000.000 (padrão 0) | `app/api/process.py` |
| Datas (`data_hora`, `data_distribuicao`, etc.) | Sempre expostas como timezone-aware (UTC) na API, mesmo que persistidas sem timezone no SQLite | `_garantir_utc` em `app/schemas/process.py` |

Essas regras de validação foram, inclusive, endurecidas a partir de achados do **contract testing com Schemathesis** (ver `tests/contract/`): a troca de `\d` (Unicode-aware) por `[0-9]` no padrão do CNJ e o limite superior de `offset` foram correções motivadas por fuzzing automatizado do contrato OpenAPI.

---

## 8. Requisitos não funcionais

| Categoria | Requisito | Evidência no projeto |
|---|---|---|
| **Disponibilidade** | Falhas no provedor externo (DataJud, LLM) não devem indisponibilizar a sincronização | RN05, RN09; fallback automático para mock |
| **Idempotência** | Sincronizações repetidas não geram duplicidade de dados | RN02, RN03; `tests/test_sync_service.py`, `tests/test_sync_reconciliation.py` |
| **Consistência/Atomicidade** | Falha em qualquer etapa do pipeline não deixa dados parciais | RN04 |
| **Observabilidade** | Logs estruturados (JSON em produção, coloridos em dev) para toda operação relevante | `app/core/logging.py`, uso de `structlog` em todos os serviços |
| **Portabilidade de banco** | Deve rodar em SQLite (dev/test) e PostgreSQL (produção) sem alterações de código | `app/core/database.py`; testes de integração com Testcontainers |
| **Documentação de contrato** | A API deve expor um contrato OpenAPI válido e testável automaticamente | Swagger UI (`/docs`), ReDoc (`/redoc`), `tests/contract/` (Schemathesis) |
| **Qualidade de código** | Lint e formatação obrigatórios no CI | Ruff + Black em `.github/workflows/ci.yml` |
| **Cobertura de testes** | Mínimo de 85% de cobertura na suíte unitária/API | `pyproject.toml` (`--cov-fail-under=85`) |
| **Segurança de segredos** | Credenciais nunca versionadas; apenas exemplo vazio (`.env.example`) | `.gitignore`, `.env.example` |

---

## 9. Rastreabilidade requisito -> código -> teste

| Regra/História | Implementação | Teste automatizado |
|---|---|---|
| RN01, RN02 (upsert por CNJ) | `app/services/sync_service.py` | `tests/test_sync_service.py::test_sync_new_process_creates_record` |
| RN03 (idempotência incremental) | `app/services/sync_service.py` | `tests/test_sync_service.py::test_sync_process_is_idempotent`, `test_sync_new_movement_adds_only_the_new_one` |
| RN04 (atomicidade) | `app/services/sync_service.py` (`try/except` + `rollback`) | `tests/test_sync_reconciliation.py::test_reconciliation_rolls_back_completely_on_partial_failure` |
| RN05, US03 (fallback mock) | `app/services/datajud_client.py` | `tests/test_datajud_client_contract.py` (respx: 404, 500, timeout) |
| RN06, US02 (determinismo do mock) | `DataJudClient._generate_mock_data` | `tests/test_datajud_client.py::test_mock_client_generates_consistent_data` |
| RN07 (resolução de tribunal) | `DataJudClient._resolve_tribunal_alias` | `tests/test_datajud_client.py::test_resolve_tribunal_alias_from_cnj` |
| RN08, US08 (enriquecimento RAG) | `app/services/rag/enricher.py` | `tests/test_rag_enricher.py` |
| RN11 (cascade delete) | `app/models/process.py` | `tests/integration/test_sync_service_postgres.py::test_reconciliation_movement_delete_cascade_on_real_postgres` |
| RN12, RN13, RN14, US04 (listagem) | `app/api/process.py::listar_processos` | `tests/test_api.py` |
| US05 (detalhe/404) | `app/api/process.py::obter_processo` | `tests/test_api.py`; `postman/JurisSync.postman_collection.json` (caso 404) |
| RN15, US06 (jurimetria) | `app/api/process.py::estatisticas_*` | `tests/test_api.py` |
| RN16, US07 (health check) | `app/main.py::health_check` | `postman/JurisSync.postman_collection.json` |
| Contrato OpenAPI (seção 7) | `app/schemas/process.py` | `tests/contract/test_openapi_contract.py` (Schemathesis) |
| Reconciliação de dados | `app/services/sync_service.py` | `tests/test_sync_reconciliation.py` |
| Integração com PostgreSQL real | - | `tests/integration/` (Testcontainers) |

---

## 10. Metodologia de desenvolvimento

Este projeto utilizou **ferramentas de IA generativa** sob a metodologia de **Especificação Direcionada (SDD - Specification-Driven Development)**:

1. **Especificação** - requisitos, regras de negócio (RN01-RN16), cenários BDD e histórias de usuário definidos antes ou em paralelo à implementação (este documento).
2. **Geração assistida** - boilerplate, documentação e parte da estrutura acelerados com IA generativa.
3. **Revisão humana** - todo código passou por **code review manual** e revisão automatizada em PRs (Cursor Bugbot, regras em `.cursor/BUGBOT.md`): idempotência de sync, reconciliação, contrato DataJud e atomicidade validados por testes automatizados (43 testes, ~90% de cobertura).
4. **Rastreabilidade** - cada regra referencia arquivo e linha no repositório; a matriz da seção 9 liga requisito → código → teste.

A IA acelerou a produção; a **correção e a coerência** são responsabilidade da revisão humana e da suíte de testes.

---

## Como manter este documento coerente

- Ao alterar uma regra de negócio no código, atualize a seção correspondente aqui **e** o cenário BDD relacionado.
- Ao adicionar um endpoint novo, crie a história de usuário, os critérios de aceite e o cenário Gherkin antes (ou junto) da implementação, quando possível.
- Este documento não substitui o [README.md](../README.md) (setup, stack, execução) nem a [documentação OpenAPI](../README.md#endpoints) (`/docs`, `/redoc`) - ele é a camada de **requisitos e regras de negócio**, enquanto o README cobre a camada **técnica/operacional**.
