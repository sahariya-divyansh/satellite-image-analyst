"""Unit tests for geocoding service, projected radius buffering, gazetteer, and AOI limits."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from satellite_analyst.errors import AOIAreaExceededError, GeocodingError
from satellite_analyst.planner.geocode import (
    GeocodeService,
    buffer_point_to_bbox,
    compute_bbox_area_km2,
)
from satellite_analyst.planner.schema import BoundingBox


def test_compute_bbox_area_km2() -> None:
    """Verify planar area calculation via UTM projection."""
    # A 0.2 x 0.2 deg box near equator is approx 22.2 x 22.2 km ~= 490 km2
    bbox = BoundingBox(min_lon=81.50, min_lat=21.15, max_lon=81.70, max_lat=21.35)
    area = compute_bbox_area_km2(bbox)
    assert 400.0 < area < 600.0


def test_buffer_point_to_bbox_projected_math() -> None:
    """Projected radius buffer must construct an equal-area box around (lat, lon)."""
    lat, lon = 21.2514, 81.6296
    radius_km = 10.0
    bbox = buffer_point_to_bbox(lat=lat, lon=lon, radius_km=radius_km)

    # Center must lie within bounding box
    assert bbox.min_lon < lon < bbox.max_lon
    assert bbox.min_lat < lat < bbox.max_lat

    # Area of (2*10 km) x (2*10 km) box should be approx 400 km2
    area = compute_bbox_area_km2(bbox)
    assert pytest.approx(area, rel=0.05) == 400.0


def test_max_aoi_guard(tmp_path: Path) -> None:
    """Exceeding max_area_km2 threshold must raise AOIAreaExceededError."""
    service = GeocodeService(
        cache_file=tmp_path / "cache.json",
        max_area_km2=500.0,  # small threshold
    )

    # 30 km radius -> (60 km)^2 = 3600 km2 > 500 km2
    with pytest.raises(AOIAreaExceededError) as exc_info:
        service.geocode("Raipur", radius_km=30.0)

    assert "exceeds maximum allowed threshold" in exc_info.value.message
    assert exc_info.value.code == "AOI_AREA_EXCEEDED"


def test_offline_gazetteer_fallback(tmp_path: Path) -> None:
    """When Nominatim fails/offline, query falls back to bundled gazetteer and marks source."""
    cache_path = tmp_path / "cache.json"
    service = GeocodeService(cache_file=cache_path)

    # Mock Nominatim to simulate offline / network error
    with patch.object(service, "_query_nominatim", return_value=None):
        res = service.geocode("Bhilai")
        assert res.name.lower() == "bhilai"
        assert res.source == "offline_gazetteer"
        assert "Chhattisgarh" in res.display_name


def test_geocode_cache_hit_and_miss(tmp_path: Path) -> None:
    """Cache misses query provider; cache hits return cached entry without network."""
    cache_path = tmp_path / "cache.json"
    service = GeocodeService(cache_file=cache_path)

    fake_bbox = BoundingBox(min_lon=81.5, min_lat=21.1, max_lon=81.8, max_lat=21.3)
    mock_nominatim = MagicMock(return_value=(21.25, 81.63, "Raipur, India", fake_bbox))

    with patch.object(service, "_query_nominatim", mock_nominatim):
        # 1. First call: cache miss -> queries provider
        res1 = service.geocode("Raipur")
        assert res1.source == "nominatim"
        assert mock_nominatim.call_count == 1

        # 2. Second call: cache hit -> does not query provider
        res2 = service.geocode("Raipur")
        assert res2.source == "cache"
        assert mock_nominatim.call_count == 1
        assert res2.bbox.as_list() == res1.bbox.as_list()


def test_geocode_unknown_place_raises_error(tmp_path: Path) -> None:
    """Non-existent place not in gazetteer and not online raises GeocodingError."""
    service = GeocodeService(cache_file=tmp_path / "cache.json")
    with (
        patch.object(service, "_query_nominatim", return_value=None),
        pytest.raises(GeocodingError),
    ):
        service.geocode("NonExistentAtlantisPlace999")
