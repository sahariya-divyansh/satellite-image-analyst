"""Grounding verifier ensuring no hallucinated numbers exist in narrative summaries."""

import re
from typing import Any

from satellite_analyst.errors import GroundingViolationError
from satellite_analyst.logging import get_logger

logger = get_logger(__name__)


class GroundingVerifier:
    """Verifies that every numerical claim in a generated narrative maps to computed facts."""

    def __init__(self, tolerance: float = 0.05) -> None:
        self.tolerance = tolerance

    def extract_numeric_tokens(self, text: str) -> list[float]:
        """Extract all isolated numerical values from text, ignoring years (e.g. 2023, 2025)."""
        # Find integers or floating point numbers (e.g. 14,210.4 or +18.54% or 0.1)
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
        """Flatten all numeric values from stats and provenance dictionaries."""
        known: set[float] = set()

        def _traverse(obj: Any) -> None:
            if isinstance(obj, (int, float)):
                # Ignore booleans (subclass of int in Python)
                if not isinstance(obj, bool):
                    known.add(float(obj))
            elif isinstance(obj, dict):
                for v in obj.values():
                    _traverse(v)
            elif isinstance(obj, (list, tuple, set)):
                for item in obj:
                    _traverse(item)

        _traverse(stats)
        _traverse(provenance)
        return known

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
            # Check if value matches any known number within relative/absolute tolerance
            matched = any(
                abs(val - k) <= max(self.tolerance, abs(k) * self.tolerance)
                or abs(abs(val) - abs(k)) <= max(self.tolerance, abs(k) * self.tolerance)
                for k in known_numbers
            )
            if not matched:
                ungrounded.append(str(val))

        if ungrounded and strict:
            raise GroundingViolationError(ungrounded_numbers=ungrounded)

        return ungrounded
