import math
import re
from collections import Counter

from app.services.rag.knowledge_base import LEGAL_KNOWLEDGE_BASE, KnowledgeChunk


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9áàâãéêíóôõúç]+", text.lower())
    return [token for token in tokens if len(token) > 2]


def _embed(text: str) -> dict[str, float]:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = float(len(tokens))
    return {token: count / total for token, count in counts.items()}


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    shared_keys = set(left) | set(right)
    dot_product = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in shared_keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot_product / (left_norm * right_norm)


class InMemoryVectorStore:
    def __init__(self, chunks: list[KnowledgeChunk] | None = None):
        self._chunks = chunks or LEGAL_KNOWLEDGE_BASE
        self._embeddings = {
            chunk.id: _embed(" ".join([chunk.texto, *chunk.termos_chave]))
            for chunk in self._chunks
        }

    def search(self, query: str, top_k: int = 3) -> list[tuple[KnowledgeChunk, float]]:
        query_embedding = _embed(query)
        scored: list[tuple[KnowledgeChunk, float]] = []

        for chunk in self._chunks:
            score = _cosine_similarity(query_embedding, self._embeddings[chunk.id])
            keyword_bonus = sum(
                0.15 for term in chunk.termos_chave if term in query.lower()
            )
            scored.append((chunk, score + keyword_bonus))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [item for item in scored[:top_k] if item[1] > 0]
