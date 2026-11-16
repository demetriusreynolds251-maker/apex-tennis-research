# ROOT CAUSE ANALYSIS
Append-only.

---
# Entry 2026-08-29 23:13
## Root-cause classification  (ALIS-L4 Phase 2)
INFRASTRUCTURE: BUILT · VALIDATION: NOT STARTED
Losses classified: **3** · EVIDENCE: **Very Low**

| cause | count | share |
|---|---|---|
| MODEL_ERROR | 0 | -- |
| VARIANCE | 3 | 100% |
| CATEGORY_ERROR | 0 | -- |
| CONFIDENCE_ERROR | 0 | -- |
| FORMAT_ERROR | 0 | -- |
| DATA_ERROR | 0 | -- |

**CONFIDENCE_ERROR:** NOT AVAILABLE -- band-level claim, needs >=10 losses in one band.

### Per-loss detail
| player | cat | line | proj | actual | cause | why |
|---|---|---|---|---|---|---|
| match | total_games | 20.5 | 24.1 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| match | total_games | 18.5 | 22.3 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| Polona Hercog | games_won | 8.5 | 9.2 | 6.0 | **VARIANCE** | actual 6.0 inside p10-p90; projection reasonable |

**Interpretation gate:** cause shares are descriptive only until n>=25 losses.

---
# Entry 2026-08-30 17:56
## Root-cause classification  (ALIS-L4 Phase 2)
INFRASTRUCTURE: BUILT · VALIDATION: NOT STARTED
Losses classified: **5** · EVIDENCE: **Low**

| cause | count | share |
|---|---|---|
| MODEL_ERROR | 2 | 40% |
| VARIANCE | 3 | 60% |
| CATEGORY_ERROR | 0 | -- |
| CONFIDENCE_ERROR | 0 | -- |
| FORMAT_ERROR | 0 | -- |
| DATA_ERROR | 0 | -- |

**CONFIDENCE_ERROR:** NOT AVAILABLE -- band-level claim, needs >=10 losses in one band.

### Per-loss detail
| player | cat | line | proj | actual | cause | why |
|---|---|---|---|---|---|---|
| Marton Fucsovics | dfs | 5.5 | 4.3 | 11.0 | **MODEL_ERROR** | actual 11.0 is +2.8 sd from projection 4.3 |
| match | total_games | 20.5 | 24.1 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| match | total_games | 18.5 | 22.3 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| Hugo Gaston | aces | 2.5 | 4.2 | 0.0 | **MODEL_ERROR** | actual outside p10-p90 (-4.2 from projection) |
| Polona Hercog | games_won | 8.5 | 9.2 | 6.0 | **VARIANCE** | actual 6.0 inside p10-p90; projection reasonable |

**Interpretation gate:** cause shares are descriptive only until n>=25 losses.

---
# Entry 2026-08-30 22:16
## Root-cause classification  (ALIS-L4 Phase 2)
INFRASTRUCTURE: BUILT · VALIDATION: NOT STARTED
Losses classified: **5** · EVIDENCE: **Low**

| cause | count | share |
|---|---|---|
| MODEL_ERROR | 2 | 40% |
| VARIANCE | 3 | 60% |
| CATEGORY_ERROR | 0 | -- |
| CONFIDENCE_ERROR | 0 | -- |
| FORMAT_ERROR | 0 | -- |
| DATA_ERROR | 0 | -- |

**CONFIDENCE_ERROR:** NOT AVAILABLE -- band-level claim, needs >=10 losses in one band.

### Per-loss detail
| player | cat | line | proj | actual | cause | why |
|---|---|---|---|---|---|---|
| Marton Fucsovics | dfs | 5.5 | 4.3 | 11.0 | **MODEL_ERROR** | actual 11.0 is +2.8 sd from projection 4.3 |
| match | total_games | 20.5 | 24.1 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| match | total_games | 18.5 | 22.3 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| Hugo Gaston | aces | 2.5 | 4.2 | 0.0 | **MODEL_ERROR** | actual outside p10-p90 (-4.2 from projection) |
| Polona Hercog | games_won | 8.5 | 9.2 | 6.0 | **VARIANCE** | actual 6.0 inside p10-p90; projection reasonable |

**Interpretation gate:** cause shares are descriptive only until n>=25 losses.

---
# Entry 2026-08-30 22:39
## Root-cause classification  (ALIS-L4 Phase 2)
INFRASTRUCTURE: BUILT · VALIDATION: NOT STARTED
Losses classified: **5** · EVIDENCE: **Low**

| cause | count | share |
|---|---|---|
| MODEL_ERROR | 2 | 40% |
| VARIANCE | 3 | 60% |
| CATEGORY_ERROR | 0 | -- |
| CONFIDENCE_ERROR | 0 | -- |
| FORMAT_ERROR | 0 | -- |
| DATA_ERROR | 0 | -- |

**CONFIDENCE_ERROR:** NOT AVAILABLE -- band-level claim, needs >=10 losses in one band.

### Per-loss detail
| player | cat | line | proj | actual | cause | why |
|---|---|---|---|---|---|---|
| Marton Fucsovics | dfs | 5.5 | 4.3 | 11.0 | **MODEL_ERROR** | actual 11.0 is +2.8 sd from projection 4.3 |
| match | total_games | 20.5 | 24.1 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| match | total_games | 18.5 | 22.3 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| Hugo Gaston | aces | 2.5 | 4.2 | 0.0 | **MODEL_ERROR** | actual outside p10-p90 (-4.2 from projection) |
| Polona Hercog | games_won | 8.5 | 9.2 | 6.0 | **VARIANCE** | actual 6.0 inside p10-p90; projection reasonable |

**Interpretation gate:** cause shares are descriptive only until n>=25 losses.

---
# Entry 2026-08-30 22:40
## Root-cause classification  (ALIS-L4 Phase 2)
INFRASTRUCTURE: BUILT · VALIDATION: NOT STARTED
Losses classified: **11** · EVIDENCE: **Moderate**

| cause | count | share |
|---|---|---|
| MODEL_ERROR | 3 | 27% |
| VARIANCE | 7 | 64% |
| CATEGORY_ERROR | 1 | 9% |
| CONFIDENCE_ERROR | 0 | -- |
| FORMAT_ERROR | 0 | -- |
| DATA_ERROR | 0 | -- |

**CONFIDENCE_ERROR:** NOT AVAILABLE -- band-level claim, needs >=10 losses in one band.

### Per-loss detail
| player | cat | line | proj | actual | cause | why |
|---|---|---|---|---|---|---|
| match | total_games | 21.5 | 24.1 | 16.0 | **MODEL_ERROR** | actual outside p10-p90 (-8.1 from projection) |
| Marton Fucsovics | dfs | 5.5 | 4.3 | 11.0 | **MODEL_ERROR** | actual 11.0 is +2.8 sd from projection 4.3 |
| Tristan Schoolka | games_won | 12.5 | 11.7 | 18.0 | **CATEGORY_ERROR** | games_won biased +1.72 across n=5; this miss runs the same way |
| match | total_games | 20.5 | 24.1 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| match | total_games | 18.5 | 22.3 | 18.0 | **VARIANCE** | actual 18.0 inside p10-p90; projection reasonable |
| Hugo Gaston | aces | 2.5 | 4.2 | 0.0 | **MODEL_ERROR** | actual outside p10-p90 (-4.2 from projection) |
| Polona Hercog | games_won | 8.5 | 9.2 | 6.0 | **VARIANCE** | actual 6.0 inside p10-p90; projection reasonable |
| Dalibor Svrcina | dfs | 4.5 | 4.2 | 7.0 | **VARIANCE** | actual 7.0 inside p10-p90; projection reasonable |
| Kei Nishikori | dfs | 2.5 | 2.0 | 4.0 | **VARIANCE** | actual 4.0 inside p10-p90; projection reasonable |
| Hugo Gaston | dfs | 2.5 | 3.0 | 1.0 | **VARIANCE** | actual 1.0 inside p10-p90; projection reasonable |
| Colton Smith | dfs | 3.5 | 3.7 | 5.0 | **VARIANCE** | actual 5.0 inside p10-p90; projection reasonable |

**Interpretation gate:** cause shares are descriptive only until n>=25 losses.
