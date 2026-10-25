"""Pydantic schemas defining structured execution plans."""

from datetime import date
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class BoundingBox(BaseModel):
    """Geographic bounding box in WGS84 degrees [min_lon, min_lat, max_lon, max_lat]."""

    model_config = ConfigDict(extra="forbid")

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


class AOIPlan(BaseModel):
    """Spatial definition of the target area."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    place: str = Field(
        ...,
        validation_alias=AliasChoices("place", "place_name"),
        description="Canonical place or region name (e.g. Raipur)",
    )
    radius_km: float = Field(
        default=15.0,
        ge=0.5,
        le=28.2,
        description="Buffer radius in km (max 28.2 km enforces 2,500 km² AOI ceiling)",
    )
    bbox: BoundingBox | None = Field(
        default=None,
        description="Geocoded WGS84 bounding box",
    )

    @property
    def place_name(self) -> str:
        return self.place


AreaOfInterest = AOIPlan


class TimeInterval(BaseModel):
    """Target temporal window for analysis."""

    model_config = ConfigDict(extra="forbid")

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


class PeriodPlan(BaseModel):
    """Calendar year and seasonal window specification for analysis."""

    model_config = ConfigDict(extra="forbid")

    year: int = Field(
        ...,
        ge=2017,
        le=2030,
        description="Calendar year (2017+ for Sentinel-2 L2A collection)",
    )
    season: str = Field(
        default="post_monsoon",
        description="Seasonal window name ('post_monsoon', 'pre_monsoon', 'monsoon')",
    )
    start_date: date | None = Field(
        default=None,
        description="Optional exact temporal window start date",
    )
    end_date: date | None = Field(
        default=None,
        description="Optional exact temporal window end date",
    )
    label: str | None = Field(
        default=None,
        description="Human-readable label describing the period",
    )


class QueryPlan(BaseModel):
    """Strictly validated query execution plan emitted by planner."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_type: Literal["water_change", "water_extent", "out_of_scope"] = Field(
        default="water_change",
        description="Type of geospatial analysis to perform",
    )
    aoi: AOIPlan = Field(..., description="Area of interest with place and buffering")
    period_a: PeriodPlan = Field(..., description="Baseline temporal period")
    period_b: PeriodPlan | None = Field(
        default=None,
        description="Comparison temporal period (required for water_change)",
    )
    season_policy: Literal["shared", "post_monsoon", "pre_monsoon", "per_period", "custom"] = Field(
        default="shared",
        description="Seasonal and threshold compositing policy",
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
    output_formats: list[str] = Field(
        default_factory=lambda: [
            "geojson",
            "cog",
            "csv",
            "report_markdown",
            "report_html",
        ],
        description="Requested export formats",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Documented assumptions applied to resolve ambiguous queries",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Flag indicating ambiguous, under-specified, or out-of-scope query",
    )
    clarification_question: str | None = Field(
        default=None,
        description="Clarification question prompt when needs_clarification is True",
    )
    planner_used: str | None = Field(
        default=None,
        description="Identifier of the planner used (e.g. 'rule_based', 'gemini', 'openai')",
    )
    fallback_reason: str | None = Field(
        default=None,
        description="Reason for fallback if primary planner failed",
    )

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map legacy time_range_a -> period_a
            if "time_range_a" in data and "period_a" not in data:
                tra = data.pop("time_range_a")
                start_d = tra.start_date if isinstance(tra, TimeInterval) else tra.get("start_date")
                end_d = tra.end_date if isinstance(tra, TimeInterval) else tra.get("end_date")
                year_a = start_d.year if isinstance(start_d, date) else int(str(start_d)[:4])
                lbl = tra.label if isinstance(tra, TimeInterval) else tra.get("label")
                data["period_a"] = {
                    "year": year_a,
                    "season": data.get("season_policy", "post_monsoon"),
                    "start_date": start_d,
                    "end_date": end_d,
                    "label": lbl,
                }
            # Map legacy time_range_b -> period_b
            if "time_range_b" in data and "period_b" not in data:
                trb = data.pop("time_range_b")
                if trb is not None:
                    start_d = (
                        trb.start_date if isinstance(trb, TimeInterval) else trb.get("start_date")
                    )
                    end_d = trb.end_date if isinstance(trb, TimeInterval) else trb.get("end_date")
                    year_b = start_d.year if isinstance(start_d, date) else int(str(start_d)[:4])
                    lbl = trb.label if isinstance(trb, TimeInterval) else trb.get("label")
                    data["period_b"] = {
                        "year": year_b,
                        "season": data.get("season_policy", "post_monsoon"),
                        "start_date": start_d,
                        "end_date": end_d,
                        "label": lbl,
                    }
                else:
                    data["period_b"] = None
        return data

    @model_validator(mode="after")
    def validate_plan_consistency(self) -> "QueryPlan":
        if self.needs_clarification:
            if not self.clarification_question:
                raise ValueError(
                    "clarification_question is required when needs_clarification is True"
                )
            return self

        if self.task_type == "out_of_scope":
            self.needs_clarification = True
            if not self.clarification_question:
                self.clarification_question = (
                    "This system specializes in historical surface water change analysis using Sentinel-2 L2A. "
                    "The requested analysis is outside the supported capabilities."
                )
            return self

        if self.task_type == "water_change":
            if self.period_b is None:
                raise ValueError(
                    "time_range_b is required (period_b) when task_type is 'water_change'"
                )
            if self.period_b.year <= self.period_a.year:
                raise ValueError(
                    f"period_b year ({self.period_b.year}) must be strictly after period_a year ({self.period_a.year})"
                )

        if not self.aoi.place.strip():
            raise ValueError("AOI place name cannot be empty")

        return self

    @property
    def time_range_a(self) -> TimeInterval:
        """Backward-compatibility property returning TimeInterval."""
        if self.period_a.start_date and self.period_a.end_date:
            return TimeInterval(
                start_date=self.period_a.start_date,
                end_date=self.period_a.end_date,
                label=self.period_a.label or f"{self.period_a.season} {self.period_a.year}",
            )
        s_date = (
            date(self.period_a.year, 3, 1)
            if self.period_a.season == "pre_monsoon"
            else date(self.period_a.year, 10, 1)
        )
        e_date = (
            date(self.period_a.year, 5, 31)
            if self.period_a.season == "pre_monsoon"
            else date(self.period_a.year, 11, 30)
        )
        lbl = (
            f"Pre-Monsoon Mar-May {self.period_a.year}"
            if self.period_a.season == "pre_monsoon"
            else f"Post-Monsoon Oct-Nov {self.period_a.year}"
        )
        return TimeInterval(start_date=s_date, end_date=e_date, label=lbl)

    @property
    def time_range_b(self) -> TimeInterval | None:
        """Backward-compatibility property returning TimeInterval."""
        if self.period_b is None:
            return None
        if self.period_b.start_date and self.period_b.end_date:
            return TimeInterval(
                start_date=self.period_b.start_date,
                end_date=self.period_b.end_date,
                label=self.period_b.label or f"{self.period_b.season} {self.period_b.year}",
            )
        s_date = (
            date(self.period_b.year, 3, 1)
            if self.period_b.season == "pre_monsoon"
            else date(self.period_b.year, 10, 1)
        )
        e_date = (
            date(self.period_b.year, 5, 31)
            if self.period_b.season == "pre_monsoon"
            else date(self.period_b.year, 11, 30)
        )
        lbl = (
            f"Pre-Monsoon Mar-May {self.period_b.year}"
            if self.period_b.season == "pre_monsoon"
            else f"Post-Monsoon Oct-Nov {self.period_b.year}"
        )
        return TimeInterval(start_date=s_date, end_date=e_date, label=lbl)


AnalysisPlan = QueryPlan
