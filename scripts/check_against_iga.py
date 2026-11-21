"""Check our calculations against iGA's own published percentage changes.

    python -m scripts.check_against_iga

iGA's CPI tables (Dataset 3) publish, for Jan 2018 - Oct 2023:
  * Table 2.02 - percentage change from the same month of the previous year
  * Table 2.03 - percentage change from the previous month
This script recomputes every one of those figures with our own analytics
functions (from the prepared Dataset 1) and counts how many agree within
0.1 percentage points. It needs Dataset 3 in data/raw/.
"""
from __future__ import annotations

import sys

import pandas as pd

from src.pipeline import analytics as A
from src.pipeline import config, labels, load
from src.pipeline.run import build, load_prepared

TABLES = {"2.02": ("yoy", "year-on-year %"), "2.03": ("mom", "month-on-month %")}


def _code(raw_code, raw_name):
    if pd.isna(raw_code):
        return config.HEADLINE_CODE if str(raw_name).strip().lower() == "all divisions" else None
    return labels.normalise_code(raw_code)


def compare(cpi: pd.DataFrame, sheet: pd.DataFrame, measure: str) -> pd.DataFrame:
    hdr = next(i for i in range(min(20, len(sheet)))
               if sum(load.parse_period_text(v) is not None for v in sheet.iloc[i].values if pd.notna(v)) >= 6)
    header = list(sheet.iloc[hdr].values)
    dates = [(j, load.parse_period_text(v)) for j, v in enumerate(header) if pd.notna(v)]
    dates = [(j, p) for j, p in dates if p is not None]
    code_j = next(j for j, h in enumerate(header) if "code" in str(h).lower())
    name_j = next(j for j, h in enumerate(header) if "division" in str(h).lower())
    rows = []
    for i in range(hdr + 1, len(sheet)):
        code = _code(sheet.iat[i, code_j], sheet.iat[i, name_j])
        if code is None:
            continue
        for j, period in dates:
            iga = pd.to_numeric(sheet.iat[i, j], errors="coerce")
            if pd.isna(iga):
                continue
            try:
                ours = A.change(cpi, code, period, measure).value
            except A.DataUnavailable:
                continue
            rows.append((code, period, float(iga), ours))
    out = pd.DataFrame(rows, columns=["code", "period", "iga", "ours"])
    out["gap"] = (out["ours"] - out["iga"]).abs()
    return out


def main() -> int:
    path = config.RAW_DIR / config.RAW_FILES["D3"]
    if not path.exists():
        print("Dataset 3 is needed for this check (see python -m scripts.download_sources).")
        return 1
    try:
        cpi = load_prepared().cpi
    except FileNotFoundError:
        cpi = build().cpi
    book = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    for sheet_name, (measure, label) in TABLES.items():
        if sheet_name not in book:
            print(f"Table {sheet_name} not found in {path.name}")
            continue
        r = compare(cpi, book[sheet_name], measure)
        ok = int((r["gap"] <= 0.1).sum())
        print(f"Table {sheet_name} ({label}): {ok}/{len(r)} of iGA's published figures reproduced within 0.1 pt")
        for x in r[r["gap"] > 0.1].itertuples():
            print(f"   differs: {x.code} {x.period:%b %Y}  iGA {x.iga:.2f}  ours {x.ours:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
