"""STAC client for Sentinel-2 L2A querying with Planetary Computer and Earth Search auto-fallback."""

from dataclasses import asdict, dataclass
from typing import Any

from satellite_analyst.config import get_settings
from satellite_analyst.data.cache import RasterDataCache
from satellite_analyst.errors import STACSearchError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox, TimeInterval

logger = get_logger(__name__)

PLANETARY_COMPUTER_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH_STAC_URL = "https://earth-search.aws.element84.com/v1"


@dataclass
class SceneItem:
    """Metadata and asset access for an individual Sentinel-2 L2A scene."""

    id: str
    datetime: str
    cloud_cover: float
    mgrs_tile: str
    processing_baseline: str
    assets: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SceneCollection:
    """Deterministic collection of retrieved Sentinel-2 scenes."""

    items: list[SceneItem]
    provider: str
    bbox: list[float]
    time_interval: str
    total_found: int

    def scene_ids(self) -> list[str]:
        return [item.id for item in self.items]

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "provider": self.provider,
            "bbox": self.bbox,
            "time_interval": self.time_interval,
            "total_found": self.total_found,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneCollection":
        items = [SceneItem(**item_data) for item_data in data.get("items", [])]
        return cls(
            items=items,
            provider=data.get("provider", "unknown"),
            bbox=data.get("bbox", []),
            time_interval=data.get("time_interval", ""),
            total_found=data.get("total_found", len(items)),
        )


class STACClient:
    """STAC discovery client with multi-provider fallback and deterministic caching."""

    def __init__(
        self,
        provider: str | None = None,
        cache: RasterDataCache | None = None,
        subscription_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self.provider = provider or settings.stac_provider
        self.cache = cache or RasterDataCache()
        self.subscription_key = subscription_key or settings.pc_sdk_subscription_key

    def _get_endpoint(self, provider: str) -> str:
        if provider == "earth_search":
            return EARTH_SEARCH_STAC_URL
        return PLANETARY_COMPUTER_STAC_URL

    def search_scenes(
        self,
        bbox: BoundingBox,
        time_range: TimeInterval,
        max_cloud_cover: float = 40.0,
        limit: int = 100,
    ) -> SceneCollection:
        """Search Sentinel-2 scenes with disk caching and automatic provider fallback."""
        cache_key = {
            "bbox": bbox.as_list(),
            "start": str(time_range.start_date),
            "end": str(time_range.end_date),
            "cloud": max_cloud_cover,
            "provider": self.provider,
        }

        # 1. Check local STAC query cache
        cached_data = self.cache.get_metadata(cache_key)
        if cached_data is not None:
            logger.info("Retrieved Sentinel-2 STAC response from local cache")
            return SceneCollection.from_dict(cached_data)

        # 2. Try primary provider
        primary = self.provider
        secondary = "earth_search" if primary == "planetary_computer" else "planetary_computer"

        try:
            collection = self._execute_search(
                provider=primary,
                bbox=bbox,
                time_range=time_range,
                max_cloud_cover=max_cloud_cover,
                limit=limit,
            )
        except Exception as e:
            logger.warning(
                f"STAC search failed on primary provider '{primary}': {e}. Attempting fallback to '{secondary}'."
            )
            try:
                collection = self._execute_search(
                    provider=secondary,
                    bbox=bbox,
                    time_range=time_range,
                    max_cloud_cover=max_cloud_cover,
                    limit=limit,
                )
            except Exception as e_fallback:
                raise STACSearchError(
                    f"Both STAC providers failed: Primary ({primary}: {e}), Fallback ({secondary}: {e_fallback})",
                    details={"bbox": bbox.as_list(), "interval": time_range.label},
                ) from e_fallback

        # Save to disk cache for reproducible offline runs
        self.cache.put_metadata(cache_key, collection.to_dict())
        return collection

    def _execute_search(
        self,
        provider: str,
        bbox: BoundingBox,
        time_range: TimeInterval,
        max_cloud_cover: float,
        limit: int,
    ) -> SceneCollection:
        """Execute pystac_client search against target endpoint and extract scene metadata."""
        import planetary_computer  # type: ignore[import-untyped]
        from pystac_client import Client  # type: ignore[import-untyped]

        endpoint = self._get_endpoint(provider)
        collection_id = "sentinel-2-l2a"

        datetime_param = f"{time_range.start_date.isoformat()}/{time_range.end_date.isoformat()}"

        client = Client.open(endpoint)
        search = client.search(
            collections=[collection_id],
            bbox=bbox.as_list(),
            datetime=datetime_param,
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
            limit=limit,
        )

        raw_items = list(search.items())

        # Sort deterministically: by datetime ascending, then item id
        def _sort_key(item: Any) -> tuple[str, str]:
            dt = str(getattr(item, "datetime", "") or item.properties.get("datetime", ""))
            return (dt, str(item.id))

        raw_items.sort(key=_sort_key)

        scene_items: list[SceneItem] = []

        for item in raw_items:
            # If using Planetary Computer, sign asset URLs in place
            if provider == "planetary_computer":
                planetary_computer.sign_inplace(item)

            props = getattr(item, "properties", {})
            cloud = float(props.get("eo:cloud_cover", 0.0))
            mgrs = str(
                props.get("s2:mgrs_tile")
                or f"{props.get('mgrs:utm_zone', '')}{props.get('mgrs:latitude_band', '')}{props.get('mgrs:grid_square', '')}"
            )
            baseline = str(props.get("s2:processing_baseline", "04.00"))

            # Extract asset hrefs for relevant bands
            assets_dict: dict[str, str] = {}
            for asset_key in ["B03", "B11", "SCL", "B08", "visual"]:
                # Earth search uses lowercase 'green', 'swir16', 'scl', or uppercase band names
                candidate_keys = [
                    asset_key,
                    asset_key.lower(),
                    "green" if asset_key == "B03" else None,
                    "swir16" if asset_key == "B11" else None,
                    "scl" if asset_key == "SCL" else None,
                    "nir" if asset_key == "B08" else None,
                ]
                for ck in candidate_keys:
                    if ck and ck in item.assets:
                        assets_dict[asset_key] = item.assets[ck].href
                        break

            dt_str = str(getattr(item, "datetime", "") or props.get("datetime", ""))

            scene_items.append(
                SceneItem(
                    id=str(item.id),
                    datetime=dt_str,
                    cloud_cover=cloud,
                    mgrs_tile=mgrs,
                    processing_baseline=baseline,
                    assets=assets_dict,
                )
            )

        return SceneCollection(
            items=scene_items,
            provider=provider,
            bbox=bbox.as_list(),
            time_interval=time_range.label,
            total_found=len(scene_items),
        )
