# 1. LLM Never Computes Geospatial Numbers or Facts

Date: 2025-10-25  
Status: Accepted  

## Context

Natural Language Interfaces for Earth Observation (EO) frequently suffer from hallucinations when large language models are asked to compute, summarize, or estimate physical quantities directly (such as water surface area, percentage change, coordinates, or pixel counts). 

In scientific and operational remote sensing (e.g., monitoring by ISRO, NRSC, or disaster response teams), halluncinating even a 5% difference in reservoir surface area can lead to erroneous reporting, misallocated resources, and loss of trust.

## Decision

We establish an immutable architectural boundary: **LLMs must NEVER compute geospatial facts or numerical values.**

The system is decomposed into three isolated stages:

1. **Planner Stage (LLM / Rule-Based Fallback)**:
   - Translates unstructured natural-language user queries (e.g., *"Show water body change near Raipur between 2023 and 2025"*) into a strictly typed, machine-executable `AnalysisPlan` adhering to a Pydantic v2 JSON schema.
   - Outputs only structured parameters: task type, geocoded spatial bounding box / polygon, two target temporal intervals, seasonal policy, index choice, minimum area thresholds, and export formats.
   - Does **not** inspect imagery or perform numerical analysis.

2. **Deterministic Geospatial Pipeline (Pure Python / Raster / Vector Math)**:
   - STAC query and asset retrieval (Microsoft Planetary Computer / Earth Search Sentinel-2 L2A).
   - Pixel-level cloud/shadow masking using Scene Classification Layer (SCL).
   - Equal-season median compositing across years to prevent seasonal false positives.
   - Modified Normalized Difference Water Index (MNDWI) calculation at native 10m resolution (properly resampling SWIR1 20m band via bilinear/cubic interpolation).
   - Adaptive Otsu thresholding with morphological opening/closing and minimum polygon size pruning.
   - Pixel-to-polygon vectorization with equal-area projection reprojection (e.g., UTM or India-appropriate equal-area CRS) for precise hectare and delta calculations.
   - All numbers, centroid coordinates, and pixel metrics originate solely from this stage.

3. **Reporter Stage (LLM / Jinja2 Template + Grounding Verifier)**:
   - Consumes the computed metrics, tables, and provenance metadata (scene IDs, acquisition timestamps, cloud cover percentages, Otsu thresholds, software versions).
   - Generates an executive narrative and Markdown/HTML summaries.
   - A dedicated `GroundingVerifier` parses every numeral in the generated text and verifies that it maps directly to an underlying computed metric in the pipeline statistics object. If an ungrounded number is detected, the narrative is flagged or rejected.

```
                    ┌──────────────────────────┐
                    │    Natural-Language      │
                    │         Query            │
                    └─────────────┬────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │      Planner (LLM)       │
                    │   Strict Pydantic Plan   │
                    └─────────────┬────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│               DETERMINISTIC GEOSPATIAL PIPELINE                        │
│                                                                        │
│  [STAC Search] ➔ [SCL Cloud Mask] ➔ [Median Composite]                 │
│  ➔ [MNDWI Math] ➔ [Otsu Threshold] ➔ [Equal-Area Vectorization]        │
│  ➔ [Hectare & Delta Statistics Table + Provenance]                     │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │   Reporter (Narrative)   │
                    │   + Grounding Verifier   │
                    │ (Reject hallucinated #s) │
                    └─────────────┬────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  Map Layers + GeoJSON +  │
                    │  Defensible Report       │
                    └──────────────────────────┘
```

## Consequences

### Positive
- **100% Defensibility**: Every polygon, hectare figure, and percentage is auditable back to STAC scene IDs, band values, and reproducible algorithms.
- **Offline / Zero-API-Key Operation**: A deterministic regex and keyword rule-based planner allows full execution without cloud LLM dependencies.
- **Provider Agnostic**: The planner and reporter plug into any LLM backend (Gemini, OpenAI, Ollama) without affecting geospatial pipeline integrity.
- **Verification**: The automated grounding validator catches model hallucinations before user delivery.

### Negative
- Natural-language queries that require non-standard ad-hoc geospatial workflows must have their schemas explicitly supported in the `AnalysisPlan`.
- The reporter must adhere to strict Jinja/prompting constraints to prevent the generation of ungrounded narrative text.
