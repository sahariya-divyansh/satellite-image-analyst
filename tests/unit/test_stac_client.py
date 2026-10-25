"""Unit tests for STAC client querying, caching, and provider fallback."""

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from satellite_analyst.data.cache import RasterDataCache
from satellite_analyst.data.stac_client import (
    SceneCollection,
    SceneItem,
    STACClient,
)
from satellite_analyst.errors import STACSearchError
from satellite_analyst.planner.schema import BoundingBox, TimeInterval


@pytest.fixture
def dummy_bbox() -> BoundingBox:
    return BoundingBox(min_lon=81.5, min_lat=21.1, max_lon=81.8, max_lat=21.3)


@pytest.fixture
def dummy_interval() -> TimeInterval:
    return TimeInterval(
        start_date=date(2023, 10, 1),
        end_date=date(2023, 11, 30),
        label="Post-Monsoon Oct-Nov 2023",
    )


def test_stac_cache_determinism(
    tmp_path: Path, dummy_bbox: BoundingBox, dummy_interval: TimeInterval
) -> None:
    """STAC responses are cached to disk so subsequent queries are deterministic and offline."""
    cache = RasterDataCache(cache_dir=tmp_path)
    client = STACClient(provider="planetary_computer", cache=cache)

    mock_collection = SceneCollection(
        items=[
            SceneItem(
                id="S2A_20231015_TEST",
                datetime="2023-10-15T05:17:51Z",
                cloud_cover=12.5,
                mgrs_tile="44QND",
                processing_baseline="04.00",
                assets={"B03": "https://example.com/b03.tif"},
            )
        ],
        provider="planetary_computer",
        bbox=dummy_bbox.as_list(),
        time_interval=dummy_interval.label,
        total_found=1,
    )

    with patch.object(client, "_execute_search", return_value=mock_collection) as mock_search:
        # First query: calls search and caches result
        res1 = client.search_scenes(bbox=dummy_bbox, time_range=dummy_interval)
        assert mock_search.call_count == 1
        assert len(res1.items) == 1
        assert res1.items[0].id == "S2A_20231015_TEST"

        # Second query: must return from cache without calling search again
        res2 = client.search_scenes(bbox=dummy_bbox, time_range=dummy_interval)
        assert mock_search.call_count == 1
        assert res2.to_dict() == res1.to_dict()


def test_stac_auto_fallback_to_secondary(
    tmp_path: Path, dummy_bbox: BoundingBox, dummy_interval: TimeInterval
) -> None:
    """When primary provider fails, client automatically retries secondary provider."""
    cache = RasterDataCache(cache_dir=tmp_path)
    client = STACClient(provider="planetary_computer", cache=cache)

    fallback_collection = SceneCollection(
        items=[
            SceneItem(
                id="S2A_EARTH_SEARCH_TEST",
                datetime="2023-10-20T05:17:51Z",
                cloud_cover=5.0,
                mgrs_tile="44QND",
                processing_baseline="04.00",
                assets={"B03": "https://example.com/earth_search_b03.tif"},
            )
        ],
        provider="earth_search",
        bbox=dummy_bbox.as_list(),
        time_interval=dummy_interval.label,
        total_found=1,
    )

    def side_effect(provider: str, **_kwargs: Any) -> SceneCollection:
        if provider == "planetary_computer":
            raise RuntimeError("Planetary computer timeout 504")
        return fallback_collection

    with patch.object(client, "_execute_search", side_effect=side_effect):
        res = client.search_scenes(bbox=dummy_bbox, time_range=dummy_interval)
        assert res.provider == "earth_search"
        assert res.items[0].id == "S2A_EARTH_SEARCH_TEST"


def test_stac_both_providers_fail_raises_typed_error(
    tmp_path: Path, dummy_bbox: BoundingBox, dummy_interval: TimeInterval
) -> None:
    """When both primary and fallback fail, client raises STACSearchError."""
    cache = RasterDataCache(cache_dir=tmp_path)
    client = STACClient(provider="planetary_computer", cache=cache)

    with patch.object(client, "_execute_search", side_effect=RuntimeError("Network unreachable")):
        with pytest.raises(STACSearchError) as exc_info:
            client.search_scenes(bbox=dummy_bbox, time_range=dummy_interval)

        assert exc_info.value.code == "STAC_SEARCH_FAILED"
        assert "Both STAC providers failed" in exc_info.value.message


@pytest.mark.network
def test_live_stac_planetary_computer_query(
    dummy_bbox: BoundingBox, dummy_interval: TimeInterval
) -> None:
    """Live network test querying Microsoft Planetary Computer for Raipur scenes."""
    client = STACClient(provider="planetary_computer")
    collection = client.search_scenes(
        bbox=dummy_bbox,
        time_range=dummy_interval,
        max_cloud_cover=40.0,
    )
    assert collection.total_found > 0
    assert len(collection.items) > 0
    assert "B03" in collection.items[0].assets
