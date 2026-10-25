"""Tests for custom domain exceptions."""

from satellite_analyst.errors import (
    GeocodingError,
    GroundingViolationError,
    PlanGenerationError,
    SatelliteAnalystError,
)


def test_base_error() -> None:
    err = SatelliteAnalystError("An error occurred", code="CUSTOM_CODE", status_code=400)
    assert err.code == "CUSTOM_CODE"
    assert err.status_code == 400
    assert str(err) == "An error occurred"


def test_geocoding_error() -> None:
    err = GeocodingError("UnknownPlace")
    assert err.status_code == 404
    assert err.code == "GEOCODING_FAILED"
    assert "UnknownPlace" in err.message


def test_plan_generation_error() -> None:
    err = PlanGenerationError("Query", "Invalid grammar")
    assert err.status_code == 422
    assert err.code == "PLAN_GENERATION_FAILED"


def test_grounding_violation_error() -> None:
    err = GroundingViolationError(ungrounded_numbers=["45.2", "99.9"])
    assert err.status_code == 500
    assert err.code == "GROUNDING_VIOLATION"
    assert "45.2" in err.message
