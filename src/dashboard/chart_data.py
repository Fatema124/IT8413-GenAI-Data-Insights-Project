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


def composition(cpi: pd.DataFrame, weights: pd.DataFrame | None, f: A.Filters) -> pd.DataFrame:
    """Chart 3 - composition: weight of each selected division in the basket,
    plus its contribution to headline year-on-year change at the end month."""
    if weights is None:
        return pd.DataFrame(columns=["code", "name", "weight", "contribution_pts", "selected"])
    contrib = A.contributions(cpi, weights, f.end)
    selected_divs = {c.split(".")[0] for c in f.codes if c != config.HEADLINE_CODE}
    if not selected_divs:                      # headline only -> show all divisions
        selected_divs = set(contrib["code"])
    contrib["selected"] = contrib["code"].isin(selected_divs)
    contrib["label"] = contrib["code"] + " " + contrib["name"]
    rest = contrib.loc[~contrib["selected"], "weight"].sum()
    shares = contrib[contrib["selected"]][["code", "label", "weight", "contribution_pts"]].copy()
    if rest > 0:
        shares = pd.concat([shares, pd.DataFrame([{"code": "rest", "label": "Rest of basket",
                                                   "weight": rest, "contribution_pts": np.nan}])],
                           ignore_index=True)
    shares.attrs.update(contrib.attrs)
    return shares


def heatmap(cpi: pd.DataFrame, f: A.Filters) -> pd.DataFrame:
    """Chart 4 - distribution of the measure across categories and months."""
    t = trend(cpi, f)
    return t.dropna(subset=["value"])


def data_coverage(cpi: pd.DataFrame, f: A.Filters) -> dict:
    """How many values the current selection holds, and how many are missing."""
    sel = A.apply_filters(cpi, f)
    return {"rows": int(len(sel)), "missing": int(sel["index"].isna().sum()),
            "months": int(sel["period"].nunique()), "categories": int(sel["code"].nunique())}
