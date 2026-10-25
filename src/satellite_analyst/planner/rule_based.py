"""Rule-based fallback planner using regex and keyword extraction."""

import re
from datetime import date
from typing import Any, Literal

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
        year_a: int
        year_b: int | None = None

        # Check for relative years: "last N years" / "past N years"
        rel_match = re.search(r"\b(?:last|past)\s+(\d+)\s+years?\b", lower_q)
        recent_match = re.search(r"\b(?:recently|recent\s+years?)\b", lower_q)

        if rel_match:
            n_years = int(rel_match.group(1))
            year_b = REFERENCE_YEAR
            year_a = max(2017, REFERENCE_YEAR - n_years)
            assumptions.append(
                f"Interpreted 'last {n_years} years' relative to {REFERENCE_YEAR}: {year_a} to {year_b}"
            )
        elif recent_match:
            year_a = 2024
            year_b = REFERENCE_YEAR
            assumptions.append(
                f"Interpreted 'recently' as last 2-year interval: {year_a} to {year_b}"
            )
        else:
            # Match 4-digit years between 2000 and 2030
            years_found = [int(y) for y in re.findall(r"\b(20[0-2][0-9]|2030)\b", cleaned)]
            years = sorted(dict.fromkeys(years_found))

            # Sentinel-2 L2A collection boundary check (2017+)
            if any(y < 2017 for y in years):
                return QueryPlan(
                    task_type="water_change",
                    aoi=AOIPlan(place="Raipur", radius_km=radius_km),
                    period_a=PeriodPlan(year=2017, season="post_monsoon"),
                    period_b=PeriodPlan(year=2019, season="post_monsoon"),
                    needs_clarification=True,
                    clarification_question=(
                        f"Sentinel-2 Level-2A surface reflectance data is only available from 2017 onwards. "
                        f"Requested year(s) {years} precede archive availability. Please select years $\\ge 2017$."
                    ),
                    assumptions=[
                        "Pre-2017 year detected; requested clarification for Sentinel-2 collection boundaries"
                    ],
                    planner_used="rule_based",
                )

            if not years:
                # Documented default
                year_a, year_b = 2023, 2025
                assumptions.append(
                    "No years specified in query; defaulted to 2023 vs 2025 comparison"
                )
            elif len(years) == 1:
                year_a = years[0]
                year_b = None
            else:
                year_a, year_b = years[0], years[1]

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
            # Default: post-monsoon Oct-Nov for clear skies & maximum extent
            season_policy = "post_monsoon"
            start_month_day = (10, 1)
            end_month_day = (11, 30)
            season_label = "Post-Monsoon Oct-Nov"
            if not any(w in lower_q for w in post_monsoon_terms):
                assumptions.append(
                    "Season not explicitly specified; defaulted to post-monsoon (Oct-Nov) for cloud-free observations"
                )

        # 5. Task type detection
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
            "badh gaya",
            "kam ho gaya",
            "badha",
        ]

        if year_b is not None or any(w in lower_q for w in change_indicators):
            task_type = "water_change"
            if year_b is None:
                # Single year provided with change request: baseline defaulted 2 years prior
                year_b = year_a
                year_a = max(2017, year_b - 2)
                assumptions.append(
                    f"Change requested with single year ({year_b}); established baseline 2 years prior ({year_a})"
                )
        else:
            task_type = "water_extent"

        # 6. Extract place name
        place_name: str | None = None

        # Try regex patterns
        # "within X km of <Place>"
        match_within = re.search(
            r"\b(?:within\s+\d+(?:\.\d+)?\s*km\s+(?:of|around|from)\s+)([A-Za-z\s\-]+?)(?=\s+(?:between|from|during|in\s+\d{4}|since|\d{4}|$))",
            cleaned,
            re.IGNORECASE,
        )
        if match_within:
            place_name = match_within.group(1).strip()

        if not place_name:
            # Standard prepositions: "near <Place>", "in <Place>", "around <Place>", "at <Place>"
            place_match = re.search(
                r"\b(?:near|in|around|over|at|for|across|of)\s+([A-Za-z\s\-]+?)(?=\s+(?:between|from|during|in\s+\d{4}|since|\d{4}|$))",
                cleaned,
                re.IGNORECASE,
            )
            if place_match:
                candidate = place_match.group(1).strip()
                # Exclude season words mistakenly matched
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
            # Known benchmark locations
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

        narrative = (
            f"Analysis of {plan.aoi.place_name} between {plan.time_range_a.label} and "
            f"{plan.time_range_b.label if plan.time_range_b else 'N/A'} indicates {dynamic_desc}. "
            f"Persistent water accounted for {stats.get('persistent_water_ha', 0.0):.2f} ha, "
            f"while gained water totaled {stats.get('gained_water_ha', 0.0):.2f} ha and "
            f"lost water totaled {stats.get('lost_water_ha', 0.0):.2f} ha. "
            f"The observed churn ratio was {stats.get('churn_ratio', 0.0) * 100:.2f}%."
        )
        return narrative
