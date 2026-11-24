"""Streamlit analytics dashboard (F2 filtering + F3 visualisations).

Usage inside the group's main app:

    from src.dashboard.page import render_dashboard
    filters = render_dashboard()        # returns the active Filters
    # pass `filters` to the report export (F9) so the report = current selection

Run on its own:  streamlit run src/dashboard/page.py   (or double-click run_app.bat)

Every chart and table below receives the same `Filters` object from the
sidebar, which is how "every analytical display responds to the active
filters" (F2) is guaranteed.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):                     # allow `streamlit run src/dashboard/page.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt
import pandas as pd
import streamlit as st

from src.dashboard import chart_data as cd
from src.pipeline import analytics as A
from src.pipeline import config
from src.pipeline.run import PreparedData, build, load_prepared, write_outputs

MEASURE_LABELS = {"yoy": "Year-on-year %", "mom": "Month-on-month %",
                  "base": "Change since Apr 2019 %", "index": "Index (Apr 2019 = 100)"}

# --------------------------------------------------------------------------
# Visual style (validated categorical palette; colour follows the category)
# --------------------------------------------------------------------------
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
HEADLINE_COLOUR = INK_2                  # the headline is the reference line: neutral ink
POPULATION_COLOURS = {"National": "#2a78d6", "Bahraini": "#eb6834", "Non-Bahraini": "#1baf7a"}
UP, DOWN, NEUTRAL = "#e34948", "#2a78d6", "#f0efec"   # diverging pair, grey midpoint
MAX_CATEGORIES = 8                       # 8 palette colours (+ neutral headline): never cycled

CSS = """
<style>
  html, body, [class*="css"] { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .block-container { padding-top: 3.5rem; padding-bottom: 3rem; }
  .pl-title { font-size: 1.9rem; font-weight: 650; color: #0b0b0b; margin: 0; letter-spacing: -0.01em; }
  .pl-sub { color: #52514e; font-size: 0.95rem; margin: 0.15rem 0 1.1rem 0; }
  .pl-focus { color: #52514e; font-size: 0.9rem; margin: 0.4rem 0 0.4rem 0; }
  div[data-testid="stMetric"] { background: #ffffff; border: 1px solid rgba(11,11,11,0.10);
      border-radius: 10px; padding: 0.75rem 1rem; }
  div[data-testid="stMetricLabel"] p { color: #52514e; font-size: 0.82rem; }
  section[data-testid="stSidebar"] h2 { font-size: 1.05rem; }
</style>
"""


def _show(fn, obj, **kw):
    """Full-width display that works on both older and newer Streamlit versions."""
    try:
        return fn(obj, width="stretch", **kw)
    except TypeError:
        return fn(obj, use_container_width=True, **kw)


def _chart(chart, height: int):
    """Apply the shared chart style and display it full width."""
    styled = (chart.properties(height=height)
              .configure(font=FONT, background=SURFACE)
              .configure_view(stroke=None)
              .configure_axis(labelColor=MUTED, titleColor=INK_2, gridColor=GRID, domainColor=AXIS,
                              tickColor=AXIS, labelFontSize=11, titleFontSize=12, titleFontWeight="normal")
              .configure_legend(labelColor=INK_2, titleColor=INK_2, labelFontSize=12, orient="bottom",
                                symbolStrokeWidth=2, labelLimit=400))
    _show(st.altair_chart, styled, theme=None)


def _series_scale(codes: list[str], names: dict[str, str]) -> alt.Scale:
    """Fixed colour per selected category: headline = neutral ink, others in palette order."""
    domain, colours, k = [], [], 0
    for code in codes:
        domain.append(f"{code} {names.get(code, '')}")
        if code == config.HEADLINE_CODE:
            colours.append(HEADLINE_COLOUR)
        else:
            colours.append(SERIES[k % len(SERIES)])
            k += 1
    return alt.Scale(domain=domain, range=colours)


def _padded_domain(values, left: float = 0.3, right: float = 0.18) -> list[float]:
    """x-axis range that always includes 0 and leaves room for the value labels.

    Labels sit right of positive bars and left of negative bars; without the
    extra room a negative label runs into the category names.
    """
    v = pd.Series(values, dtype=float).dropna()
    lo, hi = min(0.0, v.min() if len(v) else 0.0), max(0.0, v.max() if len(v) else 0.0)
    span = (hi - lo) or 1.0
    return [float(lo - (left * span if lo < 0 else 0.0)), float(hi + right * span)]


@st.cache_data(show_spinner="Preparing the CPI data (the first start on a new server takes about a minute)...")
def _load() -> PreparedData:
    """Use the prepared data; on a fresh server (e.g. Streamlit Cloud) build it first.

    data/processed/ is not in the repository, so a new server prepares it here:
    Dataset 3 is fetched from iGA (it may not be republished in the repository),
    then the same pipeline as `python -m src.pipeline.run` runs once.

    Only a COMPLETE build (with Dataset 3) is saved to data/processed/. If the
    download fails once, the next start tries again instead of reusing a copy
    without the weights; the Composition tab also offers a "try again" button.
    """
    try:
        data = load_prepared()
        if data.weights is not None:
            return data
    except FileNotFoundError:
        pass
    from scripts.download_sources import ensure_dataset3
    ensure_dataset3(verbose=False)
    data = build()
    if data.weights is not None:
        write_outputs(data)
    return data


# --------------------------------------------------------------------------
# F2 - filters
# --------------------------------------------------------------------------
def sidebar_filters(data: PreparedData) -> tuple[A.Filters, bool]:
    cpi, lab = data.cpi, data.labels
    st.sidebar.markdown("## Filters")
    st.sidebar.caption("Every chart and table follows these filters.")

    months = sorted(cpi["period"].unique())          # Jan 2010 (derived) / 2011 (Dataset 3) - Aug 2026
    start, end = st.sidebar.select_slider(
        "Time period", options=months, value=(months[-36], months[-1]),
        format_func=lambda p: pd.Timestamp(p).strftime("%b %Y"), key="f_period")

    population = st.sidebar.radio(
        "Households", config.POPULATIONS, key="f_pop",
        help="Nationality series (Dataset 2) start in May 2019 and cover the headline and 12 divisions.")

    # Only offer categories that exist for the chosen households: nationality
    # series (Dataset 2) cover the headline and the 12 divisions only.
    available = lab[lab["populations"].str.split(", ").apply(lambda pops: population in pops)]
    if population == config.NATIONAL:
        levels = ["Divisions", "Groups and items", "All"]
    else:
        levels = ["Divisions"]
        st.sidebar.caption("Bahraini / non-Bahraini figures cover the headline and the 12 divisions.")
    level = st.sidebar.radio("Category level", levels, horizontal=True, key=f"f_level_{population}")
    pool = available if level == "All" else available[
        available["level"].isin([0, 1] if level == "Divisions" else [2, 3])]
    options = pool["code"].tolist()
    default = [c for c in ["0", "01", "04", "07"] if c in options] or options[:3]
    names = dict(zip(lab["code"], lab["name"], strict=True))
    codes = st.sidebar.multiselect(
        "Categories", options, default=default, key=f"f_codes_{population}_{level}",
        max_selections=MAX_CATEGORIES, format_func=lambda c: f"{c}  {names.get(c, '')}",
        help=f"Up to {MAX_CATEGORIES} categories, so each keeps its own colour.")

    measure = st.sidebar.selectbox("Measure", list(MEASURE_LABELS), index=0, key="f_measure",
                                   format_func=MEASURE_LABELS.get,
                                   help="The three readings can differ for the same category and month.")
    by_nat = st.sidebar.toggle("Compare households in the comparison chart", value=False, key="f_bynat")

    f = A.Filters(pd.Timestamp(start), pd.Timestamp(end), codes or ["0"], population, measure)
    return f, by_nat


# --------------------------------------------------------------------------
# F3 - summary figures
# --------------------------------------------------------------------------
def _fmt(fig: A.Figure | None) -> str:
    return "n/a" if fig is None else fig.display


def summary_section(data: PreparedData, f: A.Filters) -> None:
    focus = f.codes[0]
    s = A.summary_figures(data.cpi, f, focus)
    st.markdown(f"<p class='pl-focus'><b>{focus} {s['name']}</b> · {f.population} households · "
                f"{pd.Timestamp(f.end):%B %Y}</p>", unsafe_allow_html=True)
    c = st.columns(5)
    c[0].metric("Index (Apr 2019 = 100)", _fmt(s["index"]))
    c[1].metric("Month-on-month", _fmt(s["mom"]))
    c[2].metric("Year-on-year", _fmt(s["yoy"]))
    c[3].metric("Since Apr 2019", _fmt(s["base"]))
    rng, since = s["over_range_pct"], s["range_start"]
    label = f"Since {pd.Timestamp(since):%b %Y}" if since else "Over the period"
    c[4].metric(label, "n/a" if rng is None else f"{rng:+.1f}%",
                help="Change from the first month in the selected period that has data.")

    summary = cd.selection_summary(data.cpi, f)
    if len(summary) > 1:
        summary["range_start"] = summary["range_start"].map(
            lambda p: pd.Timestamp(p).strftime("%b %Y") if p else "n/a")
        show = summary.rename(columns={
            "code": "Code", "name": "Category", "index": "Index", "mom": "MoM %", "yoy": "YoY %",
            "base": "Since Apr 2019 %", "range_start": "Period from", "over_range": "Change over period %"})
        st.markdown(f"**Summary figures for all {len(summary)} selected categories**")
        number_cols = ["Index", "MoM %", "YoY %", "Since Apr 2019 %", "Change over period %"]
        _show(st.dataframe, show, hide_index=True,
              column_config={c: st.column_config.NumberColumn(format="%.1f") for c in number_cols})
    cov = cd.data_coverage(data.cpi, f)
    st.caption(f"Selection: {cov['categories']} categories × {cov['months']} months = {cov['rows']} values"
               + (f" · {cov['missing']} missing, shown as gaps (never filled)" if cov["missing"] else ""))


# --------------------------------------------------------------------------
# F3 - charts
# --------------------------------------------------------------------------
def chart_trend(data: PreparedData, f: A.Filters) -> None:
    st.subheader("Change over time")
    df = cd.trend(data.cpi, f)
    if df.empty:
        st.info("No data for this selection.")
        return
    names = dict(zip(data.labels["code"], data.labels["name"], strict=True))
    codes, _ = cd.usable_codes(data.cpi, f)
    n_months = df["period"].nunique()
    if n_months > 48:     # long range: one label per year, no dots
        axis = alt.Axis(format="%Y", tickCount={"interval": "year", "step": 1}, labelAngle=0, grid=False)
    else:
        axis = alt.Axis(format="%b %Y", tickCount={"interval": "month", "step": 3}, labelAngle=-40, grid=False)
    y_title = MEASURE_LABELS[f.measure]
    point = alt.OverlayMarkDef(size=36, filled=True, stroke=SURFACE, strokeWidth=2) if n_months <= 48 else False
    line = alt.Chart(df).mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round", point=point).encode(
        x=alt.X("period:T", title=None, axis=axis),
        y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)),
        color=alt.Color("category:N", title=None, scale=_series_scale(codes, names)),
        tooltip=[alt.Tooltip("category:N", title="Category"),
                 alt.Tooltip("period:T", format="%b %Y", title="Month"),
                 alt.Tooltip("value:Q", format=".1f", title=y_title)])
    ref = 100 if f.measure == "index" else 0
    rule = alt.Chart(pd.DataFrame({"y": [ref]})).mark_rule(color=AXIS, strokeWidth=1).encode(
        y=alt.Y("y:Q", title=y_title))
    _chart(rule + line, height=340)
    st.caption("Reference line: " + ("April 2019 = 100." if f.measure == "index" else "no change (0%)."))


def chart_comparison(data: PreparedData, f: A.Filters, by_nat: bool) -> None:
    st.subheader(f"Comparison between categories · {pd.Timestamp(f.end):%b %Y}")
    df = cd.comparison(data.cpi, f, by_nat).dropna(subset=["value"])
    if df.empty:
        st.info("No comparable values for this selection.")
        return
    df["label"] = df["code"] + " " + df["name"]
    df["text"] = df["value"].map(lambda v: f"{v:.1f}" if f.measure == "index" else f"{v:+.1f}%")
    groups = [g for g in config.POPULATIONS if g in set(df["group"])] or list(df["group"].unique())
    colour = alt.Color("group:N", title=None,
                       scale=alt.Scale(domain=groups, range=[POPULATION_COLOURS.get(g, SERIES[0]) for g in groups]),
                       legend=alt.Legend() if by_nat else None)
    # An explicit order: a sort by field is dropped when bars and labels are layered.
    order = df.groupby("label")["value"].max().sort_values(ascending=False).index.tolist()
    y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=280, ticks=False, domain=False))
    base = alt.Chart(df).encode(y=y, x=alt.X("value:Q", title=MEASURE_LABELS[f.measure],
                                             scale=alt.Scale(domain=_padded_domain(df["value"]), nice=False),
                                             axis=alt.Axis(gridColor=GRID)))
    if by_nat:   # National first, then Bahraini, then Non-Bahraini, in every group
        base = base.encode(yOffset=alt.YOffset("group:N", sort=list(config.POPULATIONS)))
    bars = base.mark_bar(size=14 if by_nat else 18, cornerRadiusEnd=4).encode(
        color=colour, tooltip=[alt.Tooltip("label:N", title="Category"), alt.Tooltip("group:N", title="Households"),
                               alt.Tooltip("text:N", title=MEASURE_LABELS[f.measure])])
    pos = base.transform_filter("datum.value >= 0").mark_text(align="left", dx=5, color=INK_2, fontSize=11).encode(
        text="text:N")
    neg = base.transform_filter("datum.value < 0").mark_text(align="right", dx=-5, color=INK_2, fontSize=11).encode(
        text="text:N")
    n_rows = df["label"].nunique() * (3 if by_nat else 1)
    _chart(bars + pos + neg, height=max(160, 34 * n_rows))


def chart_composition(data: PreparedData, f: A.Filters) -> None:
    st.subheader("Composition of the basket")
    if data.weights is None:
        st.warning("Expenditure weights (Dataset 3) are not loaded. Dataset 3 may not be republished, so it is "
                   "not in the repository: save iGA's CPI tables XLSX as data/raw/CPI-Tables-_Jan2020-Oct_2023.xlsx "
                   "(or run `python -m scripts.download_sources`), then `python -m src.pipeline.run`. On the online "
                   "version this means the file could not be fetched from iGA's website.")
        if st.button("Try again to fetch Dataset 3 from iGA"):
            _load.clear()
            st.rerun()
        return
    try:
        comp = cd.basket(data.cpi, data.weights, f)
    except A.DataUnavailable as exc:
        st.info(str(exc))
        return
    st.caption("Weights are iGA's fixed national basket (Table 2.01), so they don't change with the period "
               "or households. Your selected divisions are highlighted. Contributions are for the end month "
               f"of the selected period ({pd.Timestamp(f.end):%B %Y})."
               + (f" {f.population} households are selected: iGA publishes no weights by nationality, so the "
                  "national basket is used." if f.population != config.NATIONAL else ""))
    left, right = st.columns(2)

    with left:
        st.markdown("**Share of household spending** · iGA Table 2.01")
        y = alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260, ticks=False, domain=False))
        base = alt.Chart(comp).encode(y=y, x=alt.X("weight:Q", title=f"Weight ({config.WEIGHT_UNIT})"))
        bars = base.mark_bar(size=16, cornerRadiusEnd=4).encode(
            color=alt.condition("datum.selected", alt.value(SERIES[0]), alt.value(AXIS)),
            tooltip=[alt.Tooltip("label:N", title="Division"), alt.Tooltip("weight:Q", format=".2f", title="Weight %")])
        text = base.mark_text(align="left", dx=5, color=INK_2, fontSize=11).encode(text="w_text:N")
        _chart(bars + text, height=420)

    with right:
        st.markdown(f"**Contribution to headline year-on-year change** · {pd.Timestamp(f.end):%b %Y}")
        c = comp.dropna(subset=["contribution_pts"])
        order = c.sort_values("contribution_pts", ascending=False)["label"].tolist()
        y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=260, ticks=False, domain=False))
        base = alt.Chart(c).encode(y=y, x=alt.X("contribution_pts:Q", title="Percentage points",
                                                scale=alt.Scale(domain=_padded_domain(c["contribution_pts"]),
                                                                nice=False)))
        bars = base.mark_bar(size=16, cornerRadiusEnd=4).encode(
            color=alt.condition("datum.contribution_pts >= 0", alt.value(UP), alt.value(DOWN)),
            opacity=alt.condition("datum.selected", alt.value(1.0), alt.value(0.35)),
            tooltip=[alt.Tooltip("label:N", title="Division"),
                     alt.Tooltip("contribution_pts:Q", format="+.2f", title="Points")])
        pos = base.transform_filter("datum.contribution_pts >= 0").mark_text(
            align="left", dx=5, color=INK_2, fontSize=11).encode(text="c_text:N")
        neg = base.transform_filter("datum.contribution_pts < 0").mark_text(
            align="right", dx=-5, color=INK_2, fontSize=11).encode(text="c_text:N")
        _chart(bars + pos + neg, height=420)
        st.caption(f"Red adds to inflation, blue reduces it. Headline year-on-year {comp.attrs['headline_yoy']:+.2f}%; "
                   f"the 12 contributions add up to {comp.attrs['sum_of_contributions']:+.2f} points "
                   "(approximation; group's own analysis).")
    st.caption("Highlighted: the divisions in your selection (all 12 when only the headline is selected).")


def chart_heatmap(data: PreparedData, f: A.Filters) -> None:
    st.subheader("Distribution across categories and months")
    df = cd.heatmap(data.cpi, f)
    if df.empty:
        st.info("No data for this selection.")
        return
    mid = 100 if f.measure == "index" else 0
    lo, hi = df["value"].min(), df["value"].max()
    span = max(abs(lo - mid), abs(hi - mid)) or 1
    heat = alt.Chart(df).mark_rect(stroke=SURFACE, strokeWidth=1).encode(
        x=alt.X("yearmonth(period):O", title=None,
                axis=alt.Axis(format="%b %y", labelAngle=-90, ticks=False, domain=False)),
        y=alt.Y("category:N", title=None, axis=alt.Axis(labelLimit=280, ticks=False, domain=False)),
        color=alt.Color("value:Q", title=MEASURE_LABELS[f.measure],
                        scale=alt.Scale(domain=[mid - span, mid, mid + span], range=[DOWN, NEUTRAL, UP]),
                        legend=alt.Legend(orient="right", gradientLength=160)),
        tooltip=[alt.Tooltip("category:N", title="Category"), alt.Tooltip("period:T", format="%b %Y", title="Month"),
                 alt.Tooltip("value:Q", format=".1f", title=MEASURE_LABELS[f.measure])])
    _chart(heat, height=max(140, 30 * df["category"].nunique()))
    st.caption("Blue = below the reference, grey = no change, red = above. Hover a cell for its value.")


def priority_section(data: PreparedData, f: A.Filters) -> None:
    st.subheader(f"Monitoring priorities · {pd.Timestamp(f.end):%B %Y} · {f.population} households")
    t = A.priority_table(data.cpi, data.weights, f.end, codes=f.codes, population=f.population)
    r = t.attrs["rules"]
    show = t.rename(columns={
        "code": "Code", "name": "Division", "mom": "MoM %", "yoy": "YoY %", "base": "vs Apr 2019 %",
        "weight": "Weight %", "gap_bh_minus_nonbh": "BH − non-BH YoY (pts)",
        "flag_rising_fastest": f"Top {r['rising_fastest_top_n']} rising",
        "flag_far_from_base": f"Top {r['furthest_from_base_top_n']} from base",
        "flag_large_weight": f"Weight ≥ {r['large_weight_min']:g}%",
        "flag_nationality_gap": f"Gap ≥ {r['nationality_gap_min']:g} pt",
        "criteria_met": "Criteria met"})
    config_cols = {c: st.column_config.NumberColumn(format="%.1f")
                   for c in ["MoM %", "YoY %", "vs Apr 2019 %", "Weight %", "BH − non-BH YoY (pts)"]}
    config_cols["Criteria met"] = st.column_config.ProgressColumn(
        "Criteria met", min_value=0, max_value=4, format="%d of 4")
    _show(st.dataframe, show, hide_index=True, column_config=config_cols)
    flags = cd.priority_flagged(data.discrepancies, f)
    if len(flags):
        divs = ", ".join(sorted(flags["code"].unique()))
        what = ("the nationality-gap criterion and the change columns use"
                if flags["used_in"].str.contains("MoM").any() else "the nationality-gap criterion uses")
        st.warning(f"Data caution: {what} Dataset 2 values for {cd.month_span(flags['period'])} that differ from "
                   f"iGA's own Table 3 (divisions {divs}). Treat those results with care. "
                   "Details: Data & sources tab.")
    st.caption("Criteria from proposal Section 1: fastest rising, furthest from base, large share of spending, "
               "different for Bahraini and non-Bahraini households. Ranks are across all 12 divisions; the table "
               "shows the divisions in your selection (all 12 when only the headline is selected). "
               "The table shows evidence; analysts decide.")


def sources_section(data: PreparedData) -> None:
    st.subheader("Data sources")
    _show(st.dataframe, pd.DataFrame([
        {"Dataset": k, "Title": v["title"], "Publisher": v["publisher"], "Used for": use,
         "Coverage": v["coverage"], "Retrieved": v["retrieved"], "Terms": v["licence"], "Link": v["url"],
         "Terms link": v.get("licence_url", "")}
        for (k, v), use in zip(config.SOURCES.items(), [
            "National index, all 69 categories", "Bahraini vs non-Bahraini index",
            "Expenditure weights (Table 2.01), headline 2011-2016 (Table 1), 2010 derived"], strict=True)]),
        hide_index=True,
        column_config={"Link": st.column_config.LinkColumn(), "Terms link": st.column_config.LinkColumn()})
    if data.discrepancies is not None and len(data.discrepancies):
        st.subheader("Known source discrepancy")
        d = data.discrepancies
        by_pop = d.groupby("population").agg(n_values=("code", "size"), n_series=("code", "nunique"))
        parts = [f"{r.n_values} values in {r.n_series} {pop} series" for pop, r in by_pop.iterrows()]
        years = sorted(d["period"].dt.year.unique())
        st.markdown(
            f"For **{len(d)} values** ({'; '.join(parts)}; {', '.join(map(str, years))}), iGA's portal file "
            "(Dataset 2) differs from iGA's own published Table 3 (September 2023 release). Table 3 is internally "
            "consistent (its divisions add up to the published headline) while Dataset 2's values for these months "
            "are not, so the portal values are likely wrong. The tool keeps Dataset 2 as its working source, as "
            "stated in the proposal, and flags every figure that uses these values: the charts, the summary "
            "figures, year-on-year changes a year later, the priority table and the model's tool results.")
        show = d.copy()
        show["period"] = show["period"].dt.strftime("%b %Y")
        _show(st.dataframe, show.rename(columns={
            "code": "Code", "name": "Division", "period": "Month", "population": "Households",
            "dataset2": "Dataset 2", "iga_table3": "iGA Table 3", "difference": "Difference"}), hide_index=True,
            column_config={c: st.column_config.NumberColumn(format="%.1f")
                           for c in ["Dataset 2", "iGA Table 3", "Difference"]})
    st.subheader("Data preparation checks (F1)")
    st.caption("Every check made in code when the data was prepared. Full write-up: docs/data_pipeline.md.")
    _show(st.dataframe, data.quality, hide_index=True)


def coverage_notes(data: PreparedData, f: A.Filters) -> None:
    """Explain empty or derived months in the selection, using the data itself (no fixed dates)."""
    cpi = data.cpi
    have = cpi[(cpi["population"] == f.population) & cpi["index"].notna()]
    if f.population != config.NATIONAL:
        first = have["period"].min()
        if f.start < first:
            st.info(f"{f.population} figures (Dataset 2) start in {first:%B %Y}, so earlier months are empty.")
        return
    divisions_from = have.loc[have["level"] > 0, "period"].min()
    if f.start < divisions_from:
        st.info(f"Before {divisions_from:%B %Y} only the headline CPI is available (Dataset 3, iGA Table 1). "
                f"Divisions and groups start in {divisions_from:%B %Y} (Dataset 1).")
    derived = have[(have["source"] == "D3-derived") & (have["period"] >= f.start) & (have["period"] <= f.end)]
    if len(derived):
        st.caption(f"{derived['period'].min():%b %Y} - {derived['period'].max():%b %Y}: derived from iGA Table 1's "
                   "12-month changes (proposal Section 1); not published index levels.")


def dataset3_notice(data: PreparedData) -> None:
    """Warn when the Dataset 3 file on this server is not the version the group used."""
    q = data.quality
    row = q[q["check"] == config.D3_FINGERPRINT_CHECK]
    if len(row) and row.iloc[0]["status"] == "warning":
        st.warning("Dataset 3 on this server is not the same file the group used (SHA-256 fingerprint differs). "
                   "Weights, the 2010-2016 headline and the cross-checks may differ from our report. "
                   "Details: Data & sources tab.")


def render_dashboard(data: PreparedData | None = None) -> A.Filters:
    data = data or _load()
    st.markdown(CSS, unsafe_allow_html=True)
    f, by_nat = sidebar_filters(data)

    dataset3_notice(data)
    coverage_notes(data, f)
    flagged = cd.flagged_values(data.discrepancies, f, by_nat)
    if len(flagged):
        st.warning(f"Data caution: {cd.caution_text(flagged)} The dashboard shows Dataset 2, as stated in our "
                   "proposal. Details: Data & sources tab.")
    _, dropped = cd.usable_codes(data.cpi, f)
    if dropped:
        st.info(f"{', '.join(dropped)}: no {f.population} series (nationality figures cover the headline "
                "and 12 divisions only), so they are left out of the charts.")

    summary_section(data, f)
    overview, composition, priorities, sources = st.tabs(
        ["Overview", "Composition & distribution", "Monitoring priorities", "Data & sources"])
    with overview:
        chart_trend(data, f)
        chart_comparison(data, f, by_nat)
    with composition:
        chart_composition(data, f)
        chart_heatmap(data, f)
    with priorities:
        priority_section(data, f)
    with sources:
        sources_section(data)

    st.divider()
    st.caption(config.ATTRIBUTION)
    st.caption(config.OWN_ANALYSIS_NOTE)
    return f


if __name__ == "__main__":
    st.set_page_config(page_title="PriceLens BH - Dashboard", page_icon="📊", layout="wide")
    st.title("PriceLens BH")
    st.markdown("<p class='pl-sub'>Cost-of-living monitor for Bahrain · Consumer Price Index, April 2019 = 100 · "
                "data to August 2026</p>", unsafe_allow_html=True)
    render_dashboard()
