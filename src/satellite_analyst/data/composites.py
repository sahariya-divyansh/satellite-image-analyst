"""Cloud masking and temporal median compositing routines."""

from dataclasses import dataclass
from typing import Any

import numpy as np

from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox, TimeInterval

logger = get_logger(__name__)

# Sentinel-2 Scene Classification Layer (SCL) classes to mask:
# 0: No data, 1: Saturated/defective, 3: Cloud shadow, 8: Cloud med prob,
# 9: Cloud high prob, 10: Cirrus, 11: Snow/ice
SCL_MASK_CLASSES: frozenset[int] = frozenset([0, 1, 3, 8, 9, 10, 11])


@dataclass
class SeasonalComposite:
    """Represents a cloud-masked, same-season median composite."""

    green: np.ndarray  # B03 at 10m
    swir1: np.ndarray  # B11 resampled to 10m
    nir: np.ndarray | None  # B08 optional
    time_interval: TimeInterval
    bbox: BoundingBox
    crs: str
    transform: Any
    scene_ids: list[str]
    cloud_fraction: float


class CompositeBuilder:
    """Builds cloud-free median composites across a target seasonal window."""

    def __init__(self, stac_client: Any = None) -> None:
        self.stac_client = stac_client

    def build_median_composite(
        self,
        bbox: BoundingBox,
        time_range: TimeInterval,
        max_cloud_cover: float = 30.0,
    ) -> SeasonalComposite:
        """Download band rasters, apply SCL mask, and compute pixel-wise median."""
        raise NotImplementedError("CompositeBuilder concrete implementation enabled in Phase 1.")
