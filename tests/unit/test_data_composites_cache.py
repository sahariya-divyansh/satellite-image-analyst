"""Unit tests for composite caching, error cases, and adapters."""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import xarray as xr

from satellite_analyst.data.adapters.bhoonidhi import BhoonidhiAdapter
from satellite_analyst.data.cache import RasterDataCache
from satellite_analyst.data.composites import (
    CompositeBuilder,
    CompositeResult,
)
from satellite_analyst.data.stac_client import SceneCollection, STACClient
from satellite_analyst.errors import InsufficientImageryError
from satellite_analyst.planner.schema import BoundingBox, TimeInterval


@pytest.fixture
def sample_composite() -> CompositeResult:
    xs = np.array([100.0, 110.0])
    ys = np.array([200.0, 190.0])
    green_arr = np.array([[0.2, 0.3], [0.4, 0.5]], dtype=np.float32)
    swir1_arr = np.array([[0.1, 0.15], [0.2, 0.25]], dtype=np.float32)
    valid_arr = np.array([[2, 2], [2, 2]], dtype=np.int16)

    return CompositeResult(
        green=xr.DataArray(
            green_arr, coords={"y": ys, "x": xs}, dims=["y", "x"], attrs={"crs": "EPSG:32644"}
        ),
        swir1=xr.DataArray(
            swir1_arr, coords={"y": ys, "x": xs}, dims=["y", "x"], attrs={"crs": "EPSG:32644"}
        ),
        valid_count=xr.DataArray(
            valid_arr, coords={"y": ys, "x": xs}, dims=["y", "x"], attrs={"crs": "EPSG:32644"}
        ),
        scene_ids=["S2A_TEST_01"],
        date_range=("2023-10-01", "2023-11-30"),
        per_scene_cloud=[{"id": "S2A_TEST_01", "cloud": 5.0}],
        bbox=[81.5, 21.1, 81.8, 21.3],
        crs="EPSG:32644",
        valid_fraction=1.0,
        software_version="0.1.0",
    )


def test_composite_disk_cache_roundtrip(tmp_path: Path, sample_composite: CompositeResult) -> None:
    """CompositeBuilder can persist and reload cached composites identically."""
    builder = CompositeBuilder(cache=RasterDataCache(cache_dir=tmp_path))
    cache_dir = tmp_path / "test_cache"

    params = {"bbox": [81.5, 21.1, 81.8, 21.3], "start": "2023-10-01"}
    builder._save_cached_composite(sample_composite, cache_dir, params)

    reloaded = builder._load_cached_composite(cache_dir)
    assert reloaded is not None
    assert reloaded.crs == "EPSG:32644"
    assert reloaded.scene_ids == ["S2A_TEST_01"]
    assert reloaded.green.shape == (2, 2)
    assert pytest.approx(float(reloaded.green.values[0, 0])) == 0.2


def test_build_composite_empty_imagery_raises_error(tmp_path: Path) -> None:
    """When STAC returns zero scenes, InsufficientImageryError is raised."""
    mock_stac = MagicMock(spec=STACClient)
    mock_stac.search_scenes.return_value = SceneCollection(
        items=[],
        provider="planetary_computer",
        bbox=[81.5, 21.1, 81.8, 21.3],
        time_interval="Oct-Nov 2023",
        total_found=0,
    )

    from datetime import date

    builder = CompositeBuilder(stac_client=mock_stac, cache=RasterDataCache(cache_dir=tmp_path))
    bbox = BoundingBox(min_lon=81.5, min_lat=21.1, max_lon=81.8, max_lat=21.3)
    interval = TimeInterval(
        start_date=date(2023, 10, 1), end_date=date(2023, 11, 30), label="Oct-Nov 2023"
    )

    with pytest.raises(InsufficientImageryError) as exc_info:
        builder.build_composite(bbox=bbox, time_range=interval)

    assert exc_info.value.code == "INSUFFICIENT_IMAGERY"


def test_bhoonidhi_adapter_stub() -> None:
    """Verify Bhoonidhi adapter initializes and returns granules list."""
    from datetime import date

    adapter = BhoonidhiAdapter()
    bbox = BoundingBox(min_lon=81.5, min_lat=21.1, max_lon=81.8, max_lat=21.3)
    interval = TimeInterval(
        start_date=date(2023, 10, 1), end_date=date(2023, 11, 30), label="Oct-Nov 2023"
    )

    products = adapter.search_products(
        satellite="RESOURCESAT-2A",
        sensor="AWIFS",
        bbox=bbox,
        time_range=interval,
    )
    assert isinstance(products, list)
    assert len(products) == 0
