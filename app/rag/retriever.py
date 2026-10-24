"""
rag/retriever.py
-------------------
Hybrid-retrieval entry point (spec section 10-11: "แนะนำ hybrid retrieval:
metadata filtering + keyword/BM25 + vector similarity + reranker").

STATUS: metadata filtering + vector similarity via the existing
ChromaRetriever (kept as-is, see retriever_chroma.py). BM25/keyword search
and the entities/topics/conditions-rich filtering described in spec
section 10 are NOT implemented yet — the underlying Chroma collection
still only carries {title, number, domain} metadata (see ingest.py), not
the full KnowledgeChunk schema. Re-ingesting the knowledge base with the
new schema is a prerequisite; tracked as its own follow-up, not a
"guessed formula" so it doesn't block the rest of this scaffold.

This module exposes the target interface now so callers (query_builder ->
retriever -> reranker -> citations) can be wired up; `retrieve()` degrades
gracefully to vector-only search against current metadata until the
knowledge base is migrated.
"""

from __future__ import annotations

from dataclasses import dataclass

from .query_builder import RetrievalQuery
from .retriever_chroma import ChromaRetriever, Chunk


@dataclass
class RetrievedChunk:
    chunk_id: str
    title: str
    content: str
    similarity: float
    metadata: dict


class Retriever:
    def __init__(self, chroma: ChromaRetriever | None = None):
        self._chroma = chroma  # lazy-created by caller to avoid import-time GeminiEmbedder cost

    def retrieve(self, query: RetrievalQuery, top_k: int = 4) -> list[RetrievedChunk]:
        if self._chroma is None:
            self._chroma = ChromaRetriever()

        exclude_domains = None  # TODO(topics->domain mapping) once chunks carry `topics`
        pairs = self._chroma.retrieve(query.text, top_k=top_k, exclude_domains=exclude_domains)
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                title=chunk.title,
                content=chunk.text,
                similarity=score,
                metadata={"number": chunk.number},
            )
            for chunk, score in pairs
        ]

    def get_by_fact_ids(self, ids: list[str]) -> list[RetrievedChunk]:
        """Direct-id retrieval bypass, matching legacy behaviour where the
        calculation layer already knows exactly which chunk id it wants
        (e.g. house-3, zodiac-สิงห์)."""
        if self._chroma is None:
            self._chroma = ChromaRetriever()
        chunks: list[Chunk] = self._chroma.get_by_ids(ids)
        return [
            RetrievedChunk(
                chunk_id=c.id, title=c.title, content=c.text, similarity=1.0,
                metadata={"number": c.number},
            )
            for c in chunks
        ]
