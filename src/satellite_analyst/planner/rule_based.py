"""Rule-based fallback planner using regex and keyword extraction."""

import re
from datetime import date
from typing import Any, Literal

from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.planner.geocode import GeocodeService
from satellite_analyst.planner.schema import (
    AnalysisPlan,
    AreaOfInterest,
    TimeInterval,
)


class RuleBasedPlanner:
    """Deterministic fallback planner using pattern matching and geocoding."""

    def __init__(self, geocoder: GeocodeService | None = None) -> None:
        self.geocoder = geocoder or GeocodeService()

    def parse_query(self, query: str) -> AnalysisPlan:
        """Parse query string into a strictly validated AnalysisPlan."""
        cleaned = query.strip()
        if not cleaned:
            raise PlanGenerationError(query=query, reason="Query string is empty")

        # 1. Extract years (4-digit numbers between 2015 and 2030)
        years_found = [int(y) for y in re.findall(r"\b(201[5-9]|202[0-9]|2030)\b", cleaned)]
        years = sorted(dict.fromkeys(years_found))

        if not years:
            # Default to 2023 and 2025 if no years explicitly specified
            year_a, year_b = 2023, 2025
        elif len(years) == 1:
            year_a = years[0]
            year_b = None
        else:
            year_a, year_b = years[0], years[1]

        # 2. Season policy detection
        lower_q = cleaned.lower()
        season_policy: Literal["post_monsoon", "pre_monsoon", "custom"]
        if any(w in lower_q for w in ["pre-monsoon", "pre monsoon", "summer", "march", "may"]):
            season_policy = "pre_monsoon"
            start_month_day = (3, 1)
            end_month_day = (5, 31)
            season_label = "Pre-Monsoon Mar-May"
        else:
            # Default: post-monsoon Oct-Nov for clear skies & max extent
            season_policy = "post_monsoon"
            start_month_day = (10, 1)
            end_month_day = (11, 30)
            season_label = "Post-Monsoon Oct-Nov"

        # 3. Task type detection
        task_type: Literal["water_change", "water_extent", "landcover_change"]
        if year_b is not None or any(
            w in lower_q for w in ["change", "expanded", "shrunk", "between", "difference"]
        ):
            task_type = "water_change"
            if year_b is None:
                year_b = year_a + 2  # default 2-year interval if change requested with 1 year
        else:
            task_type = "water_extent"

        # 4. Extract place name
        # Heuristics: "near <Place>", "in <Place>", "around <Place>", "at <Place>"
        place_match = re.search(
            r"\b(?:near|in|around|over|at|for|across)\s+([A-Za-z\s\-]+?)(?=\s+(?:between|from|during|in\s+\d{4}|since|\d{4}|$))",
            cleaned,
            re.IGNORECASE,
        )
        if place_match:
            place_name = place_match.group(1).strip()
        else:
            # Fallback check for known benchmark places
            for known in ["raipur", "vembanad", "sambhar", "bhopal", "hyderabad"]:
                if known in lower_q:
                    place_name = known.capitalize()
                    break
            else:
                place_name = "Raipur"  # Default canonical target

        # Geocode place name to bbox
        geo_res = self.geocoder.geocode(place_name)
        bbox = geo_res.bbox

        time_range_a = TimeInterval(
            start_date=date(year_a, start_month_day[0], start_month_day[1]),
            end_date=date(year_a, end_month_day[0], end_month_day[1]),
            label=f"{season_label} {year_a}",
        )

        time_range_b = None
        if task_type == "water_change" and year_b is not None:
            time_range_b = TimeInterval(
                start_date=date(year_b, start_month_day[0], start_month_day[1]),
                end_date=date(year_b, end_month_day[0], end_month_day[1]),
                label=f"{season_label} {year_b}",
            )

        return AnalysisPlan(
            task_type=task_type,
            aoi=AreaOfInterest(place_name=place_name, bbox=bbox),
            time_range_a=time_range_a,
            time_range_b=time_range_b,
            season_policy=season_policy,
            index="MNDWI",
            min_area_ha=0.1,
            output_formats=["geojson", "cog", "png", "report_markdown", "report_html", "csv"],
        )

    async def generate_plan(self, query: str) -> AnalysisPlan:
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
        direction = "expansion" if net_delta >= 0 else "reduction"

        narrative = (
            f"Analysis of {plan.aoi.place_name} between {plan.time_range_a.label} and "
            f"{plan.time_range_b.label if plan.time_range_b else 'N/A'} indicates a net "
            f"{direction} in surface water of {abs(net_delta):.2f} hectares ({pct_change:+.2f}%). "
            f"Persistent water accounted for {stats.get('persistent_water_ha', 0.0):.2f} ha, "
            f"while gained water totaled {stats.get('gained_water_ha', 0.0):.2f} ha and "
            f"lost water totaled {stats.get('lost_water_ha', 0.0):.2f} ha."
        )
        return narrative
