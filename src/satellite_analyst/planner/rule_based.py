"""Rule-based fallback planner using regex and keyword extraction."""

import re
from datetime import date
from typing import Any, Literal

from satellite_analyst.config import get_settings
from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.planner.geocode import GeocodeService
from satellite_analyst.planner.schema import (
    AnalysisPlan,
    AOIPlan,
    PeriodPlan,
    QueryPlan,
    TimeInterval,
)

# Reference current year for relative expressions (e.g. "last 2 years", "recently")
REFERENCE_YEAR = 2026

OUT_OF_SCOPE_TERMS = [
    "predict",
    "forecast",
    "future",
    "next year",
    "crop",
    "yield",
    "deforestation",
    "forest fire",
    "air quality",
    "population",
    "price",
    "building footprint",
]


class RuleBasedPlanner:
    """Deterministic fallback planner using robust pattern matching and geocoding."""

    def __init__(self, geocoder: GeocodeService | None = None) -> None:
        self.geocoder = geocoder or GeocodeService()

    def parse_query(self, query: str) -> QueryPlan:
        """Parse query string into a strictly validated QueryPlan."""
        cleaned = query.strip()
        if not cleaned:
            raise PlanGenerationError(query=query, reason="Query string is empty")

        lower_q = cleaned.lower()
        assumptions: list[str] = []

        # 1. Check for out-of-scope requests (e.g. flood forecasting, crop yield)
        if any(term in lower_q for term in OUT_OF_SCOPE_TERMS):
            return QueryPlan(
                task_type="out_of_scope",
                aoi=AOIPlan(place="Raipur", radius_km=15.0),
                period_a=PeriodPlan(year=2023, season="post_monsoon"),
                period_b=PeriodPlan(year=2025, season="post_monsoon"),
                needs_clarification=True,
                clarification_question=(
                    "This system specializes in retrospective surface water change detection using Sentinel-2 L2A (2017-present). "
                    "Predictive forecasting, crop yield modeling, and non-water domains are outside supported capabilities."
                ),
                assumptions=["Detected out-of-scope query intent; returned typed rejection."],
                planner_used="rule_based",
            )

        # 2. Extract radius if specified (e.g. "within 20 km of Raipur", "10km around Bilaspur")
        radius_km = 15.0
        radius_match = re.search(
            r"\b(?:within\s+)?(\d+(?:\.\d+)?)\s*km\s*(?:of|from|around)?\b",
            lower_q,
        )
        if radius_match:
            parsed_radius = float(radius_match.group(1))
            if parsed_radius > 28.2:
                radius_km = 28.2
                assumptions.append(
                    f"Requested radius ({parsed_radius:.1f} km) exceeds 2,500 km² AOI ceiling; clamped to 28.2 km"
                )
            elif parsed_radius < 0.5:
                radius_km = 0.5
                assumptions.append(
                    f"Requested radius ({parsed_radius:.1f} km) too small; clamped to minimum 0.5 km"
                )
            else:
                radius_km = parsed_radius

        # 3. Extract years and relative temporal bounds
        settings = get_settings()
        min_year = settings.min_year
        year_a: int = 2023
        year_b: int | None = None

        # Check for relative years: "last N years" / "past N years"
        rel_match = re.search(r"\b(?:last|past)\s+(\d+)\s+years?\b", lower_q)
        recent_match = re.search(r"\b(?:recently|recent\s+years?)\b", lower_q)

        years_found = [int(y) for y in re.findall(r"\b(20[0-2][0-9]|2030)\b", cleaned)]
        years = sorted(dict.fromkeys(years_found))

        # Check for explicit decimal coordinates in query (e.g. "21.15N, 79.08E" or "21.15, 79.08")
        coord_pattern = re.search(
            r"\b(-?\d{1,2}(?:\.\d+)?)\s*°?\s*([NSns])?\s*[,/ ]\s*(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([EWew])?\b",
            cleaned,
        )
        coord_place: str | None = None
        if coord_pattern:
            g1, g2, g3, g4 = coord_pattern.groups()
            is_coord = (g2 is not None or g4 is not None) or ("." in g1 and "." in g3)
            if is_coord:
                try:
                    c_lat = float(g1)
                    if g2 and g2.upper() == "S":
                        c_lat = -abs(c_lat)
                    c_lon = float(g3)
                    if g4 and g4.upper() == "W":
                        c_lon = -abs(c_lon)
                    if -90.0 <= c_lat <= 90.0 and -180.0 <= c_lon <= 180.0:
                        coord_place = f"{abs(c_lat):.4f}°{'N' if c_lat >= 0 else 'S'}, {abs(c_lon):.4f}°{'E' if c_lon >= 0 else 'W'}"
                except ValueError:
                    pass

        # Sentinel-2 L2A collection boundary check (configurable MIN_YEAR)
        if any(y < min_year for y in years):
            target_place = coord_place or "Raipur"
            return QueryPlan(
                task_type="out_of_scope",
                aoi=AOIPlan(place=target_place, radius_km=radius_km),
                period_a=PeriodPlan(year=min_year, season="post_monsoon"),
                period_b=None,
                needs_clarification=True,
                clarification_question=(
                    f"Sentinel-2 Level-2A surface reflectance data is only available from {min_year} onwards. "
                    f"Requested year(s) {years} precede archive availability. "
                    f"STAC observation audits confirm 0 items in 2014 and 4 sparse items in 2015 over India, "
                    f"with consistent 5-day dual-orbit revisits starting in {min_year}. Please select observation years >= {min_year}."
                ),
                assumptions=[f"Pre-{min_year} observation year detected; returned typed refusal."],
                planner_used="rule_based",
            )

        # 4. Season policy detection (including Hindi / Hinglish phrasing)
        season_policy: Literal["post_monsoon", "pre_monsoon", "monsoon", "shared"]
        start_month_day: tuple[int, int]
        end_month_day: tuple[int, int]
        season_label: str

        pre_monsoon_terms = [
            "pre-monsoon",
            "pre monsoon",
            "summer",
            "garmi",
            "sukha",
            "garmio",
            "march",
            "may",
        ]
        post_monsoon_terms = [
            "post-monsoon",
            "post monsoon",
            "baarish ke baad",
            "barsaat ke baad",
            "barsat ke baad",
            "monsoon ke baad",
            "after rain",
            "sardi",
            "thand",
            "winter",
            "october",
            "november",
        ]

        if any(w in lower_q for w in pre_monsoon_terms):
            season_policy = "pre_monsoon"
            start_month_day = (3, 1)
            end_month_day = (5, 31)
            season_label = "Pre-Monsoon Mar-May"
        else:
            season_policy = "post_monsoon"
            start_month_day = (10, 1)
            end_month_day = (11, 30)
            season_label = "Post-Monsoon Oct-Nov"
            if not any(w in lower_q for w in post_monsoon_terms):
                assumptions.append(
                    "Season not explicitly specified; defaulted to post-monsoon (Oct-Nov) for cloud-free observations"
                )

        # 5. Extract place name
        place_name: str | None = coord_place

        if not place_name:
            match_within = re.search(
                r"\b(?:within\s+\d+(?:\.\d+)?\s*km\s+(?:of|around|from)\s+)([A-Za-z\s\-]+?)(?=\s+(?:between|from|during|in\s+\d{4}|since|\d{4}|$))",
                cleaned,
                re.IGNORECASE,
            )
            if match_within:
                place_name = match_within.group(1).strip()

        if not place_name:
            place_match = re.search(
                r"\b(?:near|in|around|over|at|for|across|of)\s+([A-Za-z\s\-]+?)(?=\s+(?:between|from|during|in\s+\d{4}|since|\d{4}|$))",
                cleaned,
                re.IGNORECASE,
            )
            if place_match:
                candidate = place_match.group(1).strip()
                if not any(
                    w in candidate.lower()
                    for w in [
                        "summer",
                        "winter",
                        "post-monsoon",
                        "pre-monsoon",
                        "monsoon",
                    ]
                ):
                    place_name = candidate

        if not place_name:
            for known in [
                "raipur",
                "vembanad",
                "sambhar",
                "bhopal",
                "hyderabad",
                "bilaspur",
                "durg",
            ]:
                if known in lower_q:
                    place_name = known.capitalize()
                    break

        if not place_name:
            place_name = "Raipur"
            assumptions.append(
                "Target location not specified in query; defaulted to Raipur (Chhattisgarh, India)"
            )

        # Normalize geographic feature nouns (e.g. "Sambhar salt lake" -> "Sambhar")
        if place_name and "°" not in place_name:
            cleaned_place = re.sub(
                r"\b(?:salt\s+lake|lake|river|district|city|reservoir|wetland|dam)\b",
                "",
                place_name,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned_place:
                place_name = cleaned_place

        # 6. Task type & Temporal policy determination
        task_type: Literal["water_change", "water_extent"]
        change_indicators = [
            "change",
            "expanded",
            "expansion",
            "shrunk",
            "shrink",
            "between",
            "difference",
            "growth",
            "loss",
            "gain",
            "compare",
            "comparison",
            "versus",
            "vs",
            "badh gaya",
            "kam ho gaya",
            "badha",
        ]

        has_change_intent = (
            (len(years) >= 2)
            or any(w in lower_q for w in change_indicators)
            or (rel_match is not None)
            or (recent_match is not None)
        )

        if rel_match:
            n_years = int(rel_match.group(1))
            year_b = REFERENCE_YEAR
            year_a = max(min_year, REFERENCE_YEAR - n_years)
            assumptions.append(
                f"Interpreted 'last {n_years} years' relative to {REFERENCE_YEAR}: {year_a} to {year_b}"
            )
            task_type = "water_change"
        elif recent_match:
            year_a = 2024
            year_b = REFERENCE_YEAR
            assumptions.append(
                f"Interpreted 'recently' as last 2-year interval: {year_a} to {year_b}"
            )
            task_type = "water_change"
        elif has_change_intent:
            task_type = "water_change"
            # Policy: Change detection requires two distinct observation periods.
            if len(years) == 0:
                return QueryPlan(
                    task_type="water_change",
                    aoi=AOIPlan(place=place_name, radius_km=radius_km),
                    period_a=PeriodPlan(year=2023, season="post_monsoon"),
                    period_b=PeriodPlan(year=2025, season="post_monsoon"),
                    needs_clarification=True,
                    clarification_question=(
                        "Water change detection requires two distinct observation periods. "
                        "Please specify both baseline and comparison years (e.g., '2023 vs 2025')."
                    ),
                    assumptions=[
                        "Change detection requested with no observation years; clarification required."
                    ],
                    planner_used="rule_based",
                )
            elif len(years) == 1:
                return QueryPlan(
                    task_type="water_change",
                    aoi=AOIPlan(place=place_name, radius_km=radius_km),
                    period_a=PeriodPlan(year=years[0], season="post_monsoon"),
                    period_b=PeriodPlan(
                        year=min(REFERENCE_YEAR, years[0] + 2), season="post_monsoon"
                    ),
                    needs_clarification=True,
                    clarification_question=(
                        f"Water change detection requires two distinct observation periods to compare. "
                        f"You specified {years[0]}; please specify both a baseline and a comparison year (e.g., '{years[0] - 2} vs {years[0]}')."
                    ),
                    assumptions=[
                        f"Change detection requested with single year ({years[0]}); clarification required."
                    ],
                    planner_used="rule_based",
                )
            else:
                year_a, year_b = years[0], years[1]
        else:
            task_type = "water_extent"
            if len(years) == 0:
                year_a = 2024
                year_b = None
                assumptions.append(
                    "No observation year specified; defaulted to 2024 surface water inventory"
                )
            else:
                year_a = years[0]
                year_b = None

        # Geocode place bounds
        geo_res = self.geocoder.geocode(place_name, radius_km=radius_km)
        bbox = geo_res.bbox

        time_range_a = TimeInterval(
            start_date=date(year_a, start_month_day[0], start_month_day[1]),
            end_date=date(year_a, end_month_day[0], end_month_day[1]),
            label=f"{season_label} {year_a}",
        )

        time_range_b = None
        period_b_plan = None
        if task_type == "water_change" and year_b is not None:
            time_range_b = TimeInterval(
                start_date=date(year_b, start_month_day[0], start_month_day[1]),
                end_date=date(year_b, end_month_day[0], end_month_day[1]),
                label=f"{season_label} {year_b}",
            )
            period_b_plan = PeriodPlan(
                year=year_b,
                season=season_policy,
                start_date=time_range_b.start_date,
                end_date=time_range_b.end_date,
                label=time_range_b.label,
            )

        period_a_plan = PeriodPlan(
            year=year_a,
            season=season_policy,
            start_date=time_range_a.start_date,
            end_date=time_range_a.end_date,
            label=time_range_a.label,
        )

        aoi_plan = AOIPlan(
            place=place_name,
            radius_km=radius_km,
            bbox=bbox,
        )

        return QueryPlan(
            task_type=task_type,
            aoi=aoi_plan,
            period_a=period_a_plan,
            period_b=period_b_plan,
            season_policy=season_policy,
            index="MNDWI",
            min_area_ha=0.1,
            output_formats=[
                "geojson",
                "cog",
                "csv",
                "report_markdown",
                "report_html",
            ],
            assumptions=assumptions,
            needs_clarification=False,
            clarification_question=None,
            planner_used="rule_based",
        )

    async def generate_plan(self, query: str) -> QueryPlan:
        """Async compatibility wrapper."""
        return self.parse_query(query)

    async def generate_narrative(
        self,
        plan: AnalysisPlan,
        stats: dict[str, Any],
        _provenance: dict[str, Any],
    ) -> str:
        """Deterministic narrative template for rule-based engine."""
        net_delta = stats.get("net_change_ha", 0.0)
        pct_change = stats.get("percent_change", 0.0)
        significance = stats.get("significance", "within noise / inconclusive").lower()

        if "expansion" in significance:
            dynamic_desc = f"a net expansion in surface water of {abs(net_delta):.2f} hectares ({pct_change:+.2f}%)"
        elif "contraction" in significance:
            dynamic_desc = f"a net contraction in surface water of {abs(net_delta):.2f} hectares ({pct_change:+.2f}%)"
        else:
            dynamic_desc = f"a net change in surface water of {abs(net_delta):.2f} hectares ({pct_change:+.2f}%), evaluated as {significance}"

        total_aoi_km2 = stats.get("total_aoi_ha", 0.0) / 100.0
        total_aoi_ha = stats.get("total_aoi_ha", 0.0)

        narrative = (
            f"Analysis of {plan.aoi.place_name} across the {total_aoi_km2:.2f} km² ({total_aoi_ha:,.1f} ha) "
            f"bounding box area of interest between {plan.time_range_a.label} and "
            f"{plan.time_range_b.label if plan.time_range_b else 'N/A'} indicates {dynamic_desc}. "
            f"Persistent water accounted for {stats.get('persistent_water_ha', 0.0):.2f} ha, "
            f"while gained water totaled {stats.get('gained_water_ha', 0.0):.2f} ha and "
            f"lost water totaled {stats.get('lost_water_ha', 0.0):.2f} ha. "
            f"The observed churn ratio was {stats.get('churn_ratio', 0.0) * 100:.2f}%."
        )
        return narrative
