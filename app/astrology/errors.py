"""
errors.py
---------
Shared exceptions for the Calculation Engine.

Per spec section 18 (สิ่งที่ Claude ควรทำก่อนเริ่มเขียนสูตร), item 3:
"อย่าเดาสูตรลัคนา อายนางศะ สถานะดาว ความสัมพันธ์ดาว ทักษา หรือมหาทักษาจากความรู้ทั่วไปของ LLM"

Any module that does not yet have a verified primary-source formula must
raise FormulaNotVerifiedError rather than returning a guessed/approximate
value. This keeps "not implemented" and "silently wrong" from ever looking
the same to a caller.
"""

from __future__ import annotations


class FormulaNotVerifiedError(NotImplementedError):
    """
    Raised when a calculation would require a formula, constant, or rule
    table that has not yet been checked against a primary source.

    Attributes:
        topic: short machine key, e.g. "ascendant.longitude"
        needed: human-readable description of what reference is needed
    """

    def __init__(self, topic: str, needed: str):
        self.topic = topic
        self.needed = needed
        super().__init__(
            f"[FORMULA NOT VERIFIED] {topic}: {needed} "
            f"— see docs/formulas_needing_review.md before implementing."
        )


class CalculationInputError(ValueError):
    """Raised for invalid/insufficient input (e.g. missing birth time when
    an ascendant-dependent value is requested)."""
