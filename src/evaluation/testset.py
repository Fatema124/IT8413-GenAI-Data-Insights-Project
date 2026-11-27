"""The test set for the evaluation runs and the failure analysis.

`expected_passages(location)` turns a ground-truth source location, as written in the test set
(revised proposal, Section 3), into the passage ids the tool should retrieve, e.g.
    "Doc 6 (Exec. Regulation, OG 3165), Art. 16, p. 18; Doc 4 (Law 35/2012, EN), Art. 9, p. 6"
    -> {"D6-A16", "D4-A9"}
Legal documents (Docs 4-8) are matched by article; for Law 28/2026 the article of Law 35/2012
it inserts or replaces is used ("new Art. 23" -> D5-A23). Docs 9 and 10 are matched by page
(D9-P7 covers every window of page 7). Dataset references have no passage.

`load_items(path)` reads the test-set spreadsheet exported as CSV (columns below), so the
failure analysis can run on the full test set once the final evaluation has been run.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .failures import Item

LEGAL = {4, 5, 6, 7, 8}
_DOC = re.compile(r"Doc\s*(\d+)")
_RANGE = re.compile(r"(\d+)\s*[–-]\s*(\d+)")


def _numbers(spec: str) -> list[int]:
    """'13–14 and 17' -> [13, 14, 17]; '1–3' -> [1, 2, 3]."""
    out: list[int] = []
    for part in re.split(r",|\band\b", spec):
        if m := _RANGE.search(part):
            out += list(range(int(m.group(1)), int(m.group(2)) + 1))
        elif m := re.search(r"\d+", part):
            out.append(int(m.group()))
    return out


def expected_passages(location: str) -> frozenset[str]:
    found: set[str] = set()
    for chunk in re.split(r";", location or ""):
        m = _DOC.search(chunk)
        if not m:
            continue                                   # a dataset reference
        n = int(m.group(1))
        rest = chunk[m.end():]
        if n in LEGAL:
            new = re.findall(r"new Art\.\s*(\d+)(\s*bis)?", rest)
            if n == 5 and new:
                found |= {f"D5-A{a}{'bis' if b else ''}" for a, b in new}
                continue
            arts = re.search(r"Art\.\s*([\d\s–\-,and]+)", re.sub(r"\([^)]*\)", "", rest))
            if arts:
                found |= {f"D{n}-A{a}" for a in _numbers(arts.group(1))}
        else:
            pp = re.search(r"pp?\.\s*([\d\s–\-]+)", rest)
            for p in re.findall(r"p{1,2}\.\s*([\d\s–\-]+)", rest) if pp else []:
                found |= {f"D{n}-P{x}" for x in _numbers(p)}
    return frozenset(found)


COLUMNS = ("question", "split", "type", "question text", "ground truth", "source location")


def load_items(path: Path) -> dict[str, Item]:
    """CSV with the columns in COLUMNS (one row per question; 13a/13b allowed as ids).
    `type` is document | combined | data | unanswerable | counter; unanswerable rows must be declined."""
    items = {}
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            kind = row["type"].strip().lower()
            items[row["question"].strip()] = Item(
                row["question"].strip(), row["split"].strip().lower(), kind, row["question text"],
                row["ground truth"], expected_passages(row.get("source location", "")),
                must_decline=kind == "unanswerable")
    return items
