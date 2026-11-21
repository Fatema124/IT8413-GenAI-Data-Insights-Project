"""Check the prepared data against the proposal's ground-truth answers.

    python -m scripts.check_dev_answers

Every DEVELOPMENT question that uses the datasets is checked: 8, 10, 12, 13,
21, 23, 26, 28, 30 (answers) and 16, 19, 20 (must be declined). The other
development questions (2, 4, 6, 25) are answered from the documents only.
The 15 held-out questions are deliberately left out: the proposal and the
brief (7.1) say they must not be run or used to guide changes before the
final evaluation.

Tolerances follow proposal Section 3: index values to 1 d.p. (+/-0.05) and
percentage changes +/-0.1.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from src.pipeline import analytics as A
from src.pipeline import config
from src.pipeline.run import PreparedData, build, load_prepared

IDX, PCT = 0.05, config.GROUND_TRUTH_TOLERANCE


@dataclass
class Check:
    question: int
    what: str
    compute: Callable[[PreparedData], float | str]
    expected: float | str
    tol: float = 0.0


def _idx(code, period, pop=config.NATIONAL):
    return lambda d: A.index_value(d.cpi, code, period, pop)


def _chg(code, period, measure, pop=config.NATIONAL):
    return lambda d: A.change(d.cpi, code, period, measure, pop).value


def _largest_weight(d):
    w = d.weights[d.weights["level"] == 1]
    return w.loc[w["weight"].idxmax(), "code"]


def _prev(code, period, measure, pop=config.NATIONAL):
    """The stored index the change was computed from (shown in the answer)."""
    return lambda d: A.change(d.cpi, code, period, measure, pop).previous_index


def _declined(fn):
    """'yes' if the sources do not hold the value (the tool must decline, F7)."""
    def f(d):
        try:
            fn(d)
            return "no - a value was returned"
        except A.DataUnavailable:
            return "yes"
    return f


def _flat_since(code, start, end, value):
    def f(d):
        s = A.series(d.cpi, code).loc[start:end]
        return "yes" if len(s) and (s.round(1) == value).all() else f"no ({s.round(1).unique()[:4]})"
    return f


CHECKS = [
    Check(8, "04.5 Jul 2026 index (MoM compared with)", _prev("04.5", "2026-08", "mom"), 83.8, IDX),
    Check(8, "04.5 Aug 2025 index (YoY compared with)", _prev("04.5", "2026-08", "yoy"), 76.02, 0.005),
    Check(8, "04.5 Aug 2026 month-on-month %", _chg("04.5", "2026-08", "mom"), 6.3, PCT),
    Check(8, "04.5 Aug 2026 year-on-year %", _chg("04.5", "2026-08", "yoy"), 17.2, PCT),
    Check(8, "04.5 Aug 2026 index", _idx("04.5", "2026-08"), 89.1, IDX),
    Check(8, "04.5 Aug 2026 vs base %", _chg("04.5", "2026-08", "base"), -10.9, PCT),
    Check(10, "Division with largest weight", _largest_weight, "04"),
    Check(10, "Weight of division 04 (%)", lambda d: A.weight_of(d.weights, "04"), 25.02, 0.005),
    Check(10, "04 Aug 2026 index", _idx("04", "2026-08"), 88.9, IDX),
    Check(10, "04 Aug 2025 index", _idx("04", "2025-08"), 89.93, 0.005),
    Check(10, "04 Aug 2026 year-on-year %", _chg("04", "2026-08", "yoy"), -1.1, PCT),
    Check(12, "10 Aug 2025 index", _idx("10", "2025-08"), 108.41, 0.005),
    Check(12, "10 Sep 2025 month-on-month %", _chg("10", "2025-09", "mom"), 2.8, PCT),
    Check(12, "10 flat at 111.4 Sep 2025 - Aug 2026", _flat_since("10", "2025-09", "2026-08", 111.4), "yes"),
    Check(13, "11 Aug 2026 national index", _idx("11", "2026-08"), 115.0, IDX),
    Check(13, "11 Aug 2026 Bahraini index", _idx("11", "2026-08", "Bahraini"), 119.6, IDX),
    Check(13, "11 Aug 2026 non-Bahraini index", _idx("11", "2026-08", "Non-Bahraini"), 101.6, IDX),
    Check(13, "Bahraini minus non-Bahraini (points)",
          lambda d: A.index_value(d.cpi, "11", "2026-08", "Bahraini") - A.index_value(d.cpi, "11", "2026-08", "Non-Bahraini"),
          18.0, IDX),
    Check(13, "National figure lies between the two",
          lambda d: "yes" if A.index_value(d.cpi, "11", "2026-08", "Non-Bahraini") < A.index_value(d.cpi, "11", "2026-08")
          < A.index_value(d.cpi, "11", "2026-08", "Bahraini") else "no", "yes"),
    Check(16, "Declined: no governorate figures (Muharraq)",
          _declined(lambda d: A.index_value(d.cpi, "0", "2026-08", "Muharraq Governorate")), "yes"),
    Check(19, "Declined: data are index numbers, no shop prices",
          lambda d: "yes" if not any("price" in c.lower() for c in d.cpi.columns)
          and set(d.cpi["population"]) <= set(config.POPULATIONS) else "no", "yes"),
    Check(20, "Declined: no headline CPI for Dec 2009",
          _declined(lambda d: A.index_value(d.cpi, "0", "2009-12")), "yes"),
    Check(20, "Earliest headline month in the sources",
          lambda d: f"{A.series(d.cpi, '0').dropna().index.min():%Y-%m}", "2011-01"),
    Check(21, "Headline annual average 2019", lambda d: A.annual_average(d.cpi, "0", 2019)["annual_average"], 99.9, IDX),
    Check(21, "Headline annual average 2021", lambda d: A.annual_average(d.cpi, "0", 2021)["annual_average"], 97.0, IDX),
    Check(21, "Change 2019 -> 2021 annual average %",
          lambda d: A.compare_annual_averages(d.cpi, "0", 2019, 2021)["change_pct"], -2.9, PCT),
    Check(23, "03 Aug 2026 index", _idx("03", "2026-08"), 64.5, IDX),
    Check(23, "03 Aug 2026 vs base %", _chg("03", "2026-08", "base"), -35.5, PCT),
    Check(26, "Headline Mar 2026 index", _idx("0", "2026-03"), 102.4, IDX),
    Check(28, "01.1.2 Meat Aug 2026 index", _idx("01.1.2", "2026-08"), 137.5, IDX),
    Check(30, "Weight of division 07 (%)", lambda d: A.weight_of(d.weights, "07"), 17.84, 0.005),
]


def run(data: PreparedData, verbose: bool = True) -> list[dict]:
    results = []
    for c in CHECKS:
        try:
            got = c.compute(data)
            ok = (abs(got - c.expected) <= c.tol + 1e-9) if isinstance(c.expected, float) else got == c.expected
        except Exception as exc:  # a missing value is a failed check, not a crash
            got, ok = f"error: {exc}", False
        results.append({"question": c.question, "check": c.what, "expected": c.expected,
                        "got": round(got, 4) if isinstance(got, float) else got, "pass": ok})
        if verbose:
            shown = f"{got:.3f}" if isinstance(got, float) else got
            print(f"{'PASS' if ok else 'FAIL'}  Q{c.question:<3} {c.what:<42} expected {c.expected!s:<7} got {shown}")
    return results


def main() -> int:
    try:
        data = load_prepared()
    except FileNotFoundError:
        data = build()
    results = run(data)
    failed = [r for r in results if not r["pass"]]
    covered = sorted({c.question for c in CHECKS})
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed, covering development questions "
          f"{', '.join(map(str, covered))} (held-out set not run).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
