# PriceLens BH

Cost-of-living question answering and analytics for Bahrain, built on official iGA consumer price data.
IT8413 Generative AI for Data Insights - Group G2.

## Requirements

- Python 3.10 or newer ([python.org/downloads](https://www.python.org/downloads/); on Windows tick
  **"Add python.exe to PATH"**). Tested with Python 3.14.
- The packages in `requirements.txt` (versions pinned; installed automatically by the start file).

## 1. Add Dataset 3 (from the Moodle submission)

Dataset 3 is iGA's *Consumer Price Index - Tables, January 2020 - October 2023* (XLSX). iGA's Terms of Use do not
allow it to be republished, so it is **not in this repository**; it is included in the working datasets submitted
on Moodle. Save it as:

```
data/raw/CPI-Tables-_Jan2020-Oct_2023.xlsx
```

Datasets 1 and 2 (Bahrain Open Government Data License) are already in `data/raw/`.

## 2. Add the Gemini API key

Create the file `.streamlit/secrets.toml` (it is listed in `.gitignore` and is never committed) containing:

```toml
GEMINI_API_KEY = "your-key-here"
```

A free key can be created at [aistudio.google.com](https://aistudio.google.com/app/apikey).
<!-- Eman: confirm the key name matches the one the question-answering code reads. -->

## 3. Run the app

- **Windows:** double-click **`run_app.bat`**
- **macOS / Linux:** in a terminal inside the project folder, run `bash run_app.sh`

The first start takes 2-3 minutes (it creates a Python environment and installs the packages); later starts take
a few seconds. The app opens in the browser at http://localhost:8501. Close the window (or press Ctrl + C) to stop it.

<details>
<summary>Manual setup (the same steps as the start file)</summary>

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m src.pipeline.run        # prepares the data (data/processed/) and the quality report
streamlit run src/dashboard/page.py
```
</details>

## 4. Check the results

```bash
python -m scripts.check_dev_answers   # all development questions that use the data (31 checks)
python -m scripts.check_against_iga   # our % changes vs iGA's own published % changes
python -m pytest -q                   # automated tests
```

## Data

| # | Source (publisher: iGA) | Used for | Terms |
|---|---|---|---|
| 1 | [CPI - Division and Group - Index Number](https://www.data.gov.bh/explore/dataset/01-consumer-price-index-division-and-group-index-number/) | National index, 69 categories | Bahrain Open Government Data License v1.0 |
| 2 | [CPI, Division - Index Numbers by Nationality](https://www.data.gov.bh/explore/dataset/02-cpi-division-index-number-by-nationality/) | Bahraini vs non-Bahraini index | Bahrain Open Government Data License v1.0 |
| 3 | [CPI Tables, Jan 2020 - Oct 2023](https://www.iga.gov.bh/en/category/statistical-publications) (XLSX) | Expenditure weights, headline from 2011 | iGA website Terms of Use (not redistributed) |

The working copy covers **January 2017 - August 2026**, as in the approved proposal. How the data is prepared,
which values are changed and every check made are documented in [`docs/data_pipeline.md`](docs/data_pipeline.md)
and [`docs/quality_report.md`](docs/quality_report.md).

> Contains data from the Information & eGovernment Authority (iGA), Kingdom of Bahrain, used under the Bahrain
> Open Government Data License v1.0. Provided "as is" without warranty; the Government of Bahrain accepts no
> liability for its use. Percentage changes, averages, rankings and contributions are computed by Group G2 and
> are not official iGA figures.

## Project structure

```
data/raw/          source files (Dataset 3 added locally)
src/pipeline/      data loading, preparation and calculations (F1)
src/dashboard/     Streamlit dashboard: filters and charts (F2, F3)
scripts/           result checks and Dataset 3 download
tests/             automated tests
docs/              data preparation documentation and quality report
run_app.bat/.sh    one-click start
```
