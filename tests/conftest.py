"""Shared pytest fixtures."""

import numpy as np
import pytest

from satellite_analyst.config import Settings
from satellite_analyst.planner.schema import (
    AnalysisPlan,
    AreaOfInterest,
    BoundingBox,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Fixture providing testing settings."""
    return Settings(
        app_env="testing",
        log_level="DEBUG",
        default_llm_provider="rule_based",
    )


@pytest.fixture
def sample_bounding_box() -> BoundingBox:
    """Fixture providing Raipur bounding box."""
    return BoundingBox(
        min_lon=81.50,
        min_lat=21.15,
        max_lon=81.80,
        max_lat=21.35,
    )


@pytest.fixture
def sample_analysis_plan(sample_bounding_box: BoundingBox) -> AnalysisPlan:
    """Fixture providing a standard water change plan."""
    from datetime import date

    from satellite_analyst.planner.schema import PeriodPlan

    return AnalysisPlan(
        task_type="water_change",
        aoi=AreaOfInterest(place="Raipur", bbox=sample_bounding_box),
        period_a=PeriodPlan(
            year=2023,
            season="post_monsoon",
            start_date=date(2023, 10, 1),
            end_date=date(2023, 11, 30),
            label="Post-Monsoon Oct-Nov 2023",
        ),
        period_b=PeriodPlan(
            year=2025,
            season="post_monsoon",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 11, 30),
            label="Post-Monsoon Oct-Nov 2025",
        ),
        season_policy="post_monsoon",
        index="MNDWI",
        min_area_ha=0.1,
    )


@pytest.fixture
def synthetic_raster_pair() -> tuple[np.ndarray, np.ndarray]:
    """Generate deterministic synthetic water index rasters for testing."""
    # Raster A: Water pond in center (radius 20)
    y, x = np.ogrid[:100, :100]
    dist_from_center = np.sqrt((x - 50) ** 2 + (y - 50) ** 2)

    # Values: >0 indicates water
    raster_a = np.where(dist_from_center <= 20, 0.45, -0.35)
    # Raster B: Water pond expanded (radius 30)
    raster_b = np.where(dist_from_center <= 30, 0.50, -0.40)

    return raster_a.astype(np.float32), raster_b.astype(np.float32)
