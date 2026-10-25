"""Tests for grounding verifier ensuring numerical fidelity."""

from typing import Any

import pytest

from satellite_analyst.errors import GroundingViolationError
from satellite_analyst.report.grounding import GroundingVerifier


def test_grounding_verifier_valid_narrative() -> None:
    verifier = GroundingVerifier()
    stats = {
        "total_water_period_a_ha": 14210.4,
        "total_water_period_b_ha": 16845.2,
        "net_change_ha": 2634.8,
        "percent_change": 18.54,
    }
    provenance = {"otsu_threshold": -0.045}

    valid_text = (
        "In 2023, surface water was 14,210.4 ha, expanding to 16,845.2 ha in 2025. "
        "This is an expansion of +2,634.8 ha (+18.54%). Threshold applied: -0.045."
    )

    # Should not raise any error
    ungrounded = verifier.verify(valid_text, stats, provenance, strict=True)
    assert len(ungrounded) == 0


def test_grounding_verifier_detects_hallucination() -> None:
    verifier = GroundingVerifier()
    stats = {
        "total_water_period_a_ha": 14210.4,
        "total_water_period_b_ha": 16845.2,
    }
    provenance: dict[str, Any] = {}

    # 892.5 is an invented hallucinated number
    hallucinated_text = "Water expanded by 892.5 ha from 14,210.4 ha."

    with pytest.raises(GroundingViolationError) as exc_info:
        verifier.verify(hallucinated_text, stats, provenance, strict=True)

    assert "892.5" in str(exc_info.value)
