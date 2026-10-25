"""Summary statistics and per-waterbody tabulation module."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class WaterBodyRecord:
    """Individual segmented water body tracking record."""

    waterbody_id: str
    centroid_lon: float
    centroid_lat: float
    area_period_a_ha: float
    area_period_b_ha: float
    net_change_ha: float
    percent_change: float
    status: str  # "expanded" | "shrunk" | "persistent" | "new" | "disappeared"


@dataclass
class AreaSummaryStats:
    """Aggregated regional statistics for an AOI."""

    total_water_period_a_ha: float
    total_water_period_b_ha: float
    net_change_ha: float
    percent_change: float
    gained_water_ha: float
    lost_water_ha: float
    persistent_water_ha: float
    waterbody_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_summary_stats(
    waterbodies: list[WaterBodyRecord],
    pixel_gained_ha: float,
    pixel_lost_ha: float,
    pixel_persistent_ha: float,
) -> AreaSummaryStats:
    """Compute aggregate statistics from per-waterbody records and pixel areas."""
    total_a = pixel_persistent_ha + pixel_lost_ha
    total_b = pixel_persistent_ha + pixel_gained_ha
    net_change = total_b - total_a
    pct_change = (net_change / total_a * 100.0) if total_a > 0 else 0.0

    return AreaSummaryStats(
        total_water_period_a_ha=round(total_a, 2),
        total_water_period_b_ha=round(total_b, 2),
        net_change_ha=round(net_change, 2),
        percent_change=round(pct_change, 2),
        gained_water_ha=round(pixel_gained_ha, 2),
        lost_water_ha=round(pixel_lost_ha, 2),
        persistent_water_ha=round(pixel_persistent_ha, 2),
        waterbody_count=len(waterbodies),
    )
