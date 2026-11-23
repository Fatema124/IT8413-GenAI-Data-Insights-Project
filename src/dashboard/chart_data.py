"""Data behind each dashboard chart (F3), computed from the active filters (F2).

Kept separate from the Streamlit code so it can be tested and reused by the
report export (F9). Every function takes the same `Filters` object, which is
how "every analytical display responds to the active filters" is guaranteed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.pipeline import analytics as A
from src.pipeline import config


def usable_codes(cpi: pd.DataFrame, f: A.Filters) -> tuple[list[str], list[str]]:
    """Split the selected codes into those available for the population and those not.

    Nationality series exist only for the headline and the 12 divisions, so
    groups are dropped (and the user told) when a nationality is selected.
    """
    have = set(cpi.loc[cpi["population"] == f.population, "code"])
    return [c for c in f.codes if c in have], [c for c in f.codes if c not in have]


def trend(cpi: pd.DataFrame, f: A.Filters) -> pd.DataFrame:
    """Chart 1 - change over time: one line per selected category."""
    codes, _ = usable_codes(cpi, f)
    frames = []
    for code in codes:
        s = A.change_series(cpi, code, f.measure, f.population)
        s = s[(s.index >= f.start) & (s.index <= f.end)]
        frames.append(pd.DataFrame({"period": s.index, "value": s.values,
                                    "code": code, "category": f"{code} {A.name_of(cpi, code)}"}))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["period", "value", "code", "category"])
    return out


def comparison(cpi: pd.DataFrame, f: A.Filters, by_nationality: bool = False) -> pd.DataFrame:
    """Chart 2 - comparison between categories at the end of the selected range."""
    measure = f.measure
    if not by_nationality:
        codes, _ = usable_codes(cpi, f)
        t = A.compare_categories(cpi, f.end, measure, codes=codes, population=f.population)
        t["group"] = f.population
        return t[["code", "name", "value", "display", "group"]]
    d2_codes = set(cpi.loc[cpi["population"] == "Bahraini", "code"])
    rows = []
    for code in [c for c in f.codes if c in d2_codes]:
        t = A.compare_populations(cpi, code, f.end, measure)
        t["code"], t["name"] = code, A.name_of(cpi, code)
        t["group"] = t["population"]
        rows.append(t[["code", "name", "value", "display", "group"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["code", "name", "value", "display", "group"])


def basket(cpi: pd.DataFrame, weights: pd.DataFrame, f: A.Filters) -> pd.DataFrame:
    """Chart 3 - composition: weight of every division in the basket and its
    contribution to headline year-on-year change at the end month. Divisions
    in the selection are marked, so the chart highlights them."""
    comp = A.contributions(cpi, weights, f.end)
    selected = {c.split(".")[0] for c in f.codes if c != config.HEADLINE_CODE} or set(comp["code"])
    comp["selected"] = comp["code"].isin(selected)
    comp["label"] = comp["code"] + " " + comp["name"]
    comp["w_text"] = comp["weight"].map(lambda v: f"{v:.1f}%")
    comp["c_text"] = comp["contribution_pts"].map(lambda v: "" if pd.isna(v) else f"{v:+.2f}")
    return comp


def heatmap(cpi: pd.DataFrame, f: A.Filters) -> pd.DataFrame:
    """Chart 4 - distribution of the measure across categories and months."""
    t = trend(cpi, f)
    return t.dropna(subset=["value"])


def data_coverage(cpi: pd.DataFrame, f: A.Filters) -> dict:
    """How many values the current selection holds, and how many are missing."""
    sel = A.apply_filters(cpi, f)
    return {"rows": int(len(sel)), "missing": int(sel["index"].isna().sum()),
            "months": int(sel["period"].nunique()), "categories": int(sel["code"].nunique())}


def selection_summary(cpi: pd.DataFrame, f: A.Filters) -> pd.DataFrame:
    """Summary figures for EVERY category in the current selection (F3)."""
    codes, _ = usable_codes(cpi, f)
    rows = []
    for code in codes:
        s = A.summary_figures(cpi, f, code)
        rows.append({
            "code": code, "name": s["name"],
            "index": s["index"].value if s["index"] else np.nan,
            "mom": s["mom"].value if s["mom"] else np.nan,
            "yoy": s["yoy"].value if s["yoy"] else np.nan,
            "base": s["base"].value if s["base"] else np.nan,
            "range_start": s["range_start"] or "",
            "over_range": s["over_range_pct"] if s["over_range_pct"] is not None else np.nan,
        })
    return pd.DataFrame(rows, columns=["code", "name", "index", "mom", "yoy", "base", "range_start", "over_range"])


def flagged_in_selection(discrepancies: pd.DataFrame | None, f: A.Filters) -> pd.DataFrame:
    """Values in the current selection where Dataset 2 differs from iGA's Table 3."""
    if discrepancies is None or discrepancies.empty:
        return pd.DataFrame(columns=["code", "name", "period", "population", "dataset2", "iga_table3", "difference"])
    d = discrepancies
    return d[(d["population"] == f.population) & d["code"].isin(f.codes)
             & (d["period"] >= f.start) & (d["period"] <= f.end)]
