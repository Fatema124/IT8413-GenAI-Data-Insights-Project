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
    national_only = [c for c in f.codes if c not in d2_codes]   # detailed items: all households only
    if national_only:
        t = A.compare_categories(cpi, f.end, measure, codes=national_only, population=config.NATIONAL)
        t["group"] = config.NATIONAL
        rows.append(t[["code", "name", "value", "display", "group"]])
    rows = [r for r in rows if len(r)]
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
    comp["c_text"] = comp["contribution_pts"].map(
        lambda v: "" if pd.isna(v) else ("0.00" if abs(v) < 0.005 else f"{v:+.2f}"))   # no "-0.00"
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


# --------------------------------------------------------------------------
# Data caution: Dataset 2 values that differ from iGA's own Table 3
# --------------------------------------------------------------------------
# A displayed figure can USE a stored value without showing it: a month-on-month
# change reads the month before, a year-on-year change the same month a year
# earlier. So a 2023 year-on-year figure for non-Bahraini households is
# computed from a 2022 value, and must carry the caution too.
LOOKBACK = {"index": (0,), "base": (0,), "mom": (0, 1), "yoy": (0, 12)}
NATIONALITY_POPULATIONS = [p for p in config.POPULATIONS if p != config.NATIONAL]
_FLAG_COLUMNS = ["code", "name", "period", "population", "dataset2", "iga_table3", "difference", "used_in"]


def _m(period) -> pd.Timestamp:
    return pd.Timestamp(period).to_period("M").to_timestamp()


def months_used(f: A.Filters, measure: str | None = None) -> set[pd.Timestamp]:
    """Every stored month the current view reads, including comparison months.

    Charts read each month in the range plus its comparison month for the
    chosen measure; the summary tiles always show the index, month-on-month
    and year-on-year at the end month.
    """
    lags = LOOKBACK[measure or f.measure]
    window = pd.date_range(_m(f.start), _m(f.end), freq="MS")
    used = {p - pd.DateOffset(months=k) for p in window for k in lags}
    end = _m(f.end)
    used |= {end - pd.DateOffset(months=k) for k in (0, 1, 12)}
    return used


def _empty_flags() -> pd.DataFrame:
    return pd.DataFrame(columns=_FLAG_COLUMNS)


def flagged_values(discrepancies: pd.DataFrame | None, f: A.Filters, by_nationality: bool = False) -> pd.DataFrame:
    """Dataset 2 values that a display in the current view uses and that differ from iGA's Table 3."""
    if discrepancies is None or discrepancies.empty:
        return _empty_flags()
    d = discrepancies
    parts = []
    if f.population in NATIONALITY_POPULATIONS:
        hit = d[(d["population"] == f.population) & d["code"].isin(f.codes) & d["period"].isin(months_used(f))]
        parts.append(hit.assign(used_in="charts and summary figures"))
    if by_nationality:
        end = _m(f.end)
        comp = {end - pd.DateOffset(months=k) for k in LOOKBACK[f.measure]}
        hit = d[d["population"].isin(NATIONALITY_POPULATIONS) & d["code"].isin(f.codes) & d["period"].isin(comp)]
        parts.append(hit.assign(used_in="household comparison chart"))
    parts = [x for x in parts if len(x)]
    if not parts:
        return _empty_flags()
    return _combine(parts)


def priority_flagged(discrepancies: pd.DataFrame | None, f: A.Filters) -> pd.DataFrame:
    """Dataset 2 values behind the Monitoring priorities table.

    The nationality-gap criterion compares Bahraini and non-Bahraini
    year-on-year changes at the end month for all 12 divisions (ranks are
    across all 12), so it reads both households at the end month and 12
    months earlier, whatever households are selected. With a nationality
    selected, the MoM / YoY / since-base columns read that household too.
    """
    if discrepancies is None or discrepancies.empty:
        return _empty_flags()
    d = discrepancies
    end = _m(f.end)
    divisions = d["code"].str.fullmatch(r"\d{2}")
    gap = d[divisions & d["population"].isin(NATIONALITY_POPULATIONS)
            & d["period"].isin({end, end - pd.DateOffset(months=12)})]
    parts = [gap.assign(used_in="nationality-gap criterion")]
    if f.population in NATIONALITY_POPULATIONS:
        own = d[divisions & (d["population"] == f.population)
                & d["period"].isin({end - pd.DateOffset(months=k) for k in (0, 1, 12)})]
        parts.append(own.assign(used_in="MoM / YoY columns"))
    parts = [x for x in parts if len(x)]
    if not parts:
        return _empty_flags()
    return _combine(parts)


def flagged_codes_at(discrepancies: pd.DataFrame | None, population: str, months) -> set[str]:
    """Codes whose stored value for this household differs from iGA's Table 3 in any of these months."""
    if discrepancies is None or discrepancies.empty or population not in NATIONALITY_POPULATIONS:
        return set()
    wanted = {_m(p) for p in months if p is not None and p != ""}
    d = discrepancies
    return set(d.loc[(d["population"] == population) & d["period"].isin(wanted), "code"])


def end_month_flagged_codes(discrepancies: pd.DataFrame | None, f: A.Filters, measure: str) -> set[str]:
    """Codes whose figure at the end month (for this measure) reads a flagged value.

    A year-on-year figure for August 2026 reads August 2026 and August 2025 only, so
    flagged 2022 values elsewhere in the period do not make it doubtful.
    """
    end = _m(f.end)
    return flagged_codes_at(discrepancies, f.population, {end - pd.DateOffset(months=k) for k in LOOKBACK[measure]})


def summary_flagged_codes(discrepancies: pd.DataFrame | None, f: A.Filters, summary: pd.DataFrame) -> set[str]:
    """Rows of the summary table with a figure that reads a flagged value.

    The table shows the index, month-on-month and year-on-year at the end month, and
    the change from each row's first month with data (range_start) to the end month.
    """
    end = _m(f.end)
    common = {end - pd.DateOffset(months=k) for k in (0, 1, 12)}
    out = set()
    for code, start in zip(summary["code"], summary["range_start"], strict=True):
        months = common | ({_m(start)} if start else set())
        if code in flagged_codes_at(discrepancies, f.population, months):
            out.add(code)
    return out


def annual_flagged_years(discrepancies: pd.DataFrame | None, population: str) -> dict[str, set[int]]:
    """For each code, the calendar years whose annual average uses a flagged value (any of its 12 months)."""
    if discrepancies is None or discrepancies.empty or population not in NATIONALITY_POPULATIONS:
        return {}
    d = discrepancies[discrepancies["population"] == population]
    out: dict[str, set[int]] = {}
    for code, period in zip(d["code"], d["period"], strict=True):
        out.setdefault(code, set()).add(pd.Timestamp(period).year)
    return out


def _combine(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per flagged value, listing every display that uses it."""
    out = pd.concat(parts, ignore_index=True)
    out = out.groupby(["code", "period", "population"], as_index=False).agg(
        {**{c: "first" for c in _FLAG_COLUMNS if c not in ("code", "period", "population", "used_in")},
         "used_in": lambda s: ", ".join(sorted(set(s)))})
    return out[_FLAG_COLUMNS].sort_values(["code", "population", "period"]).reset_index(drop=True)


LAG_MONTHS = {"index": 0, "base": 0, "mom": 1, "yoy": 12}


def annual_table_notes(t: pd.DataFrame, discrepancies: pd.DataFrame | None, population: str) -> list[str]:
    """One note per row of annual_table: which shown averages (and the change) use flagged values."""
    if t.empty:
        return []
    flagged = annual_flagged_years(discrepancies, population)
    years = [int(y) for y in t.attrs["years"]]
    last = years[-1]
    notes = []
    for code in t["code"]:
        hit = flagged.get(code, set())
        shown = [y for y in years if y in hit]
        change_hit = last in hit or (last - 1) in hit
        if not shown and not change_hit:
            notes.append("")
            continue
        parts = [f"{y} average" for y in shown]
        if change_hit:
            parts.append(f"{last} vs {last - 1}")
        notes.append(f"⚠ uses values that differ from iGA's table: {', '.join(parts)}")
    return notes


def annual_table(cpi: pd.DataFrame, f: A.Filters, max_years: int = 6) -> pd.DataFrame:
    """Annual averages of the selected categories for the complete calendar years in the period.

    Uses A.annual_average (all 12 months or nothing), the same function the model tools use, so the
    dashboard and the answers agree. The last column compares the latest complete year with the year
    before (that year may lie just before the period). attrs: years shown, years left out as incomplete.
    """
    codes, _ = usable_codes(cpi, f)
    in_period = list(range(pd.Timestamp(f.start).year, pd.Timestamp(f.end).year + 1))
    avgs: dict[str, dict[int, float]] = {}
    for code in codes:
        avgs[code] = {}
        for year in [in_period[0] - 1] + in_period:
            try:
                avgs[code][year] = A.annual_average(cpi, code, year, f.population)["annual_average"]
            except A.DataUnavailable:
                pass
    complete = sorted({y for a in avgs.values() for y in a if y in in_period})
    left_out = [y for y in in_period if y not in complete]
    years = complete[-max_years:]
    out = pd.DataFrame()
    if years:
        last = years[-1]
        change_col = f"{last} vs {last - 1} (%)"
        rows = []
        for code in codes:
            a = avgs[code]
            row = {"code": code, "name": A.name_of(cpi, code)}
            row.update({str(y): a.get(y) for y in years})
            row[change_col] = (round((a[last] / a[last - 1] - 1) * 100, 4)
                               if last in a and (last - 1) in a else None)
            rows.append(row)
        out = pd.DataFrame(rows)
        out.attrs["change_col"] = change_col
    out.attrs["years"], out.attrs["left_out"] = years, left_out
    return out


def coverage(cpi: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """What each dataset covers, computed from the prepared data (not typed in), for the Data tab."""
    def months(rows):
        return f"{rows['period'].min():%b %Y} – {rows['period'].max():%b %Y}"

    def cats(rows):
        n = rows.groupby("level")["code"].nunique()
        parts = ["overall index"] if n.get(0) else []
        if n.get(1):
            parts.append(f"{n[1]} main groups")
        if n.get(2, 0) + n.get(3, 0):
            parts.append(f"{n.get(2, 0) + n.get(3, 0)} detailed items")
        return ", ".join(parts)

    out = []
    d1 = cpi[cpi["source"] == "D1"]
    out.append({"Dataset": "1", "Households": "All households", "Categories": cats(d1), "Months": months(d1),
                "Rows": len(d1), "Missing values (shown as gaps)": int(d1["index"].isna().sum())})
    d2 = cpi[cpi["source"] == "D2"]
    out.append({"Dataset": "2", "Households": "Bahraini; non-Bahraini", "Categories": cats(d2) + " (each)",
                "Months": months(d2), "Rows": len(d2), "Missing values (shown as gaps)": int(d2["index"].isna().sum())})
    d3 = cpi[cpi["source"].isin(["D3", "D3-derived"])]
    derived = cpi[cpi["source"] == "D3-derived"]
    out.append({"Dataset": "3 · Table 1", "Households": "All households", "Categories": "overall index",
                "Months": months(d3) + (f" ({derived['period'].min():%Y} derived)" if len(derived) else ""),
                "Rows": len(d3), "Missing values (shown as gaps)": int(d3["index"].isna().sum())})
    out.append({"Dataset": "3 · Table 2.01", "Households": "All households (one national basket)",
                "Categories": f"spending weights for {len(weights)} categories", "Months": "fixed",
                "Rows": len(weights), "Missing values (shown as gaps)": int(weights["weight"].isna().sum())})
    return pd.DataFrame(out)


def first_value_month(cpi: pd.DataFrame, population: str, codes: list[str], measure: str) -> pd.Timestamp | None:
    """First month in which any of these categories has a value for the measure (None: never)."""
    have = cpi[(cpi["population"] == population) & cpi["code"].isin(codes) & cpi["index"].notna()]
    if have.empty:
        return None
    return pd.Timestamp(have["period"].min()) + pd.DateOffset(months=LAG_MONTHS[measure])


def contributions_from(cpi: pd.DataFrame) -> pd.Timestamp:
    """First month with contributions: the spending groups' first yearly change (January 2018)."""
    groups = cpi[(cpi["population"] == config.NATIONAL) & (cpi["level"] == 1) & cpi["index"].notna()]
    return pd.Timestamp(groups["period"].min()) + pd.DateOffset(months=12)


def month_ticks(start, end) -> list[pd.Timestamp]:
    """Months to label on a time axis, never outside start..end (the data ends in August 2026).

    Long ranges get Januaries (every second year past nine years); shorter ranges every 1, 3 or 6 months.
    """
    start, end = pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1)
    n = (end.year - start.year) * 12 + end.month - start.month + 1
    if n > 48:
        years = [y for y in range(start.year, end.year + 1) if pd.Timestamp(year=y, month=1, day=1) >= start]
        if len(years) > 9:
            years = [y for y in years if y % 2 == 0]
        return [pd.Timestamp(year=y, month=1, day=1) for y in years]
    step = 1 if n <= 8 else 3 if n <= 18 else 6
    return [p for p in pd.date_range(start, end, freq="MS") if (p.month - 1) % step == 0]


def spread_labels(values, axis_values, plot_px: float, gap_px: float = 15) -> list[float]:
    """y positions for end-of-line labels, pushed apart so no two are closer than gap_px.

    Positions keep the order of the values; axis_values (all values on the axis) give the pixel scale.
    """
    v = pd.Series(values, dtype=float).reset_index(drop=True)
    axis = pd.Series(axis_values, dtype=float).dropna()
    gap = ((axis.max() - axis.min()) or 1.0) * gap_px / plot_px
    out = v.copy()
    prev = None
    for i in v.sort_values(ascending=False).index:      # top label first, each next one at least a gap lower
        if prev is not None and out[prev] - out[i] < gap:
            out[i] = out[prev] - gap
        prev = i
    return out.tolist()


def month_span(periods) -> str:
    """'Jan 2022' or 'Jan 2022 – Jun 2022'."""
    lo, hi = pd.Timestamp(min(periods)), pd.Timestamp(max(periods))
    return f"{lo:%b %Y}" if lo == hi else f"{lo:%b %Y} – {hi:%b %Y}"


def caution_text(flags: pd.DataFrame) -> str:
    """One plain sentence describing flagged values (empty string if none)."""
    if flags is None or flags.empty:
        return ""
    n = len(flags)
    pops = " and ".join(sorted(flags["population"].unique()))
    cats = ", ".join(sorted(flags["code"].unique()))
    return (f"{n} Dataset 2 value{'s' if n > 1 else ''} behind this view ({pops}, {month_span(flags['period'])}; "
            f"categor{'ies' if flags['code'].nunique() > 1 else 'y'} {cats}) "
            f"{'differ' if n > 1 else 'differs'} from iGA's own Table 3 by up to "
            f"{flags['difference'].abs().max():.1f} points, so figures computed from "
            f"{'them' if n > 1 else 'it'} may be wrong. Changes that compare with these months, such as "
            "year-on-year figures a year later, are affected too.")


def flagged_in_selection(discrepancies: pd.DataFrame | None, f: A.Filters) -> pd.DataFrame:
    """Kept for compatibility: the caution for the current view (see flagged_values)."""
    return flagged_values(discrepancies, f)


# --------------------------------------------------------------------------
# Automatic category choice (filter: "fastest rising", "fastest falling", ...)
# --------------------------------------------------------------------------
AUTO_MODES = ("Fastest rising", "Fastest falling", "Largest share of spending")


def auto_pick(cpi: pd.DataFrame, weights: pd.DataFrame | None, f: A.Filters, pool: list[str],
              mode: str, n: int) -> list[str]:
    """Pick the n categories from `pool` that best match `mode` at the end month.

    Rising / falling use the selected measure (the index level becomes the
    year-on-year change, because a level is not a change); spending share uses
    iGA's weights. The headline is never picked: it is the reference.
    """
    pool = [c for c in pool if c != config.HEADLINE_CODE]
    if not pool:
        return []
    if mode == "Largest share of spending":
        if weights is None:
            return []
        w = weights[weights["code"].isin(pool)].sort_values("weight", ascending=False)
        return w["code"].head(n).tolist()
    measure = "yoy" if f.measure == "index" else f.measure
    t = A.compare_categories(cpi, f.end, measure, codes=pool, population=f.population).dropna(subset=["value"])
    t = t.sort_values("value", ascending=(mode == "Fastest falling"))
    return t["code"].head(n).tolist()
