"""Build and execute the Phase 2 water change walkthrough notebook."""

import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def build_and_run_notebook(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cells_spec = [
        {
            "type": "markdown",
            "source": [
                "# Natural-Language Satellite Image Analyst: Water Change Walkthrough\n",
                "\n",
                "This notebook provides a defensible, step-by-step walkthrough of the Phase 2 geospatial pipeline for surface water change detection.\n",
                "\n",
                "**Dataset**: Operational Sentinel-2 L2A BOA Reflectance over **Raipur, Chhattisgarh** ($30 \\times 30\\text{ km}$, $900\\text{ km}^2$, Post-Monsoon Oct–Nov 2023 vs 2025).\n",
                "**Sensor Calibration**: SCL cloud/shadow filtering and ESA baseline $\\ge 04.00$ `BOA_ADD_OFFSET = -1000` radiometric correction.\n",
                "**Equal-Area Projection**: UTM Zone 44N (EPSG:32644) at 10m native pixel resolution.",
            ],
        },
        {
            "type": "markdown",
            "source": [
                "## 1. Load Pre-Computed Sentinel-2 L2A Composites\n",
                "We read the same-season median composites generated from 33 Sentinel-2 scenes in 2023 and 22 scenes in 2025.",
            ],
        },
        {
            "type": "code",
            "source": [
                "from pathlib import Path\n",
                "import numpy as np\n",
                "import rasterio\n",
                "\n",
                "# Paths to cached composites (supports execution from root or notebooks/)\n",
                "base_dir = Path('outputs') if Path('outputs').exists() else Path('../outputs')\n",
                "g23_p = base_dir / 'raipur_2023_post_monsoon_green.tif'\n",
                "s23_p = base_dir / 'raipur_2023_post_monsoon_swir1.tif'\n",
                "g25_p = base_dir / 'raipur_2025_post_monsoon_green.tif'\n",
                "s25_p = base_dir / 'raipur_2025_post_monsoon_swir1.tif'\n",
                "\n",
                "with rasterio.open(g23_p) as src:\n",
                "    green_2023 = src.read(1)\n",
                "    crs = src.crs\n",
                "    transform = src.transform\n",
                "    shape = green_2023.shape\n",
                "\n",
                "with rasterio.open(s23_p) as src:\n",
                "    swir1_2023 = src.read(1)\n",
                "with rasterio.open(g25_p) as src:\n",
                "    green_2025 = src.read(1)\n",
                "with rasterio.open(s25_p) as src:\n",
                "    swir1_2025 = src.read(1)\n",
                "\n",
                "print(f'Raster Grid Dimensions: {shape} ({shape[0]*shape[1]:,} pixels)')\n",
                "print(f'Coordinate Reference System: {crs}')\n",
                "print(f'Spatial Resolution: {abs(transform.a):.1f}m x {abs(transform.e):.1f}m per pixel')\n",
                "print(f'2023 Green BOA Reflectance [p2, p98]: [{np.nanpercentile(green_2023, 2):.4f}, {np.nanpercentile(green_2023, 98):.4f}]')\n",
                "print(f'2025 Green BOA Reflectance [p2, p98]: [{np.nanpercentile(green_2025, 2):.4f}, {np.nanpercentile(green_2025, 98):.4f}]')",
            ],
        },
        {
            "type": "markdown",
            "source": [
                "## 2. Compute Modified Normalized Difference Water Index (MNDWI)\n",
                "$$\\text{MNDWI} = \\frac{\\text{Green} - \\text{SWIR1}}{\\text{Green} + \\text{SWIR1}} = \\frac{\\text{B03} - \\text{B11}}{\\text{B03} + \\text{B11}}$$\n",
                "MNDWI suppresses built-up urban features and soil noise much more effectively than McFeeters NDWI.",
            ],
        },
        {
            "type": "code",
            "source": [
                "from satellite_analyst.analysis.indices import compute_mndwi\n",
                "\n",
                "mndwi_2023 = compute_mndwi(green_2023, swir1_2023)\n",
                "mndwi_2025 = compute_mndwi(green_2025, swir1_2025)\n",
                "\n",
                "print(f'2023 MNDWI Range: [{np.nanmin(mndwi_2023):.3f}, {np.nanmax(mndwi_2023):.3f}] (Mean: {np.nanmean(mndwi_2023):.3f})')\n",
                "print(f'2025 MNDWI Range: [{np.nanmin(mndwi_2025):.3f}, {np.nanmax(mndwi_2025):.3f}] (Mean: {np.nanmean(mndwi_2025):.3f})')",
            ],
        },
        {
            "type": "markdown",
            "source": [
                "## 3. Histogram Bimodality Verification & Shared Threshold Policy\n",
                "When water constitutes a small fraction of the total landscape ($< 5\\%$), standard Otsu thresholding erroneously bisects the unimodal dry land / agricultural peak.\n",
                "Our pipeline computes Otsu between-class variance ratio $\\eta$ and mean separation $\\Delta\\mu$. If the distribution is not bimodal, it defensively falls back to `0.0`.",
            ],
        },
        {
            "type": "code",
            "source": [
                "from satellite_analyst.analysis.water import compute_otsu_threshold, segment_dual_period_water\n",
                "\n",
                "valid_pooled = np.concatenate([mndwi_2023[np.isfinite(mndwi_2023)], mndwi_2025[np.isfinite(mndwi_2025)]])\n",
                "raw_otsu, is_bimodal, eta = compute_otsu_threshold(valid_pooled, bimodality_min_ratio=0.70)\n",
                "\n",
                "print(f'Pooled Otsu Split: {raw_otsu:.4f}')\n",
                "print(f'Variance Separation Ratio (eta): {eta:.4f} (Required: >= 0.7000)')\n",
                "print(f'Is Bimodal Land-Water Distribution: {is_bimodal}')\n",
                "if not is_bimodal:\n",
                "    print('  --> Defense Triggered: Fallback to fixed threshold 0.0000 to prevent false change.')\n",
                "\n",
                "mask_2023, mask_2025 = segment_dual_period_water(\n",
                "    mndwi_2023, mndwi_2025, policy='shared', min_area_ha=0.1\n",
                ")\n",
                "\n",
                "area_23_ha = np.sum(mask_2023.mask) * 0.01\n",
                "area_25_ha = np.sum(mask_2025.mask) * 0.01\n",
                "print(f'\\nApplied Strategy: {mask_2023.method} (Threshold: {mask_2023.threshold:.4f})')\n",
                "print(f'2023 Segmented Surface Water: {area_23_ha:,.2f} ha ({mask_2023.water_fraction*100:.2f}% of AOI)')\n",
                "print(f'2025 Segmented Surface Water: {area_25_ha:,.2f} ha ({mask_2025.water_fraction*100:.2f}% of AOI)')",
            ],
        },
        {
            "type": "markdown",
            "source": [
                "## 4. 3-Class Change Classification\n",
                "We categorize transitions into:\n",
                "- **Persistent (3)**: Water present in both 2023 and 2025\n",
                "- **Gained (1)**: Dry in 2023, water in 2025\n",
                "- **Lost (2)**: Water in 2023, dry in 2025\n",
                "- **Dry (0)**: Non-water in both periods\n",
                "- **NoData (255)**: Invalid / low-confidence observations in either period",
            ],
        },
        {
            "type": "code",
            "source": [
                "from satellite_analyst.analysis.change import detect_water_change, WaterChangeClass\n",
                "\n",
                "change_raster = detect_water_change(mask_2023, mask_2025, min_valid_obs=2)\n",
                "\n",
                "count_dry = int(np.sum(change_raster == WaterChangeClass.DRY))\n",
                "count_gained = int(np.sum(change_raster == WaterChangeClass.GAINED))\n",
                "count_lost = int(np.sum(change_raster == WaterChangeClass.LOST))\n",
                "count_persistent = int(np.sum(change_raster == WaterChangeClass.PERSISTENT))\n",
                "\n",
                "print('Pixel Transitions (1 px = 0.01 ha):')\n",
                "print(f'  Persistent Water: {count_persistent:,} px ({count_persistent*0.01:,.2f} ha)')\n",
                "print(f'  Gained Water:     {count_gained:,} px ({count_gained*0.01:,.2f} ha)')\n",
                "print(f'  Lost Water:       {count_lost:,} px ({count_lost*0.01:,.2f} ha)')\n",
                "print(f'  Dry Land:         {count_dry:,} px ({count_dry*0.01:,.2f} ha)')",
            ],
        },
        {
            "type": "markdown",
            "source": [
                "## 5. Connected-Component Waterbody Tracking & Statistics\n",
                "We group water bodies by connected components of $\\text{union}(\\text{Water}_{2023}, \\text{Water}_{2025})$, assign deterministic geographic hash IDs, and compute regional totals.",
            ],
        },
        {
            "type": "code",
            "source": [
                "from satellite_analyst.analysis.vectorize import extract_waterbody_records\n",
                "from satellite_analyst.analysis.stats import compute_summary_stats\n",
                "import pandas as pd\n",
                "\n",
                "wb_records, wb_gdf = extract_waterbody_records(\n",
                "    mask_2023.mask,\n",
                "    mask_2025.mask,\n",
                "    transform=transform,\n",
                "    crs='EPSG:32644',\n",
                "    min_area_ha=0.1\n",
                ")\n",
                "\n",
                "stats = compute_summary_stats(change_raster, wb_records, pixel_size_m=10.0)\n",
                "print(f'Total Tracked Waterbody Features: {len(wb_records):,}')\n",
                "print(f'Net Regional Water Change: {stats.net_change_ha:+.2f} ha ({stats.percent_change:+.2f}%)')\n",
                "\n",
                "df_wb = pd.DataFrame([r.to_dict() for r in wb_records])\n",
                "print('\\nTop 10 Waterbodies with Largest Dynamics:')\n",
                "print(df_wb[['waterbody_id', 'centroid_lon', 'centroid_lat', 'area_period_a_ha', 'area_period_b_ha', 'net_change_ha', 'status']].head(10).to_string(index=False))\n",
                "\n",
                "# Sanity check on Budha Talab (Vivekananda Sarovar in central Raipur)\n",
                "budha = df_wb[df_wb['waterbody_id'] == 'wb_dca58935']\n",
                "print('\\nSanity Check: Budha Talab / Vivekananda Sarovar:')\n",
                "print(budha[['waterbody_id', 'centroid_lon', 'centroid_lat', 'area_period_a_ha', 'area_period_b_ha', 'status']].to_string(index=False))",
            ],
        },
    ]

    # Clean execution namespace
    exec_globals: dict[str, Any] = {
        "__builtins__": __builtins__,
    }

    nb_cells: list[dict[str, Any]] = []
    execution_counter = 1

    for cell in cells_spec:
        if cell["type"] == "markdown":
            nb_cells.append(
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": cell["source"],
                }
            )
        elif cell["type"] == "code":
            code_str = "".join(cell["source"])
            # Capture output
            stdout_capture = io.StringIO()
            old_stdout = sys.stdout

            try:
                sys.stdout = stdout_capture
                exec(code_str, exec_globals)
            except Exception as e:
                traceback.print_exc()
                raise RuntimeError(f"Notebook execution failed in cell:\n{code_str}") from e
            finally:
                sys.stdout = old_stdout

            output_text = stdout_capture.getvalue()
            outputs: list[dict[str, Any]] = []
            if output_text:
                outputs.append(
                    {
                        "name": "stdout",
                        "output_type": "stream",
                        "text": output_text.splitlines(keepends=True),
                    }
                )

            nb_cells.append(
                {
                    "cell_type": "code",
                    "execution_count": execution_counter,
                    "metadata": {},
                    "outputs": outputs,
                    "source": cell["source"],
                }
            )
            execution_counter += 1

    nb_data = {
        "cells": nb_cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3 (ipykernel)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.12",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(nb_data, f, indent=2)

    print(f"Notebook successfully generated and executed: {output_path}")


if __name__ == "__main__":
    build_and_run_notebook(Path("notebooks/01_water_change_walkthrough.ipynb"))
