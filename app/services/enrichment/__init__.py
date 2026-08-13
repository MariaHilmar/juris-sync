"""Enriquecimento local de payload DataJud (não é RAG de produção).

Normaliza classe, assunto e tribunal com um glossário em memória e
similaridade lexical. Não usa embeddings de modelo nem banco vetorial.
"""

from app.services.enrichment.enricher import DataJudEnricher
from app.services.enrichment.glossary_index import InMemoryGlossaryIndex

__all__ = ["DataJudEnricher", "InMemoryGlossaryIndex"]
