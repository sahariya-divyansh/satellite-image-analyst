# Technical Limitations & Responsible Use

Remote sensing workflows provide planetary-scale observation but operate under physical and algorithmic constraints. This document details known limitations to ensure defensible, transparent application of `satellite-image-analyst`.

## 1. Spatial Resolution Limits

- **10m Ground Sample Distance (GSD)**: Sentinel-2 visible and NIR bands have a 10m pixel size. SWIR1 (B11) is captured at 20m and resampled to 10m.
- **Minimum Detectable Water Body Size**: Objects smaller than 0.1 hectares ($\sim 10$ pixels, or approximately $31.6\,\text{m} \times 31.6\,\text{m}$) cannot be resolved reliably. Small farm ponds (*doba* / *talab*) or narrow irrigation canals (<10m width) will suffer severe sub-pixel mixed signal attenuation and may be omitted.

## 2. Atmospheric & Cloud Interference

- **Persistent Monsoonal Cloud Cover**: In tropical and sub-tropical regions (including central and southern India), persistent cloud cover during July–September makes optical acquisitions scarce. Even with Scene Classification Layer (SCL) filtering, thin cirrus or small cloud shadows may occasionally bypass automated masking.
- **Mitigation**: The pipeline operates on post-monsoon (October–November) composites where clear-sky optical observations are abundant.

## 3. Seasonality and False Positives

- Comparing images from different seasons (e.g., peak monsoon August vs. pre-monsoon May) yields drastic surface area changes that reflect seasonal rainfall cycles rather than permanent infrastructure or land use changes.
- **Enforcement**: The planner mandates same-season comparison across years unless explicitly overridden by expert configuration.

## 4. Spectral Challenges & Edge Cases

- **Turbid / Sediment-Rich Water**: Suspended sediment increases reflectance in the green and red spectrum, which can lower MNDWI values and cause false negatives in shallow silty reservoirs.
- **Algal Blooms & Aquatic Weeds**: High chlorophyll-a concentrations (e.g., water hyacinth) produce vegetation-like spectral responses (high NIR), which may register as dry or vegetated land under pure MNDWI.
- **Topographic Shadows**: In mountainous terrain, steep slope shadows exhibit spectral signatures resembling water in optical bands. While SCL includes shadow classes, steep relief may introduce residual edge artifacts.

## 5. Threshold Sensitivity

- While automated Otsu thresholding dynamically separates water and land distributions, in scenes dominated (>95%) by dry land with tiny water bodies, the histogram unimodality can degrade Otsu accuracy. The pipeline includes bounds clamping and user overrides (`otsu_offset` or explicit threshold).

## 6. Open-Vocabulary Objects (CLIP/SAM Experimental Module)

- Any detection of complex anthropogenic objects (e.g., brick kilns, aquaculture cages) via CLIP/SAM is experimental, uncalibrated for formal cadastral or regulatory enforcement, and must be validated with high-resolution sub-meter aerial or ground truth data.
