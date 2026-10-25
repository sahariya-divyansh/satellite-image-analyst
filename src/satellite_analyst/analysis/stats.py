"""Summary statistics and per-waterbody tabulation module."""

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from satellite_analyst.analysis.change import WaterChangeClass


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

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary representation."""
        return asdict(self)


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
    valid_area_fraction: float
    total_aoi_ha: float
    valid_aoi_ha: float

    def to_dict(self) -> dict[str, Any]:
        """Convert summary statistics to dictionary representation."""
        return asdict(self)


def compute_summary_stats(
    change_raster: np.ndarray,
    waterbodies: list[WaterBodyRecord],
    pixel_size_m: float = 10.0,
) -> AreaSummaryStats:
    """Compute aggregate statistics from 3-class change raster and water body records.

    Hectare conversion is derived from the spatial resolution:
    1 pixel (10m x 10m) = 100 m² = 0.01 hectares.
    """
    pixel_ha = (pixel_size_m**2) / 10000.0

    count_dry = int(np.sum(change_raster == WaterChangeClass.DRY))
    count_gained = int(np.sum(change_raster == WaterChangeClass.GAINED))
    count_lost = int(np.sum(change_raster == WaterChangeClass.LOST))
    count_persistent = int(np.sum(change_raster == WaterChangeClass.PERSISTENT))
    total_pixels = int(change_raster.size)

    valid_pixels = count_dry + count_gained + count_lost + count_persistent
    valid_fraction = (valid_pixels / total_pixels) if total_pixels > 0 else 0.0

    ha_gained = count_gained * pixel_ha
    ha_lost = count_lost * pixel_ha
    ha_persistent = count_persistent * pixel_ha

    total_a = ha_persistent + ha_lost
    total_b = ha_persistent + ha_gained
    net_change = total_b - total_a
    pct_change = (net_change / total_a * 100.0) if total_a > 0.0 else 0.0

    total_aoi_ha = total_pixels * pixel_ha
    valid_aoi_ha = valid_pixels * pixel_ha

    return AreaSummaryStats(
        total_water_period_a_ha=round(total_a, 2),
        total_water_period_b_ha=round(total_b, 2),
        net_change_ha=round(net_change, 2),
        percent_change=round(pct_change, 2),
        gained_water_ha=round(ha_gained, 2),
        lost_water_ha=round(ha_lost, 2),
        persistent_water_ha=round(ha_persistent, 2),
        waterbody_count=len(waterbodies),
        valid_area_fraction=round(valid_fraction, 4),
        total_aoi_ha=round(total_aoi_ha, 2),
        valid_aoi_ha=round(valid_aoi_ha, 2),
    )
