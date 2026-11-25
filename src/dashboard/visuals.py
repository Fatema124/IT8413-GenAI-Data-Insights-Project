"""Small inline SVG graphics for the dashboard: the header chart and the card sparklines.

They are drawn from the real data (no decoration without meaning) and returned
as SVG strings, so they can sit inside the HTML cards. Pure Python, unit-tested.
"""
from __future__ import annotations

import itertools
import math

import pandas as pd

_ids = itertools.count(1)


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _segments(points: list[tuple[float, float | None]]) -> list[list[tuple[float, float]]]:
    """Split a line where values are missing, so gaps stay gaps (never interpolated)."""
    segs, cur = [], []
    for x, y in points:
        if y is None:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append((x, y))
    if cur:
        segs.append(cur)
    return segs


def spark_line(values: list, colour: str, width: int = 150, height: int = 40, ref: float | None = None) -> str:
    """A small line with a soft area underneath and a dot on the latest value."""
    vals = [float(v) if _ok(v) else None for v in values]
    have = [v for v in vals if v is not None]
    if len(have) < 2:
        return ""
    lo, hi = min(have + ([ref] if ref is not None else [])), max(have + ([ref] if ref is not None else []))
    span = (hi - lo) or 1.0
    pad = 3
    n = len(vals)

    def xy(i, v):
        return (pad + (width - 2 * pad) * i / (n - 1), pad + (height - 2 * pad) * (1 - (v - lo) / span))

    pts = [(xy(i, v) if v is not None else (pad + (width - 2 * pad) * i / (n - 1), None)) for i, v in enumerate(vals)]
    segs = _segments([(x, y) for x, y in pts])
    gid = f"plg{next(_ids)}"
    out = [f"<svg class='pl-spark' viewBox='0 0 {width} {height}' preserveAspectRatio='none' "
           f"xmlns='http://www.w3.org/2000/svg'><defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'>"
           f"<stop offset='0' stop-color='{colour}' stop-opacity='0.22'/>"
           f"<stop offset='1' stop-color='{colour}' stop-opacity='0'/></linearGradient></defs>"]
    if ref is not None and lo <= ref <= hi:
        ry = pad + (height - 2 * pad) * (1 - (ref - lo) / span)
        out.append(f"<line x1='0' y1='{ry:.1f}' x2='{width}' y2='{ry:.1f}' stroke='#c3c2b7' "
                   "stroke-width='1' stroke-dasharray='3 3'/>")
    for seg in segs:
        if len(seg) < 2:
            continue
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
        area = f"{seg[0][0]:.1f},{height} " + line + f" {seg[-1][0]:.1f},{height}"
        out.append(f"<polygon points='{area}' fill='url(#{gid})'/>")
        out.append(f"<polyline points='{line}' fill='none' stroke='{colour}' stroke-width='2' "
                   "stroke-linejoin='round' stroke-linecap='round'/>")
    lx, ly = next((p for p in reversed(pts) if p[1] is not None))
    out.append(f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='3' fill='{colour}' stroke='#ffffff' stroke-width='1.5'/>")
    out.append("</svg>")
    return "".join(out)


def spark_bars(values: list, width: int = 150, height: int = 40, up: str = "#e34948", down: str = "#2a78d6") -> str:
    """Small bars around zero: red above (prices rose), blue below (prices fell)."""
    vals = [float(v) if _ok(v) else None for v in values]
    have = [v for v in vals if v is not None]
    if not have:
        return ""
    top = max(max(have), 0.0)
    bottom = min(min(have), 0.0)
    span = (top - bottom) or 1.0
    n = len(vals)
    gap = 2
    bw = max(2.0, (width - gap * (n - 1)) / n)
    zero = height * top / span
    out = [f"<svg class='pl-spark' viewBox='0 0 {width} {height}' preserveAspectRatio='none' "
           "xmlns='http://www.w3.org/2000/svg'>",
           f"<line x1='0' y1='{zero:.1f}' x2='{width}' y2='{zero:.1f}' stroke='#c3c2b7' stroke-width='1'/>"]
    for i, v in enumerate(vals):
        if v is None:
            continue
        h = max(1.0, abs(v) / span * height)
        y = zero - h if v >= 0 else zero
        out.append(f"<rect x='{i * (bw + gap):.1f}' y='{y:.1f}' width='{bw:.1f}' height='{h:.1f}' rx='1' "
                   f"fill='{up if v >= 0 else down}' opacity='{1 if i == n - 1 else 0.6}'/>")
    out.append("</svg>")
    return "".join(out)


def hero_chart(series: pd.Series, derived: pd.Series, start, end, colour: str = "#8fbcf6",
               width: int = 520, height: int = 170) -> str:
    """Overall prices across all available months, with the selected period highlighted.

    The line draws itself once; derived months (2010) are dotted; the latest value pulses gently.
    """
    s = series.dropna()
    if len(s) < 2:
        return ""
    left, right, top, bottom = 34, 58, 22, 26
    lo, hi = min(s.min(), 100.0), max(s.max(), 100.0)
    lo, hi = lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.08
    t0, t1 = s.index.min(), s.index.max()
    total = (t1 - t0).days or 1

    def px(t):
        return left + (width - left - right) * (pd.Timestamp(t) - t0).days / total

    def py(v):
        return top + (height - top - bottom) * (1 - (v - lo) / (hi - lo))

    der = derived.reindex(s.index).fillna(False).astype(bool)
    pub = s[~der]
    dpts = s[der]
    if len(dpts):                                # join the dotted part to the solid line
        dpts = pd.concat([dpts, pub.iloc[:1]])
    line = " ".join(f"{px(t):.1f},{py(v):.1f}" for t, v in pub.items())
    dline = " ".join(f"{px(t):.1f},{py(v):.1f}" for t, v in dpts.items())
    area = f"{px(s.index[0]):.1f},{height - bottom} " + " ".join(
        f"{px(t):.1f},{py(v):.1f}" for t, v in s.items()) + f" {px(s.index[-1]):.1f},{height - bottom}"
    x0, x1 = px(max(pd.Timestamp(start), t0)), px(min(pd.Timestamp(end), t1))
    ex, ey = px(s.index[-1]), py(s.iloc[-1])
    base_y = py(100)
    ticks = "".join(
        f"<text x='{px(pd.Timestamp(year=y, month=1, day=1)):.1f}' y='{height - 8}' class='pl-hx'>{y}</text>"
        for y in range(t0.year + (0 if t0.month == 1 else 1), t1.year + 1, max(1, (t1.year - t0.year) // 4)))
    gid = f"plh{next(_ids)}"
    return (
        f"<svg class='pl-hero-chart' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>"
        f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'>"
        f"<stop offset='0' stop-color='{colour}' stop-opacity='0.35'/>"
        f"<stop offset='1' stop-color='{colour}' stop-opacity='0'/></linearGradient></defs>"
        f"<rect x='{x0:.1f}' y='{top - 6}' width='{max(2.0, x1 - x0):.1f}' height='{height - top - bottom + 6}' "
        "rx='6' fill='#ffffff' fill-opacity='0.08' stroke='#ffffff' stroke-opacity='0.25' stroke-dasharray='3 3'/>"
        f"<text x='{(x0 + x1) / 2:.1f}' y='{top - 9}' class='pl-hsel' text-anchor='middle'>your period</text>"
        f"<line x1='{left}' y1='{base_y:.1f}' x2='{width - right}' y2='{base_y:.1f}' stroke='#ffffff' "
        "stroke-opacity='0.3' stroke-dasharray='4 4'/>"
        f"<text x='{left - 4}' y='{base_y + 4:.1f}' class='pl-hx' text-anchor='end'>100</text>"
        f"<polygon class='pl-harea' points='{area}' fill='url(#{gid})'/>"
        + (f"<polyline points='{dline}' fill='none' stroke='{colour}' stroke-width='2' "
           "stroke-dasharray='2 4' opacity='0.8'/>" if dline else "")
        + f"<polyline class='pl-hline' pathLength='1' points='{line}' fill='none' stroke='{colour}' "
        "stroke-width='2.5' stroke-linejoin='round' stroke-linecap='round'/>"
        f"<circle class='pl-hpulse' cx='{ex:.1f}' cy='{ey:.1f}' r='5' fill='none' stroke='{colour}' "
        "stroke-width='2'/>"
        f"<circle cx='{ex:.1f}' cy='{ey:.1f}' r='4.5' fill='{colour}' stroke='#1d2432' stroke-width='2'/>"
        f"<text x='{ex + 9:.1f}' y='{ey + 4:.1f}' class='pl-hval'>{s.iloc[-1]:.1f}</text>"
        + ticks + "</svg>")
