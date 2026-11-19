"""Streamlit analytics dashboard (F2 filtering + F3 visualisations).

Usage inside the group's main app:

    from src.dashboard.page import render_dashboard
    filters = render_dashboard()        # returns the active Filters
    # pass `filters` to the report export (F9) so the report = current selection

Run on its own:  streamlit run src/dashboard/page.py
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
from src.pipeline.run import PreparedData, load_prepared

MEASURE_LABELS = {"yoy": "Year-on-year %", "mom": "Month-on-month %",
                  "base": "Change since Apr 2019 %", "index": "Index (Apr 2019 = 100)"}


def _show(fn, obj, **kw):
    """Full-width display that works on both older and newer Streamlit versions."""
    try:
        return fn(obj, width="stretch", **kw)
    except TypeError:
        return fn(obj, use_container_width=True, **kw)


@st.cache_data(show_spinner="Loading prepared CPI data...")
def _load() -> PreparedData:
    return load_prepared()


# --------------------------------------------------------------------------
# F2 - filters
# --------------------------------------------------------------------------
def sidebar_filters(data: PreparedData) -> tuple[A.Filters, bool]:
    cpi, lab = data.cpi, data.labels
    st.sidebar.header("Filters")

    months = sorted(cpi.loc[cpi["source"] != "D3", "period"].unique())
    start, end = st.sidebar.select_slider(
        "Time period", options=months, value=(months[-36], months[-1]),
        format_func=lambda p: pd.Timestamp(p).strftime("%b %Y"), key="f_period")

    population = st.sidebar.radio(
        "Households", config.POPULATIONS, horizontal=False, key="f_pop",
        help="Nationality series (Dataset 2) start in May 2019 and cover the headline and 12 divisions.")

    level = st.sidebar.radio("Category level", ["Divisions", "Groups and items", "All"],
                             horizontal=True, key="f_level")
    pool = lab if level == "All" else lab[lab["level"].isin([0, 1] if level == "Divisions" else [2, 3])]
    options = pool["code"].tolist()
    default = [c for c in ["0", "01", "04", "07"] if c in options] or options[:3]
    names = dict(zip(lab["code"], lab["name"]))
    codes = st.sidebar.multiselect("Categories", options, default=default, key="f_codes",
                                   format_func=lambda c: f"{c}  {names.get(c, '')}")

    measure = st.sidebar.selectbox("Measure", list(MEASURE_LABELS), index=0, key="f_measure",
                                   format_func=MEASURE_LABELS.get)
    by_nat = st.sidebar.toggle("Compare nationalities in chart 2", value=False, key="f_bynat")

    f = A.Filters(pd.Timestamp(start), pd.Timestamp(end), codes or ["0"], population, measure)
    return f, by_nat


# --------------------------------------------------------------------------
# F3 - summary figures and charts
# --------------------------------------------------------------------------
def _fmt(fig: A.Figure | None) -> str:
    return "n/a" if fig is None else fig.display


def kpi_row(data: PreparedData, f: A.Filters) -> None:
    focus = f.codes[0]
    s = A.summary_figures(data.cpi, f, focus)
    st.markdown(f"**{focus} {s['name']}** - {f.population}, {pd.Timestamp(f.end):%B %Y}")
    c = st.columns(5)
    c[0].metric("Index (Apr 2019 = 100)", _fmt(s["index"]))
    c[1].metric("Month-on-month", _fmt(s["mom"]))
    c[2].metric("Year-on-year", _fmt(s["yoy"]))
    c[3].metric("Since Apr 2019", _fmt(s["base"]))
    rng = s["over_range_pct"]
    c[4].metric(f"Since {pd.Timestamp(f.start):%b %Y}", "n/a" if rng is None else f"{rng:+.1f}%")
    cov = cd.data_coverage(data.cpi, f)
    st.caption(f"Selection: {cov['categories']} categories x {cov['months']} months = {cov['rows']} values"
               + (f" ({cov['missing']} missing, shown as gaps - never filled)" if cov["missing"] else ""))


def chart_trend(data: PreparedData, f: A.Filters) -> None:
    st.subheader("1 - Change over time")
    df = cd.trend(data.cpi, f)
    if df.empty:
        st.info("No data for this selection.")
        return
    y_title = MEASURE_LABELS[f.measure]
    line = alt.Chart(df).mark_line(point=True).encode(
        x=alt.X("period:T", title=None,
                axis=alt.Axis(format="%b %Y", tickCount={"interval": "month", "step": 3}, labelAngle=-45)),
        y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)),
        color=alt.Color("category:N", title=None,
                        legend=alt.Legend(orient="bottom", columns=2, labelLimit=400)),
        tooltip=[alt.Tooltip("category:N"), alt.Tooltip("period:T", format="%b %Y"),
                 alt.Tooltip("value:Q", format=".1f", title=y_title)])
    ref = 100 if f.measure == "index" else 0
    rule = alt.Chart(pd.DataFrame({"y": [ref]})).mark_rule(strokeDash=[4, 4], opacity=0.5).encode(y="y:Q")
    _show(st.altair_chart, line + rule)


def chart_comparison(data: PreparedData, f: A.Filters, by_nat: bool) -> None:
    st.subheader(f"2 - Comparison between categories, {pd.Timestamp(f.end):%b %Y}")
    df = cd.comparison(data.cpi, f, by_nat).dropna(subset=["value"])
    if df.empty:
        st.info("No comparable values for this selection.")
        return
    df["label"] = df["code"] + " " + df["name"]
    enc = dict(y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
               x=alt.X("value:Q", title=MEASURE_LABELS[f.measure]),
               color=alt.Color("group:N", title=None, legend=alt.Legend(orient="bottom")),
               tooltip=["code", "name", "group", "display"])
    if by_nat:
        enc["yOffset"] = alt.YOffset("group:N")
    _show(st.altair_chart, alt.Chart(df).mark_bar().encode(**enc))


def chart_composition(data: PreparedData, f: A.Filters) -> None:
    st.subheader("3 - Composition of the basket")
    if data.weights is None:
        st.warning("Expenditure weights (Dataset 3) are not loaded.")
        return
    try:
        df = cd.composition(data.cpi, data.weights, f)
    except A.DataUnavailable as exc:
        st.info(str(exc))
        return
    left, right = st.columns(2)
    donut = alt.Chart(df).mark_arc(innerRadius=55).encode(
        theta="weight:Q",
        color=alt.Color("label:N", title=None, legend=alt.Legend(orient="bottom", columns=1, labelLimit=400)),
        tooltip=["label", alt.Tooltip("weight:Q", format=".2f", title="Weight (%)")])
    left.markdown("Expenditure weight (% of basket, iGA Table 2.01)")
    _show(left.altair_chart, donut)
    contrib = df[df["code"] != "rest"]
    bars = alt.Chart(contrib).mark_bar().encode(
        y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X("contribution_pts:Q", title="Contribution to headline YoY (pts)"),
        color=alt.condition("datum.contribution_pts > 0", alt.value("#c0504d"), alt.value("#4f81bd")),
        tooltip=["label", alt.Tooltip("contribution_pts:Q", format=".2f")])
    right.markdown(f"Contribution to headline year-on-year change, {pd.Timestamp(f.end):%b %Y}")
    _show(right.altair_chart, bars)
    right.caption(f"Headline YoY {df.attrs['headline_yoy']:+.2f}%; sum of all 12 division contributions "
                  f"{df.attrs['sum_of_contributions']:+.2f} pts (approximation; group's own analysis).")


def chart_heatmap(data: PreparedData, f: A.Filters) -> None:
    st.subheader("4 - Distribution across categories and months")
    df = cd.heatmap(data.cpi, f)
    if df.empty:
        return
    heat = alt.Chart(df).mark_rect().encode(
        x=alt.X("yearmonth(period):O", title=None, axis=alt.Axis(format="%b %y", labelAngle=-90)),
        y=alt.Y("category:N", title=None, axis=alt.Axis(labelLimit=260)),
        color=alt.Color("value:Q", title=MEASURE_LABELS[f.measure],
                        scale=alt.Scale(scheme="redblue", reverse=True, domainMid=100 if f.measure == "index" else 0)),
        tooltip=["category", alt.Tooltip("period:T", format="%b %Y"), alt.Tooltip("value:Q", format=".1f")])
    _show(st.altair_chart, heat)


def priority_section(data: PreparedData, f: A.Filters) -> None:
    st.subheader(f"Monitoring priorities, {pd.Timestamp(f.end):%B %Y}")
    t = A.priority_table(data.cpi, data.weights, f.end)
    r = t.attrs["rules"]
    show = t.rename(columns={
        "name": "Division", "mom": "MoM %", "yoy": "YoY %", "base": "vs Apr 2019 %",
        "weight": "Weight %", "gap_bh_minus_nonbh": "BH - non-BH YoY (pts)",
        "flag_rising_fastest": f"Top {r['rising_fastest_top_n']} rising",
        "flag_far_from_base": f"Top {r['furthest_from_base_top_n']} from base",
        "flag_large_weight": f"Weight >= {r['large_weight_min']:g}%",
        "flag_nationality_gap": f"Gap >= {r['nationality_gap_min']:g} pt",
        "criteria_met": "Criteria met"})
    _show(st.dataframe, show, hide_index=True,
          column_config={c: st.column_config.NumberColumn(format="%.1f")
                                for c in ["MoM %", "YoY %", "vs Apr 2019 %", "Weight %", "BH - non-BH YoY (pts)"]})
    st.caption("Criteria from proposal Section 1 (fastest rising, furthest from base, large share of spending, "
               "different for Bahraini and non-Bahraini households). The table shows evidence; analysts decide.")


def render_dashboard(data: PreparedData | None = None) -> A.Filters:
    data = data or _load()
    f, by_nat = sidebar_filters(data)
    _, dropped = cd.usable_codes(data.cpi, f)
    if dropped:
        st.info(f"{', '.join(dropped)}: no {f.population} series (nationality figures cover the headline "
                "and 12 divisions only), so they are left out of the charts.")
    kpi_row(data, f)
    chart_trend(data, f)
    a, b = st.columns(2)
    with a:
        chart_comparison(data, f, by_nat)
    with b:
        chart_heatmap(data, f)
    chart_composition(data, f)
    priority_section(data, f)
    with st.expander("Data preparation checks (F1)"):
        _show(st.dataframe, data.quality, hide_index=True)
    st.caption(config.ATTRIBUTION)
    st.caption(config.OWN_ANALYSIS_NOTE)
    return f


if __name__ == "__main__":
    st.set_page_config(page_title="PriceLens BH - Dashboard", layout="wide")
    st.title("PriceLens BH - cost-of-living dashboard")
    render_dashboard()
