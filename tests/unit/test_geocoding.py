"""Tests for geocoding service and caching."""

from pathlib import Path
import pytest
from satellite_analyst.errors import GeocodingError
from satellite_analyst.planner.geocode import GeocodeService


def test_geocode_known_place(tmp_path: Path) -> None:
    cache_path = tmp_path / "geo_cache.json"
    service = GeocodeService(cache_file=cache_path)

    # Raipur is a known place
    bbox = service.geocode("Raipur")
    assert bbox.min_lon == 81.50
    assert bbox.max_lat == 21.35
    assert cache_path.exists()

    # Re-querying should read from cache
    bbox2 = service.geocode("raipur")
    assert bbox2.as_list() == bbox.as_list()


def test_geocode_unknown_offline_fallback(tmp_path: Path) -> None:
    cache_path = tmp_path / "geo_cache.json"
    service = GeocodeService(cache_file=cache_path, user_agent="test/1.0")

    # If geopy cannot resolve and no network, raises GeocodingError
    with pytest.raises(GeocodingError):
        service.geocode("NonExistentPlaceXYZ12345")
