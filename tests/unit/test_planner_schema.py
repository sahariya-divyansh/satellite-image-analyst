"""Tests for planner Pydantic schemas."""

import pytest
from pydantic import ValidationError

from satellite_analyst.planner.schema import (
    AnalysisPlan,
    AreaOfInterest,
    BoundingBox,
)


def test_valid_bounding_box() -> None:
    bbox = BoundingBox(min_lon=81.5, min_lat=21.1, max_lon=81.8, max_lat=21.4)
    assert bbox.as_list() == [81.5, 21.1, 81.8, 21.4]


def test_invalid_bounding_box_coordinates() -> None:
    # min_lon > max_lon
    with pytest.raises(ValidationError):
        BoundingBox(min_lon=82.0, min_lat=21.1, max_lon=81.0, max_lat=21.4)

    # min_lat > max_lat
    with pytest.raises(ValidationError):
        BoundingBox(min_lon=81.0, min_lat=22.0, max_lon=82.0, max_lat=21.0)


def test_valid_analysis_plan(sample_analysis_plan: AnalysisPlan) -> None:
    assert sample_analysis_plan.task_type == "water_change"
    assert sample_analysis_plan.index == "MNDWI"
    assert sample_analysis_plan.time_range_b is not None


def test_water_change_requires_time_range_b(sample_bounding_box: BoundingBox) -> None:
    from satellite_analyst.planner.schema import PeriodPlan

    with pytest.raises(ValidationError, match="time_range_b is required"):
        AnalysisPlan(
            task_type="water_change",
            aoi=AreaOfInterest(place="Raipur", bbox=sample_bounding_box),
            period_a=PeriodPlan(year=2023),
            period_b=None,  # Invalid for water_change!
        )


def test_query_plan_strict_validation() -> None:
    from satellite_analyst.planner.schema import AOIPlan, PeriodPlan, QueryPlan

    # Pre-2017 year rejected (Sentinel-2 L2A collection starts 2017)
    with pytest.raises(ValidationError):
        PeriodPlan(year=2015, season="post_monsoon")

    # Radius > 28.2 km rejected (enforces 2500 km² ceiling)
    with pytest.raises(ValidationError):
        AOIPlan(place="Raipur", radius_km=30.0)

    # Period B year <= Period A year rejected
    with pytest.raises(ValidationError, match="period_b year.*must be strictly after"):
        QueryPlan(
            aoi=AOIPlan(place="Raipur", radius_km=15.0),
            period_a=PeriodPlan(year=2024),
            period_b=PeriodPlan(year=2023),
        )

    # Unknown fields rejected
    with pytest.raises(ValidationError):
        QueryPlan(
            aoi=AOIPlan(place="Raipur"),
            period_a=PeriodPlan(year=2023),
            period_b=PeriodPlan(year=2025),
            invalid_field=123,  # type: ignore[call-arg]
        )

    # needs_clarification requires clarification_question
    with pytest.raises(ValidationError, match="clarification_question is required"):
        QueryPlan(
            needs_clarification=True,
            clarification_question=None,
            aoi=AOIPlan(place="Raipur"),
            period_a=PeriodPlan(year=2023),
        )

    # out_of_scope automatically sets needs_clarification
    plan_oos = QueryPlan(
        task_type="out_of_scope",
        aoi=AOIPlan(place="Unknown"),
        period_a=PeriodPlan(year=2023),
    )
    assert plan_oos.needs_clarification is True
    assert plan_oos.clarification_question is not None
