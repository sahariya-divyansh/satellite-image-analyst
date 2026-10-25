"""Grounding verifier ensuring no hallucinated numbers exist in narrative summaries."""

import re
from typing import Any

from satellite_analyst.errors import GroundingViolationError
from satellite_analyst.logging import get_logger

logger = get_logger(__name__)

GROUNDED_NARRATIVE_SYSTEM_PROMPT = (
    "You are a scientific Earth Observation technical analyst writing a strictly factual executive summary "
    "of Sentinel-2 surface water dynamics.\n"
    "NON-NEGOTIABLE GROUNDING RULES:\n"
    "1. Every number in your text MUST match a number in the provided Facts JSON. Never hallucinate, invent, or estimate values.\n"
    "2. Describe the net change using the EXACT scientific significance label provided in the facts ('within noise / inconclusive', 'significant expansion', or 'significant contraction'). Never use 'expanded' or 'shrank' if the label is 'within noise / inconclusive'.\n"
    "3. Never claim unverified causal mechanisms (e.g. irrigation canals or river sandbars). Refer to them strictly as 'possible contributors (not verified)'.\n"
    "4. State the baseline water, comparison water, net change, churn ratio, and sensitivity range."
)


class GroundingVerifier:
    """Verifies that every numerical claim in a generated narrative maps to computed facts."""

    def __init__(self, tolerance: float = 0.05) -> None:
        self.tolerance = tolerance

    def extract_numeric_tokens(self, text: str) -> list[float]:
        """Extract all isolated numerical values from text, ignoring calendar years (1900-2100)."""
        raw_matches = re.findall(r"[-+]?\b\d+(?:,\d{3})*(?:\.\d+)?\b", text)
        extracted: list[float] = []

        for match in raw_matches:
            clean_str = match.replace(",", "")
            try:
                val = float(clean_str)
                # Ignore calendar years between 1900 and 2100
                if 1900 <= val <= 2100 and val.is_integer():
                    continue
                extracted.append(val)
            except ValueError:
                continue

        return extracted

    def collect_known_numbers(
        self,
        stats: dict[str, Any],
        provenance: dict[str, Any],
    ) -> set[float]:
        """Flatten all numeric values from stats and provenance with common unit conversions."""
        raw_known: set[float] = set()

        def _traverse(obj: Any) -> None:
            if isinstance(obj, (int, float)):
                if not isinstance(obj, bool):
                    raw_known.add(float(obj))
            elif isinstance(obj, dict):
                for v in obj.values():
                    _traverse(v)
            elif isinstance(obj, (list, tuple, set)):
                for item in obj:
                    _traverse(item)

        _traverse(stats)
        _traverse(provenance)

        expanded_known: set[float] = set(raw_known)
        for num in raw_known:
            # Absolute value
            abs_n = abs(num)
            expanded_known.add(abs_n)
            expanded_known.add(-abs_n)

            # Area unit conversions: 100 ha = 1 km²
            expanded_known.add(round(num / 100.0, 2))
            expanded_known.add(round(num / 100.0, 3))
            expanded_known.add(round(num * 100.0, 2))

            # Fraction to percentage: 0.1234 -> 12.34%
            if 0.0 <= abs_n <= 1.0:
                expanded_known.add(round(num * 100.0, 2))
                expanded_known.add(round(num * 100.0, 1))

            # Rounding variants
            expanded_known.add(round(num, 1))
            expanded_known.add(round(num, 0))

        # Add common fixed metadata numbers (e.g. 10m resolution, 0.1 ha min area)
        expanded_known.update([10.0, 0.1, 0.0, 1.0, 2.0, 3.0, 100.0])

        return expanded_known

    def verify(
        self,
        narrative: str,
        stats: dict[str, Any],
        provenance: dict[str, Any],
        strict: bool = True,
    ) -> list[str]:
        """Verify narrative against computed stats.

        Returns list of ungrounded numeric tokens found.
        Raises GroundingViolationError if strict=True and ungrounded numbers exist.
        """
        tokens = self.extract_numeric_tokens(narrative)
        known_numbers = self.collect_known_numbers(stats, provenance)

        ungrounded: list[str] = []
        for val in tokens:
            matched = any(
                abs(val - k) <= max(self.tolerance, abs(k) * self.tolerance) for k in known_numbers
            )
            if not matched:
                ungrounded.append(str(val))

        if ungrounded and strict:
            raise GroundingViolationError(ungrounded_numbers=ungrounded)

        return ungrounded
