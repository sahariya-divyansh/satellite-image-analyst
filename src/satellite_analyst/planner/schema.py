"""Pydantic schemas defining structured execution plans."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Geographic bounding box in WGS84 degrees [min_lon, min_lat, max_lon, max_lat]."""

    min_lon: float = Field(..., ge=-180.0, le=180.0, description="Western longitude")
    min_lat: float = Field(..., ge=-90.0, le=90.0, description="Southern latitude")
    max_lon: float = Field(..., ge=-180.0, le=180.0, description="Eastern longitude")
    max_lat: float = Field(..., ge=-90.0, le=90.0, description="Northern latitude")

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundingBox":
        if self.min_lon >= self.max_lon:
            raise ValueError(f"min_lon ({self.min_lon}) must be less than max_lon ({self.max_lon})")
        if self.min_lat >= self.max_lat:
            raise ValueError(f"min_lat ({self.min_lat}) must be less than max_lat ({self.max_lat})")
        return self

    def as_list(self) -> list[float]:
        return [self.min_lon, self.min_lat, self.max_lon, self.max_lat]


class AreaOfInterest(BaseModel):
    """Spatial definition of the target area."""

    place_name: str = Field(..., description="Canonical place or region name (e.g. Raipur)")
    bbox: BoundingBox = Field(..., description="Geocoded WGS84 bounding box")
    radius_km: float | None = Field(
        default=None, ge=0.5, le=100.0, description="Optional buffer radius"
    )


class TimeInterval(BaseModel):
    """Target temporal window for analysis."""

    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")
    label: str = Field(..., description="Human-readable label, e.g. 'Oct-Nov 2023'")

    @model_validator(mode="after")
    def validate_dates(self) -> "TimeInterval":
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) cannot be after end_date ({self.end_date})"
            )
        return self


class AnalysisPlan(BaseModel):
    """Strictly validated analysis plan emitted by LLM or rule-based planner."""

    task_type: Literal["water_change", "water_extent", "landcover_change"] = Field(
        default="water_change",
        description="Type of geospatial analysis to perform",
    )
    aoi: AreaOfInterest = Field(..., description="Area of interest with geocoded coordinates")
    time_range_a: TimeInterval = Field(..., description="Baseline temporal period")
    time_range_b: TimeInterval | None = Field(
        default=None,
        description="Comparison temporal period (required for water_change)",
    )
    season_policy: Literal["post_monsoon", "pre_monsoon", "custom"] = Field(
        default="post_monsoon",
        description="Seasonal compositing policy enforcing equal season comparison",
    )
    index: Literal["MNDWI", "NDWI"] = Field(
        default="MNDWI",
        description="Spectral water index to compute",
    )
    min_area_ha: float = Field(
        default=0.1,
        ge=0.01,
        le=500.0,
        description="Minimum water body area in hectares to retain post-vectorization",
    )
    max_cloud_cover_percent: float = Field(
        default=30.0,
        ge=0.0,
        le=100.0,
        description="Maximum scene cloud cover percentage for initial STAC filtering",
    )
    output_formats: list[
        Literal["geojson", "cog", "png", "report_markdown", "report_html", "csv"]
    ] = Field(
        default=["geojson", "cog", "png", "report_markdown", "report_html", "csv"],
        description="Requested export formats",
    )

    @model_validator(mode="after")
    def validate_task_consistency(self) -> "AnalysisPlan":
        if self.task_type == "water_change" and self.time_range_b is None:
            raise ValueError("time_range_b is required when task_type is 'water_change'")
        return self
