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
    net_change_pct: float
    gained_water_ha: float
    lost_water_ha: float
    persistent_water_ha: float
    churn_ratio: float
    significance: str
    waterbody_count: int
    valid_area_fraction: float
    total_aoi_ha: float
    valid_aoi_ha: float
    headline_1ha: dict[str, Any]

    @property
    def total_aoi_km2(self) -> float:
        """Total bounding box AOI area in square kilometers."""
        return round(self.total_aoi_ha / 100.0, 2)

    @property
    def valid_aoi_km2(self) -> float:
        """Clear-sky valid analyzed AOI area in square kilometers."""
        return round(self.valid_aoi_ha / 100.0, 2)

    def to_dict(self) -> dict[str, Any]:
        """Convert summary statistics to dictionary representation."""
        d = asdict(self)
        d["total_aoi_km2"] = self.total_aoi_km2
        d["valid_aoi_km2"] = self.valid_aoi_km2
        return d


@dataclass
class ThresholdSensitivity:
    """Evaluation of net change sensitivity across varied MNDWI thresholds."""

    threshold_low: float
    threshold_mid: float
    threshold_high: float
    net_change_low_ha: float
    net_change_mid_ha: float
    net_change_high_ha: float
    net_change_range_ha: list[float]
    sign_flips: bool
    is_stable: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Convert sensitivity evaluation to dictionary representation."""
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

    # Churn ratio and scientific significance assessment
    total_active_water = ha_persistent + ha_gained + ha_lost
    churn_ratio = (ha_gained + ha_lost) / total_active_water if total_active_water > 0.0 else 0.0

    if ha_persistent == 0.0 and (ha_gained > 0.0 or ha_lost > 0.0):
        significance = "inconclusive (zero baseline persistent water)"
    elif abs(net_change) < 0.10 * ha_persistent or churn_ratio > 0.25:
        significance = "within noise / inconclusive"
    elif net_change > 0.0:
        significance = "significant expansion"
    elif net_change < 0.0:
        significance = "significant contraction"
    else:
        significance = "no change"

    # Headline statistics for waterbodies >= 1.0 ha
    wb_1ha = [wb for wb in waterbodies if max(wb.area_period_a_ha, wb.area_period_b_ha) >= 1.0]
    total_a_1ha = sum(wb.area_period_a_ha for wb in wb_1ha)
    total_b_1ha = sum(wb.area_period_b_ha for wb in wb_1ha)
    net_1ha = total_b_1ha - total_a_1ha
    pct_1ha = (net_1ha / total_a_1ha * 100.0) if total_a_1ha > 0.0 else 0.0

    headline_1ha = {
        "count": len(wb_1ha),
        "total_water_period_a_ha": round(total_a_1ha, 2),
        "total_water_period_b_ha": round(total_b_1ha, 2),
        "net_change_ha": round(net_1ha, 2),
        "percent_change": round(pct_1ha, 2),
    }

    return AreaSummaryStats(
        total_water_period_a_ha=round(total_a, 2),
        total_water_period_b_ha=round(total_b, 2),
        net_change_ha=round(net_change, 2),
        percent_change=round(pct_change, 2),
        net_change_pct=round(pct_change, 2),
        gained_water_ha=round(ha_gained, 2),
        lost_water_ha=round(ha_lost, 2),
        persistent_water_ha=round(ha_persistent, 2),
        churn_ratio=round(churn_ratio, 4),
        significance=significance,
        waterbody_count=len(waterbodies),
        valid_area_fraction=round(valid_fraction, 4),
        total_aoi_ha=round(total_aoi_ha, 2),
        valid_aoi_ha=round(valid_aoi_ha, 2),
        headline_1ha=headline_1ha,
    )


def compute_threshold_sensitivity(
    mndwi_a: np.ndarray,
    mndwi_b: np.ndarray,
    valid_mask: np.ndarray,
    mid_threshold: float = 0.0,
    offset: float = 0.1,
    pixel_size_m: float = 10.0,
) -> ThresholdSensitivity:
    """Evaluate stability of net change across perturbed MNDWI threshold values."""
    pixel_ha = (pixel_size_m**2) / 10000.0
    t_low = round(mid_threshold - offset, 2)
    t_mid = round(mid_threshold, 2)
    t_high = round(mid_threshold + offset, 2)

    def _net_change(t: float) -> float:
        wa = (mndwi_a > t) & valid_mask
        wb = (mndwi_b > t) & valid_mask
        return round(float(np.sum(wb) - np.sum(wa)) * pixel_ha, 2)

    nc_low = _net_change(t_low)
    nc_mid = _net_change(t_mid)
    nc_high = _net_change(t_high)

    all_nc = [nc_low, nc_mid, nc_high]
    min_nc = min(all_nc)
    max_nc = max(all_nc)
    sign_flips = bool(min_nc < 0.0 and max_nc > 0.0)
    is_stable = bool(
        not sign_flips
        and (
            abs(max_nc - min_nc) <= abs(nc_mid) * 0.5
            if nc_mid != 0.0
            else (max_nc - min_nc) <= 10.0
        )
    )

    if sign_flips:
        summary = (
            f"Sensitive: Net change flips sign across thresholds [{t_low}, {t_mid}, {t_high}] "
            f"ranging from {min_nc:+.2f} ha to {max_nc:+.2f} ha."
        )
    else:
        summary = (
            f"Robust: Net change maintains consistent sign ({min_nc:+.2f} ha to {max_nc:+.2f} ha) "
            f"across thresholds [{t_low}, {t_mid}, {t_high}]."
        )

    return ThresholdSensitivity(
        threshold_low=t_low,
        threshold_mid=t_mid,
        threshold_high=t_high,
        net_change_low_ha=nc_low,
        net_change_mid_ha=nc_mid,
        net_change_high_ha=nc_high,
        net_change_range_ha=[min_nc, max_nc],
        sign_flips=sign_flips,
        is_stable=is_stable,
        summary=summary,
    )
