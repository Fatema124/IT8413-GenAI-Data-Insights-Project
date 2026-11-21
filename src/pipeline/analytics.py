"""Step 3: the calculations every part of the app uses.

One set of functions serves three consumers, so a figure is computed the
same way wherever it appears:
  * the dashboard (F2, F3),
  * the model's tools for questions over the data (F4/F6, Eman's part) -
    each function returns a plain dict that can be sent back to the model,
  * the report export (F9).

The brief warns that month-on-month, year-on-year and since-base readings
"can differ for the same category and date"; every change function
therefore says which reading it is and which two stored values it used.

Missing data is never guessed: if a needed value is absent the function
raises DataUnavailable, which the app turns into a refusal (F7).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import config

MEASURES = {
    "mom": "month-on-month change (%)",
    "yoy": "year-on-year change (%)",
    "base": "change since April 2019 (%)",
    "index": "index level (April 2019 = 100)",
}
_LAG = {"mom": 1, "yoy": 12}


class DataUnavailable(LookupError):
    """The sources do not contain the value needed (never filled or guessed)."""


@dataclass
class Figure:
    """A computed number plus everything needed to verify it."""
    measure: str
    value: float
    code: str
    name: str
    population: str
    period: str
    compared_with: str | None
    current_index: float | None
    previous_index: float | None
    unit: str
    sources: str
    note: str = config.OWN_ANALYSIS_NOTE

    @property
    def display(self) -> str:
        d = config.DISPLAY_DECIMALS
        return f"{self.value:.{d}f}" if self.measure == "index" else f"{self.value:+.{d}f}%"

    def to_dict(self) -> dict:
        out = asdict(self)
        out["value"] = round(self.value, 4)
        out["display"] = self.display
        return out


# --------------------------------------------------------------------------
# Basic access
# --------------------------------------------------------------------------
def _month(period) -> pd.Timestamp:
    return pd.Timestamp(period).to_period("M").to_timestamp()


def series(cpi: pd.DataFrame, code: str, population: str = config.NATIONAL) -> pd.Series:
    s = cpi[(cpi["code"] == code) & (cpi["population"] == population)]
    if s.empty:
        raise DataUnavailable(f"No {population} series for code {code}.")
    return s.set_index("period")["index"].sort_index()


def name_of(cpi: pd.DataFrame, code: str) -> str:
    hit = cpi.loc[cpi["code"] == code, "name"]
    return hit.iloc[0] if len(hit) else code


def _source_of(cpi: pd.DataFrame, code: str, population: str, periods) -> str:
    rows = cpi[(cpi["code"] == code) & (cpi["population"] == population) & cpi["period"].isin(periods)]
    names = {"D1": "Dataset 1", "D2": "Dataset 2", "D3": "Dataset 3"}
    return ", ".join(sorted({names.get(s, s) for s in rows["source"]}))


def index_value(cpi: pd.DataFrame, code: str, period, population: str = config.NATIONAL) -> float:
    s = series(cpi, code, population)
    p = _month(period)
    if p not in s.index or pd.isna(s.loc[p]):
        first, last = s.dropna().index.min(), s.dropna().index.max()
        raise DataUnavailable(
            f"{population} index for {code} is not available for {p:%B %Y} "
            f"(available {first:%b %Y} - {last:%b %Y}).")
    return float(s.loc[p])


# --------------------------------------------------------------------------
# Changes
# --------------------------------------------------------------------------
def change(cpi: pd.DataFrame, code: str, period, measure: str = "yoy",
           population: str = config.NATIONAL) -> Figure:
    """Index level or % change for one category, month and population."""
    if measure not in MEASURES:
        raise ValueError(f"measure must be one of {list(MEASURES)}")
    p = _month(period)
    cur = index_value(cpi, code, p, population)
    if measure == "index":
        prev_p, prev, value = None, None, cur
    elif measure == "base":
        prev_p, prev = _month(config.BASE_PERIOD), config.BASE_VALUE
        value = (cur / prev - 1) * 100
    else:
        prev_p = p - pd.DateOffset(months=_LAG[measure])
        prev = index_value(cpi, code, prev_p, population)
        value = (cur / prev - 1) * 100
    periods = [p] + ([prev_p] if prev_p is not None and measure != "base" else [])
    return Figure(measure=measure, value=float(value), code=code, name=name_of(cpi, code),
                  population=population, period=f"{p:%Y-%m}",
                  compared_with=None if prev_p is None else f"{prev_p:%Y-%m}",
                  current_index=cur, previous_index=prev,
                  unit="index points" if measure == "index" else "%",
                  sources=_source_of(cpi, code, population, periods))


def annual_average(cpi: pd.DataFrame, code: str, year: int, population: str = config.NATIONAL) -> dict:
    """Mean of the 12 monthly values; refuses if any month is missing."""
    s = series(cpi, code, population)
    months = pd.date_range(f"{year}-01-01", f"{year}-12-01", freq="MS")
    vals = s.reindex(months)
    if vals.isna().any():
        missing = ", ".join(f"{m:%b}" for m in vals[vals.isna()].index)
        raise DataUnavailable(f"Annual average for {year} needs all 12 months; missing: {missing}.")
    return {"code": code, "name": name_of(cpi, code), "population": population, "year": year,
            "annual_average": round(float(vals.mean()), 4), "months_used": 12,
            "sources": _source_of(cpi, code, population, months), "note": config.OWN_ANALYSIS_NOTE}


def compare_annual_averages(cpi: pd.DataFrame, code: str, year_a: int, year_b: int,
                            population: str = config.NATIONAL) -> dict:
    a = annual_average(cpi, code, year_a, population)
    b = annual_average(cpi, code, year_b, population)
    pct = (b["annual_average"] / a["annual_average"] - 1) * 100
    return {"code": code, "name": a["name"], "population": population,
            f"average_{year_a}": a["annual_average"], f"average_{year_b}": b["annual_average"],
            "change_pct": round(pct, 4), "sources": a["sources"], "note": config.OWN_ANALYSIS_NOTE}


def compare_populations(cpi: pd.DataFrame, code: str, period, measure: str = "yoy") -> pd.DataFrame:
    """National vs Bahraini vs non-Bahraini for one category and month."""
    rows = []
    for pop in config.POPULATIONS:
        try:
            rows.append(change(cpi, code, period, measure, pop).to_dict())
        except DataUnavailable as exc:
            rows.append({"population": pop, "code": code, "measure": measure, "value": np.nan,
                         "display": "not available", "note": str(exc)})
    return pd.DataFrame(rows)


def compare_categories(cpi: pd.DataFrame, period, measure: str = "yoy", codes=None,
                       level: int | None = 1, population: str = config.NATIONAL) -> pd.DataFrame:
    """One row per category, sorted by the measure (largest first)."""
    pool = cpi[cpi["population"] == population]
    if codes is None:
        codes = sorted(pool.loc[pool["level"] == level, "code"].unique())
    rows = []
    for code in codes:
        try:
            rows.append(change(cpi, code, period, measure, population).to_dict())
        except DataUnavailable as exc:
            rows.append({"code": code, "name": name_of(cpi, code), "value": np.nan,
                         "display": "not available", "note": str(exc)})
    if not rows:   # nothing selected / nothing available: an empty table, not an error
        return pd.DataFrame(columns=["code", "name", "value", "display", "note"])
    out = pd.DataFrame(rows)
    return out.sort_values("value", ascending=False, na_position="last").reset_index(drop=True)


def change_series(cpi: pd.DataFrame, code: str, measure: str = "yoy",
                  population: str = config.NATIONAL) -> pd.Series:
    """The whole monthly series of a measure (for charts)."""
    s = series(cpi, code, population).asfreq("MS")
    if measure == "index":
        return s
    if measure == "base":
        return (s / config.BASE_VALUE - 1) * 100
    return (s / s.shift(_LAG[measure]) - 1) * 100


# --------------------------------------------------------------------------
# Weights and contributions
# --------------------------------------------------------------------------
def weight_of(weights: pd.DataFrame | None, code: str) -> float:
    if weights is None:
        raise DataUnavailable("Expenditure weights (Dataset 3) are not loaded.")
    hit = weights.loc[weights["code"] == code, "weight"]
    if hit.empty:
        raise DataUnavailable(f"iGA's Table 2.01 gives no weight for code {code}.")
    return float(hit.iloc[0])


def contributions(cpi: pd.DataFrame, weights: pd.DataFrame, period) -> pd.DataFrame:
    """Approximate contribution of each division to headline year-on-year change.

    contribution_i = w_i x (I_i,t - I_i,t-12) / headline_t-12, in percentage
    points. This is exact for a fixed-weight index whose weights and prices
    share the same base; iGA's index is close to that, so the sum is
    compared with the published headline change and the gap is reported.
    """
    p = _month(period)
    prev = p - pd.DateOffset(months=12)
    head_prev = index_value(cpi, config.HEADLINE_CODE, prev)
    head_yoy = change(cpi, config.HEADLINE_CODE, p, "yoy").value
    rows = []
    for w in weights[weights["level"] == 1].itertuples():
        try:
            cur, old = index_value(cpi, w.code, p), index_value(cpi, w.code, prev)
            pts = w.weight / 100 * (cur - old) / head_prev * 100
        except DataUnavailable:
            pts = np.nan
        rows.append({"code": w.code, "name": w.name, "weight": w.weight, "contribution_pts": pts})
    out = pd.DataFrame(rows).sort_values("contribution_pts", ascending=False).reset_index(drop=True)
    out.attrs["headline_yoy"] = head_yoy
    out.attrs["sum_of_contributions"] = float(out["contribution_pts"].sum())
    out.attrs["period"] = f"{p:%Y-%m}"
    return out


# --------------------------------------------------------------------------
# Monitoring priorities (the decision in proposal Section 1)
# --------------------------------------------------------------------------
def priority_table(cpi: pd.DataFrame, weights: pd.DataFrame | None, period,
                   rules: dict | None = None, codes=None,
                   population: str = config.NATIONAL) -> pd.DataFrame:
    """Flag divisions on the four prioritisation criteria in the proposal.

    Ranks ("top 3") are taken across all 12 divisions, then the table is cut
    to the divisions in the current selection (`codes`), so it responds to the
    filters without changing what "top 3" means. MoM / YoY / since-base use
    the selected households. The table shows the evidence; analysts decide.
    """
    r = {**config.PRIORITY_RULES, **(rules or {})}
    p = _month(period)
    divs = sorted(cpi.loc[(cpi["level"] == 1) & (cpi["population"] == config.NATIONAL), "code"].unique())
    rows = []
    for code in divs:
        row = {"code": code, "name": name_of(cpi, code)}
        for m in ("mom", "yoy", "base"):
            try:
                row[m] = change(cpi, code, p, m, population).value
            except DataUnavailable:
                row[m] = np.nan
        try:
            row["weight"] = weight_of(weights, code)
        except DataUnavailable:
            row["weight"] = np.nan
        try:
            row["gap_bh_minus_nonbh"] = (change(cpi, code, p, "yoy", "Bahraini").value
                                         - change(cpi, code, p, "yoy", "Non-Bahraini").value)
        except DataUnavailable:
            row["gap_bh_minus_nonbh"] = np.nan
        rows.append(row)
    t = pd.DataFrame(rows)
    t["flag_rising_fastest"] = t["yoy"].rank(ascending=False, method="min") <= r["rising_fastest_top_n"]
    t["flag_far_from_base"] = t["base"].abs().rank(ascending=False, method="min") <= r["furthest_from_base_top_n"]
    t["flag_large_weight"] = t["weight"] >= r["large_weight_min"]
    t["flag_nationality_gap"] = t["gap_bh_minus_nonbh"].abs() >= r["nationality_gap_min"]
    flags = [c for c in t.columns if c.startswith("flag_")]
    t["criteria_met"] = t[flags].sum(axis=1).astype(int)
    selected = {c.split(".")[0] for c in (codes or []) if c != config.HEADLINE_CODE}
    if selected:                       # headline only / nothing -> keep all 12 divisions
        t = t[t["code"].isin(selected)]
    t.attrs["period"] = f"{p:%Y-%m}"
    t.attrs["rules"] = r
    t.attrs["population"] = population
    return t.sort_values(["criteria_met", "yoy"], ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Filters (F2) and summary figures (F3)
# --------------------------------------------------------------------------
@dataclass
class Filters:
    start: pd.Timestamp
    end: pd.Timestamp
    codes: list[str]
    population: str = config.NATIONAL
    measure: str = "yoy"


def apply_filters(cpi: pd.DataFrame, f: Filters) -> pd.DataFrame:
    """The ONE place filters are applied, so every display uses the same selection."""
    return cpi[(cpi["period"] >= _month(f.start)) & (cpi["period"] <= _month(f.end))
               & cpi["code"].isin(f.codes) & (cpi["population"] == f.population)]


def summary_figures(cpi: pd.DataFrame, f: Filters, code: str) -> dict:
    """KPI tiles for one category at the end of the selected range."""
    out = {"code": code, "name": name_of(cpi, code), "period": f"{_month(f.end):%Y-%m}",
           "population": f.population}
    for m in ("index", "mom", "yoy", "base"):
        try:
            out[m] = change(cpi, code, f.end, m, f.population)
        except DataUnavailable:
            out[m] = None
    # Change over the selected period, measured from the first month in the
    # period that has a value (e.g. May 2019 for nationality series). The
    # month used is returned with it, so the label always says what it is.
    out["over_range_pct"], out["range_start"] = None, None
    try:
        s = series(cpi, code, f.population)
        window = s[(s.index >= _month(f.start)) & (s.index <= _month(f.end))].dropna()
        if len(window) and out["index"] and window.index[0] < _month(f.end):
            out["over_range_pct"] = (out["index"].value / float(window.iloc[0]) - 1) * 100
            out["range_start"] = f"{window.index[0]:%Y-%m}"
    except DataUnavailable:
        pass
    return out
