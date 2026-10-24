"""
rag/citations.py
-------------------
Builds the `source_ids` the API/UI displays per spec section 13/19
("UI/API แสดงแหล่งอ้างอิงของหลักพยากรณ์") and formats a citation for a
retrieved chunk from its ChunkSource fields (title/author/edition/chapter/
page/url) so the frontend can render a real bibliographic reference instead
of just a raw id.
"""

from __future__ import annotations

from .retriever import RetrievedChunk


def source_ids_for(chunks: list[RetrievedChunk]) -> list[str]:
    return [c.chunk_id for c in chunks]


def format_citation(chunk: RetrievedChunk) -> str:
    """Best-effort human-readable citation. Falls back to title-only until
    the knowledge base is migrated to carry full ChunkSource metadata
    (see retriever.py STATUS note)."""
    return chunk.title
