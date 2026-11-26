"""Check that every number in an answer was produced by code (F4).

The brief (F4): "Any numeric figure that is given in an answer must be
produced by code running over the data." The prompt tells the model this;
this module checks it after the fact. A number in the answer is supported
when it equals, after rounding to the decimals the answer shows, a number
that appears in a tool result (or in the question, or in an earlier turn's
tool results for follow-ups). Signs are ignored, because "fell 1.1%" writes
-1.1 without its minus sign.

Unsupported numbers are not hidden or changed. They are reported, the app
shows a warning beside the answer, and the record keeps them for the
evaluation (a "calculation was wrong" failure, brief 7.4).
"""
from __future__ import annotations

import math
import re
from typing import Iterable

# 1,234.5  12.3  -4  2026  (commas inside numbers allowed; letters glued in front are not, e.g. "v1")
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z0-9.,])\d+(?:\.\d+)?")
# Small whole numbers used as words ("12 months", "3 divisions", "the 2 groups") are not figures,
# unless they are written as a percentage or as points.
_SMALL_WORD_MAX = 12
_FIGURE_AFTER = re.compile(r"\s*(%|per\s*cent|percent|percentage\s+points?|index\s+points?|points?|pts?\b)",
                           re.IGNORECASE)


def _numbers_with_context(text: str):
    """(as written, value, decimals shown, written as a figure such as '3%' or '3 points')."""
    for m in _NUMBER.finditer(text or ""):
        raw = m.group(0)
        clean = raw.replace(",", "")
        decimals = len(clean.split(".")[1]) if "." in clean else 0
        yield raw, float(clean), decimals, bool(_FIGURE_AFTER.match(text, m.end()))


def numbers_in_text(text: str) -> list[tuple[str, float, int]]:
    """Every number written in `text`: (as written, value, decimals shown)."""
    return [(raw, v, d) for raw, v, d, _ in _numbers_with_context(text)]


def numbers_in_result(obj) -> set[float]:
    """Every number inside a tool result: numeric values and numbers written in its strings.

    The "arguments" entry is skipped: it echoes what the model asked for, so it proves nothing.
    """
    found: set[float] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            if not (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
                found.add(abs(float(x)))
        elif isinstance(x, str):
            found.update(abs(v) for _, v, _ in numbers_in_text(x))
        elif isinstance(x, dict):
            for k, v in x.items():
                if k != "arguments":           # what the model sent, not what the code computed
                    walk(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v)

    walk(obj)
    return found


def question_numbers(question: str) -> set[float]:
    """Numbers in the question that may be repeated in the answer: months, years and codes.

    A figure the user wrote ("was inflation 5%?") is not evidence: the answer must get it from a tool.
    """
    return {v for _, v, _, is_figure in _numbers_with_context(question) if not is_figure}


def matches(written: float, decimals: int, known: Iterable[float]) -> bool:
    """True if some known number rounds to `written` at the decimals shown."""
    half = 0.5 * 10 ** (-decimals) + 1e-9
    target = abs(written)
    return any(abs(abs(k) - target) <= half for k in known)


def unsupported_numbers(answer: str, known: Iterable[float]) -> list[str]:
    """Numbers in the answer that no tool result (or question) supports, as written, in order."""
    known = list(known)
    bad = []
    for raw, value, decimals, is_figure in _numbers_with_context(answer):
        if decimals == 0 and value <= _SMALL_WORD_MAX and not is_figure:
            continue
        if not matches(value, decimals, known) and raw not in bad:
            bad.append(raw)
    return bad
