# Release Notes: v0.1.0

**Release Date**: October 28, 2026  
**Author**: Divyansh  
**Repository**: [satellite-image-analyst](https://github.com/sahariya-divyansh/satellite-image-analyst)

---

## Overview

We are pleased to release **v0.1.0** of the **Natural-Language Satellite Image Analyst**, an Earth observation system designed to translate natural language questions into defensible, reproducible remote sensing pipelines.

A central engineering principle of this system is that **LLMs cannot and must never calculate geospatial numbers**. In this release, natural language understanding is decoupled from scientific computation: an LLM acts purely as an architectural compiler (producing a strict Pydantic plan) and a grounded reporter, while deterministic raster math and vector geoprocessing compute 100% of the indices, surface areas, and change statistics.

---

## Key Capabilities in v0.1.0

### 1. Natural Language Planner
- Translates conversational, technical, and multilingual (Hindi/Hinglish) queries into validated `AnalysisPlan` specifications.
- Supports Rule-Based fallback, Google Gemini (`gemini-1.5-flash`), OpenAI (`gpt-4o-mini`), and local Ollama (`llama3.2`).
- Robust coordinate parsing (decimal degrees `21.15N, 79.08E`), temporal relative dates (*"over the last 3 years"*), radial buffering (*"within 25 km"*), and typed refusals for out-of-scope or pre-operational archive requests (<2017).

### 2. Deterministic Remote Sensing Pipeline
- **Sentinel-2 L2A STAC Client**: Automated search and streaming from Microsoft Planetary Computer.
- **Scene Classification Masking**: Strict filtering of cloud, shadow, and cirrus pixels using Sentinel-2 SCL layers.
- **BOA Offset Calibration**: Automatic detection of ESA processing baseline $\ge 04.00$ with $-1000\,\text{DN}$ offset correction, preserving radiometric continuity across the January 2022 archive boundary.
- **MNDWI & Adaptive Thresholding**: 10m green and resampled SWIR1 band ratioing with automated Otsu histogram bimodality checking.
- **3-Class Change Categorization**: Classifies surface water into Persistent, Expansion, and Contraction, reprojected into local equal-area UTM coordinates.
- **Vector Polygon Extraction**: Contiguous polygon clustering filtered by a $0.1\,\text{ha}$ minimum mapping unit.

### 3. Claim Grounding Verification
- Cryptographically verified narrative reports.
- Grounding verifier scans generated text against pipeline numerical outputs with configurable tolerance, flagging any ungrounded figures.

### 4. Interactive Web Interface & API
- Modern responsive dashboard with Leaflet interactive mapping.
- Layer toggles for Persistent Water, Expansion, Contraction, and Bounding Box envelopes.
- Provenance inspection drawer and exportable Markdown reports.
- Offline `DEMO_MODE=true` option for environments without live STAC access.

---

## Reproducible Benchmark Highlights

- **Planner Development Benchmark ($n=42$)**: $85.71\%$ Exact Match (development set, not held-out).
- **Planner Held-Out Benchmark v1 ($n=30$)**: $76.67\%$ Exact Match (frozen independent benchmark).
- **Planner Held-Out Benchmark v2 ($n=20$)**: $95.00\%$ original (19/20); $100.00\%$ (20/20) after correcting a test expectation to match pipeline spatial guardrails.
- **JRC Global Surface Water Agreement (Post-Monsoon 2020)**:
  - **Raipur, CG**: Permanent Water IoU = $0.1650$ (F1: $0.2832$, 95% CI `[0.1399, 0.1900]`); Seasonal Water IoU = $0.2210$.
  - **Bhopal, MP**: Permanent Water IoU = $0.5472$ (F1: $0.7073$, 95% CI `[0.5099, 0.5856]`); Large Lake Recall = $95.40\%$; Seasonal Water IoU = $0.6470$.
  - **Jodhpur, RJ**: Permanent Water IoU = $0.1199$ (F1: $0.2141$, 95% CI `[0.0420, 0.2018]`); Seasonal Water IoU = $0.1540$.
- **Raipur Inter-Annual Series (2018–2025)**:
  - Median consecutive-year step: $272.97\,\text{ha}$; Mean step: $458.44\,\text{ha}$; Multi-year $\sigma = 321.72\,\text{ha}$.
  - Leave-one-out without 2019: Median step = $244.39\,\text{ha}$, Mean step = $245.59\,\text{ha}$, $\sigma = 117.76\,\text{ha}$.
  - Observed 2023 $\to$ 2025 change ($+46.66\,\text{ha}$, $+2.79\%$) is consistent with within-noise fluctuations; classified as `within noise / inconclusive`.
- **Stable-Pixel Radiometric Audit**: Mean green reflectance difference across the Jan 2022 baseline change is $\Delta = -0.0006$ ($-0.70\%$) on $n=55,304$ identical stable land pixels.
- **Code Coverage**: $80.50\%$ branch/statement coverage with 96 unit tests passing.

---

## What v0.1.0 Does Not Claim

- Not an accuracy-certified regulatory product; requires sub-meter ground validation for legal disputes.
- No causal attribution: physical shifts are reported without asserting uncomputed precipitation or dam inflow causes.
- Reference agreement differences reflect sensor resolution (10m vs 30m), timing, and post-monsoon phenology.
- Independent 150-point sample template published; human ground truth labels pending manual inspection.
