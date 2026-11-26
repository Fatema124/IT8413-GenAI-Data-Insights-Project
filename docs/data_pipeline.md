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
| 1 Read | `load.py` | Reads each file as published, without changing any value. Fixes only what stops it being read: line breaks in headers, `;` delimiter, months laid out as columns in Dataset 3. |
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
Dataset 3 adds the weights (Table 2.01), the headline for 2011-2016 and the 2010 headline derived from Table 1's 12-month changes.

## 3. Preparation decisions (what F1 asks for)

**What the pipeline changes.** Every published value is used as stored, except in these documented cases:

| Change | Scale | Why |
|---|---|---|
| Published **0.0** values are set to **missing** | 84 values: 04.2 Imputed rentals, 11.2 Accommodation, 12.4 Social protection, Jan 2017 - Apr 2019 | An index cannot be 0; iGA's notes say these series start in May 2019 (3.1) |
| Rows after **August 2026** are **dropped** | 95 rows: September 2026 (69 in Dataset 1, 26 in Dataset 2) | The proposal and its ground truth cover January 2017 - August 2026 (3.1) |
| Dataset 3 Table 1 is used only for **2011-2016** | 72 headline months kept | Its 2020 rows disagree with iGA's own Table 2.01 and with Dataset 1 (3.2) |
| COICOP codes and labels are standardised | 1,599 codes re-padded; headline labels unified; one name per code | Joins and display only; **no value changes** (3.3) |

Nothing is filled, interpolated or replaced from another source. The 179 Dataset 2 values that differ from iGA's
Table 3 are kept as published and flagged (3.2).

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
| Dataset 2 is compared with iGA's Table 3 (nationality index, Jan 2020 - Oct 2023): **1,017 of 1,196 values match**. The 179 that differ are all in **2022**: every non-Bahraini division and 8 Bahraini divisions (largest gap 59 points; e.g. non-Bahraini transport, Jan 2022: Dataset 2 145.7, Table 3 107.8). Table 3's divisions add up to the published headline; Dataset 2's 2022 divisions do not (Mar 2022: 103.7 vs headline 100.1). | The portal values for these months are very likely wrong. Dataset 2 stays the working source (proposal), every affected value is listed in `source_discrepancies.csv`, and the dashboard warns whenever a selection includes one. Whether to replace them with Table 3 is a group decision, because it could change ground-truth answers. |
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
Dataset 1: 8,004 rows; Dataset 2: 2,288 rows (10,292 in total, above the 2,000 minimum). No other reduction.

Datasets 1-2 are recorded as retrieved on 13/10/2026 (proposal Section 2). The committed CSV files also
contain September 2026 (8,073 and 2,314 rows). The pipeline removes the months after August 2026
(`DATA_END`), which leaves exactly the proposal's 8,004 and 2,288 rows, so every ground-truth answer stays
reproducible. From Dataset 3, Table 2.01 (weights), the 2011-2016 rows of Table 1 and Table 1's
2011 % changes (to derive 2010) are used; Tables 2.02, 2.03 and 3 are used only for cross-checks.

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
| Dataset 2 vs iGA Table 3 | 1,017/1,196 match; 179 differ, all in 2022 (see 3.2) |
| Our MoM / YoY vs iGA's published percentages (Tables 2.02, 2.03) | 4,744/4,746 and 4,777/4,779 reproduced within 0.1 pt; the 4 exceptions are errors in iGA's tables (e.g. 904.46% printed for a move from 99.0 to 99.4) |
| 2010 headline (derived) | 12 months from Table 1's 12-month changes; December 2010 computed two ways (12-month and 1-month change) agrees to 0.000 points |
| Dataset 3 version | SHA-256 matches the group's copy (checked on every build; a different file is flagged in the app) |
| Development-set data answers | **31/31 checks pass**: every development question that uses the datasets. 8, 10, 12, 13, 21, 23, 26, 28, 30: the values match. 16, 19, 20: the data cannot answer them, and for 16 the model's tool layer returns `not_available`. Whether the model's final answer declines is tested in the evaluation runs (F7), not here |

The full log is in `docs/quality_report.md`.

## 4. Filters (F2)

The filters sit in four numbered steps in the sidebar, so a user who does not know the data can start
from ready-made choices (tutor feedback at the build checkpoint, 25/11/2026).

| Step | Filter | Options |
|---|---|---|
| 1 | Time period | Presets: last 12 months, last 3 years, last 5 years, since April 2019, all years; or **Custom** (any months, Jan 2010 - Aug 2026). Before 2017 only the headline exists; 2010 is derived |
| 2 | Households | All households (national), Bahraini, non-Bahraini; option to compare all three side by side (detailed items have no household split, so they show all households only, and the chart says so) |
| 3 | Detail | Main groups (12 divisions), detailed items, or both (national only) |
| 3 | Within | Narrow the detailed items to one main group (e.g. only the items inside Food) |
| 3 | How to choose | By hand (up to 8), or automatically: fastest rising, fastest falling, largest share of spending (3 - 8 categories), with the overall index as a reference |
| 4 | Show change as | Price level (index), change from the previous month, from a year earlier, or since April 2019 |
| - | Key numbers for | Which selected category the four key-number cards describe |
| - | Reset | Returns every filter to its default |

All filters are held in one `Filters` object and applied by one function, `analytics.apply_filters`;
every chart, summary figure, plain-language finding and table receives the same object, so every display
responds to the active filters. When a nationality is selected, groups and items (national only) are left
out and the user is told.

## 5. Dashboard (F3)

| # | Visualisation | Type the brief asks for | Responds to |
|---|---|---|---|
| Key numbers + summary table | Four cards (price level, monthly change, yearly change, change over the period), each with a plain-language sentence and a tag naming the measure; a table for every selected category with a CSV download | Summary figures | all filters |
| Findings | "In plain words": 3 - 4 sentences generated from the data (overall change, biggest rise and fall in the selection, biggest contributor) | Summary figures | all filters |
| 1 | Line chart of the measure over time | Change over time | period, categories, households, measure |
| 2 | Bar chart of the measure at the end month (optionally National vs Bahraini vs non-Bahraini) | Comparison between categories | all filters |
| 3 | Basket weights (horizontal bar chart) and contribution of each division to headline YoY | Composition | categories (highlighted), end month (contributions); see 5.1 |
| 4 | Heatmap of the measure by category and month | Distribution | all filters |
| + | Monitoring priorities table: each division against the four criteria in the proposal | Supports the decision | categories, households, end month (ranks across all 12 divisions) |
| + | Year by year: annual average price level of each complete calendar year in the period (latest 6) and the change from the year before, computed with the same `annual_average` function the model tools use | Comparison between periods (proposal: "including annual averages") | period, categories, households |
| + | Data & sources: "Before you quote a figure" (limits of use, addressed to users), the sources with terms, and a coverage table counted from the prepared data (rows, months, categories, missing values per dataset) | Limits of use; what the data covers | - |

The header shows overall prices for the selected households across every available month, with the
selected period highlighted, so the user sees where the period sits in the longer history. Each key-number
card carries a small chart of the same measure (3 years, 12 months and 2 years up to the end of the period,
then the selected period); gaps stay gaps. Every chart states the question it answers and how to read it in
one line, worded for the measure on screen. Time axes label only months inside the data (never after
August 2026). Lines carry an end label only when there are four or fewer, and those labels are spaced so
they never overlap; with more lines the legend names them. When a period has no figures for the measure (e.g. Bahraini households before May 2019, or a yearly change before its first year), one note at the top says why and what to choose, and each empty chart says so in one line; contributions and the watch list say from which month they exist (January 2018 nationally; May 2020 for the watch list by nationality). The CSV download opens cleanly in Excel. Spending weights and contributions are
national only (iGA publishes no weights by nationality), and the page says so. Why each chart type was chosen
is recorded in [`docs/chart_choices.md`](chart_choices.md). A glossary ("What do these numbers mean?")
explains index, base period, the three changes, weights and contributions in plain words.

**Contribution** (chart 3) = weight × (index now − index a year ago) ÷ headline a year ago, in percentage
points. It is an approximation; the sum is shown next to the published headline change so the gap is visible.

**Priority thresholds** (group's choice, `config.PRIORITY_RULES`): top 3 by YoY; top 3 by distance from base;
weight ≥ 10%; Bahraini − non-Bahraini YoY gap ≥ 1.0 pt. The table shows evidence; analysts decide.

### 5.1 Why the composition chart follows the filters differently (design decision, F2)

Every analytical display is driven by one `Filters` object (time range, households, categories and
measure). One display, the basket composition chart, responds to these filters in a restricted way by
design. The expenditure weights come from iGA's Table 2.01, which publishes one fixed set of weights for the
national basket. iGA publishes no weights by month or by nationality, so the weights cannot change with the
time range or the household filter: showing different values would invent figures the source does not
contain. Instead, the chart highlights the divisions in the user's category selection, and the contribution
chart beside it is computed at the end month of the selected range. When Bahraini or non-Bahraini households
are selected, the dashboard says that the national basket is used. All other displays (trend, comparison,
heatmap, summary figures and priority table) respond to every filter. The same explanation is shown as a
caption under the chart.

### 5.3 Look and feel (design decision)

The users are government analysts and the people they reply to, so the page is designed to look like an
official report rather than a consumer app: a white filter panel on a light grey page, a navy header, one
calm blue accent for everything you can click (`.streamlit/config.toml`), cool greys for text and chart
axes, and no emoji in labels (small line icons instead). Text meets WCAG AA contrast (4.5:1 or more; the
lowest is 4.7:1, axis labels). Colour never carries meaning on its own: rises and falls also have ▲ / ▼
and words, and every chart has a sentence that says how to read it. Movement is limited to a short fade-in
and the header line drawing once; it is switched off for people whose computer asks for reduced motion.
Chart colours come from a palette checked for colour-blind readers, and a category keeps its colour
whatever else is selected.

### 5.2 Data caution for Dataset 2's 2022 values

179 Dataset 2 values in 2022 differ from iGA's own Table 3 (section 3.5). A figure can use a stored value
without showing it: a month-on-month change reads the month before, and a year-on-year change reads the
same month a year earlier. The caution (`chart_data.flagged_values`) therefore checks every month a view
reads, not only the months it shows. For example, non-Bahraini year-on-year changes for January to
December 2023 are flagged, because each compares with a 2022 value. The household comparison chart, the
summary figures and the priority table's nationality-gap criterion (`chart_data.priority_flagged`) are
checked the same way, and the model's tools add a `caution` to any result that uses a flagged value.

## 6. How to run and check

```bash
python -m src.pipeline.inspect_raw     # 1. look at the raw files and the column mapping
python -m src.pipeline.run             # 2. build data/processed/ + quality_report.md
python -m scripts.check_dev_answers    # 3. development-set data answers vs the proposal
python -m scripts.check_against_iga    #    our % changes vs iGA's own published % changes
python -m pytest -q                    # 4. unit tests (synthetic files with the same quirks)
streamlit run src/dashboard/page.py    # 5. the dashboard on its own
```

`check_dev_answers` covers every development question that uses the datasets (8, 10, 12, 13, 16, 19, 20, 21, 23, 26, 28, 30;
questions 2, 4, 6 and 25 use only the documents). For 16, 19 and 20 it checks data coverage (the data cannot
answer them); it is not evidence that the model declines, which comes from the evaluation runs. Held-out
questions are not run before the final evaluation (brief Section 7.1).

## 7. Licence handling
Datasets 1-2 (Bahrain Open Government Data License v1.0, 20 May 2025,
https://www.nea.gov.bh/Documents/OpenDataLicense.pdf) may be committed with attribution. The set statement
(clause 3.3(c): provider, licence URL, disclaimer), the extraction date (3.3(a)) and the note that computed
figures are the group's own analysis (3.3(b)) are shown under the dashboard and in the README; the text lives
in one place, `config.ATTRIBUTION`. Dataset 3 (iGA Terms of Use) is
not committed: `data/raw/*.xlsx` and `data/processed/` are git-ignored. `python -m scripts.download_sources`
fetches Dataset 3 from iGA and checks its SHA-256 fingerprint against the group's copy, so a changed file is
reported rather than silently used. The working datasets are submitted to the tutor on Moodle (proposal Section 2).

Dataset 3 is used inside the tool: the expenditure weights (chart 3, contributions, the priority table) and the
headline from January 2011 (chart 1 and the KPIs when the period starts before 2017). The "Data sources" panel
under the dashboard lists all three datasets with their terms.

**Open point for the tutor (proposal Terms B).** The proposal's position was that Dataset 3 is "used only
inside the tool and not published". The deployed app is public, so anyone can see figures that come from
Dataset 3 (weights, the 2010-2016 headline, Table 3 values in the discrepancy table). The group will confirm
with the tutor that this is acceptable; if not, the Streamlit app is switched to private (Settings → Sharing)
and shared only with the tutor and the group.

## 8. Model tools for questions over the data (interface for F4 and F6)

`src/pipeline/tools.py` is the layer the model calls; the model never computes a number itself.

| Job | How |
|---|---|
| Accept what users type | Categories by code or name ("4.5", "Transport", "headline"); households ("non bahraini", "expats"); months ("2026-08", "Aug 2026", "latest") |
| Return plain JSON | Every result is a dict of plain values (no DataFrames, no NaN), with the stored values used and the source |
| Say why something failed | `not_available` = the sources do not hold it, so the app declines (F7). `bad_input` = the request was unclear ("last month"), so fix it or ask, never decline. `error` = a bug |
| Carry cautions | A result that uses a flagged 2022 Dataset 2 value includes a `caution`; a derived 2010 value includes a note |

`TOOL_DECLARATIONS` describes the 12 tools (name, description, JSON-schema parameters) for function calling.
Usage: `Toolbox(prepared_data).call("get_change", {"category": "transport", "month": "2026-08", "measure": "yoy"})`.

## 9. Decisions to record in the report

- **Dataset 2 versus Table 3 (2022).** Dataset 2 stays the working source, as the proposal states, and every
  figure that uses an inconsistent 2022 value is flagged on screen and in the tool results. No test question
  uses 2022 nationality figures.
- **Stored precision.** The proposal mentions unrounded values in July and August 2025. The quality report
  finds them more widely: Dataset 1 from January 2017, and Dataset 2 in March 2025 and February 2026.
  Values are kept at their stored precision and rounded only for display.
- **2010.** Derived from Table 1's 12-month changes and labelled "derived" wherever it appears; nothing
  before 2010 can be derived, so December 2009 is declined (Q20).
