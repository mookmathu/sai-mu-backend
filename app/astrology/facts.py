"""
astrology/facts.py
---------------------
Turns a NatalChart (+ optional TransitSnapshot) into the flat "Atomic
Facts" list defined in spec section 9. This is the ONLY bridge allowed
between the Calculation Engine and the RAG layer — RAG/LLM code must never
read NatalChart fields directly, only AtomicFact objects produced here, so
that every claim in a final answer can be traced to `source="calculation_engine"`
plus this function.

This module does NOT need any unverified formula to run — it only reshapes
whatever the NatalChart already contains, so it is safe to implement fully
now even though several upstream calculators still raise
FormulaNotVerifiedError. As those get implemented, more fact_types will
simply start appearing in the output; no change needed here.
"""

from __future__ import annotations

from app.rag.schemas import AtomicFact

from .schemas import NatalChart, TransitSnapshot


def extract_atomic_facts(chart: NatalChart) -> list[AtomicFact]:
    facts: list[AtomicFact] = []

    if chart.native.ascendant is not None:
        facts.append(
            AtomicFact(
                fact_type="ascendant_sign",
                attributes={"sign": chart.native.ascendant.sign.value},
            )
        )

    for planet in chart.native.planets:
        if planet.house is not None:
            facts.append(
                AtomicFact(
                    fact_type="planet_in_house",
                    attributes={
                        "planet": planet.id.value,
                        "house": planet.house,
                        "sign": planet.sign.value,
                    },
                )
            )
        else:
            # House not assignable yet (no ascendant/house_method) — still
            # emit the sign, which IS verified, as its own fact type rather
            # than fabricating a house number.
            facts.append(
                AtomicFact(
                    fact_type="planet_sign",
                    attributes={"planet": planet.id.value, "sign": planet.sign.value},
                )
            )
        for dignity in planet.dignities:
            facts.append(
                AtomicFact(
                    fact_type="planet_dignity",
                    attributes={"planet": planet.id.value, "dignity": dignity.name},
                )
            )

    for house in chart.native.houses:
        facts.append(
            AtomicFact(
                fact_type="house_lord",
                attributes={"house": house.house, "planet": house.lord.value},
            )
        )

    for rel in chart.native.relationships:
        facts.append(
            AtomicFact(
                fact_type="planet_relationship",
                attributes={
                    "planet_a": rel.planet_a.value,
                    "planet_b": rel.planet_b.value,
                    "relation": rel.relation,
                },
            )
        )

    if chart.native.taksa:
        for entry in chart.native.taksa.entries:
            facts.append(
                AtomicFact(
                    fact_type="taksa_role",
                    attributes={"role": entry.role.value, "planet": entry.ruling_planet.value},
                )
            )

    for entry in chart.native.maha_taksa:
        facts.append(
            AtomicFact(
                fact_type="maha_taksa_period",
                attributes={
                    "period_label": entry.period_label,
                    "planet": entry.ruling_planet.value,
                    "starts_on": str(entry.starts_on) if entry.starts_on else None,
                    "ends_on": str(entry.ends_on) if entry.ends_on else None,
                },
            )
        )

    for snapshot in chart.transits:
        facts.extend(extract_transit_facts(snapshot))

    return facts


def extract_transit_facts(snapshot: TransitSnapshot) -> list[AtomicFact]:
    facts: list[AtomicFact] = []
    for planet in snapshot.planets:
        attrs = {
            "planet": planet.id.value,
            "sign": planet.sign.value,
            "date": str(snapshot.as_of),
        }
        if planet.house is not None:
            attrs["house"] = planet.house
        facts.append(AtomicFact(fact_type="transit_position", attributes=attrs))
    for rel in snapshot.relations_to_natal:
        facts.append(
            AtomicFact(
                fact_type="transit_relation",
                attributes={
                    "transit_planet": rel.planet_a.value,
                    "natal_target": rel.planet_b.value,
                    "relation": rel.relation,
                    "date": str(snapshot.as_of),
                },
            )
        )
    return facts
