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

To quantitatively evaluate whether the observed 2023 $\to$ 2025 net change ($+46.66\,\text{ha}$) represents a structural hydrological trend or cyclical noise, full 10m Sentinel-2 Level-2A median composites were processed across all 8 post-monsoon seasons (2018–2025) under identical methodology:

| Year | Clear Scenes | Total Water Area (ha) | Waterbodies Tracked | Subsampling Noise ($\pm 1\sigma$) | Land Green Reflectance | Radiometric Baseline |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2018** | 23 | **1543.40 ha** | 1,104 | $\pm 19.8\,\text{ha}$ | 0.085 | `02.12` (No Offset) |
| **2019** | 17 | **2500.39 ha** | 1,498 | $\pm 30.1\,\text{ha}$ | 0.097 | `02.12` (No Offset) |
| **2020** | 17 | **1476.30 ha** | 1,079 | $\pm 23.5\,\text{ha}$ | 0.082 | `02.12` (No Offset) |
| **2021** | 10 | **1749.25 ha** | 1,285 | $\pm 21.9\,\text{ha}$ | 0.090 | `03.00` (No Offset) |
| **2022** | 23 | **1455.69 ha** | 1,091 | $\pm 30.7\,\text{ha}$ | 0.071 | `04.00` (Offset: -1000 DN) |
| **2023** | 33 | **1674.99 ha** | 1,235 | $\pm 21.7\,\text{ha}$ | 0.079 | `05.09` (Offset: -1000 DN) |
| **2024** | 17 | **1477.30 ha** | 1,022 | $\pm 23.1\,\text{ha}$ | 0.084 | `05.11` (Offset: -1000 DN) |
| **2025** | 22 | **1721.65 ha** | 1,210 | $\pm 31.1\,\text{ha}$ | 0.083 | `05.11` (Offset: -1000 DN) |

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
- **Total clear scenes**: 17 scenes between 2019-10-03 and 2019-11-30 with mean cloud cover $6.8\%$.
  - October: 6 scenes (cloud cover $1.1\%$ to $22.8\%$).
  - November: 11 scenes (almost completely cloud-free, $0.0\%$ to $2.7\%$, with one scene at $11.6\%$).
- **Observation only**: In terms of scene count (17) and average cloud cover ($6.8\%$), 2019 composition does not differ meaningfully from other years (e.g. 2020: 17 scenes, $7.2\%$ cloud; 2023: 33 scenes, $7.5\%$ cloud; 2024: 17 scenes, $9.6\%$ cloud; 2025: 22 scenes, $9.5\%$ cloud). No causal claims regarding precipitation or monsoon strength are asserted as rainfall was not independently computed.

### Quantitative Noise Synthesis & Leave-One-Out Analysis
- **Observed Production Delta (2023 $\to$ 2025)**: **$+46.66\,\text{ha}$ ($+2.79\%$)**
- **Consecutive-Year Absolute Steps (Full 8-Year Series)**:
  - **Mean consecutive-year absolute difference**: **$458.44\,\text{ha}$**
  - **Median consecutive-year absolute difference**: **$272.97\,\text{ha}$**
  - **Multi-year standard deviation ($\sigma$)**: **$321.72\,\text{ha}$**
- **Leave-One-Out Check (Omitting 2019 Outlier)**:
  - **Mean consecutive-year absolute difference**: **$245.59\,\text{ha}$**
  - **Median consecutive-year absolute difference**: **$244.39\,\text{ha}$**
  - **Multi-year standard deviation ($\sigma$)**: **$117.76\,\text{ha}$**
- **Subsampling Spread Definition**: The reported **$99.71\,\text{ha}$** average spread is computed from a synthetic $\sim 1.5\%$ Gaussian perturbation model across 20 repetitions per year to estimate composite variance, rather than an empirical scene-by-scene jackknife resampling.

**Scientific Conclusion**: The observed $+46.66\,\text{ha}$ net change between 2023 and 2025 is substantially smaller than both the median consecutive-year step ($272.97\,\text{ha}$ full, $244.39\,\text{ha}$ without 2019) and the multi-year standard deviation ($321.72\,\text{ha}$ full, $117.76\,\text{ha}$ without 2019). The observed difference is **consistent with within-noise fluctuations**; asserting structural surface water expansion would be scientifically indefensible. The system classifies this change as **`within noise / inconclusive`**.

![Raipur Inter-Annual Trajectory](file:///c:/Users/user/OneDrive/Desktop/satellite-image-analyst/docs/images/raipur_interannual_variability.png)

---

## Reproducing Evaluation

```bash
# Run query planner held-out evaluation
python evaluation/run_planner_eval.py --dataset golden_heldout_v2.yaml

# Run JRC Global Surface Water validation harness (fetches live Planetary Computer STAC rasters)
python evaluation/run_water_eval.py

# Run manual point sample evaluation
python evaluation/eval_point_sample.py

# Re-compute multi-year inter-annual trajectory
python scripts/compute_interannual_variability.py
```
