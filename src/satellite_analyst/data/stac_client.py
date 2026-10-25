"""STAC client for querying Sentinel-2 L2A assets."""

from typing import Any

from satellite_analyst.data.cache import RasterDataCache
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox, TimeInterval

logger = get_logger(__name__)

PLANETARY_COMPUTER_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH_STAC_URL = "https://earth-search.aws.element84.com/v1"


class STACClient:
    """Client for discovering Sentinel-2 L2A scenes via STAC APIs."""

    def __init__(
        self,
        provider: str = "planetary_computer",
        cache: RasterDataCache | None = None,
        subscription_key: str | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache or RasterDataCache()
        self.subscription_key = subscription_key
        self.endpoint = (
            PLANETARY_COMPUTER_STAC_URL
            if provider == "planetary_computer"
            else EARTH_SEARCH_STAC_URL
        )

    def search_scenes(
        self,
        bbox: BoundingBox,
        time_range: TimeInterval,
        max_cloud_cover: float = 30.0,
        _limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search for Sentinel-2 L2A items matching spatial and temporal constraints."""
        cache_key = {
            "endpoint": self.endpoint,
            "bbox": bbox.as_list(),
            "start": str(time_range.start_date),
            "end": str(time_range.end_date),
            "cloud": max_cloud_cover,
        }
        cached = self.cache.get_metadata(cache_key)
        if cached is not None and "items" in cached:
            logger.info("Retrieved STAC scenes from local cache")
            items: list[dict[str, Any]] = cached["items"]
            return items

        # In Phase 1, pystac_client and planetary_computer will be connected
        logger.info(
            f"Querying STAC {self.endpoint} for bbox={bbox.as_list()} interval={time_range.label}"
        )
        return []
