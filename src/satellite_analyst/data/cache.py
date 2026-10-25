"""Disk-based cache for STAC query responses and downloaded raster chunks."""

import hashlib
import json
from pathlib import Path
from typing import Any

from satellite_analyst.logging import get_logger

logger = get_logger(__name__)


class RasterDataCache:
    """Manages deterministic on-disk caching of query metadata and raster tiles."""

    def __init__(self, cache_dir: Path | None = None, max_size_gb: int = 10) -> None:
        self.cache_dir = cache_dir or Path("./data/cache")
        self.max_size_gb = max_size_gb
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, key_data: dict[str, Any] | str) -> str:
        serialized = (
            json.dumps(key_data, sort_keys=True) if isinstance(key_data, dict) else key_data
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_metadata(self, key: str | dict[str, Any]) -> dict[str, Any] | None:
        """Retrieve cached metadata if available."""
        h = self._hash_key(key)
        target = self.cache_dir / f"meta_{h}.json"
        if target.exists():
            try:
                with open(target, encoding="utf-8") as f:
                    data: dict[str, Any] = json.load(f)
                    return data
            except Exception as e:
                logger.warning(f"Error reading metadata cache {target}: {e}")
        return None

    def put_metadata(self, key: str | dict[str, Any], data: dict[str, Any]) -> None:
        """Store metadata in disk cache."""
        h = self._hash_key(key)
        target = self.cache_dir / f"meta_{h}.json"
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Error writing metadata cache {target}: {e}")

    def get_raster_path(self, cache_key: str, suffix: str = ".tif") -> Path:
        """Return deterministic path for a raster file."""
        h = self._hash_key(cache_key)
        return self.cache_dir / f"raster_{h}{suffix}"
