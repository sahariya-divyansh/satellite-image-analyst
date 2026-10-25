"""Geocoding service with rate limiting, retries, projected radius buffering, and offline fallback."""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pyproj import Transformer

from satellite_analyst.analysis.vectorize import estimate_utm_epsg
from satellite_analyst.config import get_settings
from satellite_analyst.errors import AOIAreaExceededError, GeocodingError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox

logger = get_logger(__name__)


@dataclass
class GeocodeResult:
    """Structured result of a geocoding lookup."""

    name: str
    lat: float
    lon: float
    bbox: BoundingBox
    display_name: str
    source: Literal["nominatim", "offline_gazetteer", "cache", "coordinate_literal"]
    area_km2: float


def compute_bbox_area_km2(bbox: BoundingBox) -> float:
    """Calculate geodesic planar area of bounding box in km2 via UTM reprojection."""
    mid_lon = (bbox.min_lon + bbox.max_lon) / 2.0
    mid_lat = (bbox.min_lat + bbox.max_lat) / 2.0
    utm_code = estimate_utm_epsg(mid_lon, mid_lat)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_code}", always_xy=True)

    x_min, y_min = transformer.transform(bbox.min_lon, bbox.min_lat)
    x_max, y_max = transformer.transform(bbox.max_lon, bbox.max_lat)

    width_m = abs(x_max - x_min)
    height_m = abs(y_max - y_min)
    return float((width_m * height_m) / 1_000_000.0)


def buffer_point_to_bbox(lat: float, lon: float, radius_km: float) -> BoundingBox:
    """Build a buffered bounding box around a point using local UTM projection."""
    utm_code = estimate_utm_epsg(lon, lat)
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_code}", always_xy=True)
    to_wgs84 = Transformer.from_crs(f"EPSG:{utm_code}", "EPSG:4326", always_xy=True)

    center_x, center_y = to_utm.transform(lon, lat)
    buffer_m = radius_km * 1000.0

    min_x, max_x = center_x - buffer_m, center_x + buffer_m
    min_y, max_y = center_y - buffer_m, center_y + buffer_m

    west_lon, south_lat = to_wgs84.transform(min_x, min_y)
    east_lon, north_lat = to_wgs84.transform(max_x, max_y)

    return BoundingBox(
        min_lon=min(west_lon, east_lon),
        min_lat=min(south_lat, north_lat),
        max_lon=max(west_lon, east_lon),
        max_lat=max(south_lat, north_lat),
    )


class GeocodeService:
    """Geocoding service with persistent disk cache, rate limiting, and gazetteer fallback."""

    def __init__(
        self,
        cache_file: Path | None = None,
        gazetteer_file: Path | None = None,
        user_agent: str | None = None,
        max_area_km2: float | None = None,
    ) -> None:
        settings = get_settings()
        self.user_agent = user_agent or settings.geocoding_user_agent
        self.cache_file = cache_file or (settings.cache_dir / "geocoding_cache.json")
        self.gazetteer_file = gazetteer_file or Path("data/gazetteer.json")
        self.max_area_km2 = max_area_km2 or settings.max_aoi_area_km2
        self._last_request_time = 0.0
        self._cache: dict[str, dict[str, Any]] = {}
        self._gazetteer: dict[str, dict[str, Any]] = {}

        self._load_cache()
        self._load_gazetteer()

    def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception as e:
                logger.warning(f"Error reading geocoding cache {self.cache_file}: {e}")
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving geocoding cache {self.cache_file}: {e}")

    def _load_gazetteer(self) -> None:
        if self.gazetteer_file.exists():
            try:
                with open(self.gazetteer_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("cities", []):
                        self._gazetteer[item["name"].strip().lower()] = item
            except Exception as e:
                logger.warning(f"Error reading gazetteer {self.gazetteer_file}: {e}")

    def _rate_limit(self) -> None:
        """Enforce Nominatim policy: 1 request per second."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def geocode(
        self,
        place_name: str,
        radius_km: float | None = None,
    ) -> GeocodeResult:
        """Geocode place name to GeocodeResult with validation and projected radius support."""
        normalized = place_name.strip().lower()
        if not normalized:
            raise GeocodingError(place=place_name, reason="Empty place name")

        # 0. Check for explicit decimal coordinates in input (e.g. "21.15N, 79.08E" or "21.15, 79.08")
        coord_match = re.search(
            r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*°?\s*([NSns])?[\s,]+(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([EWew])?\s*$",
            place_name.strip(),
        )
        if coord_match:
            c_lat = float(coord_match.group(1))
            if coord_match.group(2) and coord_match.group(2).upper() == "S":
                c_lat = -abs(c_lat)
            c_lon = float(coord_match.group(3))
            if coord_match.group(4) and coord_match.group(4).upper() == "W":
                c_lon = -abs(c_lon)
            if -90.0 <= c_lat <= 90.0 and -180.0 <= c_lon <= 180.0:
                rad = radius_km or 15.0
                c_bbox = buffer_point_to_bbox(c_lat, c_lon, rad)
                c_area = compute_bbox_area_km2(c_bbox)
                if c_area > self.max_area_km2:
                    raise AOIAreaExceededError(c_area, self.max_area_km2)
                return GeocodeResult(
                    name=place_name.strip(),
                    lat=c_lat,
                    lon=c_lon,
                    bbox=c_bbox,
                    display_name=f"Point Coordinate ({c_lat:.4f}, {c_lon:.4f})",
                    source="coordinate_literal",
                    area_km2=c_area,
                )

        cache_key = f"{normalized}__radius_{radius_km}" if radius_km else normalized

        # 1. Check persistent disk cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if isinstance(entry, list):
                bbox = BoundingBox(
                    min_lon=entry[0],
                    min_lat=entry[1],
                    max_lon=entry[2],
                    max_lat=entry[3],
                )
                lat = (bbox.min_lat + bbox.max_lat) / 2.0
                lon = (bbox.min_lon + bbox.max_lon) / 2.0
                disp_name = place_name
                cached_name = place_name
                area_km2 = compute_bbox_area_km2(bbox)
            else:
                bbox = BoundingBox(
                    min_lon=entry["bbox"][0],
                    min_lat=entry["bbox"][1],
                    max_lon=entry["bbox"][2],
                    max_lat=entry["bbox"][3],
                )
                lat = float(entry["lat"])
                lon = float(entry["lon"])
                disp_name = entry.get("display_name", place_name)
                cached_name = entry.get("name", place_name)
                area_km2 = float(entry.get("area_km2") or compute_bbox_area_km2(bbox))

            if area_km2 > self.max_area_km2:
                raise AOIAreaExceededError(area_km2, self.max_area_km2)

            return GeocodeResult(
                name=cached_name,
                lat=lat,
                lon=lon,
                bbox=bbox,
                display_name=disp_name,
                source="cache",
                area_km2=area_km2,
            )

        # 2. Try online Nominatim with rate limiting and exponential backoff
        nominatim_result = self._query_nominatim(place_name)

        if nominatim_result is not None:
            lat, lon, disp_name, raw_bbox = nominatim_result
            if radius_km is not None and radius_km > 0:
                bbox = buffer_point_to_bbox(lat, lon, radius_km)
            else:
                bbox = raw_bbox

            area_km2 = compute_bbox_area_km2(bbox)
            if area_km2 > self.max_area_km2:
                raise AOIAreaExceededError(area_km2, self.max_area_km2)

            res = GeocodeResult(
                name=place_name,
                lat=lat,
                lon=lon,
                bbox=bbox,
                display_name=disp_name,
                source="nominatim",
                area_km2=area_km2,
            )
            self._cache[cache_key] = {
                "name": place_name,
                "lat": lat,
                "lon": lon,
                "bbox": bbox.as_list(),
                "display_name": disp_name,
                "area_km2": area_km2,
            }
            self._save_cache()
            return res

        # 3. Fallback to offline gazetteer
        if normalized in self._gazetteer:
            g_item = self._gazetteer[normalized]
            lat = float(g_item["lat"])
            lon = float(g_item["lon"])
            disp_name = g_item.get("display_name", place_name)

            if radius_km is not None and radius_km > 0:
                bbox = buffer_point_to_bbox(lat, lon, radius_km)
            else:
                raw = g_item["bbox"]
                bbox = BoundingBox(
                    min_lon=raw[0],
                    min_lat=raw[1],
                    max_lon=raw[2],
                    max_lat=raw[3],
                )

            area_km2 = compute_bbox_area_km2(bbox)
            if area_km2 > self.max_area_km2:
                raise AOIAreaExceededError(area_km2, self.max_area_km2)

            res = GeocodeResult(
                name=g_item.get("name", place_name),
                lat=lat,
                lon=lon,
                bbox=bbox,
                display_name=disp_name,
                source="offline_gazetteer",
                area_km2=area_km2,
            )
            self._cache[cache_key] = {
                "name": g_item.get("name", place_name),
                "lat": lat,
                "lon": lon,
                "bbox": bbox.as_list(),
                "display_name": disp_name,
                "area_km2": area_km2,
            }
            self._save_cache()
            return res

        raise GeocodingError(
            place=place_name,
            reason="Location not found via Nominatim and not present in offline gazetteer.",
        )

    def _query_nominatim(
        self,
        place_name: str,
        retries: int = 3,
    ) -> tuple[float, float, str, BoundingBox] | None:
        """Query Nominatim with rate limiting and exponential backoff."""
        try:
            from geopy.geocoders import Nominatim  # type: ignore[import-untyped]
        except ImportError:
            return None

        geolocator = Nominatim(user_agent=self.user_agent, timeout=5)

        for attempt in range(retries):
            self._rate_limit()
            try:
                location: Any = geolocator.geocode(place_name)
                if location is None:
                    return None

                lat = float(location.latitude)
                lon = float(location.longitude)
                disp_name = getattr(location, "address", place_name)
                raw = getattr(location, "raw", {})
                b = raw.get("boundingbox")

                if b and len(b) == 4:
                    # Nominatim returns [south, north, west, east]
                    raw_bbox = BoundingBox(
                        min_lon=float(b[2]),
                        min_lat=float(b[0]),
                        max_lon=float(b[3]),
                        max_lat=float(b[1]),
                    )
                else:
                    raw_bbox = buffer_point_to_bbox(lat, lon, radius_km=10.0)

                return lat, lon, disp_name, raw_bbox
            except Exception as e:
                logger.warning(
                    f"Nominatim lookup failed for '{place_name}' (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    time.sleep(2**attempt)
                else:
                    return None

        return None
