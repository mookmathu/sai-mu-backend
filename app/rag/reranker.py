"""
rag/reranker.py
------------------
Spec section 11, step 8: "rerank โดยให้ exact structured match มีน้ำหนักสูงกว่า
semantic similarity". Boosts chunks whose id/metadata exactly matches one of
the query's fact_ids over pure vector-similarity ranking.
"""

from __future__ import annotations

from .query_builder import RetrievalQuery
from .retriever import RetrievedChunk

_EXACT_MATCH_BOOST = 0.5


def rerank(query: RetrievalQuery, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    fact_id_set = set(query.fact_ids)

    def score(c: RetrievedChunk) -> float:
        boost = _EXACT_MATCH_BOOST if c.chunk_id in fact_id_set else 0.0
        return c.similarity + boost

    return sorted(chunks, key=score, reverse=True)


def deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    out: list[RetrievedChunk] = []
    for c in chunks:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        out.append(c)
    return out
