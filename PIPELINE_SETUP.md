# Fatema's part: setup, checks and commit plan

## 1. Put the files in the group repository
Copy `src/`, `scripts/`, `tests/`, `docs/` and `data/raw/.gitkeep` into the repo root.
Add the lines in `.gitignore.pipeline` to `.gitignore` and the lines in
`requirements-pipeline.txt` to `requirements.txt` (agree this with Eman, who owns the repo).

## 2. Add the real files to `data/raw/`
Use exactly these names (or change `RAW_FILES` in `src/pipeline/config.py`):

| Source | File name |
|---|---|
| Dataset 1 | `01-consumer-price-index-division-and-group-index-number.csv` |
| Dataset 2 | `02-cpi-division-index-number-by-nationality.csv` |
| Dataset 3 | `CPI-Tables-_Jan2020-Oct_2023.xlsx` |

The pipeline keeps data only up to August 2026 (`DATA_END` in config.py), so a later download with extra months still gives the proposal's 8,004 + 2,288 rows. Write the real download date in the report.

## 3. Run, in this order
```bash
pip install -r requirements.txt
python -m src.pipeline.inspect_raw      # check the column mapping printed for D1, D2 and the D3 sheets
python -m src.pipeline.run              # builds data/processed/ and quality_report.md
python -m scripts.check_dev_answers     # 19/19 PASS on the real data (checked 19/11/2026)
python -m pytest -q                     # expect all tests to pass
streamlit run src/dashboard/page.py
```
If `inspect_raw` prints a MAPPING PROBLEM, set the column name in `COLUMN_OVERRIDES` in `config.py`.
If a check in `quality_report.md` says CHECK, read its detail before going on.

## 4. Commit in small steps from your own GitHub account
The commit history is the evidence of your contribution (brief Section 2), so commit each step separately:

1. `F1: add pipeline config and COICOP label normalisation`
2. `F1: load Datasets 1-3 and handle header line breaks and layouts`
3. `F1: prepare data - missing values, units, labels - with quality log`
4. `F1: add run script, processed outputs and data preparation report`
5. `Add analytics functions (MoM, YoY, since base, averages, weights)`
6. `F2/F3: add dashboard filters, four charts, KPIs and priority table`
7. `Add tests with synthetic quirk files and dev-set answer checker`
8. `Docs: data pipeline and preparation decisions`

Never commit API keys, the iGA XLSX, or `data/processed/`.

## 5. For Eman (F4/F6 tools)
Each function in `src/pipeline/analytics.py` returns a dict (`Figure.to_dict()`) with the value, the two
stored index values used, the periods and the source, so it can be registered as a Gemini function and the
model only writes the explanation around computed numbers. `DataUnavailable` means "decline" (F7).
