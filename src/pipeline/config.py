"""Central configuration for the PriceLens BH data pipeline (F1).

Everything that describes *the sources* (file names, versions, licence
statements, base period) or *a preparation decision* (how codes, labels and
missing values are handled) lives here, so the decisions are written down in
one place and the report can point to them.

Source numbers (Dataset 1-3) follow Section 2 of the approved proposal (G2).
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# File names inside data/raw/. Rename here if your downloaded files differ.
RAW_FILES = {
    "D1": "01-consumer-price-index-division-and-group-index-number.csv",
    "D2": "02-cpi-division-index-number-by-nationality.csv",
    "D3": "CPI-Tables-_Jan2020-Oct_2023.xlsx",
}

# --------------------------------------------------------------------------
# Source metadata (shown in the app, the report export and the README)
# --------------------------------------------------------------------------
SOURCES = {
    "D1": {
        "title": "Consumer Price Index (CPI) - Division and Group - Index Number",
        "publisher": "Information & eGovernment Authority (iGA)",
        "url": "https://www.data.gov.bh/explore/dataset/01-consumer-price-index-division-and-group-index-number/",
        "coverage": "Monthly, Jan 2017 - Aug 2026",
        "retrieved": "2026-10-13",   # update to the group's actual download date if different
        "licence": "Bahrain Open Government Data License v1.0",
        "expected_rows": 8004,
    },
    "D2": {
        "title": "Consumers Price Index (CPI), Division - Index Numbers by Nationality",
        "publisher": "Information & eGovernment Authority (iGA)",
        "url": "https://www.data.gov.bh/explore/dataset/02-cpi-division-index-number-by-nationality/",
        "coverage": "Monthly, May 2019 - Aug 2026",
        "retrieved": "2026-10-13",
        "licence": "Bahrain Open Government Data License v1.0",
        "expected_rows": 2288,
    },
    "D3": {
        "title": "Consumer Price Index - Tables, January 2020 - October 2023 (XLSX, published 30/10/2023)",
        "publisher": "Information & eGovernment Authority (iGA)",
        "url": "https://www.iga.gov.bh/en/category/statistical-publications",
        "coverage": "Weights (Table 2.01); headline history from Jan 2011",
        "retrieved": "2026-10-27",
        "licence": "iGA website Terms of Use (not redistributed)",
        "expected_rows": None,
    },
}

# Licence clause 3.3(c) requires a set attribution statement; 3.3(b) requires
# that our own analysis is labelled as ours. Both are displayed in the app.
ATTRIBUTION = (
    "Contains data from the Information & eGovernment Authority (iGA), "
    "Kingdom of Bahrain, used under the Bahrain Open Government Data License "
    "v1.0. Data extracted on 13/10/2026 (Datasets 1-2). Provided 'as is' "
    "without warranty; the Government of Bahrain accepts no liability for its use."
)
OWN_ANALYSIS_NOTE = (
    "Percentage changes, averages, rankings and contributions are computed "
    "by Group G2 from the published index numbers; they are not official iGA figures."
)

# --------------------------------------------------------------------------
# Measurement units
# --------------------------------------------------------------------------
BASE_PERIOD = "2019-04"          # April 2019 = 100 for every series
BASE_VALUE = 100.0
INDEX_UNIT = "index points (April 2019 = 100)"
WEIGHT_UNIT = "% of the CPI basket"
DISPLAY_DECIMALS = 1             # proposal Section 3: index values to 1 d.p.
GROUND_TRUTH_TOLERANCE = 0.1     # proposal Section 3: +/-0.1 on % changes

# Working-copy cut-off. The proposal's ground truth uses data up to August
# 2026 (8,004 + 2,288 rows). Later downloads add months; they are dropped
# here so every answer stays reproducible. Change only if the group agrees.
DATA_END = "2026-08"

# --------------------------------------------------------------------------
# Category labels
# --------------------------------------------------------------------------
HEADLINE_CODE = "0"
HEADLINE_NAME = "All items (headline CPI)"
NATIONAL = "National"
POPULATIONS = ("National", "Bahraini", "Non-Bahraini")

# Labels that refer to the headline index in either file (proposal: the
# headline row is labelled differently in D1 and D2).
HEADLINE_LABEL_PATTERNS = (
    r"^consumers?\s+price\s+index(s|es)?\b",
    r"^cpi$",
    r"^general\s+index",
    r"^all\s+items",
)

# Spelling fixes for category names, applied after whitespace cleaning.
# Add entries here when `python -m src.pipeline.inspect_raw` shows a variant.
NAME_FIXES: dict[str, str] = {
    "Consumer Price Indexs": HEADLINE_NAME,
    "Consumers Price Index - CPI": HEADLINE_NAME,
}

# Official COICOP division names (used when a file's label is misspelt).
DIVISION_NAMES = {
    "01": "Food and Non-Alcoholic Beverages",
    "02": "Alcoholic Beverages and Tobacco",
    "03": "Clothing and Footwear",
    "04": "Housing, Water, Electricity, Gas and Other Fuels",
    "05": "Furnishings, Household Equipment and Routine Household Maintenance",
    "06": "Health",
    "07": "Transport",
    "08": "Communication",
    "09": "Recreation and Culture",
    "10": "Education",
    "11": "Restaurants and Hotels",
    "12": "Miscellaneous Goods and Services",
}

# Nationality labels as they may appear in Dataset 2 -> canonical label.
NATIONALITY_MAP = {
    "bahraini": "Bahraini",
    "bahrainis": "Bahraini",
    "non-bahraini": "Non-Bahraini",
    "non bahraini": "Non-Bahraini",
    "non-bahrainis": "Non-Bahraini",
    "nonbahraini": "Non-Bahraini",
}

# --------------------------------------------------------------------------
# Column recognition
# --------------------------------------------------------------------------
# Headers are normalised (line breaks removed, lower-cased) and then matched
# by keyword. If a file uses names the rules cannot resolve, set them here,
# e.g. COLUMN_OVERRIDES["D1"] = {"value": "index number"}.
COLUMN_OVERRIDES: dict[str, dict[str, str]] = {"D1": {}, "D2": {}}

# Dataset 3 is not committed (iGA Terms of Use). `python -m scripts.download_sources`
# fetches it from iGA and checks it is the same version the group used.
# Paste the direct link of the XLSX (right-click the download link on the iGA
# page -> Copy link address).
D3_DOWNLOAD_URL: str | None = ("https://www.iga.gov.bh/en/Media/Others/Statistical%20Publications/"
                                 "Economic%20Statistics/CPI/CPI-Tables-%20Jan2020-Oct%202023.xlsx")
D3_PAGE_URL = "https://www.iga.gov.bh/en/category/statistical-publications"
D3_SHA256 = "5b3f8ef1bdf5ebcf5bae98c216880411df5f7422ccef356641c0ed0820e7d14f"  # file used by the group
D3_BYTES = 228243

# Dataset 3 sheets. None = find automatically by searching cell text.
D3_WEIGHTS_SHEET: str | None = "2.01"  # Table 2.01: 'Expenditure Weights' column
D3_NATIONALITY_SHEET: str | None = "3"  # Table 3: index by nationality (cross-check of Dataset 2)
D3_HISTORY_SHEET: str | None = "1"     # Table 1: headline CPI, monthly from Jan 2011
D3_HISTORY_KEEP = ("2011-01", "2016-12")  # only these rows are used (proposal)

# --------------------------------------------------------------------------
# Monitoring priorities (supports the decision in proposal Section 1)
# --------------------------------------------------------------------------
# A division is flagged on each criterion below. Thresholds are the group's
# documented choice and are shown in the dashboard next to the table.
PRIORITY_RULES = {
    "rising_fastest_top_n": 3,      # top-N divisions by year-on-year change
    "furthest_from_base_top_n": 3,  # top-N by absolute change since April 2019
    "large_weight_min": 10.0,       # weight >= 10% of the basket
    "nationality_gap_min": 1.0,     # |Bahraini YoY - non-Bahraini YoY| >= 1.0 pt
}
