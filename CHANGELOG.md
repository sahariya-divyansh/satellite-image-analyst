# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-10-28

### Added
- **Empirical Scene Subsampling Framework**: Replaced synthetic perturbation noise with empirical scene subsampling across all 8 post-monsoon seasons (2018–2025) in Raipur. For each year, $k = \min(10, \lfloor 0.80 \times N \rfloor)$ scenes are randomly drawn without replacement across 20 seeded repetitions. Empirical 8-year mean subsampling spread is $674.47\,\text{ha}$ (mean $\sigma = 188.11\,\text{ha}$), ranging from $342.71\,\text{ha}$ (2024) to $1,509.53\,\text{ha}$ (2025).
- **Candidate Water Mask Variants**: Added implementations of `AWEIsh` (Automated Water Extraction Index shadow), `AWEInsh` (non-shadow), and `MNDWI + NDVI < 0.1` in `indices.py`, with an opt-in configuration flag `water_mask_variant: str = "mndwi"` in `Settings`.
- **Water Mask Precision Diagnosis**: Implemented `evaluation/diagnose_water_masks.py` cross-tabulating Sentinel-2 water pixels against ESA WorldCover 10m land cover and JRC GSW occurrence. Diagnosed that in post-monsoon Raipur, 12.3% (2020) to 22.1% (2023) of detected water pixels lie on cropland and 31.8% to 49.8% have 0% historical occurrence, demonstrating that precision disagreement with permanent water references is driven by genuine post-monsoon seasonal agricultural inundation.
- **Mask Variant Benchmarking against ESA WorldCover**: Evaluated variants on dev pool (Raipur 2020: AWEIsh F1 0.3615 vs MNDWI 0.3571; Bhopal 2020: AWEIsh F1 0.7957 vs MNDWI 0.7897; Pooled Dev: AWEIsh 0.6834 vs MNDWI 0.6804) and untouched held-out test set (Jodhpur 2020: AWEIsh 0.3216 vs MNDWI 0.3164). Confirmed statistical equivalence via overlapping 95% bootstrap CIs and retained baseline MNDWI as default for band I/O efficiency.
- **Expanded Unit Test Suite**: Increased unit test count to 109 passing tests and boosted test coverage from 80.50% to 83.31% across core packages without pragmas.

### Changed
- Removed all occurrences of synthetic noise models, the synthetic `99.71 ha` spread, and per-year synthetic `±` spreads across code, documentation, and evaluation results.
- Updated `evaluation/results/interannual_variability_raipur.json` and `docs/images/raipur_interannual_variability.png` with empirical 95% error bands.
- Contextualized the observed Raipur 2023 to 2025 shift ($+46.66\,\text{ha}$, $+2.79\%$) against the empirical subsampling spread ($674.47\,\text{ha}$) and median consecutive-year step ($272.97\,\text{ha}$, without 2019: $244.39\,\text{ha}$), affirming the `within noise / inconclusive` verdict under both Baseline MNDWI ($-74.91\,\text{ha}$) and AWEIsh ($-29.02\,\text{ha}$).

## [0.1.0] - 2026-10-28

### Added
- Natural language query planner supporting regex/keyword parsing and LLM backends (Gemini, OpenAI, Ollama) with strict Pydantic plan validation.
- STAC client querying Microsoft Planetary Computer for Sentinel-2 Level-2A surface reflectance data.
- Temporal median compositing with SCL cloud/shadow filtering and automatic per-scene BOA offset correction (`-1000 DN`) for ESA baseline $\ge 04.00$.
- Modified Normalized Difference Water Index (MNDWI) calculation with 10m spatial resampling.
- Adaptive thresholding (Otsu bimodality diagnostics) and 3-class change categorization (Persistent, Expansion, Contraction).
- Local equal-area UTM spatial reprojection and contiguous vector polygon extraction with $0.1\,\text{ha}$ minimum mapping unit.
- Claim Grounding Verifier cross-checking LLM narrative reports against deterministic pipeline outputs with numeric tolerance checks.
- Interactive Leaflet-based Web UI and FastAPI backend supporting layer toggles, statistical drawers, and offline `DEMO_MODE`.
- JRC Global Surface Water validation harness supporting automated Planetary Computer STAC retrieval, 50% majority aggregation, boundary exclusion, block-bootstrap 95% CIs, and size stratification across Raipur, Bhopal, and Jodhpur.
- Multi-year inter-annual time-series analysis (Raipur 2018–2025) and stable-pixel radiometric continuity audit.
- Independent stratified 150-point sample validation template for expert ground truth verification.
- Comprehensive documentation suite: Architecture, Methodology, Evaluation & Benchmarks, Limitations, ADR 0001, Documentation Index, and Release Notes.
- Dockerfile, docker-compose orchestration, and GitHub Actions CI.
