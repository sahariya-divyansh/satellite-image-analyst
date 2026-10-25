# Remote Sensing Methodology

This document details the scientific and numerical basis for all spectral indices, masking routines, compositing algorithms, and change classifications implemented in `satellite_analyst`.

## 1. Sentinel-2 L2A Input Data & Preprocessing

Sentinel-2 Level-2A products provide Bottom-of-Atmosphere (BOA) surface reflectance.

- **Collections**:
  - Microsoft Planetary Computer: `sentinel-2-l2a`
  - Earth Search (Element 84 / AWS): `sentinel-2-l2a`
- **Resolution Alignment**:
  - Green (B03): 10m native
  - SWIR1 (B11): 20m native
  - *Preprocessing requirement*: SWIR1 must be resampled to 10m matching B03 using bilinear interpolation before index computation to avoid grid misalignment artifacts.

## 2. Cloud and Shadow Masking (SCL)

Sentinel-2 L2A provides a 20m Scene Classification Layer (SCL). Pixels matching any of the following classifications are masked out (`NaN`):
- `0`: No data
- `1`: Saturated or defective
- `3`: Cloud shadows
- `8`: Cloud medium probability
- `9`: Cloud high probability
- `10`: Thin cirrus
- `11`: Snow or ice

Valid surface classifications retained:
- `4`: Vegetation
- `5`: Not-vegetated (bare soil)
- `6`: Water
- `7`: Unclassified

## 3. Same-Season Median Compositing

Comparing imagery across different calendar seasons creates widespread false positives due to natural monsoonal fill and agricultural drawdown.

To maintain temporal consistency, `satellite_analyst` enforces same-season temporal bounds across years:
- **Default (Post-Monsoon)**: October 1 – November 30 (captures maximum surface water extent under clear skies).
- **Alternative (Pre-Monsoon)**: March 1 – May 31 (captures minimum baseline perennial water body extent).

A pixel-wise median is calculated over all valid (unmasked) observations within the seasonal window:
$$\tilde{R}(x, y) = \text{median}\left(\{ R_t(x, y) \mid t \in [T_{\text{start}}, T_{\text{end}}] \text{ and } \text{SCL}_t(x, y) \text{ is valid} \}\right)$$

## 4. Modified Normalized Difference Water Index (MNDWI)

Xu (2006) formulated MNDWI to distinguish open water from built-up urban surfaces:

$$\text{MNDWI} = \frac{\rho_{\text{Green}} - \rho_{\text{SWIR1}}}{\rho_{\text{Green}} + \rho_{\text{SWIR1}}} = \frac{\text{B03} - \text{B11}}{\text{B03} + \text{B11}}$$

- Water typically displays positive values ($\text{MNDWI} > 0$), while soil, vegetation, and urban infrastructure exhibit negative values.

## 5. Thresholding & Morphological Refinement

1. **Adaptive Thresholding**: Otsu's method determines an optimal threshold $T^*$ separating the bimodal distribution of MNDWI values over the AOI:
   $$\sigma_w^2(T^*) = \min_T \sigma_w^2(T)$$
2. **Morphological Filtering**: A $3 \times 3$ structural element performs binary opening (erosion followed by dilation) to eliminate single-pixel salt-and-pepper noise along coastlines and canal fringes.
3. **Minimum Area Filter**: Any connected component below `min_area_ha` (default $0.1\,\text{ha} \approx 10$ Sentinel-2 pixels) is removed.

## 6. Change Detection Classification

Given binary water masks $W_A$ (Period A) and $W_B$ (Period B):

$$\text{Class}(x, y) = \begin{cases}
1 & \text{if } W_A(x, y) = 0 \text{ and } W_B(x, y) = 1 \quad (\textbf{Gained Water}) \\
2 & \text{if } W_A(x, y) = 1 \text{ and } W_B(x, y) = 0 \quad (\textbf{Lost Water}) \\
3 & \text{if } W_A(x, y) = 1 \text{ and } W_B(x, y) = 1 \quad (\textbf{Persistent Water}) \\
0 & \text{if } W_A(x, y) = 0 \text{ and } W_B(x, y) = 0 \quad (\textbf{Dry Land})
\end{cases}$$

## 7. Equal-Area Coordinate Reprojection & Area Calculation

Calculating area directly on geographic coordinates (WGS84 / EPSG:4326 degrees) introduces severe latitude-dependent distortions.

Before polygon area calculations:
1. All geometry polygons are reprojected into an appropriate equal-area projection:
   - Regional: Appropriate UTM Zone (e.g., EPSG:32644 for Raipur, Chhattisgarh, India) or India Equal Area (EPSG:7755).
2. Planar area $A_{\text{sqm}}$ is computed in square meters:
   $$A_{\text{ha}} = \frac{A_{\text{sqm}}}{10,000}$$
3. Centroids are recorded in both projected coordinates and geographic WGS84 for mapping.
