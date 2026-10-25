"""Generate stratified random validation point sample across Raipur 2023 Sentinel-2 composite."""

import csv
import random
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from scipy.ndimage import binary_dilation, binary_erosion

# Find 2023 composite directory in data/cache
cache_dir = Path("data/cache")
comp_dir = None
for p in cache_dir.iterdir():
    if p.is_dir() and p.name.startswith("composite_"):
        prov_file = p / "cached_provenance.json"
        if prov_file.exists():
            text = prov_file.read_text(encoding="utf-8")
            if "2023" in text:
                comp_dir = p
                break

if not comp_dir:
    raise RuntimeError("No cached 2023 composite directory found in data/cache!")

print(f"Sampling points from: {comp_dir}")

with (
    rasterio.open(comp_dir / "cached_green.tif") as g_src,
    rasterio.open(comp_dir / "cached_swir1.tif") as s_src,
):
    green = g_src.read(1).astype(np.float32)
    swir1 = s_src.read(1).astype(np.float32)
    transform = g_src.transform
    crs = g_src.crs

denom = green + swir1
mndwi = np.where(denom > 0, (green - swir1) / denom, np.nan)
valid = np.isfinite(mndwi)

water_mask = (mndwi > 0.0) & valid
struct = np.ones((3, 3), dtype=bool)

# Interior water (eroded by 2 pixels)
interior_water = binary_erosion(water_mask, structure=struct, iterations=2) & valid

# Interior land (eroded land by 3 pixels)
interior_land = (
    binary_erosion(~water_mask, structure=struct, iterations=3) & valid & (mndwi < -0.05)
)

# Boundary zone (dilation of water XOR erosion of water)
edge_zone = (
    binary_dilation(water_mask, structure=struct, iterations=1)
    ^ binary_erosion(water_mask, structure=struct, iterations=1)
) & valid

rng = np.random.default_rng(20261025)


def sample_coords(mask: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(mask)
    if len(xs) < n:
        raise ValueError(f"Not enough pixels in stratum: {len(xs)} < {n}")
    choice = rng.choice(len(xs), size=n, replace=False)
    return ys[choice], xs[choice]


n_water = 60
n_land = 60
n_edge = 30

y_w, x_w = sample_coords(interior_water, n_water)
y_l, x_l = sample_coords(interior_land, n_land)
y_e, x_e = sample_coords(edge_zone, n_edge)

all_ys = np.concatenate([y_w, y_l, y_e])
all_xs = np.concatenate([x_w, x_l, x_e])
strata = ["water"] * n_water + ["non_water"] * n_land + ["boundary"] * n_edge
our_labels = (
    [1] * n_water + [0] * n_land + [int(mndwi[y, x] > 0.0) for y, x in zip(y_e, x_e, strict=False)]
)

# Transform pixel coords to UTM, then to WGS84
transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

out_rows = []
for i, (r, c, st, ol) in enumerate(zip(all_ys, all_xs, strata, our_labels, strict=False), start=1):
    east, north = rasterio.transform.xy(transform, r, c, offset="center")
    lon, lat = transformer.transform(east, north)
    val = float(mndwi[r, c])
    out_rows.append(
        {
            "point_id": f"pt_{i:03d}",
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "our_label": ol,
            "stratum": st,
            "mndwi_value": round(val, 4),
            "human_label": "",  # To be populated by human expert evaluator
            "notes": "",
        }
    )

# Shuffle points so strata are interspersed for unbiased manual labeling
random.Random(20261025).shuffle(out_rows)

out_csv = Path("evaluation/point_sample_template.csv")
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "point_id",
            "latitude",
            "longitude",
            "our_label",
            "stratum",
            "mndwi_value",
            "human_label",
            "notes",
        ],
    )
    writer.writeheader()
    writer.writerows(out_rows)

print(f"Generated {len(out_rows)} stratified sample points -> {out_csv}")
