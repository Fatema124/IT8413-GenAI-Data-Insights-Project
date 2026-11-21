# Data pipeline and analytics dashboard (F1, F2, F3)

Lead: Fatema Alashiri · Contributor: Eman Khamdan · PriceLens BH, Group G2, IT8413

This document records how the working data is loaded and prepared (F1), how
it is filtered (F2) and what the dashboard shows (F3). Every rule below is
implemented in code under `src/pipeline/` and checked by `tests/`.

---

## 1. The pipeline in one picture

```
data/raw/                      src/pipeline/                         data/processed/
 D1 national CPI   ─┐
 D2 by nationality ─┼─► load.py ─► prepare.py ─► run.py ─────────►  cpi_long.csv
 D3 iGA tables     ─┘   (read)     (clean+check)  (save+report)       weights.csv, labels.csv
                                                                      quality_report.md
                                     analytics.py  ◄── one set of calculations used by
                                                       the dashboard, the model's tools (F4/F6)
                                                       and the report export (F9)
```

| Step | File | What it does |
|---|---|---|
| 1 Read | `load.py` | Reads each file as published. Fixes only what stops it being read: line breaks in headers, `;` delimiter, months laid out as columns in Dataset 3. |
| 2 Prepare | `prepare.py` | Every real decision about missing values, units and labels (Section 3). Logs each check. |
| 3 Join and save | `run.py` | Joins Datasets 1-3 into one long table and writes the outputs and the quality report. |
| 4 Compute | `analytics.py` | Month-on-month, year-on-year and since-base changes, annual averages, comparisons, weights, contributions, priorities. |
| 5 Show | `src/dashboard/` | Filters (F2) and charts (F3). |

## 2. The prepared table

`cpi_long.csv` is in long ("tidy") format: **one row = one month × one category × one household group.**

| Column | Meaning |
|---|---|
| `period`, `year`, `month` | Month of the index value |
| `code` | COICOP code in canonical form (`0` headline, `01` division, `01.1` group, `01.1.2` item) |
| `name` | One canonical name per code |
| `level` | 0 headline, 1 division, 2 group, 3 item (derived from the code) |
| `division` | Two-digit division the code belongs to |
| `population` | `National` (Dataset 1, Dataset 3), `Bahraini`, `Non-Bahraini` (Dataset 2) |
| `index` | Index number, April 2019 = 100, at the precision stored in the source |
| `source`, `source_row` | Which file and which row the value came from (for tracing an answer back) |

The shared dimensions that let the datasets be analysed together are **month** and **COICOP code**
(proposal, "How the datasets relate"). Dataset 2 joins Dataset 1 on the headline and the 12 divisions;
Dataset 3 adds the weights (Table 2.01) and the headline for 2011-2016.

## 3. Preparation decisions (what F1 asks for)

### 3.1 Missing values
| Decision | Why |
|---|---|
| A blank or non-numeric value stays missing and is counted in the quality report. It is **never filled or interpolated.** | Replies are quoted in the press and in parliament; an invented value would be a published error. |
| **0.0 is treated as missing.** Dataset 1 stores 0.0 for 04.2 Imputed rentals, 11.2 Accommodation and 12.4 Social protection from Jan 2017 to Apr 2019 (84 values). | An index cannot be 0; iGA's notes to Table 2.01 say these series were separated or added in May 2019. Left as 0, they would produce changes of -100%. |
| Every series is checked for missing months between the first and last month of its dataset. | A gap would silently change a year-on-year comparison. |
| A calculation that needs a missing value raises `DataUnavailable`, which the app reports as not available (F7). | Keeps refusal behaviour honest. |
| Nationality figures start in May 2019; earlier nationality questions are declined. Annual averages need all 12 months (so 2026 has none yet). | Proposal Section 1, out of scope. |

| **Working-copy cut-off: August 2026.** The files supplied contain September 2026 (69 + 26 rows); these are removed, leaving exactly the 8,004 and 2,288 rows recorded in the proposal. | Every ground-truth answer was computed on data to August 2026. |

### 3.2 Measurement units
| Decision | Why |
|---|---|
| Index values are kept at the stored precision (e.g. 76.02, or unrounded in Jul-Aug 2025). Rounding to 1 d.p. happens only on display. | Ground-truth changes are computed from stored values (proposal Section 3). Rounding first would move some answers by 0.1. |
| Each change states its reading: MoM (vs previous month), YoY (vs same month last year), since base (vs April 2019 = 100), and the two stored values used. | The brief says these readings can differ for the same category and date. |
| April 2019 = 100 is checked for every national series. | Confirms all series share the base. |
| Weights are read as % of the basket; if stored as shares they are converted (×100). Division weights must add up to 100%. | Wrong units would make contributions 100 times too small or large. |
| Every Dataset 1 value is compared with iGA's own Table 2.01 (Jan 2017 - Oct 2023): **5,574 of 5,574 values match.** | Independent confirmation that the portal file and the publication agree. |
| Table 1's headline is compared with Dataset 1: the 12 months of 2020 differ (by up to 3.0 points), while Table 2.01 and Table 1's own 2020 annual average (97.6) agree with Dataset 1. Only Table 1's 2011-2016 rows are used. | The inconsistency is inside iGA's file and does not touch the rows we use. |
| All computed figures are labelled as the group's own analysis. | Licence clause 3.3(b). |

### 3.3 Category labels
| Decision | Why |
|---|---|
| From June 2023 Dataset 1 drops the leading zero in divisions 01-09 (`1.1` for `01.1`, 41 of 69 codes each month). Codes are re-padded. | Otherwise one category becomes two series and the join with Dataset 2 fails after May 2023. |
| The headline is labelled `Consumers Price Index - CPI` (level 0) in Dataset 1 and `Consumer Price Indexs` (level 1) in Dataset 2. Both become code `0`, one name. | One headline series per household group. |
| Levels are derived from the code, not from each file's `level` column. | The two files number levels differently. |
| Each code gets one name: official COICOP names for divisions, otherwise the most frequent published label. Known misspellings are corrected in `config.NAME_FIXES`. | A one-off misspelling never becomes the displayed name. |
| Nationality labels are unified to `Bahraini` / `Non-Bahraini`. | |

### 3.4 Size and reduction
Dataset 1: 8,004 rows; Dataset 2: 2,288 rows (10,292 in total, above the 2,000 minimum). No reduction.
From Dataset 3 only Table 2.01 (weights) and the 2011-2016 headline rows are used; the working copy is kept
at the version retrieved on 13/10/2026 so every ground-truth answer stays reproducible.

### 3.5 Results on the real data (19/11/2026)

| Check | Result |
|---|---|
| Rows in working copy | D1 8,004 · D2 2,288 (as in the proposal) · D3 history 72 |
| Leading zero re-padded | 1,599 codes, from June 2023, 41 per month |
| Missing months / duplicates | 0 / 0 |
| Base April 2019 = 100 | 66/66 series that exist in April 2019 |
| Division weights | add up to 100.00% (Housing 25.02%, Transport 17.84%) |
| Weighted divisions vs headline | mean gap 0.09 index points |
| Contributions, Aug 2026 | sum +2.97 pts vs published headline YoY +2.93% |
| Development-set data answers | **19/19 checks pass** (questions 8, 10, 12, 13, 21, 23, 26, 28, 30) |

The full log is in `docs/quality_report.md`.

## 4. Filters (F2)

| Filter | Options |
|---|---|
| Time period | Any range of months, Jan 2011 - Aug 2026 (before 2017: headline only, from Dataset 3) |
| Households | National, Bahraini, Non-Bahraini |
| Category level and categories | Headline, divisions, groups and items |
| Measure | Year-on-year, month-on-month, since April 2019, index level |

All filters are held in one `Filters` object and applied by one function, `analytics.apply_filters`;
every chart and summary figure receives the same object, so every display responds to the active filters.
When a nationality is selected, groups and items (national only) are left out and the user is told.

## 5. Dashboard (F3)

| # | Visualisation | Type the brief asks for | Responds to |
|---|---|---|---|
| KPIs | Index, MoM, YoY, since base, change over the range for the first selected category | Summary figures | all filters |
| 1 | Line chart of the measure over time | Change over time | period, categories, households, measure |
| 2 | Bar chart of the measure at the end month (optionally National vs Bahraini vs non-Bahraini) | Comparison between categories | all filters |
| 3 | Basket weights (donut) and contribution of each division to headline YoY | Composition | categories, end month |
| 4 | Heatmap of the measure by category and month | Distribution | all filters |
| + | Monitoring priorities table: each division against the four criteria in the proposal | Supports the decision | end month |

**Contribution** (chart 3) = weight × (index now − index a year ago) ÷ headline a year ago, in percentage
points. It is an approximation; the sum is shown next to the published headline change so the gap is visible.

**Priority thresholds** (group's choice, `config.PRIORITY_RULES`): top 3 by YoY; top 3 by distance from base;
weight ≥ 10%; Bahraini − non-Bahraini YoY gap ≥ 1.0 pt. The table shows evidence; analysts decide.

## 6. How to run and check

```bash
python -m src.pipeline.inspect_raw     # 1. look at the raw files and the column mapping
python -m src.pipeline.run             # 2. build data/processed/ + quality_report.md
python -m scripts.check_dev_answers    # 3. development-set data answers vs the proposal
python -m pytest -q                    # 4. unit tests (synthetic files with the same quirks)
streamlit run src/dashboard/page.py    # 5. the dashboard on its own
```

`check_dev_answers` covers only development questions (8, 10, 12, 13, 21, 23, 26, 28, 30). Held-out
questions are not run before the final evaluation (brief Section 7.1).

## 7. Licence handling
Datasets 1-2 (Bahrain Open Government Data License v1.0) may be committed with attribution; the
attribution statement and extraction date are shown under the dashboard. Dataset 3 (iGA Terms of Use) is
not committed: `data/raw/*.xlsx` and `data/processed/` are git-ignored. `python -m scripts.download_sources`
fetches Dataset 3 from iGA and checks its SHA-256 fingerprint against the group's copy, so a changed file is
reported rather than silently used. The working datasets are submitted to the tutor on Moodle (proposal Section 2).

Dataset 3 is used inside the tool: the expenditure weights (chart 3, contributions, the priority table) and the
headline from January 2011 (chart 1 and the KPIs when the period starts before 2017). The "Data sources" panel
under the dashboard lists all three datasets with their terms.
