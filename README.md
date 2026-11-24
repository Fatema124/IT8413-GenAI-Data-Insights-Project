<div align="center">

<a href="https://pricelens-bh.streamlit.app">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/banner-dark.svg">
    <img src="docs/images/banner.svg" alt="PriceLens BH: cost-of-living monitor for Bahrain, with the headline CPI from January 2011 to August 2026" width="100%">
  </picture>
</a>

<br>

[![Open the live app](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://pricelens-bh.streamlit.app)

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?logo=streamlit&logoColor=white)
![Tests](https://img.shields.io/badge/tests-76%20passing-2ea44f)
![Development checks](https://img.shields.io/badge/development%20checks-31%2F31-2ea44f)
![Data](https://img.shields.io/badge/data-iGA%20Bahrain-2a78d6)

**IT8413 Generative AI for Data Insights · Group G2 · Bahrain Polytechnic** 🇧🇭

[**Live app**](https://pricelens-bh.streamlit.app) ·
[**Status**](#-project-status) ·
[**Quick start**](#-quick-start) ·
[**How it works**](#-how-it-works) ·
[**Data**](#-data) ·
[**Team**](#-team)

</div>

<br>

<div align="center">
  <a href="https://pricelens-bh.streamlit.app">
    <img src="docs/images/dashboard-framed.png" alt="PriceLens BH dashboard: filters, summary figures and a data caution" width="92%">
  </a>
  <br>
  <sub>The dashboard on Streamlit Community Cloud. Click the picture to open it.</sub>
</div>

<br>

## ✨ What it does

PriceLens BH turns Bahrain's official consumer price index into answers analysts can quote with confidence.
The data pipeline and analytics dashboard (F1 - F3) are complete and live, and the tools the model will call are ready.

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🔎 16 years of prices</h3>
      Filter by period (2010 - Aug 2026; 2010 derived), household (national, Bahraini, non-Bahraini), category and measure.
    </td>
    <td width="33%" valign="top">
      <h3>📈 Four analytical views</h3>
      Change over time, comparison between categories, basket composition with contributions, and a heatmap.
    </td>
    <td width="33%" valign="top">
      <h3>🧮 Summary figures</h3>
      Index level, month-on-month, year-on-year and change since April 2019 for every selected category.
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <h3>🎯 Monitoring priorities</h3>
      Every division scored against the four criteria in our proposal: rising fastest, furthest from base, large share of spending, different by nationality.
    </td>
    <td width="33%" valign="top">
      <h3>⚠️ Data you can trust</h3>
      Every figure traces back to the stored values and the dataset it came from; known problems in the source are flagged on screen.
    </td>
    <td width="33%" valign="top">
      <h3>☁️ Runs anywhere</h3>
      Open it online, or start it on your own computer with one double-click on Windows or one command on macOS and Linux.
    </td>
  </tr>
</table>

## 🧩 Project status

| Part | Features | Status |
|---|---|---|
| Data pipeline and analytics dashboard | F1 · F2 · F3 | ✅ Done |
| Question answering over data | F4 · F6 · F8 | 🔧 Model tools ready ([`tools.py`](src/pipeline/tools.py)); model next |
| Document retrieval, citations and refusal | F5 · F7 | ⏳ Coming next |
| Query log, configuration display and report export | F9 · F10 | ⏳ Coming next |
| Evaluation runs, vendor benchmark and enhancements | - | ⏳ Coming next |

## ✅ Verified against the source

| Check | Result |
|---|---|
| Development questions that use the data | **31 / 31** checks pass (12 questions; for 3 of them the checks confirm the data cannot answer, so the tool must decline) |
| Dataset 1 vs iGA's own Table 2.01 | **5,574 / 5,574** values match |
| Our month-on-month and year-on-year % vs iGA's published % | **4,744 / 4,746** and **4,777 / 4,779** (the exceptions are typos in iGA's tables) |
| Dataset 2 vs iGA's Table 3 | **179** inconsistent values found in 2022, kept as published and flagged in the dashboard |
| 2010 headline, derived from iGA's 12-month changes | December 2010 computed two ways agrees to **0.000** points |
| Dataset 3 version | SHA-256 fingerprint matches the group's copy on every build |
| Automated tests | **76** passing |

The held-out test questions are never run before the final evaluation.

## 🚀 Quick start

> [!TIP]
> **Online:** just open the [live app](https://pricelens-bh.streamlit.app). The steps below are for running it on your own computer.

**You need:** Python 3.10 or newer ([python.org](https://www.python.org/downloads/); on Windows tick **"Add python.exe to PATH"**).

#### 1 · Add Dataset 3 (from the Moodle submission)

iGA's Terms of Use don't allow this file to be republished, so it is **not in the repository**. Save it as:

```
data/raw/CPI-Tables-_Jan2020-Oct_2023.xlsx
```

Or run `python -m scripts.download_sources` to fetch it from iGA's website (its fingerprint is checked).

#### 2 · Add the Gemini API key

Needed by the question-answering features (F4 - F8); the dashboard runs without it.
Create `.streamlit/secrets.toml` (git-ignored, never committed):

```toml
GEMINI_API_KEY = "your-key-here"
```

<!-- Eman: confirm the key name matches the one the question-answering code reads. -->

#### 3 · Run

| Windows | macOS / Linux |
|---|---|
| Double-click **`run_app.bat`** | `bash run_app.sh` |

The first start takes 2-3 minutes (it creates the environment and installs the pinned packages); later starts take seconds.
The app opens at http://localhost:8501.

<details>
<summary><b>Manual setup</b></summary>

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m src.pipeline.run        # prepares the data and the quality report
streamlit run src/dashboard/page.py
```
</details>

## 🧭 How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/pipeline-dark.svg">
  <img src="docs/images/pipeline.svg" alt="Three iGA datasets flow through load.py, prepare.py and run.py into analytics.py, which feeds the dashboard (live), the model tools and the report export (coming next)" width="100%">
</picture>

One set of calculations feeds the dashboard, the model's tools and the report, so a figure is always computed
the same way. The model calls them through [`src/pipeline/tools.py`](src/pipeline/tools.py), which accepts what
users type ("transport", "Aug 2026") and tells apart "not in the sources" (decline) from "unclear request" (ask
again). When the sources don't hold a value, the tool declines instead of guessing.
Full details: [`docs/data_pipeline.md`](docs/data_pipeline.md).

## 💬 Question answering

> 🚧 *This section will be completed by the question-answering team: how to ask questions over the data and the
> documents (F4 - F8), the model used, and example questions and answers.*

<!-- Eman / Abrar: add the question-answering description, the model and provider, and screenshots here. -->

## 📏 Evaluation and benchmark

> 🚧 *Results of the control, baseline, v1 and v2 runs, the vendor benchmark and the two enhancements will be added
> after the evaluation.*

<!-- Add the results table and the link to the results spreadsheet here. -->

## 📚 Data

| # | Source (publisher: iGA) | Used for | Terms |
|---|---|---|---|
| 1 | [CPI - Division and Group - Index Number](https://www.data.gov.bh/explore/dataset/01-consumer-price-index-division-and-group-index-number/) | National index, 69 categories | Bahrain Open Government Data License v1.0 |
| 2 | [CPI, Division - Index Numbers by Nationality](https://www.data.gov.bh/explore/dataset/02-cpi-division-index-number-by-nationality/) | Bahraini vs non-Bahraini index | Bahrain Open Government Data License v1.0 |
| 3 | [CPI Tables, Jan 2020 - Oct 2023](https://www.iga.gov.bh/en/Media/Others/Statistical%20Publications/Economic%20Statistics/CPI/CPI-Tables-%20Jan2020-Oct%202023.xlsx) (XLSX download) | Expenditure weights, headline 2011 - 2016 (2010 derived), cross-checks | iGA website Terms of Use (not redistributed) |

The working copy covers **January 2017 - August 2026**, as in the approved proposal. Which values the pipeline
changes, and why, is listed in [`docs/data_pipeline.md`](docs/data_pipeline.md); every check is in
[`docs/quality_report.md`](docs/quality_report.md); download dates, versions and terms are in
[`docs/sources.md`](docs/sources.md).

> [!NOTE]
> Contains data from the Information & eGovernment Authority (iGA), Kingdom of Bahrain, via www.data.gov.bh,
> governed by the Bahrain Open Government Data License v1.0 (20 May 2025), available at
> https://www.nea.gov.bh/Documents/OpenDataLicense.pdf. Data extracted on 13/10/2026 (Datasets 1-2).
> Provided "as is" without warranty; to the fullest
> extent permitted by law, the Government of Bahrain is not liable for any loss caused by the use of the data
> or of analyses derived from it. Percentage changes, averages, rankings and contributions are computed by
> Group G2 from the published index numbers; they are not official iGA figures.

<details>
<summary><b>🧪 Checking the results</b></summary>

```bash
python -m scripts.check_dev_answers   # development questions that use the data (31 checks)
python -m scripts.check_against_iga   # our % changes vs iGA's own published % changes
python -m pytest -q                   # automated tests
```
</details>

<details>
<summary><b>📁 Project structure</b></summary>

```
data/raw/          source files (Dataset 3 added locally)
src/pipeline/      data loading, preparation, calculations and the model's tools
src/dashboard/     Streamlit dashboard: filters and charts
scripts/           result checks, Dataset 3 download, sources record
tests/             automated tests
docs/              data preparation, quality report, sources, images
run_app.bat/.sh    one-click start
```

<!-- Add the folders for the question-answering and document parts here. -->
</details>

## 👥 Team

| Member | Leads |
|---|---|
| **Eman Khamdan** | Question answering over data (F4, F6, F8) · test set and evaluation runs · repository and credentials |
| **Fatema Alashiri** | Data pipeline and dashboard (F1 - F3) · query log and report export (F9, F10) · vendor benchmark · enhancements · presentation |
| **Abrar Alawadhi** | Document retrieval, citations and refusal (F5, F7) · sources file · failure analysis · responsible AI · project report |

<br>

<div align="center">
<sub>Built for IT8413 Generative AI for Data Insights · Bahrain Polytechnic · 2026</sub>
</div>
