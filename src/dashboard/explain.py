"""Plain-language text for the dashboard: every number says what it means.

The users in Brief A are analysts in a consumer affairs department who reply to
ministers, journalists and members of the public. Not every reader is a
statistician, so each figure on screen comes with a short sentence in plain
words, each chart says what it shows and how to read it, and the key terms
are explained once in a glossary.

Everything here is pure Python (no Streamlit), so it is unit-tested.
"""
from __future__ import annotations

import re

import pandas as pd

from src.pipeline import analytics as A
from src.pipeline import config

BASE_LABEL = "April 2019"

# What each reading is called on screen (short), in full, and what it compares.
MEASURES = {
    "index": {"short": "Price level", "label": "Price level (April 2019 = 100)",
              "tag": "Index", "unit": "points",
              "help": "Prices relative to April 2019, which is set to 100. 104.2 means 4.2% higher than April 2019."},
    "mom": {"short": "vs previous month", "label": "Change from the previous month (%)",
            "tag": "Month-on-month", "unit": "%",
            "help": "How much prices changed compared with the month before."},
    "yoy": {"short": "vs a year earlier", "label": "Change from a year earlier (%)",
            "tag": "Year-on-year (annual inflation)", "unit": "%",
            "help": "How much prices changed compared with the same month one year earlier. "
                    "This is the usual 'inflation rate'."},
    "base": {"short": "vs April 2019", "label": "Change since April 2019 (%)",
             "tag": "Since base period", "unit": "%",
             "help": "How much prices changed since April 2019, the base period of the index."},
}

GLOSSARY = [
    ("Consumer Price Index (CPI)",
     "Tracks the prices of the goods and services households buy, such as food, rent, fuel and school fees."),
    ("Price level (index)",
     "Prices compared with April 2019, which is set to 100. An index of 104.2 means prices are 4.2% higher "
     "than in April 2019; 89.0 means 11% lower."),
    ("Change from the previous month",
     "Compares a month with the month before. Useful for spotting sudden moves."),
    ("Change from a year earlier",
     "Compares a month with the same month last year. This is the annual inflation rate quoted in the news."),
    ("Change since April 2019",
     "Compares a month with the base period. The three changes can differ for the same category and month."),
    ("Weight (share of spending)",
     "How much of an average household's spending goes to a category. Housing is about a quarter."),
    ("Contribution",
     "How many percentage points of the overall yearly change came from one category: its weight times its "
     "own change."),
    ("Households",
     "National covers all households. Bahraini and non-Bahraini figures are published separately for the "
     "overall index and the 12 main spending groups, from May 2019."),
]

# One entry per chart: the question it answers and a one-line reading guide (shown on screen),
# plus its type and why it was chosen (for the report and the presentation: docs/chart_choices.md).
CHARTS = {
    "trend": {
        "title": "How have prices changed over time?",
        "short": "Each line is one category. The dashed line is the reference (April 2019 = 100, or no change).",
        "type": "Line chart · change over time",
        "read": "Each line is one category. Higher means prices were higher (or rising faster). "
                "The grey line is the reference: April 2019 = 100, or no change (0%).",
        "why": "A line is the clearest way to show how a value moves month by month and to compare a few "
               "categories on one scale. Brief F3: change over time.",
    },
    "comparison": {
        "title": "How do the categories compare?",
        "short": "Longer bars mean larger values at the end of your period; bars left of zero mean prices fell.",
        "type": "Bar chart · comparison between categories",
        "read": "Each bar is one category at the last month of your period, largest at the top. "
                "Bars to the left of zero mean prices fell.",
        "why": "Bars of the same width are compared by length, which people read more accurately than angles "
               "or colours. Brief F3: comparison between categories.",
    },
    "weights": {
        "title": "What do households spend their money on?",
        "short": "Share of an average household budget. Your selected groups are in blue.",
        "type": "Bar chart · composition",
        "read": "Each bar is a main spending group's share of an average household budget. "
                "Your selected groups are in blue.",
        "why": "With 12 groups, a sorted bar chart shows the shares far more clearly than a pie chart. "
               "Brief F3: composition.",
    },
    "contributions": {
        "title": "What pushed overall prices up or down?",
        "short": "Red pushed overall prices up, blue pulled them down. Longer bars mattered more.",
        "type": "Bar chart · contribution to inflation",
        "read": "Red bars pushed the overall yearly change up; blue bars pulled it down. "
                "Longer bars mattered more.",
        "why": "A category matters by how much it changed AND how much households spend on it. "
               "This chart combines the two, so it explains the headline figure.",
    },
    "heatmap": {
        "title": "Which months saw the biggest changes?",
        "short": "Red means prices were up, blue down, grey little change. Hover over a square for its value.",
        "type": "Heat map · distribution across categories and months",
        "read": "Each square is one category in one month. Red means prices were up, blue down, "
                "grey about the same. Hover over a square to see its value.",
        "why": "A heat map shows many months and categories at once, so patterns such as a seasonal rise "
               "or one unusual month stand out. Brief F3: distribution.",
    },
}

_SMALL = {"and", "or", "of", "for", "the", "to", "in", "on", "by", "with", "a", "an"}


def display_name(name: str) -> str:
    """Tidier label for the screen: 'Actual Rentals For Housing*' -> 'Actual rentals for housing'.

    Presentation only; the stored labels are unchanged.
    """
    text = re.sub(r"\s*\((nd|sd|d|s)\)\s*$", "", str(name), flags=re.I).rstrip("*").strip()
    words = text.split()
    out = [words[0]] if words else []
    for w in words[1:]:
        out.append(w.lower() if w.lower().strip(",") in _SMALL else w)
    return " ".join(out)


def month(p) -> str:
    return f"{pd.Timestamp(p):%B %Y}"


def fmt_value(value, measure: str) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.1f}" if measure == "index" else f"{value:+.1f}%"


def direction(value, measure: str = "yoy") -> tuple[str, str]:
    """('up' | 'down' | 'flat', arrow) for a change; for the index, relative to 100."""
    if value is None or pd.isna(value):
        return "na", "–"
    v = value - 100 if measure == "index" else value
    if abs(v) < 0.05:
        return "flat", "■"
    return ("up", "▲") if v > 0 else ("down", "▼")


def sentence(fig: A.Figure | None, measure: str) -> str:
    """What one figure means, in one plain sentence."""
    if fig is None or fig.value is None or pd.isna(fig.value):
        return "Not available for this month and households."
    v, now = fig.value, month(fig.period)
    if measure == "index":
        diff = v - 100
        if abs(diff) < 0.05:
            return f"Prices in {now} were the same as in {BASE_LABEL}."
        return f"Prices in {now} were {abs(diff):.1f}% {'higher' if diff > 0 else 'lower'} than in {BASE_LABEL} (= 100)."
    then = month(fig.compared_with) if fig.compared_with else BASE_LABEL
    if abs(v) < 0.05:
        return f"Prices did not change between {then} and {now}."
    word = "rose" if v > 0 else "fell"
    return f"Prices {word} {abs(v):.1f}% between {then} and {now}."


def period_sentence(pct, start, end) -> str:
    if pct is None or start is None:
        return "Choose a longer period to see the change over it."
    if abs(pct) < 0.05:
        return f"No change from {month(start)} to {month(end)}."
    return f"Prices {'rose' if pct > 0 else 'fell'} {abs(pct):.1f}% from {month(start)} to {month(end)}."


def key_findings(cpi: pd.DataFrame, weights: pd.DataFrame | None, f: A.Filters,
                 flagged_codes: set[str] | None = None) -> list[str]:
    """Three to four plain sentences about the current selection (they follow every filter)."""
    return [text for _, text in key_findings_tagged(cpi, weights, f, flagged_codes)]


def key_findings_tagged(cpi: pd.DataFrame, weights: pd.DataFrame | None, f: A.Filters,
                        flagged_codes: set[str] | None = None) -> list[tuple[str, str]]:
    """Findings with a kind ('overall', 'up', 'down', 'driver') so the page can give each an icon.

    Categories whose figures use a flagged source value get a ⚠ after their number.
    """
    warn = (lambda code: " ⚠" if code in (flagged_codes or set()) else "")
    m = "yoy" if f.measure == "index" else f.measure
    than = {"yoy": "than a year earlier", "mom": "than the month before", "base": f"than in {BASE_LABEL}"}[m]
    short = MEASURES[m]["short"]
    end, out = month(f.end), []
    pop = {"National": "all households", "Bahraini": "Bahraini households",
           "Non-Bahraini": "non-Bahraini households"}[f.population]
    try:
        h = A.change(cpi, config.HEADLINE_CODE, f.end, m, f.population)
        if abs(h.value) < 0.05:
            out.append(("overall", f"In {end}, overall prices for {pop} were **about the same** {than}."))
        else:
            word = "higher" if h.value > 0 else "lower"
            out.append(("overall", f"In {end}, overall prices for {pop} were **{abs(h.value):.1f}% {word}**"
                                   f"{warn(config.HEADLINE_CODE)} {than}."))
    except A.DataUnavailable:
        pass
    selected = [c for c in f.codes if c != config.HEADLINE_CODE]
    if selected:
        t = A.compare_categories(cpi, f.end, m, codes=selected, population=f.population).dropna(subset=["value"])
        if len(t) == 1:
            one = t.iloc[0]
            out.append(("up" if one["value"] >= 0 else "down",
                        f"Your selected category, **{display_name(one['name'])}**, changed by "
                        f"**{one['value']:+.1f}%**{warn(one['code'])} {short}."))
        elif len(t) >= 2:
            top = t.iloc[0]
            verb = ("rose the most" if top["value"] > 0.05 else
                    "did not change" if abs(top["value"]) < 0.05 else "fell the least")
            out.append(("up", f"Of your selected categories, **{display_name(top['name'])}** {verb}: "
                              f"**{top['value']:+.1f}%**{warn(top['code'])} {short}."))
        if len(t) >= 2:
            low = t.iloc[-1]
            verb = "fell the most" if low["value"] < -0.05 else "rose the least"
            out.append(("down", f"**{display_name(low['name'])}** {verb}: **{low['value']:+.1f}%**"
                                f"{warn(low['code'])} {short}."))
    if weights is not None:
        try:
            c = A.contributions(cpi, weights, f.end).dropna(subset=["contribution_pts"])
            if len(c):
                top = c.sort_values("contribution_pts", ascending=False).iloc[0]
                out.append(("driver", f"Nationally, **{display_name(top['name'])}** added the most to the "
                                      f"yearly change in overall prices ({top['contribution_pts']:+.2f} percentage "
                                      f"points of {c.attrs['headline_yoy']:+.1f}%)."))
        except A.DataUnavailable:
            pass
    return out


def priority_reasons(row: pd.Series, rules: dict) -> str:
    """Why a division is on the watch list, in plain words."""
    parts = []
    if row.get("flag_rising_fastest"):
        parts.append(f"among the {rules['rising_fastest_top_n']} fastest rising ({row['yoy']:+.1f}% in a year)")
    if row.get("flag_far_from_base"):
        parts.append(f"among the {rules['furthest_from_base_top_n']} furthest from April 2019 ({row['base']:+.1f}%)")
    if row.get("flag_large_weight"):
        parts.append(f"a large share of spending ({row['weight']:.1f}%)")
    if row.get("flag_nationality_gap"):
        gap = row["gap_bh_minus_nonbh"]
        who = "Bahraini" if gap > 0 else "non-Bahraini"
        parts.append(f"a gap between households: {abs(gap):.1f} points higher yearly change for {who}")
    if not parts:
        return "No criterion met"
    text = "; ".join(parts)
    return text[0].upper() + text[1:]
