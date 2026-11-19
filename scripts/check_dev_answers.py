"""Check the prepared data against the proposal's ground-truth answers.

    python -m scripts.check_dev_answers

Only DEVELOPMENT-set questions are checked. Held-out questions
(9, 11, 14, 22, 24, 27, 29, 31 among the data questions) are deliberately
left out: the brief (7.1) says the held-out set must not be run or used to
guide changes before the final evaluation.

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


def _flat_since(code, start, end, value):
    def f(d):
        s = A.series(d.cpi, code).loc[start:end]
        return "yes" if len(s) and (s.round(1) == value).all() else f"no ({s.round(1).unique()[:4]})"
    return f


CHECKS = [
    Check(8, "04.5 Aug 2026 month-on-month %", _chg("04.5", "2026-08", "mom"), 6.3, PCT),
    Check(8, "04.5 Aug 2026 year-on-year %", _chg("04.5", "2026-08", "yoy"), 17.2, PCT),
    Check(8, "04.5 Aug 2026 index", _idx("04.5", "2026-08"), 89.1, IDX),
    Check(8, "04.5 Aug 2026 vs base %", _chg("04.5", "2026-08", "base"), -10.9, PCT),
    Check(10, "Division with largest weight", _largest_weight, "04"),
    Check(10, "Weight of division 04 (%)", lambda d: A.weight_of(d.weights, "04"), 25.02, 0.005),
    Check(10, "04 Aug 2026 year-on-year %", _chg("04", "2026-08", "yoy"), -1.1, PCT),
    Check(12, "10 Sep 2025 month-on-month %", _chg("10", "2025-09", "mom"), 2.8, PCT),
    Check(12, "10 flat at 111.4 Sep 2025 - Aug 2026", _flat_since("10", "2025-09", "2026-08", 111.4), "yes"),
    Check(13, "11 Aug 2026 national index", _idx("11", "2026-08"), 115.0, IDX),
    Check(13, "11 Aug 2026 Bahraini index", _idx("11", "2026-08", "Bahraini"), 119.6, IDX),
    Check(13, "11 Aug 2026 non-Bahraini index", _idx("11", "2026-08", "Non-Bahraini"), 101.6, IDX),
    Check(21, "Headline annual average 2019", lambda d: A.annual_average(d.cpi, "0", 2019)["annual_average"], 99.9, IDX),
    Check(21, "Headline annual average 2021", lambda d: A.annual_average(d.cpi, "0", 2021)["annual_average"], 97.0, IDX),
    Check(21, "Change 2019 -> 2021 annual average %",
          lambda d: A.compare_annual_averages(d.cpi, "0", 2019, 2021)["change_pct"], -2.9, PCT),
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
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed (development set only).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
