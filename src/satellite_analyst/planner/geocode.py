"""Geocoding service with disk/memory caching and known place fallbacks."""

import json
from pathlib import Path
from typing import Any

from satellite_analyst.errors import GeocodingError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox

logger = get_logger(__name__)

# Known curated bounding boxes [min_lon, min_lat, max_lon, max_lat] for instant offline testing & benchmarks
KNOWN_PLACES: dict[str, list[float]] = {
    "raipur": [81.50, 21.15, 81.80, 21.35],
    "vembanad": [76.30, 9.50, 76.55, 9.90],
    "sambhar": [74.85, 26.85, 75.25, 27.10],
    "bhopal": [77.30, 23.15, 77.55, 23.35],
    "hyderabad": [78.35, 17.30, 78.60, 17.50],
}


class GeocodeService:
    """Geocodes place names into WGS84 bounding boxes with persistent caching."""

    def __init__(
        self,
        cache_file: Path | None = None,
        user_agent: str = "satellite-image-analyst/0.1.0",
    ) -> None:
        self.user_agent = user_agent
        self.cache_file = cache_file or Path("./data/cache/geocoding_cache.json")
        self._cache: dict[str, list[float]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read geocode cache: {e}")
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist geocode cache: {e}")

    def geocode(self, place_name: str, radius_km: float | None = None) -> BoundingBox:
        """Resolve a place name into a geographic bounding box."""
        normalized = place_name.strip().lower()

        # Check offline cache
        if normalized in self._cache:
            coords = self._cache[normalized]
            return BoundingBox(
                min_lon=coords[0],
                min_lat=coords[1],
                max_lon=coords[2],
                max_lat=coords[3],
            )

        # Check offline curated fixtures
        if normalized in KNOWN_PLACES:
            coords = KNOWN_PLACES[normalized]
            self._cache[normalized] = coords
            self._save_cache()
            return BoundingBox(
                min_lon=coords[0],
                min_lat=coords[1],
                max_lon=coords[2],
                max_lat=coords[3],
            )

        # Online lookup using geopy Nominatim
        try:
            from geopy.geocoders import Nominatim  # type: ignore[import-untyped]

            geolocator = Nominatim(user_agent=self.user_agent)
            location: Any = geolocator.geocode(place_name)
            if not location:
                raise GeocodingError(place=place_name, reason="Nominatim returned no results")

            raw = getattr(location, "raw", {})
            boundingbox = raw.get("boundingbox")
            if boundingbox and len(boundingbox) == 4:
                # Nominatim returns [south, north, west, east]
                min_lat = float(boundingbox[0])
                max_lat = float(boundingbox[1])
                min_lon = float(boundingbox[2])
                max_lon = float(boundingbox[3])
            else:
                # Create a ~0.15 deg box around point if bounding box is missing
                lat, lon = float(location.latitude), float(location.longitude)
                delta = (radius_km or 10.0) / 111.0
                min_lat, max_lat = lat - delta, lat + delta
                min_lon, max_lon = lon - delta, lon + delta

            coords = [min_lon, min_lat, max_lon, max_lat]
            self._cache[normalized] = coords
            self._save_cache()

            return BoundingBox(
                min_lon=min_lon,
                min_lat=min_lat,
                max_lon=max_lon,
                max_lat=max_lat,
            )
        except Exception as e:
            if isinstance(e, GeocodingError):
                raise
            raise GeocodingError(place=place_name, reason=str(e)) from e
