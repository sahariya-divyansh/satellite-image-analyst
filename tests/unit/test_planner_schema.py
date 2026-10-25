"""Tests for planner Pydantic schemas."""

import pytest
from pydantic import ValidationError

from satellite_analyst.planner.schema import (
    AnalysisPlan,
    AreaOfInterest,
    BoundingBox,
    TimeInterval,
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
    from datetime import date

    with pytest.raises(ValidationError, match="time_range_b is required"):
        AnalysisPlan(
            task_type="water_change",
            aoi=AreaOfInterest(place_name="Raipur", bbox=sample_bounding_box),
            time_range_a=TimeInterval(
                start_date=date(2023, 10, 1),
                end_date=date(2023, 11, 30),
                label="Oct-Nov 2023",
            ),
            time_range_b=None,  # Invalid for water_change!
        )
