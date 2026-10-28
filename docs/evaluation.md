# Evaluation & Benchmarks

This document records rigorous evaluation protocols and reproducible benchmarks for:
1. **Planner Evaluation**: Natural-language query translation across LLM backends and rule-based fallback on both development and independent held-out benchmarks.
2. **Water Mask Validation**: Comparison against the JRC Global Surface Water (Pekel et al.) reference dataset across 3 contrasting Areas of Interest (AOIs).
3. **Multi-Year Inter-Annual Surface Water Trajectory**: Long-term time-series analysis (Raipur 2018–2025) and radiometric continuity across ESA baseline changes.

> **Note on Evaluation Integrity**: In accordance with our core engineering principles, metrics tables below are populated strictly by automated execution of real benchmark scripts (`evaluation/run_planner_eval.py`, `evaluation/run_water_eval.py`). No fabricated numbers or synthetic benchmarks are committed.

---

## 1. Natural Language Planner Evaluation

### Benchmark Datasets
1. **Development Suite (`evaluation/golden_queries.yaml`)**: 42 curated queries covering standard phrasing, pre/post monsoon windows, and basic edge cases.
2. **Held-Out Benchmark Suite v1 (`evaluation/golden_heldout.yaml`)**: 30 independent queries authored to evaluate generalization across varied phrasing styles:
   - Technical / formal remote sensing terminology
   - Conversational / colloquial phrasing
   - Hindi and Hinglish expressions (e.g. *baarish ke baad*, *garmi me*, *pichle 2 saal*)
   - Phonetic and typographical errors (e.g. *Raypur*, *Bhopall*, *whater*)
   - Ambiguous queries with missing locations or relative dates (*recently*, *past 3 years*)
   - Explicit radial distance buffering (*within 20 km of Raipur*, *10km around Bilaspur*)
   - Prompt injection attempts (*Ignore previous instructions...*)
   - Pre-2017 Sentinel-2 L2A archive boundary queries
   - Out-of-scope predictive queries requiring typed refusal / clarification
3. **Held-Out Benchmark Suite v2 (`evaluation/golden_heldout_v2.yaml`)**: 20 fresh queries written after initial architectural improvements.

### Benchmark Performance (Real Execution)

#### Held-Out Benchmark Suite v1 (Frozen: 30 Queries — `golden_heldout.yaml`)
*Evaluated with initial RuleBasedPlanner without post-hoc tuning. Frozen as v1 baseline.*

| Evaluation Metric | Measured Accuracy | Correct / Total |
| :--- | :--- | :--- |
| **Overall Exact Match (EM)** | **76.67%** | 23 / 30 |
| **Task Type Classification** | **86.67%** | 26 / 30 |
| **AOI Place Name Resolution** | **80.00%** | 24 / 30 |
| **Season Policy Extraction** | **86.67%** | 26 / 30 |
| **Temporal Year Bounds** | **83.33%** | 25 / 30 |
| **Clarification / Typed Refusal** | **86.67%** | 26 / 30 |

#### Held-Out Benchmark Suite v2 (20 Queries — `golden_heldout_v2.yaml`)
*Record: **19/20 original; 20/20 after correcting a test expectation** ($n=20$, written after fixes, not an independent benchmark).*

| Evaluation Metric | Original Execution | After Guardrail Expectation Correction |
| :--- | :--- | :--- |
| **Overall Exact Match (EM)** | **95.00%** (19 / 20) | **100.00%** (20 / 20) |
| **Task Type Classification** | **95.00%** (19 / 20) | **100.00%** (20 / 20) |
| **AOI Place Name Resolution** | **95.00%** (19 / 20) | **100.00%** (20 / 20) |
| **Season Policy Extraction** | **95.00%** (19 / 20) | **100.00%** (20 / 20) |
| **Temporal Year Bounds** | **95.00%** (19 / 20) | **100.00%** (20 / 20) |
| **Clarification / Typed Refusal** | **95.00%** (19 / 20) | **100.00%** (20 / 20) |

##### Audit of Query `ho2_16` and Description Discrepancy
- **Query Text**: `"Detect reservoir expansion within 45 km of Durg between 2022 and 2024."`
- **Spatial Geometry**: A 45 km buffer around Durg corresponds to a circular area of $\pi \cdot 45^2 = 6,361.7\,\text{km}^2$, exceeding the pipeline's maximum allowed spatial envelope ($2,500\,\text{km}^2$).
- **Discrepancy History**:
  - In commit `e5bb0e9`, the benchmark author originally wrote `radius_km: 28.2` expecting silent clamping to the maximum equivalent radius ($\sqrt{2500/\pi} \approx 28.2\,\text{km}$).
  - However, the pipeline guardrail raises `AOIAreaExceededError` (typed refusal requesting clarification) to prevent silent geographic truncation.
  - In commit `e541aa2`, the test expectation was corrected to match this typed refusal (`task_type: "refusal"`), bringing exact match from 19/20 to 20/20.
  - **Honest Note on Past Documentation**: The Phase 5 report description referring to "entire state of Madhya Pradesh" was an accidental conflation with regional query stress tests. `ho2_16` specifically targeted a 45 km radial buffer around Durg.

---

### Empirical Archive Audit: Determining `MIN_YEAR`

To establish a defensible physical boundary for Sentinel-2 Level-2A analysis, an automated STAC observation query was executed against Microsoft Planetary Computer for the Raipur Area of Interest across the post-monsoon window (Oct 1 – Nov 30, cloud cover < 30%):

| Year | STAC Sentinel-2 L2A Scenes (Raipur AOI) | Constellation Status |
| :--- | :--- | :--- |
| **2014** | **0 scenes** | Pre-launch (Sentinel-2A launched 23 June 2015) |
| **2015** | **4 scenes (full year)** | Commissioning phase, sparse global acquisition |
| **2016** | **8 scenes** | Sentinel-2A single-orbit operation only |
| **2017** | **9 scenes** | Sentinel-2B launched (March 2017); dual-orbit operational rollout |
| **2018** | **23 scenes** | Full nominal 5-day dual-orbit revisit frequency established |

**Architectural Finding**: Queries specifying years prior to 2017 cannot construct valid composite stacks. `MIN_YEAR = 2017` is enforced in `Settings` and triggers a typed refusal (`task_type="out_of_scope"`) with an empirical explanation.

---

## 2. Water Mask Validation against JRC Global Surface Water

### Reference Dataset Access Audit
Access from this execution environment was tested across candidate reference data sources:

| Source & Product | Endpoint / Collection | Status | Real Result / Diagnostic |
| :--- | :--- | :--- | :--- |
| **JRC GSW Monthly History** | JRC / GCS Direct GeoTIFF tiles | **Failed (404)** | HTTP 404: Not Found (raw monthly history tiles require Google Earth Engine API export) |
| **Planetary Computer `jrc-gsw`** | `https://planetarycomputer.microsoft.com/api/stac/v1` | **Accessible** | Full access to tiles `80E_30Nv1_3_2020`, `70E_30Nv1_3_2020` (Occurrence, Extent, Seasonality) |
| **Planetary Computer `esa-worldcover`** | `https://planetarycomputer.microsoft.com/api/stac/v1` | **Accessible** | Full access to 10m land cover class 80 (Permanent Water) for 2020 and 2021 |

Following our preference hierarchy, **JRC GSW Water Occurrence (v1.3, 2020)** was selected as the operational reference.

### Methodological Ground Rules
1. **Reporting Terminology**: Disagreements with JRC GSW reflect sensor resolution differences (Landsat 30m vs. Sentinel-2 10m), acquisition date offsets, and seasonal phenology. We report strictly as **'agreement with JRC GSW'**, never 'accuracy'.
2. **Phenological Note**: Our Post-Monsoon (Oct–Nov) Sentinel-2 composite captures surface water immediately after seasonal rains. It inherently detects seasonal ponds and expanded margins that recede during dry periods. Consequently, agreement with JRC Permanent Water ($\ge 50\%$ occurrence) is constrained by seasonal water by design.
3. **Spatial Aggregation**: 10m Sentinel-2 water masks are aggregated to the 30m JRC grid using a 50% majority rule ($\ge 5$ of 9 sub-pixels).
4. **Boundary Exclusion**: A 1-pixel boundary zone around water edges is evaluated both with and without exclusion to isolate boundary co-registration noise.
5. **Spatial Uncertainty**: 95% confidence intervals are computed via spatial block-bootstrapping ($10 \times 10$ pixel blocks, $B=200$).
6. **Stratification**: Metrics are stratified by reference water body area ($<1\,\text{ha}$, $1-10\,\text{ha}$, $>10\,\text{ha}$).

### Quantitative Agreement Benchmark (Real Execution: Post-Monsoon 2020)

| AOI & Hydrological Regime | Metric | Permanent Water ($\ge 50\%$) (All Pixels) | Permanent Water ($\ge 50\%$) (Boundary Excluded) | Seasonal Water ($\ge 10\%$) (All Pixels) |
| :--- | :--- | :---: | :---: | :---: |
| **Raipur, Chhattisgarh**<br>*(Alluvial plains & agricultural drainage)* | **IoU**<br>**Precision**<br>**Recall**<br>**F1 Score** | **0.1650**<br>0.1932<br>0.5307<br>**0.2832** | **0.1077**<br>0.1101<br>0.8336<br>**0.1945** | **0.2210**<br>0.4454<br>0.3048<br>**0.3620** |
| **Bhopal, Madhya Pradesh**<br>*(Lake-heavy urban plateau: Bhojtal / Halali)* | **IoU**<br>**Precision**<br>**Recall**<br>**F1 Score** | **0.5472**<br>0.5636<br>0.9495<br>**0.7073** | **0.5609**<br>0.5693<br>0.9742<br>**0.7187** | **0.6470**<br>0.7595<br>0.8137<br>**0.7857** |
| **Jodhpur, Rajasthan**<br>*(Arid desert fringe & ephemeral impoundments)* | **IoU**<br>**Precision**<br>**Recall**<br>**F1 Score** | **0.1199**<br>0.1601<br>0.3232<br>**0.2141** | **0.0974**<br>0.1089<br>0.4794<br>**0.1775** | **0.1540**<br>0.3212<br>0.2283<br>**0.2669** |

#### Spatial Block-Bootstrap Confidence Intervals (95% CI)
- **Raipur**: IoU 95% CI: `[0.1399, 0.1900]`, F1 95% CI: `[0.2454, 0.3192]`
- **Bhopal**: IoU 95% CI: `[0.5099, 0.5856]`, F1 95% CI: `[0.6754, 0.7386]`
- **Jodhpur**: IoU 95% CI: `[0.0420, 0.2018]`, F1 95% CI: `[0.0806, 0.3359]`

#### Stratification by Water Body Size (Permanent Water $\ge 50\%$)
- **Raipur**:
  - $< 1\,\text{ha}$ ($n=1,643$ ref px): IoU = 0.0226, Recall = 0.2368, F1 = 0.0441
  - $1-10\,\text{ha}$ ($n=2,657$ ref px): IoU = 0.0884, Recall = 0.5702, F1 = 0.1625
  - $> 10\,\text{ha}$ ($n=1,521$ ref px): IoU = 0.0726, Recall = 0.7791, F1 = 0.1353
- **Bhopal**:
  - $< 1\,\text{ha}$ ($n=131$ ref px): IoU = 0.0010, Recall = 0.3740, F1 = 0.0020
  - $1-10\,\text{ha}$ ($n=77$ ref px): IoU = 0.0004, Recall = 0.2727, F1 = 0.0009
  - $> 10\,\text{ha}$ ($n=28,433$ ref px, large reservoirs): **IoU = 0.5473, Recall = 0.9540, F1 = 0.7074**
- **Jodhpur**:
  - $< 1\,\text{ha}$ ($n=25$ ref px): IoU = 0.0022, Recall = 0.1600, F1 = 0.0044
  - $1-10\,\text{ha}$ ($n=249$ ref px): IoU = 0.0059, Recall = 0.0482, F1 = 0.0118
  - $> 10\,\text{ha}$ ($n=614$ ref px): IoU = 0.1269, Recall = 0.4414, F1 = 0.2252

#### Threshold Sensitivity Comparison (Permanent Water $\ge 50\%$)
- **Raipur**: MNDWI > -0.05 (IoU = 0.1581, F1 = 0.2731) | MNDWI > 0.0 (IoU = 0.1650, F1 = 0.2832) | MNDWI > +0.05 (IoU = 0.1728, F1 = 0.2947)
- **Bhopal**: MNDWI > -0.05 (IoU = 0.5354, F1 = 0.6974) | MNDWI > 0.0 (IoU = 0.5472, F1 = 0.7073) | MNDWI > +0.05 (IoU = 0.5582, F1 = 0.7165) | Otsu (>0.09, IoU = 0.5656, F1 = 0.7226)
- **Jodhpur**: MNDWI > -0.05 (IoU = 0.1142, F1 = 0.2050) | MNDWI > 0.0 (IoU = 0.1199, F1 = 0.2141) | MNDWI > +0.05 (IoU = 0.1238, F1 = 0.2204)

---

## 3. Independent Point-Sample Validation (Raipur 2023)

To provide an independent, transparent accuracy metric, a stratified random sample of 150 points was extracted across the Raipur 2023 post-monsoon Sentinel-2 composite:
- **Sample Distribution**:
  - 60 Interior Water Points (eroded waterbody interiors)
  - 60 Interior Non-Water Points (eroded dryland/agricultural fields)
  - 30 Boundary Edge Points (within 1 pixel of waterbody perimeters)
- **Dataset File**: [`evaluation/point_sample_template.csv`](file:///c:/Users/user/OneDrive/Desktop/satellite-image-analyst/evaluation/point_sample_template.csv)
- **Status**: **Pending Manual Labels**. In accordance with our honesty rules, human ground-truth labels are left blank for manual expert verification.
- **Evaluation Tool**: Running `python evaluation/eval_point_sample.py` automatically computes overall accuracy, precision, recall, F1, and 95% Wilson score confidence intervals once labels (`1` = water, `0` = non-water, or `unsure`) are populated.

---

## 4. Multi-Year Surface Water Trajectory (Raipur 2018–2025)

To quantitatively evaluate whether the observed 2023 $\to$ 2025 net change ($+46.66\,\text{ha}$) represents a structural hydrological trend or cyclical noise, full 10m Sentinel-2 Level-2A median composites were processed across all 8 post-monsoon seasons (2018–2025) under identical methodology.

Scene subsampling sensitivity was empirically evaluated by drawing $k = \min(10, \lfloor 0.80 \times N \rfloor)$ scenes at random without replacement across 20 seeded repetitions per year ($N$ = total clear scenes available in that season):

| Year | Total Scenes ($N$) | Subsample Size ($k$) | Full Composite Water Area (ha) | Subsample Mean Area (ha) | Subsample Std ($\sigma$, ha) | Empirical 95% CI (ha) | 95% Spread (ha) | Radiometric Baseline |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2018** | 13 | 10 | **1543.39** | 1546.91 | 130.81 | `[1311.67, 1768.40]` | 456.73 | `02.12` (No Offset) |
| **2019** | 20 | 10 | **2500.39** | 2694.40 | 366.92 | `[2197.12, 3472.31]` | 1275.19 | `02.12` (No Offset) |
| **2020** | 18 | 10 | **1476.28** | 1462.59 | 105.62 | `[1234.66, 1604.48]` | 369.82 | `02.12` (No Offset) |
| **2021** | 10 | 8 | **1749.25** | 1719.37 | 157.07 | `[1380.99, 1957.76]` | 576.77 | `03.00` (No Offset) |
| **2022** | 23 | 10 | **1455.69** | 1466.13 | 103.64 | `[1339.23, 1702.25]` | 363.02 | `04.00` (Offset: -1000 DN) |
| **2023** | 15 | 10 | **1674.99** | 1814.44 | 164.16 | `[1569.15, 2071.18]` | 502.03 | `05.09` (Offset: -1000 DN) |
| **2024** | 14 | 10 | **1477.26** | 1497.26 | 96.09 | `[1387.86, 1730.57]` | 342.71 | `05.11` (Offset: -1000 DN) |
| **2025** | 13 | 10 | **1721.65** | 1769.58 | 380.57 | `[964.55, 2474.08]` | 1509.53 | `05.11` (Offset: -1000 DN) |

Across all 8 years:
- **Mean Annual Surface Water Area**: **$1,699.86\,\text{ha}$**
- **Average 95% Subsampling Spread**: **$674.47\,\text{ha}$**
- **Mean Subsampling Standard Deviation ($\bar{\sigma}$)**: **$188.11\,\text{ha}$**

### Radiometric Calibration Verification (Stable Land Pixel Audit)
The transition from ESA processing baseline `03.00` to `04.00+` on 2022-01-25 introduced a $-1000\,\text{DN}$ ($-0.10$ reflectance) BOA offset. To verify continuity on identical pixels, surface reflectance was compared on $n=55,304$ stable non-water land pixels between cloud-free acquisitions 8 days apart:
- **Pre-Baseline Acquisition**: 2022-01-20 (PB `03.00`, mean green reflectance = **0.0814**)
- **Post-Baseline Acquisition**: 2022-01-28 (PB `04.00`, mean green reflectance = **0.0809**)
- **Real Difference (WITH -1000 DN offset correction)**:
  - Mean difference: **$-0.0006$ ($-0.70\%$)**
  - Median difference: **$-0.0015$**
  - Standard deviation: **$0.0094$**
- **Difference WITHOUT offset correction (naive DN / 10000)**:
  - Mean difference: **$+0.0994$ ($+122.09\%$)** (an artificial $+0.1000$ reflectance jump).
This confirms that the per-item BOA offset maintains radiometric continuity within $<1\%$ relative error.

### Observation Audit for 2019
The 2019 season registered an elevated surface water area ($2,500.39\,\text{ha}$). An audit of STAC acquisition metadata shows:
- **Total clear scenes**: 20 scenes between 2019-10-01 and 2019-11-30 with mean cloud cover $6.8\%$.
  - October: 7 scenes (cloud cover $1.1\%$ to $22.8\%$).
  - November: 13 scenes (almost completely cloud-free, $0.0\%$ to $2.7\%$, with one scene at $11.6\%$).
- **Observation only**: In terms of scene count (20) and average cloud cover ($6.8\%$), 2019 composition does not differ meaningfully from other years (e.g. 2020: 18 scenes, $7.2\%$ cloud; 2023: 15 scenes, $7.5\%$ cloud; 2024: 14 scenes, $9.6\%$ cloud; 2025: 13 scenes, $9.5\%$ cloud). No causal claims regarding precipitation or monsoon strength are asserted as rainfall was not independently computed.

### Quantitative Multi-Year Context & Step Analysis
- **Observed Production Delta (2023 $\to$ 2025)**: **$+46.66\,\text{ha}$ ($+2.79\%$)**
- **Consecutive-Year Absolute Steps (Full 8-Year Series)**:
  - **Mean consecutive-year absolute difference**: **$458.44\,\text{ha}$**
  - **Median consecutive-year absolute difference**: **$272.97\,\text{ha}$**
  - **Multi-year standard deviation ($\sigma$)**: **$321.72\,\text{ha}$**
- **Leave-One-Out Check (Omitting 2019 Outlier)**:
  - **Mean consecutive-year absolute difference**: **$245.59\,\text{ha}$**
  - **Median consecutive-year absolute difference**: **$244.39\,\text{ha}$**
  - **Multi-year standard deviation ($\sigma$)**: **$117.76\,\text{ha}$**
- **Empirical Subsampling Comparison**: The $+46.66\,\text{ha}$ net shift is **over 14 times smaller** than the average empirical 95% subsampling spread ($674.47\,\text{ha}$) and **nearly 6 times smaller** than the median consecutive-year step ($272.97\,\text{ha}$).

**Scientific Conclusion**: The observed $+46.66\,\text{ha}$ net change between 2023 and 2025 is substantially smaller than both the median consecutive-year step ($272.97\,\text{ha}$ full, $244.39\,\text{ha}$ without 2019) and the multi-year standard deviation ($321.72\,\text{ha}$ full, $117.76\,\text{ha}$ without 2019). The observed difference is **consistent with within-noise fluctuations**; asserting structural surface water expansion would be scientifically indefensible. The system classifies this change as **`within noise / inconclusive`**.

![Raipur Inter-Annual Trajectory](file:///c:/Users/user/OneDrive/Desktop/satellite-image-analyst/docs/images/raipur_interannual_variability.png)

---

## 5. Water Mask Precision Diagnosis & Extraction Variant Benchmarking

### Diagnostic Analysis of Raipur Precision Mismatch
In Section 2, the post-monsoon Raipur 2020 water mask yielded an IoU of $0.1650$ and precision of $0.1932$ against JRC Global Surface Water ($\ge 50\%$ permanent water). To diagnose this discrepancy, water mask pixels were cross-tabulated against **ESA WorldCover 10m (2020)** and **JRC GSW Occurrence (v1.3)**:

#### Land Cover Breakdown of Pipeline Water Pixels
| Region & Year | Total Water (ha) | Permanent Water (WC 80) | Cropland (WC 40) | Grassland (WC 30) | Tree Cover (WC 10) | Built-up (WC 50) | JRC 0% Occ (Never Water) | JRC $\ge 50\%$ Occ (Perm) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Raipur 2020** | 685.8 ha | **64.81%** | **12.28%** | **11.53%** | 6.14% | 2.67% | **31.80%** | 31.92% |
| **Raipur 2023** | 1,851.1 ha | **41.47%** | **22.05%** | **17.51%** | 10.97% | 4.19% | **49.75%** | 15.95% |
| **Bhopal 2020** | 3,865.8 ha | **74.31%** | **8.43%** | **4.09%** | 7.50% | 4.49% | **14.13%** | **62.77%** |

**Key Diagnostic Finding**: In agricultural alluvial plains like Raipur, **12.3% to 22.1%** of post-monsoon water pixels fall on WorldCover Cropland and **31.8% to 49.8%** have 0% historical occurrence in multi-decadal JRC GSW. This reflects genuine physical post-monsoon standing water and flooded paddy fields that dry out in the dry season. By contrast, in Bhopal, **74.3%** of water pixels fall on permanent waterbodies (Bhojtal reservoir) and only **14.1%** have 0% historical occurrence.

### Extraction Variant Benchmarking against ESA WorldCover (Class 80)
Four water extraction formulations were evaluated against ESA WorldCover 10m Class 80 (Permanent Water):
1. **Baseline MNDWI**: $\text{MNDWI} > 0.0$
2. **MNDWI + NDVI Filter**: $\text{MNDWI} > 0.0 \land \text{NDVI} < 0.10$
3. **AWEInsh**: Automated Water Extraction Index (Non-Shadow) $> 0.0$
4. **AWEIsh**: Automated Water Extraction Index (Shadow-Elimination) $> 0.0$

Evaluation was conducted on the development pool (**Raipur 2020** and **Bhopal 2020**) and tested on an untouched held-out AOI (**Jodhpur 2020**, arid desert fringe):

| AOI & Partition | Variant | IoU | Precision | Recall | F1 Score | 95% Bootstrap CI (F1) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Raipur 2020**<br>*(Dev Pool)* | **Baseline MNDWI** | 0.2173 | 0.6560 | 0.2453 | 0.3571 | `[0.3337, 0.3893]` |
| | **MNDWI + NDVI < 0.1** | 0.1908 | 0.6516 | 0.2125 | 0.3205 | `[0.2989, 0.3515]` |
| | **AWEInsh** | 0.1875 | 0.6910 | 0.2047 | 0.3158 | `[0.2896, 0.3486]` |
| | **AWEIsh** | **0.2206** | 0.6517 | **0.2501** | **0.3615** | `[0.3382, 0.3942]` |
| **Bhopal 2020**<br>*(Dev Pool)* | **Baseline MNDWI** | 0.6524 | 0.7431 | **0.8425** | 0.7897 | `[0.7734, 0.8036]` |
| | **MNDWI + NDVI < 0.1** | 0.6581 | **0.7771** | 0.8113 | 0.7938 | `[0.7776, 0.8083]` |
| | **AWEInsh** | 0.6590 | 0.7622 | 0.8295 | 0.7944 | `[0.7779, 0.8097]` |
| | **AWEIsh** | **0.6608** | 0.7658 | 0.8281 | **0.7957** | `[0.7798, 0.8105]` |
| **Pooled Dev**<br>*(Raipur + Bhopal)* | **AWEIsh**<br>**Baseline MNDWI**<br>**AWEInsh**<br>**MNDWI + NDVI < 0.1** | —<br>—<br>—<br>— | —<br>—<br>—<br>— | —<br>—<br>—<br>— | **0.6834**<br>**0.6804**<br>0.6768<br>0.6736 | —<br>—<br>—<br>— |
| **Jodhpur 2020**<br>*(Untouched Held-Out)* | **Baseline MNDWI** | 0.1879 | 0.5203 | 0.2273 | 0.3164 | `[0.2466, 0.3790]` |
| | **MNDWI + NDVI < 0.1** | 0.1819 | 0.5331 | 0.2163 | 0.3078 | `[0.2401, 0.3729]` |
| | **AWEInsh** | 0.1409 | **0.5355** | 0.1605 | 0.2470 | `[0.1683, 0.3142]` |
| | **AWEIsh** | **0.1916** | 0.5253 | **0.2317** | **0.3216** | `[0.2516, 0.3863]` |

#### Architectural Decision & Variant Rationale
1. On the pooled development set, `AWEIsh` achieved **0.6834** pooled F1 vs **0.6804** for `Baseline MNDWI` ($\Delta \text{F1} = +0.0030$).
2. On untouched held-out Jodhpur, `AWEIsh` achieved **0.3216** vs **0.3164** ($\Delta \text{F1} = +0.0052$).
3. **Statistical Equivalence**: Across all three sites, the 95% bootstrap confidence intervals for `AWEIsh` and `Baseline MNDWI` overlap almost completely. The marginal numerical difference does not alter the fundamental phenological reality of post-monsoon cropland inundation.
4. **Band Efficiency**: Baseline MNDWI requires only 2 spectral bands (B03, B11), whereas AWEIsh requires 5 bands (B02, B03, B08, B11, B12), more than doubling network download volume and RAM usage.
5. **Decision**: Baseline `mndwi` is retained as the production default. `water_mask_variant: str = "mndwi"` is exposed in `Settings` to allow users to select `awei_sh`, `awei_nsh`, or `mndwi_ndvi`.

### Raipur 2023 $\to$ 2025 Change Detection Rerun (Baseline vs AWEIsh)
To verify whether variant selection impacts change detection verdicts, the Raipur 2023 vs 2025 comparison was re-run using both formulations:

| Formulation | 2023 Water Area (ha) | 2025 Water Area (ha) | Net Change (ha) | Relative Shift (%) | Scientific Significance |
| :--- | :---: | :---: | :---: | :---: | : |
| **Baseline MNDWI** | 1,851.10 ha | 1,776.19 ha | $-74.91\,\text{ha}$ | $-4.05\%$ | **Within noise / inconclusive** |
| **AWEIsh** | 1,862.84 ha | 1,833.82 ha | $-29.02\,\text{ha}$ | $-1.56\%$ | **Within noise / inconclusive** |

**Verdict**: Under both formulations, the net change between 2023 and 2025 is negative and small ($-1.56\%$ to $-4.05\%$), well within the multi-year standard deviation ($\sigma = 321.72\,\text{ha}$) and the empirical subsampling spread ($674.47\,\text{ha}$). The conclusion that the observed shift is **consistent with within-noise fluctuations** holds robustly across both spectral indices.

---

## 6. Reproducing Evaluation

```bash
# Run query planner held-out evaluation
python evaluation/run_planner_eval.py --dataset golden_heldout_v2.yaml

# Run JRC Global Surface Water validation harness (fetches live Planetary Computer STAC rasters)
python evaluation/run_water_eval.py

# Run manual point sample evaluation
python evaluation/eval_point_sample.py

# Re-compute multi-year inter-annual trajectory with empirical subsampling
python scripts/compute_interannual_variability.py

# Re-run water mask precision diagnostics and variant benchmarking
python evaluation/diagnose_water_masks.py
```
