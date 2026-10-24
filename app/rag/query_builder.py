"""
rag/query_builder.py
-----------------------
Turns an Intent + the AtomicFacts relevant to it into structured metadata
filters for retriever.py (spec section 11, steps 4-6: "Build atomic facts
-> เลือก fact families ที่เกี่ยวข้องกับ topic mapping -> สร้าง metadata filters").

Replaces the legacy pattern of hand-formatting chunk ids like
f"house-{house_no}" / f"zodiac-{sign}" scattered through rag_service.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import AtomicFact, Intent


@dataclass
class RetrievalQuery:
    text: str
    topics: list[str] = field(default_factory=list)
    metadata_filters: dict[str, object] = field(default_factory=dict)
    fact_ids: list[str] = field(default_factory=list)


# Which AtomicFact.fact_type values are relevant to each Topic. This is the
# structured replacement for the old ad-hoc if/elif dispatch in chat.py.
_TOPIC_FACT_FAMILIES: dict[str, list[str]] = {
    "love": ["planet_in_house", "planet_sign", "house_lord", "transit_relation", "planet_relationship"],
    "career": ["planet_in_house", "planet_sign", "house_lord", "planet_dignity"],
    "finance": ["planet_in_house", "planet_sign", "house_lord", "planet_dignity"],
    "health": ["planet_in_house", "planet_sign", "house_lord", "taksa_role"],
    "family": ["planet_in_house", "planet_sign", "house_lord"],
    "travel": ["planet_in_house", "planet_sign", "transit_position", "transit_relation"],
    "overview": ["ascendant_sign", "planet_in_house", "planet_sign", "house_lord", "taksa_role"],
}


def build_query(question: str, intent: Intent, facts: list[AtomicFact]) -> RetrievalQuery:
    relevant_types = set(_TOPIC_FACT_FAMILIES.get(intent.topic.value, []))
    relevant_facts = [f for f in facts if f.fact_type in relevant_types] if relevant_types else facts

    filters: dict[str, object] = {"tradition": "thai_astrology", "topics": [intent.topic.value]}
    planets = {f.attributes.get("planet") for f in relevant_facts if f.attributes.get("planet")}
    houses = {f.attributes.get("house") for f in relevant_facts if f.attributes.get("house")}
    if planets:
        filters["entities.planet"] = sorted(planets)
    if houses:
        filters["entities.house"] = sorted(houses)

    return RetrievalQuery(
        text=question,
        topics=[intent.topic.value],
        metadata_filters=filters,
        fact_ids=[f.fact_id() for f in relevant_facts],
    )
