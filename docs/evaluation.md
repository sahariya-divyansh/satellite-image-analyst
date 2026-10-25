# Evaluation & Benchmarks

This document records rigorous evaluation protocols and reproducible benchmarks for:
1. **Planner Evaluation**: Natural-language query translation across LLM backends and rule-based fallback.
2. **Water Mask Validation**: Comparison against the JRC Global Surface Water (Pekel et al.) reference dataset across 3 contrasting Area of Interests (AOIs).

> **Note on Evaluation Integrity**: In accordance with our core engineering principles, metrics tables below are populated strictly by automated execution of `make evaluate`. No fabricated numbers or synthetic benchmarks are ever committed.

---

## 1. Natural Language Planner Evaluation

### Dataset
A golden benchmark set of 42 diverse natural-language queries (`evaluation/golden_queries.yaml`) spanning:
- Standard multi-year water change queries
- Single-year water extent queries
- Explicit bounding box and place name specifications
- Variations in phrasing (e.g., "monsoon", "pre-monsoon", "drought", "flooded")
- Ambiguous and edge-case inputs

### Metrics
- **Exact Match (EM)**: Proportion of plans where all fields match the golden plan identically.
- **Field-Level Accuracy**:
  - `task_type` accuracy
  - `aoi` geocoded overlap (IoU $\ge 0.8$)
  - `temporal` extraction accuracy (start/end years and intervals)
  - `season_policy` accuracy
  - `index` accuracy

### Benchmark Results

> **Benchmark Classification**: Development golden set, rule-based planner, not a held-out benchmark. Results indicate baseline rule heuristic conformance against designed development queries.

| Provider | Model | Queries | Exact Match (%) | Task Type Acc (%) | Temporal Acc (%) | AOI Acc (%) |
|---|---|---|---|---|---|---|
| Rule-Based | Regex/Keyword Engine | 42 | 85.71% | 90.48% | 90.48% | 85.71% |
| Gemini | gemini-1.5-flash | 42 | *Pending API key* | *Pending API key* | *Pending API key* | *Pending API key* |
| OpenAI | gpt-4o-mini | 42 | *Pending API key* | *Pending API key* | *Pending API key* | *Pending API key* |
| Ollama | llama3.2 | 42 | *Pending local model* | *Pending local model* | *Pending local model* | *Pending local model* |

---

## 2. Water Mask Validation against JRC Global Surface Water

### Reference Ground Truth
We evaluate generated binary water masks against the **EC JRC Global Surface Water (GSW)** dataset (Pekel et al., *Nature* 2016) at 30m resolution resampled to the Sentinel-2 10m grid.

### Selected AOIs
1. **Raipur Region, Chhattisgarh, India** (Mixed urban, agricultural reservoirs, and Mahanadi river tributaries).
2. **Vembanad Lake Region, Kerala, India** (High-moisture coastal wetlands, backwaters, dense vegetation interface).
3. **Sambhar Salt Lake, Rajasthan, India** (Arid / semi-arid saline playa lake with high spectral soil reflectance).

### Metrics
- **Intersection over Union (IoU)**: $\frac{|W_{\text{pred}} \cap W_{\text{ref}}|}{|W_{\text{pred}} \cup W_{\text{ref}}|}$
- **Precision**: $\frac{\text{TP}}{\text{TP} + \text{FP}}$
- **Recall**: $\frac{\text{TP}}{\text{TP} + \text{FN}}$
- **F1-Score**: $\frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$

### JRC GSW Comparison Results

| Region | Characteristic | Season | IoU | Precision | Recall | F1-Score |
|---|---|---|---|---|---|---|
| Raipur, CG | Inland Agricultural & Rivers | Post-Monsoon | *Run `make evaluate` to populate* | *Run to populate* | *Run to populate* | *Run to populate* |
| Vembanad, KL | Coastal Backwaters & Wetlands | Post-Monsoon | *Run `make evaluate` to populate* | *Run to populate* | *Run to populate* | *Run to populate* |
| Sambhar, RJ | Arid Saline Playa | Post-Monsoon | *Run `make evaluate` to populate* | *Run to populate* | *Run to populate* | *Run to populate* |

---

## Reproducing Evaluation

To run the complete benchmark suite:
```bash
make evaluate
```
Artifacts and JSON result summaries are written to `evaluation/results/`.
