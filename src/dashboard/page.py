"""Streamlit analytics dashboard (F2 filtering + F3 visualisations).

Usage inside the group's main app:

    from src.dashboard.page import render_dashboard
    filters = render_dashboard()        # returns the active Filters
    # pass `filters` to the report export (F9) so the report = current selection

Run on its own:  streamlit run src/dashboard/page.py   (or double-click run_app.bat)

Design rules (tutor feedback, 25/11/2026: "readable for someone who is not an
analyst"):
  * every number carries a plain-language sentence saying what it means;
  * every chart says what question it answers, how to read it and why that
    chart type was chosen;
  * filters are grouped in numbered steps with presets, so nobody has to
    know the data to start;
  * notes about the data are short, calm and point to the details.

Every chart and table receives the same `Filters` object from the sidebar,
which is how "every analytical display responds to the active filters" (F2)
is guaranteed.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

if __package__ in (None, ""):                     # allow `streamlit run src/dashboard/page.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt
import pandas as pd
import streamlit as st

from src.dashboard import chart_data as cd
from src.dashboard import explain as E
from src.dashboard import visuals as V
from src.pipeline import analytics as A
from src.pipeline import config
from src.pipeline.run import PreparedData, build, load_prepared, write_outputs

MEASURE_LABELS = {m: v["label"] for m, v in E.MEASURES.items()}
HOUSEHOLD_LABELS = {"National": "All households (national)", "Bahraini": "Bahraini households",
                    "Non-Bahraini": "Non-Bahraini households"}
PERIOD_PRESETS = {"Last 12 months": 12, "Last 3 years": 36, "Last 5 years": 60,
                  "Since April 2019": "base", "All years": "all", "Custom": "custom"}
LEVELS = {"Main groups (12)": [0, 1], "Detailed items": [2, 3], "Both": [0, 1, 2, 3]}
PICK_MODES = ("I'll choose",) + cd.AUTO_MODES

# --------------------------------------------------------------------------
# Visual style (validated categorical palette; colour follows the category)
# --------------------------------------------------------------------------
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
HEADLINE_COLOUR = INK_2                  # the headline is the reference line: neutral ink
POPULATION_COLOURS = {"National": "#2a78d6", "Bahraini": "#eb6834", "Non-Bahraini": "#1baf7a"}
UP, DOWN, NEUTRAL = "#e34948", "#2a78d6", "#f0efec"   # diverging pair, grey midpoint
MAX_CATEGORIES = 8                       # 8 palette colours (+ neutral headline): never cycled

CSS = """
<style>
  html, body, [class*="css"] { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.2rem; padding-bottom: 3rem;
      max-width: 1280px; }
  /* header: dark band that continues the dark filter panel */
  .pl-hero { position: relative; overflow: hidden; border-radius: 20px; padding: 1.5rem 1.7rem 1.3rem;
      margin-bottom: 1rem; color: #ffffff;
      background: radial-gradient(1200px 300px at 85% -20%, rgba(110,168,245,0.35), transparent 60%),
                  linear-gradient(135deg, #1d2432 0%, #1f2f4d 55%, #234a86 100%);
      box-shadow: 0 10px 30px rgba(29,36,50,0.25); display: grid; grid-template-columns: 1.15fr 1fr;
      gap: 1.2rem; align-items: center; }
  .pl-hero .pl-kicker { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
      color: #8fbcf6; margin: 0 0 0.35rem; }
  .pl-hero .pl-title { font-size: 2.3rem; font-weight: 750; margin: 0; color: #ffffff;
      letter-spacing: -0.025em; line-height: 1.1; }
  .pl-hero .pl-lead { color: #d6deea; font-size: 1rem; margin: 0.5rem 0 0.9rem; line-height: 1.45; }
  .pl-hero .pl-chip { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.18); color: #dfe7f3; }
  .pl-hero .pl-chip b { color: #ffffff; }
  .pl-hero .pl-hc { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.10);
      border-radius: 14px; padding: 0.55rem 0.7rem 0.2rem; }
  .pl-hero .pl-hc-t { font-size: 0.78rem; color: #b8c4d6; margin: 0 0 0.1rem; }
  .pl-hero .pl-hc-t b { color: #ffffff; }
  .pl-hero-chart { width: 100%; height: auto; display: block; }
  .pl-hx { font-size: 10px; fill: #9fb0c8; }
  .pl-hsel { font-size: 10px; fill: #dfe7f3; font-weight: 600; }
  .pl-hval { font-size: 13px; fill: #ffffff; font-weight: 700; }
  .pl-hline { stroke-dasharray: 1; animation: plDraw 2.6s cubic-bezier(.45,0,.2,1) .2s both; }
  .pl-harea { animation: plFade 1s ease 2.2s both; }
  .pl-hpulse { transform-box: fill-box; transform-origin: center; animation: plPulse 2.8s ease-out 2.8s infinite both; }
  @media (max-width: 900px) { .pl-hero { grid-template-columns: 1fr; } }
  .pl-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0; }
  .pl-chip { background: #ffffff; border: 1px solid #dcdad3; border-radius: 999px; padding: 0.18rem 0.7rem;
      font-size: 0.8rem; color: #3d3c39; white-space: nowrap; }
  .pl-chip b { color: #0b0b0b; font-weight: 600; }
  .pl-chip.blue { background: #eaf2fc; border-color: #c9dcf6; color: #1b5aa6; }
  /* section titles */
  .pl-section { font-size: 1.15rem; font-weight: 650; color: #0b0b0b; margin: 1.3rem 0 0.15rem; }
  .pl-section-sub { color: #6b6a66; font-size: 0.88rem; margin: 0 0 0.7rem; }
  /* key number cards */
  .pl-card { background: #ffffff; border: 1px solid #e3e7ee; border-top: 4px solid var(--c, #2a78d6);
      border-radius: 14px; padding: 0.85rem 1rem 0.85rem; min-height: 13rem;
      box-shadow: 0 1px 3px rgba(16,24,40,0.06); transition: transform .2s ease, box-shadow .2s ease;
      animation: plUp .5s ease both; animation-delay: var(--d, 0s); }
  .pl-card:hover { transform: translateY(-3px); box-shadow: 0 10px 22px rgba(16,24,40,0.10); }
  .pl-spark { width: 100%; height: 2.4rem; display: block; margin: 0.15rem 0 0.1rem; }
  .pl-spark-cap { font-size: 0.7rem; color: #8a93a3; margin: 0 0 0.2rem; }
  .pl-card .top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .pl-card .lbl { color: #3d3c39; font-size: 0.84rem; font-weight: 650; margin: 0; }
  .pl-ico { width: 2.1rem; height: 2.1rem; border-radius: 50%; display: flex; align-items: center;
      justify-content: center; background: var(--bg, #eaf2fc); flex: none; }
  .pl-ico svg { width: 1.15rem; height: 1.15rem; stroke: var(--c, #2a78d6); fill: none; stroke-width: 2;
      stroke-linecap: round; stroke-linejoin: round; }
  .pl-card .val { font-size: 2rem; font-weight: 650; color: #0b0b0b; margin: 0.15rem 0 0.25rem;
      letter-spacing: -0.02em; line-height: 1.15; }
  .pl-card .say { color: #3d3c39; font-size: 0.86rem; margin: 0.35rem 0 0.5rem; line-height: 1.35; }
  .pl-tag { display: inline-block; background: #f0efec; color: #52514e; border-radius: 6px;
      padding: 0.08rem 0.45rem; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.01em; }
  .pl-dir { display: inline-block; border-radius: 999px; padding: 0.1rem 0.55rem; font-size: 0.78rem;
      font-weight: 650; margin-left: 0.15rem; vertical-align: middle; }
  .pl-dir.up { background: #fdecec; color: #b42318; }
  .pl-dir.down { background: #eaf2fc; color: #1b5aa6; }
  .pl-dir.flat, .pl-dir.na { background: #f0efec; color: #52514e; }
  /* findings */
  .pl-findings { background: #ffffff; border: 1px solid #e3e7ee; border-radius: 14px; padding: 0.9rem 1.1rem;
      margin: 0.9rem 0 0.4rem; box-shadow: 0 1px 3px rgba(16,24,40,0.06); animation: plUp .5s ease .25s both; }
  .pl-findings p.h { font-weight: 700; margin: 0 0 0.5rem; color: #0b0b0b; font-size: 1rem; }
  .pl-find { display: flex; gap: 0.65rem; align-items: flex-start; margin: 0.38rem 0; color: #2b2a28;
      font-size: 0.93rem; line-height: 1.4; }
  .pl-find .b { flex: none; width: 1.55rem; height: 1.55rem; border-radius: 8px; display: flex; align-items: center;
      justify-content: center; font-size: 0.78rem; font-weight: 800; margin-top: 0.05rem; }
  .pl-find .b.overall { background: #eaf2fc; color: #1b5aa6; }
  .pl-find .b.up { background: #fdecec; color: #b42318; }
  .pl-find .b.down { background: #e6f4ff; color: #175cd3; }
  .pl-find .b.driver { background: #fff4e0; color: #9a5b00; }
  /* notes */
  .pl-note { border-radius: 10px; padding: 0.55rem 0.85rem; margin: 0.35rem 0; font-size: 0.88rem;
      line-height: 1.4; border: 1px solid; }
  .pl-note.info { background: #f3f7fd; border-color: #d5e3f6; color: #23436b; }
  .pl-note.caution { background: #fff8eb; border-color: #f3dfb3; color: #6b4a06; }
  /* chart headers */
  .pl-chart-h { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; margin: 1.1rem 0 0.1rem; }
  .pl-chart-h .t { font-size: 1.12rem; font-weight: 650; color: #0b0b0b; }
  .pl-chart-h .pl-when { color: #6b7280; font-size: 0.85rem; font-weight: 500; }
  .pl-chart-read { color: #6b6a66; font-size: 0.84rem; margin: 0.05rem 0 0.4rem; }
  /* panels: white boxes for charts and tables (keyed containers get the class st-key-<key>) */
  div[class*="st-key-pl_panel"] { background: #ffffff; border-radius: 14px; padding: 0.4rem 0.9rem 0.6rem;
      box-shadow: 0 1px 3px rgba(16,24,40,0.06); }
  /* sidebar (dark, see .streamlit/config.toml) */
  section[data-testid="stSidebar"] .pl-brand { display: flex; align-items: center; gap: 0.55rem; margin: 0 0 0.6rem; }
  section[data-testid="stSidebar"] .pl-brand svg { width: 1.9rem; height: 1.9rem; }
  section[data-testid="stSidebar"] .pl-brand span { font-size: 1.05rem; font-weight: 700; color: #ffffff; }
  section[data-testid="stSidebar"] .pl-step { font-size: 0.74rem; font-weight: 700; letter-spacing: 0.08em;
      text-transform: uppercase; color: #8fbcf6; margin: 1.15rem 0 0.25rem; padding-top: 0.7rem;
      border-top: 1px solid #333d50; }
  section[data-testid="stSidebar"] .pl-side-h { font-size: 1.1rem; font-weight: 700; margin: 0; color: #ffffff; }
  section[data-testid="stSidebar"] .pl-side-sub { color: #aab4c3; font-size: 0.82rem; margin: 0.1rem 0 0.2rem; }
  /* make the active period / detail button obvious on the dark panel */
  section[data-testid="stSidebar"] button[data-testid="stBaseButton-segmented_controlActive"],
  section[data-testid="stSidebar"] button[kind="segmented_controlActive"] {
      background: #6ea8f5 !important; border-color: #6ea8f5 !important; }
  section[data-testid="stSidebar"] button[data-testid="stBaseButton-segmented_controlActive"] p,
  section[data-testid="stSidebar"] button[kind="segmented_controlActive"] p { color: #0f1729 !important;
      font-weight: 700; }
  div[data-testid="stExpander"] details summary p { font-weight: 600; }
  /* tabs as pills */
  div[data-baseweb="tab-list"] { gap: 0.45rem; flex-wrap: wrap; }
  button[data-baseweb="tab"] { background: #ffffff; border: 1px solid #dfe3ea !important; border-radius: 999px;
      padding: 0.35rem 1rem !important; height: auto; }
  button[data-baseweb="tab"] p { font-size: 0.93rem; font-weight: 600; }
  button[data-baseweb="tab"][aria-selected="true"] { background: #1d2432; border-color: #1d2432 !important; }
  button[data-baseweb="tab"][aria-selected="true"] p { color: #ffffff; }
  div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] { display: none; }
  /* motion: gentle, once; none for people who ask for reduced motion */
  @keyframes plUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  @keyframes plFade { from { opacity: 0; } to { opacity: 1; } }
  @keyframes plDraw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
  @keyframes plPulse { 0% { transform: scale(1); opacity: .6; } 70%, 100% { transform: scale(2.6); opacity: 0; } }
  @media (prefers-reduced-motion: reduce) {
    .pl-card, .pl-findings, .pl-hline, .pl-harea, .pl-hpulse { animation: none !important; }
  }
</style>
"""


ICONS = {   # 24 x 24 line icons
    "tag": "<path d='M3 12V4h8l10 10-7 7z'/><circle cx='7.5' cy='7.5' r='1.3'/>",
    "calendar": "<rect x='3' y='5' width='18' height='16' rx='2'/><path d='M3 10h18M8 3v4M16 3v4'/>",
    "trend": "<path d='M3 17l6-6 4 4 8-8'/><path d='M15 7h6v6'/>",
    "range": "<circle cx='12' cy='12' r='9'/><path d='M12 7v5l3 3'/>",
}
CARD_COLOURS = {"tag": ("#2a78d6", "#eaf2fc"), "calendar": ("#eb6834", "#fdeee6"),
                "trend": ("#1baf7a", "#e5f6ef"), "range": ("#6250d6", "#eeebfb")}
LOGO = ("<svg viewBox='0 0 64 64'><circle cx='28' cy='28' r='22' fill='#253049' stroke='#6ea8f5' stroke-width='5'/>"
        "<rect x='17' y='30' width='6' height='10' rx='2' fill='#6ea8f5'/>"
        "<rect x='26' y='23' width='6' height='17' rx='2' fill='#6ea8f5'/>"
        "<rect x='35' y='15' width='6' height='25' rx='2' fill='#e34948'/>"
        "<line x1='45' y1='45' x2='59' y2='59' stroke='#ffffff' stroke-width='6' stroke-linecap='round'/></svg>")


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def _esc(text) -> str:
    return html.escape(str(text))


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


def _label(code: str, names: dict[str, str]) -> str:
    return f"{code} {E.display_name(names.get(code, ''))}"


def _series_scale(codes: list[str], names: dict[str, str]) -> alt.Scale:
    """Fixed colour per selected category: headline = neutral ink, others in palette order."""
    domain, colours, k = [], [], 0
    for code in codes:
        domain.append(_label(code, names))
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


def _keep_one(key: str, default: str) -> None:
    """Clicking the active button again would leave nothing selected; keep a choice instead."""
    if st.session_state.get(key) is None:
        st.session_state[key] = default


def _choice(container, label: str, options: list[str], default: str, key: str, help: str | None = None) -> str:
    """A row of buttons (segmented control) where Streamlit has it, otherwise a radio."""
    seg = getattr(container, "segmented_control", None)
    if seg is not None:
        value = seg(label, options, default=default, key=key, help=help, on_change=_keep_one, args=(key, default))
        return value or default
    return container.radio(label, options, index=options.index(default), key=key, help=help)


@st.cache_data(show_spinner="Preparing the CPI data (the first start on a new server takes about a minute)...")
def _load() -> PreparedData:
    """Use the prepared data; on a fresh server (e.g. Streamlit Cloud) build it first.

    data/processed/ is not in the repository, so a new server prepares it here:
    Dataset 3 is fetched from iGA (it may not be republished in the repository),
    then the same pipeline as `python -m src.pipeline.run` runs once.

    Only a COMPLETE build (with Dataset 3) is saved to data/processed/. If the
    download fails once, the next start tries again instead of reusing a copy
    without the weights; the Spending tab also offers a "try again" button.
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
# F2 - filters, in four numbered steps
# --------------------------------------------------------------------------
def _period_range(months: list, preset: str) -> tuple:
    end = months[-1]
    rule = PERIOD_PRESETS[preset]
    if rule == "all":
        return months[0], end
    if rule == "base":
        return pd.Timestamp(config.BASE_PERIOD + "-01"), end
    return months[max(0, len(months) - rule)], end


def sidebar_filters(data: PreparedData) -> tuple[A.Filters, bool]:
    cpi, lab, sb = data.cpi, data.labels, st.sidebar
    names = dict(zip(lab["code"], lab["name"], strict=True))
    _html(f"<div class='pl-brand'>{LOGO}<span>PriceLens BH</span></div>"
          "<p class='pl-side-h'>Filters</p><p class='pl-side-sub'>Every number, chart and table on the page "
          "follows these choices.</p>")

    # 1 - time period: presets first, a slider only for "Custom"
    sb.markdown("<p class='pl-step'>1 · Time period</p>", unsafe_allow_html=True)
    months = sorted(pd.Timestamp(p) for p in cpi["period"].unique())
    preset = _choice(sb, "Period", list(PERIOD_PRESETS), "Last 3 years", "f_preset",
                     help="Pick a ready-made period, or 'Custom' to choose any months from 2010 to August 2026.")
    if preset == "Custom":
        start, end = sb.select_slider("Months", options=months, value=(months[-36], months[-1]),
                                      format_func=lambda p: pd.Timestamp(p).strftime("%b %Y"), key="f_period")
    else:
        start, end = _period_range(months, preset)
    n_months = (end.year - start.year) * 12 + end.month - start.month + 1
    sb.caption(f"{pd.Timestamp(start):%b %Y} – {pd.Timestamp(end):%b %Y} · {n_months} months")

    # 2 - households
    sb.markdown("<p class='pl-step'>2 · Households</p>", unsafe_allow_html=True)
    population = sb.radio("Whose prices?", config.POPULATIONS, key="f_pop", format_func=HOUSEHOLD_LABELS.get,
                          help="Bahraini and non-Bahraini figures (Dataset 2) start in May 2019 and cover the "
                               "overall index and the 12 main spending groups.")
    by_nat = sb.toggle("Compare all three groups side by side", value=False, key="f_bynat",
                       help="Shows national, Bahraini and non-Bahraini bars next to each other in the "
                            "'How do the categories compare?' chart.")

    # 3 - categories
    sb.markdown("<p class='pl-step'>3 · Categories</p>", unsafe_allow_html=True)
    available = lab[lab["populations"].str.split(", ").apply(lambda pops: population in pops)]
    if population == config.NATIONAL:
        level = _choice(sb, "Detail", list(LEVELS), "Main groups (12)", "f_level",
                        help="Main groups are the 12 spending divisions (food, housing, transport ...). "
                             "Detailed items are the groups inside them (bread, rent, fuel ...).")
    else:
        level = "Main groups (12)"
        sb.caption("Bahraini / non-Bahraini figures exist for the overall index and the 12 main groups.")
    pool = available[available["level"].isin(LEVELS[level])]
    within = "All main groups"
    if level != "Main groups (12)":
        divisions = sorted(lab.loc[lab["level"] == 1, "code"])
        within = sb.selectbox("Within", ["All main groups"] + divisions, key="f_within",
                              format_func=lambda c: c if c == "All main groups" else _label(c, names),
                              help="Narrow the list to the items inside one main spending group.")
        if within != "All main groups":
            pool = pool[(pool["code"] == within) | pool["code"].str.startswith(within + ".")
                        | (pool["code"] == config.HEADLINE_CODE)]
    options = pool["code"].tolist()
    modes = [m for m in PICK_MODES if not (m == "Largest share of spending" and data.weights is None)]
    mode = sb.radio("How to choose", modes, key="f_mode", horizontal=False,
                    help="Let the dashboard pick the categories that rose or fell most, or that take the largest "
                         "share of household spending, at the end of your period.")
    measure = st.session_state.get("f_measure", "yoy")     # needed for automatic picks (set in step 4)
    if mode == "I'll choose":
        default = [c for c in ["0", "01", "04", "07"] if c in options] or options[:3]
        codes = sb.multiselect("Categories", options, default=default, key=f"f_codes_{population}_{level}_{within}",
                               max_selections=MAX_CATEGORIES, format_func=lambda c: _label(c, names),
                               help=f"Up to {MAX_CATEGORIES}, so each keeps its own colour.")
    else:
        n = sb.slider("How many", 3, MAX_CATEGORIES, 5, key="f_n")
        probe = A.Filters(pd.Timestamp(start), pd.Timestamp(end), options, population, measure)
        codes = cd.auto_pick(cpi, data.weights, probe, options, mode, n)
        if sb.checkbox("Include the overall index (All items) for reference", value=True, key="f_head"):
            codes = [config.HEADLINE_CODE] + codes
        sb.caption("Picked: " + ", ".join(_label(c, names) for c in codes) if codes else "Nothing to pick.")

    # 4 - how to show change
    sb.markdown("<p class='pl-step'>4 · Show change as</p>", unsafe_allow_html=True)
    measure = sb.radio("Measure", list(E.MEASURES), index=2, key="f_measure",
                       format_func=lambda m: E.MEASURES[m]["label"])
    sb.caption(E.MEASURES[measure]["help"])

    sb.divider()
    if sb.button("↺ Reset all filters", key="f_reset"):
        for k in [k for k in st.session_state if str(k).startswith("f_")]:
            del st.session_state[k]
        st.rerun()

    f = A.Filters(pd.Timestamp(start), pd.Timestamp(end), codes or ["0"], population, measure)
    return f, by_nat


# --------------------------------------------------------------------------
# Header, selection, notes
# --------------------------------------------------------------------------
def header(data: PreparedData, f: A.Filters) -> None:
    cpi = data.cpi
    last = pd.Timestamp(cpi["period"].max())
    h = cpi[(cpi["code"] == config.HEADLINE_CODE) & (cpi["population"] == f.population)].sort_values("period")
    series = h.set_index("period")["index"]
    derived = h.set_index("period")["source"].eq("D3-derived")
    chart = V.hero_chart(series, derived, f.start, f.end)
    first = series.dropna().index.min()
    chart_box = (f"<div class='pl-hc'><p class='pl-hc-t'>Overall prices · <b>{_esc(HOUSEHOLD_LABELS[f.population])}"
                 f"</b> · {first:%Y} – {last:%Y}</p>{chart}</div>") if chart else ""
    _html(
        "<div class='pl-hero'><div><p class='pl-kicker'>Bahrain cost-of-living monitor</p>"
        "<div class='pl-title'>PriceLens BH</div>"
        "<p class='pl-lead'>How prices are changing in Bahrain, by spending category and household group, "
        "from the official Consumer Price Index.</p><div class='pl-chips'>"
        "<span class='pl-chip'>Official data: <b>iGA, Kingdom of Bahrain</b></span>"
        f"<span class='pl-chip'>Latest month: <b>{last:%B %Y}</b></span>"
        "<span class='pl-chip'>April 2019 = <b>100</b></span></div></div>"
        f"{chart_box}</div>")


def selection_bar(data: PreparedData, f: A.Filters) -> None:
    codes, _ = cd.usable_codes(data.cpi, f)
    chips = [f"Households: <b>{_esc(HOUSEHOLD_LABELS[f.population])}</b>",
             f"Period: <b>{pd.Timestamp(f.start):%b %Y} – {pd.Timestamp(f.end):%b %Y}</b>",
             f"Categories: <b>{len(codes)}</b>",
             f"Showing: <b>{_esc(E.MEASURES[f.measure]['label'])}</b>"]
    _html("<div class='pl-chips'>" + "".join(f"<span class='pl-chip'>{c}</span>" for c in chips) + "</div>")
    with st.expander("What do these numbers mean?"):
        cols = st.columns(2)
        for i, (term, meaning) in enumerate(E.GLOSSARY):
            cols[i % 2].markdown(f"**{term}**  \n{meaning}")


def _note(kind: str, text: str) -> None:
    icon = {"info": "ℹ️", "caution": "⚠️"}[kind]
    _html(f"<div class='pl-note {kind}'>{icon}&nbsp; {text}</div>")


def data_notes(data: PreparedData, f: A.Filters, by_nat: bool) -> None:
    """Short, calm notes about the data behind this view (details live in Data & sources)."""
    q = data.quality
    row = q[q["check"] == config.D3_FINGERPRINT_CHECK]
    if len(row) and row.iloc[0]["status"] == "warning":
        _note("caution", "Dataset 3 on this server is not the exact file the group used, so weights and the "
                         "2010–2016 figures may differ from our report. See <b>Data &amp; sources</b>.")
    cpi = data.cpi
    have = cpi[(cpi["population"] == f.population) & cpi["index"].notna()]
    if f.population != config.NATIONAL:
        first = have["period"].min()
        if f.start < first:
            _note("info", f"{_esc(HOUSEHOLD_LABELS[f.population])}: figures start in {first:%B %Y}, so earlier "
                          "months are empty.")
    else:
        divisions_from = have.loc[have["level"] > 0, "period"].min()
        if f.start < divisions_from:
            _note("info", f"Before {divisions_from:%B %Y} only the overall index (All items) exists; spending "
                          f"categories start in {divisions_from:%B %Y}.")
        derived = have[(have["source"] == "D3-derived") & (have["period"] >= f.start) & (have["period"] <= f.end)]
        if len(derived):
            _note("info", "2010 values are calculated from iGA's 12-month changes (shown as derived), "
                          "not published index levels.")
    flagged = cd.flagged_values(data.discrepancies, f, by_nat)
    if len(flagged):
        pops = " and ".join(sorted(flagged["population"].unique())).replace("Non-", "non-")
        _note("caution", f"{len(flagged)} {pops} value{'s' if len(flagged) > 1 else ''} for "
                         f"{cd.month_span(flagged['period'])} used here differ from iGA's own published table by "
                         f"up to {flagged['difference'].abs().max():.1f} points, so figures built on them may be "
                         "inaccurate. Affected rows are marked ⚠ below. Details: <b>Data &amp; sources</b>.")
    _, dropped = cd.usable_codes(data.cpi, f)
    if dropped:
        _note("info", f"{', '.join(dropped)}: not published for {f.population.replace('Non-', 'non-')} "
                      "households (only the overall index and the 12 main groups are), so left out.")


# --------------------------------------------------------------------------
# F3 - key numbers, findings and the summary table
# --------------------------------------------------------------------------
def _card(label: str, fig: A.Figure | None, measure: str, say: str, tag: str, value_text: str | None = None,
          value: float | None = None, icon: str = "tag", spark: str = "", spark_cap: str = "",
          delay: float = 0.0) -> str:
    v = fig.value if fig is not None else value
    shown = value_text if value_text is not None else E.fmt_value(v, measure)
    kind, arrow = E.direction(v, measure)
    words = ({"up": "above 100", "down": "below 100", "flat": "at 100", "na": ""} if measure == "index"
             else {"up": "up", "down": "down", "flat": "no change", "na": ""})
    word = words[kind]
    chip = f"<span class='pl-dir {kind}'>{arrow} {word}</span>" if kind != "na" else ""
    c, bg = CARD_COLOURS[icon]
    ico = f"<span class='pl-ico'><svg viewBox='0 0 24 24'>{ICONS[icon]}</svg></span>"
    sp = f"{spark}<p class='pl-spark-cap'>{_esc(spark_cap)}</p>" if spark else ""
    return (f"<div class='pl-card' style='--c:{c};--bg:{bg};--d:{delay:.2f}s'><div class='top'>"
            f"<p class='lbl'>{_esc(label)}</p>{ico}</div>"
            f"<p class='val'>{_esc(shown)} {chip}</p>{sp}<p class='say'>{_esc(say)}</p>"
            f"<span class='pl-tag'>{_esc(tag)}</span></div>")


def key_numbers(data: PreparedData, f: A.Filters) -> None:
    names = dict(zip(data.labels["code"], data.labels["name"], strict=True))
    codes, _ = cd.usable_codes(data.cpi, f)
    codes = codes or [config.HEADLINE_CODE]
    left, right = st.columns([3, 2])
    left.markdown("<p class='pl-section'>Key numbers</p>", unsafe_allow_html=True)
    focus = right.selectbox("Key numbers for", codes, key="f_focus_" + "_".join(codes),
                            format_func=lambda c: "Key numbers for: " + _label(c, names),
                            label_visibility="collapsed")
    s = A.summary_figures(data.cpi, f, focus)
    _html(f"<p class='pl-section-sub'>{_esc(E.display_name(s['name']))} · "
          f"{_esc(HOUSEHOLD_LABELS[f.population])} · {pd.Timestamp(f.end):%B %Y}</p>")
    start = s["range_start"]
    end = pd.Timestamp(f.end)

    def recent(measure: str, months: int) -> list:
        ser = A.change_series(data.cpi, focus, measure, f.population)
        ser = ser[(ser.index <= end) & (ser.index > end - pd.DateOffset(months=months))]
        return ser.tolist()

    window = A.change_series(data.cpi, focus, "index", f.population)
    window = window[(window.index >= pd.Timestamp(f.start)) & (window.index <= end)].tolist()
    cards = [
        _card("Price level", s["index"], "index", E.sentence(s["index"], "index"), "Index · April 2019 = 100",
              icon="tag", spark=V.spark_line(recent("index", 36), "#2a78d6", ref=100.0),
              spark_cap="last 3 years · dashed line = 100", delay=0.0),
        _card("Monthly change", s["mom"], "mom", E.sentence(s["mom"], "mom"), "Month-on-month", icon="calendar",
              spark=V.spark_bars(recent("mom", 12)), spark_cap="each month of the last year", delay=0.08),
        _card("Yearly change (inflation)", s["yoy"], "yoy", E.sentence(s["yoy"], "yoy"),
              "Year-on-year", icon="trend", spark=V.spark_line(recent("yoy", 24), "#1baf7a", ref=0.0),
              spark_cap="last 2 years · dashed line = 0%", delay=0.16),
        _card("Change over your period", None, "base",
              E.period_sentence(s["over_range_pct"], start, f.end),
              f"From {pd.Timestamp(start):%b %Y}" if start else "Period change",
              value_text=E.fmt_value(s["over_range_pct"], "yoy"), value=s["over_range_pct"], icon="range",
              spark=V.spark_line(window, "#6250d6"), spark_cap="price level across your period", delay=0.24),
    ]
    for col, card in zip(st.columns(4), cards, strict=True):
        with col:
            _html(card)


def findings(data: PreparedData, f: A.Filters) -> None:
    flagged = cd.flagged_values(data.discrepancies, f)
    items = E.key_findings_tagged(data.cpi, data.weights, f, set(flagged["code"]) if len(flagged) else set())
    if not items:
        return
    badge = {"overall": "●", "up": "▲", "down": "▼", "driver": "◆"}
    rows = "".join(
        f"<div class='pl-find'><span class='b {kind}'>{badge[kind]}</span><span>"
        + re.sub(r"[*][*](.+?)[*][*]", r"<b>\1</b>", _esc(text)) + "</span></div>"
        for kind, text in items)
    _html(f"<div class='pl-findings'><p class='h'>In plain words</p>{rows}</div>")


def summary_table(data: PreparedData, f: A.Filters) -> None:
    summary = cd.selection_summary(data.cpi, f)
    if summary.empty:
        return
    flagged = cd.flagged_values(data.discrepancies, f)
    marked = set(flagged["code"]) if len(flagged) else set()
    show = pd.DataFrame({
        "Category": summary["code"] + "  " + summary["name"].map(E.display_name),
        "Price level": summary["index"],
        "vs previous month (%)": summary["mom"],
        "vs a year earlier (%)": summary["yoy"],
        "vs April 2019 (%)": summary["base"],
        "Over your period (%)": summary["over_range"],
        "Period from": summary["range_start"].map(lambda p: pd.Timestamp(p).strftime("%b %Y") if p else "–"),
        "Note": summary["code"].map(lambda c: "⚠ uses 2022 values that differ from iGA's table"
                                    if c in marked else ""),
    })
    if not show["Note"].any():
        show = show.drop(columns=["Note"])
    _html("<div class='pl-chart-h'><span class='t'>Your categories in numbers</span>"
          f"<span class='pl-when'>{pd.Timestamp(f.end):%B %Y}</span></div>")
    pct = "%.1f%%"
    _show(st.dataframe, show, hide_index=True, column_config={
        "Price level": st.column_config.NumberColumn(format="%.1f", help=E.MEASURES["index"]["help"]),
        "vs previous month (%)": st.column_config.NumberColumn(format=pct, help=E.MEASURES["mom"]["help"]),
        "vs a year earlier (%)": st.column_config.NumberColumn(format=pct, help=E.MEASURES["yoy"]["help"]),
        "vs April 2019 (%)": st.column_config.NumberColumn(format=pct, help=E.MEASURES["base"]["help"]),
        "Over your period (%)": st.column_config.NumberColumn(
            format=pct, help="Change from the first month of your period that has data to the last month."),
    })
    cov = cd.data_coverage(data.cpi, f)
    left, right = st.columns([3, 1])
    if cov["missing"]:
        left.caption(f"{cov['missing']} months with no published value are left empty, never estimated.")
    right.download_button("⬇ Download these figures (CSV)", show.to_csv(index=False).encode("utf-8"),
                          file_name=f"pricelens_{pd.Timestamp(f.end):%Y-%m}.csv", mime="text/csv",
                          key="dl_summary")


# --------------------------------------------------------------------------
# F3 - charts (each says what it answers, how to read it, and why this chart)
# --------------------------------------------------------------------------
def _panel(key: str):
    """A white box around a chart or table (bordered container; styled through its key)."""
    try:
        return st.container(border=True, key=f"pl_panel_{key}")
    except TypeError:                     # Streamlit before keyed containers
        return st.container(border=True)


def chart_header(key: str, suffix: str = "") -> None:
    c = E.CHARTS[key]
    _html(f"<div class='pl-chart-h'><span class='t'>{_esc(c['title'])}</span>"
          f"<span class='pl-when'>{_esc(suffix)}</span></div>"
          f"<p class='pl-chart-read'>{_esc(c['short'])}</p>")


def chart_trend(data: PreparedData, f: A.Filters) -> None:
    chart_header("trend", f"{pd.Timestamp(f.start):%b %Y} – {pd.Timestamp(f.end):%b %Y}")
    df = cd.trend(data.cpi, f)
    if df.empty:
        st.info("No data for this selection.")
        return
    names = dict(zip(data.labels["code"], data.labels["name"], strict=True))
    codes, _ = cd.usable_codes(data.cpi, f)
    label_of = {f"{c} {names.get(c, '')}": _label(c, names) for c in codes}
    df["category"] = df["category"].map(lambda x: label_of.get(x, x))
    n_months = df["period"].nunique()
    if n_months > 48:     # long range: one label per year, no dots
        axis = alt.Axis(format="%Y", tickCount={"interval": "year", "step": 1}, labelAngle=0, grid=False)
    else:
        axis = alt.Axis(format="%b %Y", tickCount={"interval": "month", "step": 3}, labelAngle=-40, grid=False)
    y_title = MEASURE_LABELS[f.measure]
    end = pd.Timestamp(f.end) + pd.DateOffset(months=max(2, n_months // 10))    # room for end labels
    x = alt.X("period:T", title=None, axis=axis,
              scale=alt.Scale(domain=[alt.DateTime(year=f.start.year, month=f.start.month, date=1),
                                      alt.DateTime(year=end.year, month=end.month, date=1)]))
    point = alt.OverlayMarkDef(size=36, filled=True, stroke=SURFACE, strokeWidth=2) if n_months <= 48 else False
    colour = alt.Color("category:N", title=None, scale=_series_scale(codes, names))
    line = alt.Chart(df).mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round", point=point).encode(
        x=x, y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)), color=colour,
        tooltip=[alt.Tooltip("category:N", title="Category"),
                 alt.Tooltip("period:T", format="%B %Y", title="Month"),
                 alt.Tooltip("value:Q", format=".1f", title=y_title)])
    last = df.dropna(subset=["value"]).sort_values("period").groupby("category", as_index=False).tail(1)
    last = last.assign(text=last["value"].map(lambda v: E.fmt_value(v, f.measure)))
    labels = alt.Chart(last).mark_text(align="left", dx=7, fontSize=11, fontWeight=600).encode(
        x=x, y="value:Q", text="text:N", color=alt.Color("category:N", scale=_series_scale(codes, names),
                                                          legend=None))
    ref = 100 if f.measure == "index" else 0
    ref_text = "April 2019 = 100" if f.measure == "index" else "no change"
    rule = alt.Chart(pd.DataFrame({"y": [ref], "t": [ref_text]}))
    rule_line = rule.mark_rule(color=AXIS, strokeWidth=1, strokeDash=[4, 4]).encode(y="y:Q")
    rule_text = rule.mark_text(align="left", baseline="bottom", dy=-3, color=MUTED, fontSize=10).encode(
        y="y:Q", text="t:N", x=alt.value(4))
    _chart(rule_line + rule_text + line + labels, height=320)


def chart_comparison(data: PreparedData, f: A.Filters, by_nat: bool) -> None:
    chart_header("comparison", f"{pd.Timestamp(f.end):%B %Y}")
    df = cd.comparison(data.cpi, f, by_nat).dropna(subset=["value"])
    if df.empty:
        st.info("No comparable values for this selection.")
        return
    df["label"] = df["code"] + " " + df["name"].map(E.display_name)
    df["text"] = df["value"].map(lambda v: E.fmt_value(v, f.measure))
    df["group"] = df["group"].map(lambda g: HOUSEHOLD_LABELS.get(g, g))
    groups = [HOUSEHOLD_LABELS[g] for g in config.POPULATIONS if HOUSEHOLD_LABELS[g] in set(df["group"])]
    groups = groups or list(df["group"].unique())
    colours = {HOUSEHOLD_LABELS[k]: v for k, v in POPULATION_COLOURS.items()}
    colour = alt.Color("group:N", title=None,
                       scale=alt.Scale(domain=groups, range=[colours.get(g, SERIES[0]) for g in groups]),
                       legend=alt.Legend() if by_nat else None)
    # An explicit order: a sort by field is dropped when bars and labels are layered.
    order = df.groupby("label")["value"].max().sort_values(ascending=False).index.tolist()
    y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=190, ticks=False, domain=False))
    base = alt.Chart(df).encode(y=y, x=alt.X("value:Q", title=MEASURE_LABELS[f.measure],
                                             scale=alt.Scale(domain=_padded_domain(df["value"]), nice=False),
                                             axis=alt.Axis(gridColor=GRID)))
    if by_nat:   # National first, then Bahraini, then Non-Bahraini, in every group
        base = base.encode(yOffset=alt.YOffset("group:N", sort=groups))
    bars = base.mark_bar(size=14 if by_nat else 18, cornerRadiusEnd=4).encode(
        color=colour, tooltip=[alt.Tooltip("label:N", title="Category"), alt.Tooltip("group:N", title="Households"),
                               alt.Tooltip("text:N", title=MEASURE_LABELS[f.measure])])
    pos = base.transform_filter("datum.value >= 0").mark_text(align="left", dx=5, color=INK_2, fontSize=11).encode(
        text="text:N")
    neg = base.transform_filter("datum.value < 0").mark_text(align="right", dx=-5, color=INK_2, fontSize=11).encode(
        text="text:N")
    zero = alt.Chart(pd.DataFrame({"x": [100 if f.measure == "index" else 0]})).mark_rule(
        color=AXIS, strokeWidth=1).encode(x="x:Q")
    n_rows = df["label"].nunique() * (3 if by_nat else 1)
    _chart(zero + bars + pos + neg, height=max(320, 34 * n_rows))


def chart_composition(data: PreparedData, f: A.Filters) -> None:
    if data.weights is None:
        _note("caution", "The spending weights (Dataset 3) could not be loaded. Online, this means the file "
                         "could not be fetched from iGA's website; on your computer, run "
                         "<code>python -m scripts.download_sources</code>.")
        if st.button("Try again to fetch Dataset 3 from iGA"):
            _load.clear()
            st.rerun()
        return
    try:
        comp = cd.basket(data.cpi, data.weights, f)
    except A.DataUnavailable as exc:
        st.info(str(exc))
        return
    comp["label"] = comp["code"] + " " + comp["name"].map(E.display_name)
    note = ("One fixed national basket (iGA Table 2.01): it does not change with the period"
            + (" and is also used for Bahraini and non-Bahraini households." if f.population != config.NATIONAL
               else "."))
    left, right = st.columns(2, gap="large")

    with left:
        chart_header("weights")
        st.caption(note)
        y = alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260, ticks=False, domain=False))
        base = alt.Chart(comp).encode(y=y, x=alt.X("weight:Q", title="Share of household spending (%)"))
        bars = base.mark_bar(size=16, cornerRadiusEnd=4).encode(
            color=alt.condition("datum.selected", alt.value(SERIES[0]), alt.value(AXIS)),
            tooltip=[alt.Tooltip("label:N", title="Spending group"),
                     alt.Tooltip("weight:Q", format=".1f", title="Share of spending (%)")])
        text = base.mark_text(align="left", dx=5, color=INK_2, fontSize=11).encode(text="w_text:N")
        _chart(bars + text, height=430)
    
    with right:
        chart_header("contributions", f"{pd.Timestamp(f.end):%B %Y}")
        st.caption(f"Overall yearly change: {comp.attrs['headline_yoy']:+.1f}%. The bars add up to "
                   f"{comp.attrs['sum_of_contributions']:+.2f} points (our approximation).")
        c = comp.dropna(subset=["contribution_pts"])
        order = c.sort_values("contribution_pts", ascending=False)["label"].tolist()
        y = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=260, ticks=False, domain=False))
        base = alt.Chart(c).encode(y=y, x=alt.X("contribution_pts:Q", title="Percentage points of the yearly change",
                                                scale=alt.Scale(domain=_padded_domain(c["contribution_pts"]),
                                                                nice=False)))
        bars = base.mark_bar(size=16, cornerRadiusEnd=4).encode(
            color=alt.condition("datum.contribution_pts >= 0", alt.value(UP), alt.value(DOWN)),
            opacity=alt.condition("datum.selected", alt.value(1.0), alt.value(0.35)),
            tooltip=[alt.Tooltip("label:N", title="Spending group"),
                     alt.Tooltip("contribution_pts:Q", format="+.2f", title="Points")])
        pos = base.transform_filter("datum.contribution_pts >= 0").mark_text(
            align="left", dx=5, color=INK_2, fontSize=11).encode(text="c_text:N")
        neg = base.transform_filter("datum.contribution_pts < 0").mark_text(
            align="right", dx=-5, color=INK_2, fontSize=11).encode(text="c_text:N")
        _chart(bars + pos + neg, height=430)
    

def chart_heatmap(data: PreparedData, f: A.Filters) -> None:
    chart_header("heatmap")
    df = cd.heatmap(data.cpi, f)
    if df.empty:
        st.info("No data for this selection.")
        return
    names = dict(zip(data.labels["code"], data.labels["name"], strict=True))
    df["category"] = df["category"].map(lambda x: _label(x.split(" ")[0], names))
    mid = 100 if f.measure == "index" else 0
    lo, hi = df["value"].min(), df["value"].max()
    span = max(abs(lo - mid), abs(hi - mid)) or 1
    n_months = df["period"].nunique()
    if n_months > 36:    # many months: label each January only
        x_axis = alt.Axis(labelExpr="month(datum.value) == 0 ? timeFormat(datum.value, '%Y') : ''",
                          labelAngle=0, ticks=False, domain=False)
    else:
        x_axis = alt.Axis(format="%b %y", labelAngle=-90, ticks=False, domain=False)
    heat = alt.Chart(df).mark_rect(stroke=SURFACE, strokeWidth=1).encode(
        x=alt.X("yearmonth(period):O", title=None, axis=x_axis),
        y=alt.Y("category:N", title=None, axis=alt.Axis(labelLimit=300, ticks=False, domain=False)),
        color=alt.Color("value:Q", title=MEASURE_LABELS[f.measure],
                        scale=alt.Scale(domain=[mid - span, mid, mid + span], range=[DOWN, NEUTRAL, UP]),
                        legend=alt.Legend(orient="right", gradientLength=160)),
        tooltip=[alt.Tooltip("category:N", title="Category"), alt.Tooltip("period:T", format="%B %Y", title="Month"),
                 alt.Tooltip("value:Q", format=".1f", title=MEASURE_LABELS[f.measure])])
    _chart(heat, height=max(140, 30 * df["category"].nunique()))


def priority_section(data: PreparedData, f: A.Filters) -> None:
    _html("<p class='pl-section'>Which spending groups need watching?</p>"
          f"<p class='pl-section-sub'>{pd.Timestamp(f.end):%B %Y} · {_esc(HOUSEHOLD_LABELS[f.population])}. "
          "Each main spending group is checked against four criteria. The table shows the evidence; "
          "analysts decide.</p>")
    t = A.priority_table(data.cpi, data.weights, f.end, codes=f.codes, population=f.population)
    r = t.attrs["rules"]
    show = pd.DataFrame({
        "Spending group": t["code"] + "  " + t["name"].map(E.display_name),
        "Criteria met": t["criteria_met"],
        "Why to watch": [E.priority_reasons(row, r) for _, row in t.iterrows()],
        "vs a year earlier (%)": t["yoy"],
        "vs April 2019 (%)": t["base"],
        "Share of spending (%)": t["weight"],
        "Bahraini minus non-Bahraini (points)": t["gap_bh_minus_nonbh"],
    })
    _show(st.dataframe, show, hide_index=True, column_config={
        "Criteria met": st.column_config.ProgressColumn("Criteria met", min_value=0, max_value=4, format="%d of 4",
                                                        help="How many of the four criteria the group meets."),
        "Why to watch": st.column_config.TextColumn(width="large"),
        "vs a year earlier (%)": st.column_config.NumberColumn(format="%.1f%%"),
        "vs April 2019 (%)": st.column_config.NumberColumn(format="%.1f%%"),
        "Share of spending (%)": st.column_config.NumberColumn(format="%.1f%%"),
        "Bahraini minus non-Bahraini (points)": st.column_config.NumberColumn(
            format="%.1f", help="Year-on-year change for Bahraini households minus non-Bahraini households."),
    })
    flags = cd.priority_flagged(data.discrepancies, f)
    if len(flags):
        _note("caution", f"The household-gap criterion uses 2022 values that differ from iGA's own table "
                         f"(groups {', '.join(sorted(flags['code'].unique()))}); treat those results with care.")
    with st.expander("The four criteria"):
        st.markdown(
            f"1. **Fastest rising:** among the {r['rising_fastest_top_n']} largest year-on-year increases.\n"
            f"2. **Furthest from April 2019:** among the {r['furthest_from_base_top_n']} largest changes since the "
            "base period, up or down.\n"
            f"3. **Large share of spending:** at least {r['large_weight_min']:g}% of household spending.\n"
            f"4. **Different for households:** Bahraini and non-Bahraini yearly changes at least "
            f"{r['nationality_gap_min']:g} points apart.\n\n"
            "Ranks are across all 12 groups; the table shows the groups in your selection "
            "(all 12 when only the overall index is selected).")


def sources_section(data: PreparedData) -> None:
    _html("<p class='pl-section'>Where the data comes from</p>"
          "<p class='pl-section-sub'>All figures come from the Information &amp; eGovernment Authority (iGA). "
          "Changes, rankings and contributions are our own calculations, not official iGA figures.</p>")
    _show(st.dataframe, pd.DataFrame([
        {"Dataset": k, "Title": v["title"], "Used for": use, "Coverage": v["coverage"], "Retrieved": v["retrieved"],
         "Terms": v["licence"], "Link": v["url"], "Terms link": v.get("licence_url", "")}
        for (k, v), use in zip(config.SOURCES.items(), [
            "National index, all 69 categories", "Bahraini vs non-Bahraini index",
            "Spending weights (Table 2.01), overall index 2011-2016 (Table 1), 2010 derived"], strict=True)]),
        hide_index=True,
        column_config={"Link": st.column_config.LinkColumn(), "Terms link": st.column_config.LinkColumn()})
    if data.discrepancies is not None and len(data.discrepancies):
        d = data.discrepancies
        with st.expander(f"Known issue in the source: {len(d)} values in 2022 (Dataset 2)", expanded=False):
            by_pop = d.groupby("population").agg(n_values=("code", "size"), n_series=("code", "nunique"))
            parts = [f"{r.n_values} values in {r.n_series} {pop} series" for pop, r in by_pop.iterrows()]
            st.markdown(
                f"For **{len(d)} values** ({'; '.join(parts)}), iGA's portal file (Dataset 2) differs from iGA's own "
                "published Table 3. Table 3 adds up to the published overall index; Dataset 2 does not, so the "
                "portal values are probably wrong. The dashboard keeps the published Dataset 2 values and "
                "marks every figure that uses these values.")
            show = d.copy()
            show["period"] = show["period"].dt.strftime("%b %Y")
            _show(st.dataframe, show.rename(columns={
                "code": "Code", "name": "Spending group", "period": "Month", "population": "Households",
                "dataset2": "Dataset 2", "iga_table3": "iGA Table 3", "difference": "Difference"}), hide_index=True,
                column_config={c: st.column_config.NumberColumn(format="%.1f")
                               for c in ["Dataset 2", "iGA Table 3", "Difference"]})
    with st.expander("Data preparation checks"):
        st.caption("Every check made in code when the data was prepared. Full write-up: docs/data_pipeline.md.")
        _show(st.dataframe, data.quality, hide_index=True)


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------
def render_dashboard(data: PreparedData | None = None, show_header: bool = True) -> A.Filters:
    data = data or _load()
    _html(CSS)
    with st.sidebar:
        f, by_nat = sidebar_filters(data)
    if show_header:
        header(data, f)
    selection_bar(data, f)
    data_notes(data, f, by_nat)
    key_numbers(data, f)
    findings(data, f)

    _html("<p class='pl-section'>At a glance</p>")
    left, right = st.columns(2, gap="medium")
    with left, _panel("trend"):
        chart_trend(data, f)
    with right, _panel("comparison"):
        chart_comparison(data, f, by_nat)
    with _panel("summary"):
        summary_table(data, f)

    spending, monthly, watch, sources = st.tabs(
        ["🧺 Spending & drivers", "🗓️ Month by month", "🎯 What to watch", "📚 Data & sources"])
    with spending, _panel("spending"):
        chart_composition(data, f)
    with monthly, _panel("monthly"):
        chart_heatmap(data, f)
    with watch, _panel("watch"):
        priority_section(data, f)
    with sources, _panel("sources"):
        sources_section(data)

    st.divider()
    st.caption(config.ATTRIBUTION)
    st.caption(config.OWN_ANALYSIS_NOTE)
    return f


if __name__ == "__main__":
    st.set_page_config(page_title="PriceLens BH · Bahrain cost of living", page_icon="📊", layout="wide")
    render_dashboard()
