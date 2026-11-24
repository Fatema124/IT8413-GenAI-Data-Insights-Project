"""Tools the model calls for questions over the data (F4, F6): a safe layer over analytics.

The model (Gemini 3.5 Flash-Lite, proposal Section 5) never computes a number
itself. It calls these tools and quotes what they return, so every figure in
an answer comes from the stored data. This layer sits between the model and
src/pipeline/analytics.py and does three jobs:

1. It accepts what users actually type. "transport", "4.5", "non bahraini",
   "August 2026" and "latest" are resolved to the exact code, household and
   month before anything is computed.
2. It returns plain JSON. Every result is a dict of str / int / float / bool /
   None / list, so it can go straight back to the model (no DataFrames, no NaN).
3. It says WHY something failed, because the right reaction differs:
     status "ok"             the answer, with the stored values it used
     status "not_available"  the sources do not hold it -> the app declines (F7)
     status "bad_input"      the request was unclear (e.g. "last month") ->
                             fix the argument or ask the user; never a refusal
     status "error"          a bug; log it, never present it as an answer

Usage (question-answering code, F4):

    from src.pipeline.tools import Toolbox, TOOL_DECLARATIONS
    tools = Toolbox(prepared_data)                      # PreparedData from run.py
    tools.call("get_change", {"category": "transport", "month": "2026-08", "measure": "yoy"})

TOOL_DECLARATIONS describes every tool (name, description, JSON-schema
parameters) in the form function-calling APIs expect.
"""
from __future__ import annotations

import inspect
import json
import math
import re
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import analytics as A
from . import config, labels

OK, NOT_AVAILABLE, BAD_INPUT, ERROR = "ok", "not_available", "bad_input", "error"
LATEST = pd.Timestamp(config.DATA_END + "-01")


class BadInput(ValueError):
    """The request could not be understood; the model should fix it, not refuse."""


class NotInSources(LookupError):
    """The sources do not cover what was asked (for example a governorate)."""


# --------------------------------------------------------------------------
# Resolving loose input
# --------------------------------------------------------------------------
_HEADLINE_WORDS = {"0", "00", "headline", "headline cpi", "all items", "all-items", "cpi", "overall",
                   "general", "general index", "total", "consumer price index", "all"}
_HOUSEHOLDS = {
    "national": config.NATIONAL, "all": config.NATIONAL, "all households": config.NATIONAL,
    "overall": config.NATIONAL, "total": config.NATIONAL, "bahrain": config.NATIONAL, "kingdom": config.NATIONAL,
    "bahraini": "Bahraini", "bahrainis": "Bahraini", "citizens": "Bahraini", "bahraini households": "Bahraini",
    "non-bahraini": "Non-Bahraini", "non bahraini": "Non-Bahraini", "nonbahraini": "Non-Bahraini",
    "non-bahrainis": "Non-Bahraini", "non bahrainis": "Non-Bahraini", "expat": "Non-Bahraini",
    "expats": "Non-Bahraini", "expatriate": "Non-Bahraini", "expatriates": "Non-Bahraini",
    "foreigners": "Non-Bahraini", "non-citizens": "Non-Bahraini", "non citizens": "Non-Bahraini",
}
_MEASURES = {
    "mom": "mom", "month-on-month": "mom", "month on month": "mom", "monthly": "mom", "monthly change": "mom",
    "1 month": "mom", "1-month": "mom", "one month": "mom",
    "yoy": "yoy", "year-on-year": "yoy", "year on year": "yoy", "annual": "yoy", "annual change": "yoy",
    "12 months": "yoy", "12-month": "yoy", "12 month": "yoy", "yearly": "yoy", "inflation": "yoy",
    "base": "base", "since base": "base", "since april 2019": "base", "since 2019": "base",
    "vs base": "base", "change since base": "base", "cumulative": "base",
    "index": "index", "level": "index", "index level": "index", "value": "index",
}
_LATEST_WORDS = {"latest", "latest month", "most recent", "last available", "current", "now", "newest"}
_RELATIVE = re.compile(r"\b(last|this|next|previous|ago|today|yesterday|recent months?)\b", re.I)


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower().replace("&", "and")


def resolve_household(text) -> str:
    key = _norm(text).replace(" households", "").replace(" household", "")
    if key in ("", "none"):
        return config.NATIONAL
    if key in _HOUSEHOLDS:
        return _HOUSEHOLDS[key]
    raise NotInSources(
        f"The sources give the CPI for national, Bahraini and non-Bahraini households only; "
        f"there are no figures for '{text}' (for example by governorate, city or income group).")


def resolve_measure(text) -> str:
    key = _norm(text) or "yoy"
    if key in _MEASURES:
        return _MEASURES[key]
    raise BadInput(f"Unknown measure '{text}'. Use one of: index, mom (month-on-month), "
                   "yoy (year-on-year), base (change since April 2019).")


def resolve_month(text) -> pd.Timestamp:
    """'2026-08', '2026/8', '08/2026', 'Aug 2026', 'August 2026', '2026 August', 'latest'."""
    if isinstance(text, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(text).to_period("M").to_timestamp()
    raw = str(text or "").strip()
    key = _norm(raw)
    if key in _LATEST_WORDS:
        return LATEST
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?", key)
    if m:
        return _month(int(m.group(1)), int(m.group(2)), raw)
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", key)
    if m:
        return _month(int(m.group(2)), int(m.group(1)), raw)
    m = re.fullmatch(r"([a-z]+)\.?,? (\d{4})", key) or re.fullmatch(r"(\d{4}),? ([a-z]+)\.?", key)
    if m:
        a, b = m.groups()
        name, year = (a, b) if a.isalpha() else (b, a)
        for fmt in ("%B", "%b"):
            try:
                return _month(int(year), datetime.strptime(name[:3] if fmt == "%b" else name, fmt).month, raw)
            except ValueError:
                continue
    if _RELATIVE.search(key):
        raise BadInput(f"'{raw}' is relative. Give a calendar month such as {LATEST:%Y-%m}; "
                       f"the latest month in the data is {LATEST:%B %Y}.")
    raise BadInput(f"Could not read the month '{raw}'. Use the form YYYY-MM, for example {LATEST:%Y-%m}.")


def _month(year: int, month: int, raw: str) -> pd.Timestamp:
    if not 1 <= month <= 12:
        raise BadInput(f"'{raw}' has no valid month number.")
    return pd.Timestamp(year=year, month=month, day=1)


def resolve_year(text) -> int:
    m = re.fullmatch(r"\s*(\d{4})\s*", str(text))
    if not m:
        raise BadInput(f"Could not read the year '{text}'. Use four digits, for example 2025.")
    return int(m.group(1))


# --------------------------------------------------------------------------
# JSON helpers
# --------------------------------------------------------------------------
def to_json(obj):
    """Recursively convert to JSON-safe Python types (NaN -> None, months -> 'YYYY-MM')."""
    if isinstance(obj, dict):
        return {str(k): to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return [to_json(r) for r in obj.to_dict("records")]
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return f"{pd.Timestamp(obj):%Y-%m}"
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(float(obj)) or math.isinf(float(obj)) else round(float(obj), 4)
    if obj is None or isinstance(obj, (str, int)):
        return obj
    if obj is pd.NaT:
        return None
    return str(obj)


# --------------------------------------------------------------------------
# The toolbox
# --------------------------------------------------------------------------
class Toolbox:
    """All model tools over one prepared dataset. `call` never raises."""

    def __init__(self, data):
        self.data = data
        self.cpi = data.cpi
        self.weights = data.weights
        self.labels = data.labels
        disc = getattr(data, "discrepancies", None)
        self._flagged = set()
        if disc is not None and len(disc):
            self._flagged = {(r.code, r.population, f"{pd.Timestamp(r.period):%Y-%m}")
                             for r in disc.itertuples()}
        self._tools = {
            "list_categories": self.list_categories,
            "data_coverage": self.data_coverage,
            "get_index": self.get_index,
            "get_change": self.get_change,
            "get_series": self.get_series,
            "get_annual_average": self.get_annual_average,
            "compare_annual_averages": self.compare_annual_averages,
            "compare_households": self.compare_households,
            "rank_categories": self.rank_categories,
            "get_weight": self.get_weight,
            "get_contributions": self.get_contributions,
            "get_priorities": self.get_priorities,
        }

    # ---------------------------------------------------------------- dispatch
    def call(self, name: str, args: dict | None = None) -> dict:
        """Run one tool by name. Always returns a JSON-safe dict with a 'status'."""
        args = dict(args or {})
        fn = self._tools.get(name)
        if fn is None:
            return {"status": BAD_INPUT, "tool": name, "message": f"Unknown tool '{name}'.",
                    "available_tools": sorted(self._tools)}
        try:
            inspect.signature(fn).bind(**args)
        except TypeError as exc:                    # unknown or missing argument names
            return to_json({"status": BAD_INPUT, "tool": name, "message": f"Wrong arguments: {exc}",
                            "arguments": args})
        try:
            out = fn(**args)
            result = {"status": OK, "tool": name, **out}
        except BadInput as exc:
            result = {"status": BAD_INPUT, "tool": name, "message": str(exc)}
        except (NotInSources, A.DataUnavailable) as exc:
            result = {"status": NOT_AVAILABLE, "tool": name, "message": str(exc)}
        except Exception as exc:                    # a bug: report it, never an answer
            result = {"status": ERROR, "tool": name, "message": f"{exc.__class__.__name__}: {exc}"}
        result["arguments"] = args
        return to_json(result)

    def call_json(self, name: str, args: dict | None = None) -> str:
        return json.dumps(self.call(name, args), ensure_ascii=False, allow_nan=False)

    # ---------------------------------------------------------------- resolving
    def resolve_category(self, text) -> tuple[str, str, list[dict]]:
        """(code, how it was matched, other close matches)."""
        lab = self.labels
        raw = str(text or "").strip()
        key = _norm(raw)
        if not key:
            raise BadInput("No category given. Use a code such as 07 or a name such as 'Transport'.")
        if key in _HEADLINE_WORDS:
            return config.HEADLINE_CODE, "headline", []
        if re.fullmatch(r"\d+(\.\d+)*", key):
            code = labels.normalise_code(key)
            if code in set(lab["code"]):
                return code, "code", []
            raise BadInput(f"No category has the code '{raw}'. Divisions are 01-12; "
                           "call list_categories to see every code.")
        names = lab.assign(_n=lab["name"].map(_norm))
        exact = names[names["_n"] == key].sort_values("level")
        contains = names[names["_n"].str.contains(re.escape(key), regex=True)].sort_values(["level", "code"])
        others = [{"code": r.code, "name": r.name} for r in contains.itertuples()][:8]
        if len(exact):
            code = exact.iloc[0]["code"]
            return code, "name", [o for o in others if o["code"] != code]
        divisions = contains[contains["level"] == 1]
        if len(divisions) == 1:
            code = divisions.iloc[0]["code"]
            return code, "name contains", [o for o in others if o["code"] != code]
        if len(contains) == 1:
            return contains.iloc[0]["code"], "name contains", []
        if len(contains) > 1:
            raise BadInput(f"'{raw}' matches several categories; pick one by code: "
                           + "; ".join(f"{o['code']} {o['name']}" for o in others))
        raise BadInput(f"No category matches '{raw}'. Call list_categories to see every name and code.")

    def _category(self, text) -> dict:
        code, how, others = self.resolve_category(text)
        out = {"code": code, "name": A.name_of(self.cpi, code), "matched_by": how}
        if others:
            out["other_matches"] = others
        return out

    def _caution(self, code: str, population: str, periods) -> str | None:
        hits = sorted(p for p in periods if p and (code, population, p) in self._flagged)
        if not hits:
            return None
        return (f"Dataset 2 value(s) used here ({', '.join(hits)}) differ from iGA's own published Table 3; "
                "the result may be wrong. Say so in the answer.")

    def _figure(self, fig: A.Figure, category: dict) -> dict:
        out = fig.to_dict()
        if category.get("other_matches"):
            out["other_matches"] = category["other_matches"]
        out["matched_by"] = category["matched_by"]
        caution = self._caution(fig.code, fig.population, [fig.period, fig.compared_with])
        if caution:
            out["caution"] = caution
        if "derived" in out.get("sources", ""):
            out["derived_note"] = ("2010 values are derived from iGA Table 1's 12-month changes; "
                                   "they are not published index levels.")
        return out

    # ---------------------------------------------------------------- tools
    def list_categories(self, level: int | None = None, household: str | None = None,
                        search: str | None = None) -> dict:
        lab = self.labels.copy()
        if level is not None:
            lab = lab[lab["level"] == int(level)]
        if household:
            pop = resolve_household(household)
            lab = lab[lab["populations"].str.split(", ").apply(lambda ps: pop in ps)]
        if search:
            lab = lab[lab["name"].map(_norm).str.contains(re.escape(_norm(search)))]
        cols = [c for c in ["code", "name", "level", "first_month", "last_month", "populations", "weight"]
                if c in lab.columns]
        return {"count": len(lab), "categories": lab[cols],
                "levels": {"0": "headline", "1": "division", "2": "group", "3": "sub-group / item"}}

    def data_coverage(self) -> dict:
        cpi = self.cpi
        pops = {}
        for pop in config.POPULATIONS:
            s = cpi[(cpi["population"] == pop) & cpi["index"].notna()]
            if len(s):
                pops[pop] = {"first_month": s["period"].min(), "last_month": s["period"].max(),
                             "categories": int(s["code"].nunique())}
        divisions_from = cpi[(cpi["population"] == config.NATIONAL) & (cpi["level"] > 0)]["period"].min()
        return {"households": pops, "divisions_and_groups_from": divisions_from,
                "base": "April 2019 = 100", "working_copy_ends": LATEST,
                "derived": "2010 headline values are derived from iGA Table 1's 12-month changes.",
                "not_in_sources": ["forecasts", "prices at named shops or of single products",
                                   "figures by governorate or city", "explanations of price movements"],
                "flagged_values": len(self._flagged),
                "note": config.OWN_ANALYSIS_NOTE}

    def get_index(self, category, month, household: str | None = None) -> dict:
        cat, pop, p = self._category(category), resolve_household(household), resolve_month(month)
        return self._figure(A.change(self.cpi, cat["code"], p, "index", pop), cat)

    def get_change(self, category, month, measure: str = "yoy", household: str | None = None) -> dict:
        cat, pop, p = self._category(category), resolve_household(household), resolve_month(month)
        return self._figure(A.change(self.cpi, cat["code"], p, resolve_measure(measure), pop), cat)

    def get_series(self, category, start_month, end_month, measure: str = "index",
                   household: str | None = None) -> dict:
        cat, pop = self._category(category), resolve_household(household)
        start, end, m = resolve_month(start_month), resolve_month(end_month), resolve_measure(measure)
        if start > end:
            start, end = end, start
        s = A.change_series(self.cpi, cat["code"], m, pop)
        s = s[(s.index >= start) & (s.index <= end)]
        if s.dropna().empty:
            raise A.DataUnavailable(f"No {pop} values for {cat['code']} between {start:%b %Y} and {end:%b %Y}.")
        points = [{"month": p, "value": v} for p, v in s.items()]
        flagged = [p["month"] for p in points if (cat["code"], pop, f"{p['month']:%Y-%m}") in self._flagged]
        out = {**cat, "population": pop, "measure": m, "unit": config.INDEX_UNIT if m == "index" else "%",
               "points": points[:240], "highest": {"month": s.idxmax(), "value": s.max()},
               "lowest": {"month": s.idxmin(), "value": s.min()},
               "missing_months": int(s.isna().sum()), "sources": A._source_of(self.cpi, cat["code"], pop, s.index),
               "note": config.OWN_ANALYSIS_NOTE}
        if flagged:
            out["caution"] = self._caution(cat["code"], pop, [f"{p:%Y-%m}" for p in flagged])
        return out

    def get_annual_average(self, category, year, household: str | None = None) -> dict:
        cat, pop = self._category(category), resolve_household(household)
        return {**A.annual_average(self.cpi, cat["code"], resolve_year(year), pop), "matched_by": cat["matched_by"]}

    def compare_annual_averages(self, category, year_a, year_b, household: str | None = None) -> dict:
        cat, pop = self._category(category), resolve_household(household)
        return {**A.compare_annual_averages(self.cpi, cat["code"], resolve_year(year_a), resolve_year(year_b), pop),
                "matched_by": cat["matched_by"]}

    def compare_households(self, category, month, measure: str = "yoy") -> dict:
        cat, p, m = self._category(category), resolve_month(month), resolve_measure(measure)
        rows = []
        for pop in config.POPULATIONS:
            try:
                rows.append(self._figure(A.change(self.cpi, cat["code"], p, m, pop), cat))
            except A.DataUnavailable as exc:
                rows.append({"population": pop, "status": NOT_AVAILABLE, "message": str(exc)})
        if all(r.get("status") == NOT_AVAILABLE for r in rows):
            raise A.DataUnavailable(rows[0]["message"])
        return {**cat, "month": p, "measure": m, "households": rows}

    def rank_categories(self, month, measure: str = "yoy", level: int = 1, household: str | None = None) -> dict:
        p, m, pop = resolve_month(month), resolve_measure(measure), resolve_household(household)
        t = A.compare_categories(self.cpi, p, m, level=int(level), population=pop)
        t = t.dropna(subset=["value"]) if "value" in t else t
        if t.empty:
            raise A.DataUnavailable(f"No {pop} values at level {level} for {p:%B %Y}.")
        keep = [c for c in ["code", "name", "value", "display", "current_index", "previous_index",
                            "compared_with", "sources"] if c in t.columns]
        return {"month": p, "measure": m, "population": pop, "level": int(level), "ranking": t[keep],
                "note": config.OWN_ANALYSIS_NOTE}

    def get_weight(self, category) -> dict:
        cat = self._category(category)
        w = A.weight_of(self.weights, cat["code"])
        return {**cat, "weight": w, "unit": config.WEIGHT_UNIT,
                "source": "Dataset 3 (iGA Table 2.01, expenditure weights)",
                "note": "iGA publishes one national basket; there are no weights by month or by nationality."}

    def get_contributions(self, month) -> dict:
        if self.weights is None:
            raise A.DataUnavailable("Expenditure weights (Dataset 3) are not loaded.")
        p = resolve_month(month)
        t = A.contributions(self.cpi, self.weights, p)
        return {"month": p, "headline_yoy": t.attrs["headline_yoy"],
                "sum_of_contributions": t.attrs["sum_of_contributions"], "unit": "percentage points",
                "contributions": t[["code", "name", "weight", "contribution_pts"]],
                "method": "weight x (index now - index a year ago) / headline a year ago; an approximation",
                "note": config.OWN_ANALYSIS_NOTE}

    def get_priorities(self, month, household: str | None = None) -> dict:
        p, pop = resolve_month(month), resolve_household(household)
        t = A.priority_table(self.cpi, self.weights, p, population=pop)
        gap_months = {f"{p:%Y-%m}", f"{p - pd.DateOffset(months=12):%Y-%m}"}
        flagged = sorted({c for (c, pp, m) in self._flagged if m in gap_months and pp != config.NATIONAL})
        out = {"month": p, "population": pop, "rules": t.attrs["rules"], "divisions": t,
               "note": "The table shows evidence on the proposal's four criteria; analysts decide."}
        if flagged:
            out["caution"] = (f"The nationality-gap criterion uses Dataset 2 values that differ from iGA's "
                              f"Table 3 for divisions {', '.join(flagged)}.")
        return out


# --------------------------------------------------------------------------
# Declarations for function calling
# --------------------------------------------------------------------------
_CAT = {"type": "string", "description": "Category code (e.g. '07', '04.5') or name (e.g. 'Transport'). "
                                         "'headline' or '0' means All items."}
_MONTH = {"type": "string", "description": "Calendar month as YYYY-MM (e.g. '2026-08'), or 'latest'."}
_HOUSEHOLD = {"type": "string", "description": "'National' (default), 'Bahraini' or 'Non-Bahraini'.",
              "enum": list(config.POPULATIONS)}
_MEASURE = {"type": "string", "enum": ["index", "mom", "yoy", "base"],
            "description": "index = level (April 2019 = 100); mom = month-on-month %; "
                           "yoy = year-on-year %; base = % change since April 2019."}


def _decl(name, description, properties, required):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}


TOOL_DECLARATIONS = [
    _decl("list_categories", "List CPI categories with codes, levels, coverage and weights. Use it to find a code.",
          {"level": {"type": "integer", "description": "0 headline, 1 division, 2 group, 3 sub-group"},
           "household": _HOUSEHOLD, "search": {"type": "string", "description": "Words in the category name"}}, []),
    _decl("data_coverage", "What the data covers: months per household, base period, what is not in the sources.",
          {}, []),
    _decl("get_index", "Index level of one category for one month (April 2019 = 100).",
          {"category": _CAT, "month": _MONTH, "household": _HOUSEHOLD}, ["category", "month"]),
    _decl("get_change", "Month-on-month, year-on-year or since-April-2019 % change, with the two stored values used.",
          {"category": _CAT, "month": _MONTH, "measure": _MEASURE, "household": _HOUSEHOLD},
          ["category", "month", "measure"]),
    _decl("get_series", "Monthly values between two months, with the highest and lowest month.",
          {"category": _CAT, "start_month": _MONTH, "end_month": _MONTH, "measure": _MEASURE,
           "household": _HOUSEHOLD}, ["category", "start_month", "end_month"]),
    _decl("get_annual_average", "Average of the 12 monthly index values of one year (declines if a month is missing).",
          {"category": _CAT, "year": {"type": "integer"}, "household": _HOUSEHOLD}, ["category", "year"]),
    _decl("compare_annual_averages", "% change between two years' annual average index.",
          {"category": _CAT, "year_a": {"type": "integer"}, "year_b": {"type": "integer"}, "household": _HOUSEHOLD},
          ["category", "year_a", "year_b"]),
    _decl("compare_households", "National, Bahraini and non-Bahraini values side by side for one category and month.",
          {"category": _CAT, "month": _MONTH, "measure": _MEASURE}, ["category", "month"]),
    _decl("rank_categories", "Rank all categories of one level by a measure for one month (largest first).",
          {"month": _MONTH, "measure": _MEASURE, "level": {"type": "integer", "description": "1 = divisions"},
           "household": _HOUSEHOLD}, ["month", "measure"]),
    _decl("get_weight", "Share of household spending (expenditure weight, %) of a division or group, iGA Table 2.01.",
          {"category": _CAT}, ["category"]),
    _decl("get_contributions", "How much each division added to headline year-on-year inflation (percentage points).",
          {"month": _MONTH}, ["month"]),
    _decl("get_priorities", "The proposal's four monitoring criteria for all 12 divisions in one month.",
          {"month": _MONTH, "household": _HOUSEHOLD}, ["month"]),
]
