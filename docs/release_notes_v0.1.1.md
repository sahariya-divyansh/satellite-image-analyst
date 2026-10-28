# Release Notes: v0.1.1

**Release Date**: October 28, 2026  
**Author**: Divyansh  
**Repository**: [satellite-image-analyst](https://github.com/sahariya-divyansh/satellite-image-analyst)

---

## Overview

**v0.1.1** is a scientific rigor and transparency release for the **Natural-Language Satellite Image Analyst**. This release accomplishes two major scientific objectives:

1. **Replaces Synthetic Perturbation with Empirical Scene Subsampling**: Eliminates synthetic noise models and the synthetic $99.71\,\text{ha}$ spread figure across all code and documentation. Implements empirical jackknife-style scene subsampling ($k = \min(10, \lfloor 0.80 \times N \rfloor)$ across 20 seeded repetitions) across the entire 2018–2025 multi-year record for Raipur.
2. **Diagnoses Water Mask Precision & Benchmarks Extraction Variants**: Evaluates Sentinel-2 water pixels against ESA WorldCover 10m and JRC Global Surface Water occurrence. Diagnoses that lower precision in post-monsoon agricultural plains is driven by genuine seasonal post-monsoon crop inundation and flooded paddy fields rather than urban misclassification. Benchmarks four candidate water mask formulations (`MNDWI`, `AWEIsh`, `AWEInsh`, `MNDWI + NDVI < 0.1`) across a development pool (Raipur, Bhopal) and an untouched held-out test set (Jodhpur).

---

## Key Highlights & Real Measured Results

### 1. Empirical Scene Subsampling (Raipur 2018–2025)

To quantify composite composition variance without synthetic assumptions, $k = \min(10, \lfloor 0.80 \times N \rfloor)$ scenes were drawn at random without replacement across 20 seeded repetitions per post-monsoon season:

| Year | Available Scenes ($N$) | Subsample Size ($k$) | Full Composite Area (ha) | Subsample Mean (ha) | Subsample Std ($\sigma$, ha) | Empirical 95% CI (ha) | 95% Spread (ha) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2018** | 13 | 10 | **1,543.39** | 1,546.91 | 130.81 | `[1311.67, 1768.40]` | 456.73 |
| **2019** | 20 | 10 | **2,500.39** | 2,694.40 | 366.92 | `[2197.12, 3472.31]` | 1,275.19 |
| **2020** | 18 | 10 | **1,476.28** | 1,462.59 | 105.62 | `[1234.66, 1604.48]` | 369.82 |
| **2021** | 10 | 8 | **1,749.25** | 1,719.37 | 157.07 | `[1380.99, 1957.76]` | 576.77 |
| **2022** | 23 | 10 | **1,455.69** | 1,466.13 | 103.64 | `[1339.23, 1702.25]` | 363.02 |
| **2023** | 15 | 10 | **1,674.99** | 1,814.44 | 164.16 | `[1569.15, 2071.18]` | 502.03 |
| **2024** | 14 | 10 | **1,477.26** | 1,497.26 | 96.09 | `[1387.86, 1730.57]` | 342.71 |
| **2025** | 13 | 10 | **1,721.65** | 1,769.58 | 380.57 | `[964.55, 2474.08]` | 1,509.53 |

- **Average Empirical 95% Subsampling Spread**: **$674.47\,\text{ha}$** (mean $\sigma = 188.11\,\text{ha}$).
- **Comparison to Observed Change**: The observed $+46.66\,\text{ha}$ shift ($+2.79\%$) between 2023 and 2025 is **>14 times smaller** than the empirical subsampling spread ($674.47\,\text{ha}$) and **<1/5th** of the median consecutive-year step ($272.97\,\text{ha}$, without 2019: $244.39\,\text{ha}$).
- **Scientific Verdict**: The observed difference is unambiguously consistent with within-noise composite fluctuation.

### 2. Water Mask Precision Diagnosis & Extraction Variant Benchmarking

#### Diagnostic Finding (Land Cover Breakdown)
Cross-tabulation of Sentinel-2 water masks against ESA WorldCover 10m and JRC GSW occurrence revealed:
- **Raipur 2020**: **12.28%** of water pixels fall on Cropland, **11.53%** on Grassland; **31.80%** have 0% historical occurrence in JRC GSW.
- **Raipur 2023**: **22.05%** of water pixels fall on Cropland, **17.51%** on Grassland; **49.75%** have 0% historical occurrence in JRC GSW.
- **Bhopal 2020 (Contrast)**: **74.31%** fall on Permanent Water (class 80), only **8.43%** on cropland; **62.77%** have $\ge 50\%$ occurrence in JRC GSW.

Disagreement with permanent water references in alluvial agricultural plains is driven by physical post-monsoon standing water in paddy fields rather than spectral confusion with urban land.

#### Variant Benchmarking against ESA WorldCover (Class 80)
| Partition / AOI | Baseline MNDWI F1 | AWEIsh F1 | AWEInsh F1 | MNDWI + NDVI F1 |
| :--- | :---: | :---: | :---: | :---: |
| **Raipur 2020** (Dev) | 0.3571 `[0.334, 0.389]` | **0.3615** `[0.338, 0.394]` | 0.3158 `[0.290, 0.349]` | 0.3205 `[0.299, 0.352]` |
| **Bhopal 2020** (Dev) | 0.7897 `[0.773, 0.804]` | **0.7957** `[0.780, 0.811]` | 0.7944 `[0.778, 0.810]` | 0.7938 `[0.778, 0.808]` |
| **Pooled Dev** (Raipur + Bhopal) | 0.6804 | **0.6834** | 0.6768 | 0.6736 |
| **Jodhpur 2020** (Held-Out) | 0.3164 `[0.247, 0.379]` | **0.3216** `[0.252, 0.386]` | 0.2470 `[0.168, 0.314]` | 0.3078 `[0.240, 0.373]` |

- **Statistical Equivalence**: 95% bootstrap confidence intervals for AWEIsh and Baseline MNDWI overlap completely across all three sites.
- **Production Default**: Baseline `mndwi` is retained as default because it achieves equivalent F1 while requiring only 2 spectral bands (B03, B11) instead of 5 bands (B02, B03, B08, B11, B12), halving memory and bandwidth consumption. `water_mask_variant: str = "mndwi"` is exposed in `Settings`.
- **Rerun Consistency**: Under both variants, Raipur 2023 $\to$ 2025 change is negative and small (MNDWI: $-74.91\,\text{ha}$, $-4.05\%$; AWEIsh: $-29.02\,\text{ha}$, $-1.56\%$), both classified as `within noise / inconclusive`.

### 3. Test Coverage & Quality Assurance
- **Coverage**: **83.31%** branch/statement coverage (exceeding the $\ge 83\%$ requirement).
- **Unit Tests**: **109 passing unit tests** across analysis, data, planner, API, and validation components (all non-network, zero `pragma: no cover`).
- **Static Typing**: `mypy src tests evaluation` passes with 0 issues across 65 source files.
- **Linting & Formatting**: `ruff` checks and formats pass cleanly.

---

## Upgrade Guide

`v0.1.1` is backward-compatible with `v0.1.0`. All existing workflows, configurations, and API endpoints continue to work without modification.
