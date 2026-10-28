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


def test_stac_per_item_baseline_detection(
    tmp_path: Path, dummy_bbox: BoundingBox, dummy_interval: TimeInterval
) -> None:
    """STAC client resolves per-item processing baseline dynamically from props, N-tag, or acquisition date."""
    from unittest.mock import MagicMock

    cache = RasterDataCache(cache_dir=tmp_path)
    client = STACClient(provider="earth_search", cache=cache)

    # 1. Legacy item with explicit s2:processing_baseline
    item_legacy = MagicMock()
    item_legacy.id = "S2A_MSIL2A_20201015T051751_R019_T44QNJ_20201015T080000"
    item_legacy.datetime = "2020-10-15T05:17:51Z"
    item_legacy.properties = {"s2:processing_baseline": "02.14", "eo:cloud_cover": 5.0}
    item_legacy.assets = {"B03": MagicMock(href="https://example.com/b03.tif")}

    # 2. Legacy item with N-tag in ID
    item_ntag = MagicMock()
    item_ntag.id = "S2B_MSIL2A_20210320T050649_N0300_R019_T44QNJ_20210320T080000"
    item_ntag.datetime = "2021-03-20T05:06:49Z"
    item_ntag.properties = {"eo:cloud_cover": 2.0}
    item_ntag.assets = {"B03": MagicMock(href="https://example.com/b03.tif")}

    # 3. Modern 2023 item
    item_modern = MagicMock()
    item_modern.id = "S2A_MSIL2A_20231015T050721_N0509_R019_T44QNJ_20231015T110000"
    item_modern.datetime = "2023-10-15T05:07:21Z"
    item_modern.properties = {"s2:processing_baseline": "05.09", "eo:cloud_cover": 1.0}
    # 4. Item without baseline or N-tag before Jan 2022 -> 02.14
    item_inferred_legacy = MagicMock()
    item_inferred_legacy.id = "S2A_MSIL2A_20210515_NO_TAG"
    item_inferred_legacy.datetime = "2021-05-15T05:00:00Z"
    item_inferred_legacy.properties = {"eo:cloud_cover": 3.0}
    item_inferred_legacy.assets = {"B03": MagicMock(href="https://example.com/b03.tif")}

    # 5. Item without baseline or N-tag after Jan 2022 -> 04.00
    item_inferred_modern = MagicMock()
    item_inferred_modern.id = "S2A_MSIL2A_20220615_NO_TAG"
    item_inferred_modern.datetime = "2022-06-15T05:00:00Z"
    item_inferred_modern.properties = {"eo:cloud_cover": 4.0}
    item_inferred_modern.assets = {"B03": MagicMock(href="https://example.com/b03.tif")}

    mock_pystac_client = MagicMock()
    mock_search = MagicMock()
    mock_search.items.return_value = [
        item_legacy,
        item_ntag,
        item_modern,
        item_inferred_legacy,
        item_inferred_modern,
    ]
    mock_pystac_client.search.return_value = mock_search

    with (
        patch("pystac_client.Client.open", return_value=mock_pystac_client),
        patch("planetary_computer.sign_inplace") as mock_sign,
    ):
        collection = client._execute_search(
            provider="planetary_computer",
            bbox=dummy_bbox,
            time_range=dummy_interval,
            max_cloud_cover=40.0,
            limit=10,
        )
        assert mock_sign.call_count == 5

    assert len(collection.items) == 5
    # Sorted by datetime:
    # 0: 2020-10-15 -> 02.14
    # 1: 2021-03-20 -> 03.00
    # 2: 2021-05-15 -> 02.14 (inferred from date < 2022-01-25)
    # 3: 2022-06-15 -> 04.00 (inferred from date >= 2022-01-25)
    # 4: 2023-10-15 -> 05.09
    assert collection.items[0].processing_baseline == "02.14"
    assert collection.items[1].processing_baseline == "03.00"
    assert collection.items[2].processing_baseline == "02.14"
    assert collection.items[3].processing_baseline == "04.00"
    assert collection.items[4].processing_baseline == "05.09"


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
