"""Synthetic raw files that copy every known quirk of the real sources.

The real files are not stored in the repository (licence terms), so the
tests run on look-alike files built here. Each quirk listed in the proposal
is reproduced on purpose, so a test fails if the pipeline stops handling it:

  * the real column names (N, Year, '01 January', COICOP Code, Level,
    'COICOP <line break> Division & Group', Point) and a line break in the header
  * a later download with one extra month (Sep 2026) beyond the cut-off
  * 0.0 used for a series before it was published (04.2 before May 2019)
  * Dataset 1 drops the leading zero in divisions 01-09 from June 2023
  * headline labelled 'Consumers Price Index - CPI' (level 0) in D1 and
    'Consumer Price Indexs' (level 1) in D2
  * mixed precision (unrounded values in Jul-Aug 2025)
  * one misspelt label and one blank value
  * Dataset 3 laid out like iGA's file: sheet '1' (year row, then month rows)
    and sheet '2.01' (code, level, name, weights, one column per month)

A few values are planted to equal the proposal's development-set answers
(questions 8, 13, 23, 26, 28) so the answer checker can be tested.
Numbers are otherwise invented.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

D1_CODES = ["0"] + [f"{d:02d}" for d in range(1, 13)] + ["01.1", "01.1.2", "04.1", "04.2", "04.5", "07.2"]
D2_CODES = ["0"] + [f"{d:02d}" for d in range(1, 13)]
NAMES = {
    "0": "Consumers Price Index - CPI", "01": "Food and Non-Alcoholic Beverages",
    "02": "Alcoholic Beverages and Tobacco", "03": "Clothing and Footwear",
    "04": "Housing, Water, Electricity, Gas and Other Fuels", "05": "Furnishings, Household Equipment",
    "06": "Health", "07": "Transport", "08": "Communication", "09": "Recreation and Culture",
    "10": "Education", "11": "Restaurants and Hotels", "12": "Miscellaneous Goods and Services",
    "01.1": "Food", "01.1.2": "Meat", "04.1": "Actual Rentals for Housing",
    "04.2": "Imputed Rentals For Housing*", "04.5": "Electricity, Gas and Other Fuels", "07.2": "Operation of Personal Transport Equipment",
}
WEIGHTS = {"01": 13.07, "02": 0.41, "03": 4.36, "04": 25.02, "05": 6.98, "06": 2.13,
           "07": 17.84, "08": 5.41, "09": 4.66, "10": 8.60, "11": 5.06, "12": 6.46}

PLANTED = {  # (code, 'YYYY-MM') -> value, matching proposal ground truth
    ("04.5", "2026-07"): "83.8", ("04.5", "2026-08"): "89.1", ("04.5", "2025-08"): "76.02",
    ("03", "2026-08"): "64.5", ("0", "2026-03"): "102.4", ("01.1.2", "2026-08"): "137.5",
    ("11", "2026-08"): "115.0", ("04", "2025-08"): "89.93", ("04", "2026-08"): "88.9",
    ("10", "2025-08"): "108.41",
}
PLANTED_D2 = {("11", "2026-08", "Bahraini"): "119.6", ("11", "2026-08", "Non-Bahraini"): "101.6"}


def _series(code: str, months: pd.DatetimeIndex, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.1, 0.6, len(months))
    level = 100 + np.cumsum(steps)
    base = months.get_loc(pd.Timestamp("2019-04-01")) if pd.Timestamp("2019-04-01") in months else None
    if base is not None:
        level = level - level[base] + 100.0   # every series = 100 in April 2019
    return level


def _fmt(value: float, period: pd.Timestamp) -> str:
    if period.year == 2025 and period.month in (7, 8):
        return f"{value:.6f}"                 # unrounded months
    return f"{value:.1f}"


def make_d1(path: Path) -> None:
    months = pd.date_range("2017-01-01", "2026-09-01", freq="MS")   # includes Sep 2026
    rows = []
    for k, code in enumerate(D1_CODES):
        values = _series(code, months, seed=k)
        for p, v in zip(months, values, strict=True):
            if code == "10" and p >= pd.Timestamp("2025-09-01"):
                v = 111.4                       # flat after Sep 2025 (like question 12)
            text = PLANTED.get((code, f"{p:%Y-%m}"), _fmt(v, p))
            if code == "04.2" and p < pd.Timestamp("2019-05-01"):
                text = "0.0"                    # not yet published
            shown = code
            if code != "0" and p >= pd.Timestamp("2023-06-01") and int(code.split(".")[0]) <= 9:
                shown = code.lstrip("0")        # '01.1' -> '1.1' from June 2023
            name = NAMES[code]
            if code == "06" and p == pd.Timestamp("2021-03-01"):
                name = "Helth"                  # one-off misspelling
            rows.append({"Year": p.year, "Month": p.strftime("%m %B"),
                         "COICOP Code": shown, "Level": 0.0 if code == "0" else code.count(".") + 2.0,
                         "COICOP \nDivision & Group": name, "Point": text})
    df = pd.DataFrame(rows)
    df.insert(0, "N", range(1, len(df) + 1))
    df.loc[(df["COICOP Code"] == "8") & (df["Year"] == 2024) & (df["Month"] == "05 May"), "Point"] = ""
    df.to_csv(path, index=False)


def make_d2(path: Path) -> None:
    months = pd.date_range("2019-05-01", "2026-09-01", freq="MS")
    rows = []
    for k, code in enumerate(D2_CODES):
        for j, nat in enumerate(["Bahraini", "Non-Bahraini"]):
            values = _series(code, pd.date_range("2019-04-01", "2026-09-01", freq="MS"), seed=100 + 2 * k + j)[1:]
            for p, v in zip(months, values, strict=True):
                text = PLANTED_D2.get((code, f"{p:%Y-%m}", nat), f"{v:.1f}")
                rows.append({"Year": p.year, "Month": p.strftime("%m %B"), "COICOP Code": code,
                             "Level": 1.0 if code == "0" else 2.0,
                             "COICOP \nDivision & Group": "Consumer Price Indexs" if code == "0" else NAMES[code],
                             "Nationality": nat, "Point": text})
    df = pd.DataFrame(rows)
    df.insert(0, "N", range(1, len(df) + 1))
    df.to_csv(path, index=False)


def _table3(d2_path: Path) -> list[list]:
    """iGA Table 3 layout: a date row (each date over two columns), then a nationality row.
    One value is changed on purpose (Non-Bahraini transport, Jan 2022) to test the cross-check."""
    d2 = pd.read_csv(d2_path, dtype=str)
    d2.columns = [" ".join(c.split()) for c in d2.columns]
    d2["period"] = pd.to_datetime(d2["Year"] + "-" + d2["Month"].str[:2] + "-01")
    months = pd.date_range("2020-01-01", "2023-10-01", freq="MS")
    date_row, nat_row = ["Code", "Level", "COICOP \nDivision & Group"], [None, None, None]
    for p in months:
        date_row += [p, None]
        nat_row += ["Bahraini", "Non-Bahraini"]
    rows = [["Table 3"], ["Consumers price index, division- index numbers by nationality"], [None], [None],
            [None], [None], date_row, nat_row]
    for code in D2_CODES:
        name = "All Divisions" if code == "0" else NAMES[code]
        row = [None if code == "0" else code, None if code == "0" else 2, name]
        for p in months:
            for nat in ("Bahraini", "Non-Bahraini"):
                v = float(d2[(d2["COICOP Code"] == code) & (d2["Nationality"] == nat) & (d2["period"] == p)]["Point"].iloc[0])
                if code == "07" and nat == "Non-Bahraini" and p == pd.Timestamp("2022-01-01"):
                    v -= 40.0                       # planted discrepancy
                row.append(v)
        rows.append(row)
    width = max(len(r) for r in rows)
    return [r + [None] * (width - len(r)) for r in rows]


def make_d3(path: Path, d1_path: Path, d2_path: Path | None = None) -> None:
    d1 = pd.read_csv(d1_path, dtype=str)
    d1.columns = [" ".join(c.split()) for c in d1.columns]
    d1["period"] = pd.to_datetime(d1["Year"] + "-" + d1["Month"].str[:2] + "-01")
    d1["code"] = [c if c == "0" else ".".join([c.split(".")[0].zfill(2)] + c.split(".")[1:]) for c in d1["COICOP Code"]]
    head = d1[d1["code"] == "0"].set_index("period")["Point"].astype(float)
    month_names = ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"]
    # Sheet '1': title rows, yearly rows, then a year row followed by 12 month rows
    # Columns as in iGA's file: C = April 2019 = 100, D = 2006 = 100, G / H = 1-month / 12-month % change.
    t1 = [[None] * 8, ["Table 1"] + [None] * 7, ["Consumer Price Index (All Items)"] + [None] * 7,
          [None] * 8, ["Period", None, "Consumer Price Index (CPI)", None, None, None, "Percentage Change", None],
          [None, None, "April 2019=100", "2006=100", None, None, "1 month", "12 months"],
          [None] * 8, [2011, "Yearly", 84.0, 111.6, None, None, None, -0.4]]
    rng = np.random.default_rng(7)
    values = {}
    for year in list(range(2011, 2017)) + [2020, 2021]:
        for m in range(1, 13):
            p = pd.Timestamp(year=year, month=m, day=1)
            values[p] = head.get(p, round(85 + rng.normal(0, 1), 1))
    # 2010 (never published in Table 1): only used to compute 2011's % changes,
    # so the pipeline's derivation can be checked against known values.
    for m in range(1, 13):
        values[pd.Timestamp(year=2010, month=m, day=1)] = round(84 + 0.1 * m, 3)
    for year in list(range(2011, 2017)) + [2020, 2021]:
        t1.append([year] + [None] * 7)
        for m, name in enumerate(month_names, start=1):
            p = pd.Timestamp(year=year, month=m, day=1)
            value = values[p]
            if year == 2020 and m <= 3:
                value -= 3.0                    # iGA's Table 1 2020 rows disagree with Dataset 1
            pct_1m = pct_12m = None
            if year == 2011:
                pct_1m = (value / values[p - pd.DateOffset(months=1)] - 1) * 100
                pct_12m = (value / values[p - pd.DateOffset(years=1)] - 1) * 100
            t1.append([None, name, value, value * 1.33, None, None, pct_1m, pct_12m])
    t1 += [[None] * 8, ["Source: IGA"] + [None] * 7]
    # Sheet '2.01': weights column plus one column per month Jan 2017 - Oct 2023
    months = pd.date_range("2017-01-01", "2023-10-01", freq="MS")
    t2 = [["Table 2.01"], ["Consumers price index"], ["Divisions and groups – index numbers"],
          ["Base: April 2019 (=100)"], [None], [None], [None],
          ["Code", "Level", "COICOP \nDivision & Group", "Expenditure \nWeights"] + list(months)]
    piv = d1.pivot(index="code", columns="period", values="Point").astype(float)
    t2.append([None, None, "All Divisions", 100] + [piv.loc["0", p] for p in months])
    for code in [c for c in D1_CODES if c != "0"]:
        w = WEIGHTS.get(code, 1.0)
        t2.append([code, code.count(".") + 2, NAMES[code], w] + [piv.loc[code, p] for p in months])
    t2 += [[None], ["Source: IGA"]]
    width = max(len(r) for r in t2)
    t2 = [r + [None] * (width - len(r)) for r in t2]        # equal-length rows
    width1 = max(len(r) for r in t1)
    t1 = [r + [None] * (width1 - len(r)) for r in t1]
    with pd.ExcelWriter(path) as xl:
        pd.DataFrame([["Consumers Price Index: September 2023"], ["List of tables"]]).to_excel(
            xl, sheet_name="Contents", header=False, index=False)
        pd.DataFrame(t1).to_excel(xl, sheet_name="1", header=False, index=False)
        pd.DataFrame(t2).to_excel(xl, sheet_name="2.01", header=False, index=False)
        if d2_path is not None:
            pd.DataFrame(_table3(d2_path)).to_excel(xl, sheet_name="3", header=False, index=False)


def make_all(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    from src.pipeline import config
    d1 = raw_dir / config.RAW_FILES["D1"]
    make_d1(d1)
    d2 = raw_dir / config.RAW_FILES["D2"]
    make_d2(d2)
    make_d3(raw_dir / config.RAW_FILES["D3"], d1, d2)
    return raw_dir
