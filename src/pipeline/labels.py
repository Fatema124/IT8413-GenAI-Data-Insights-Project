"""Category labels: COICOP codes, names and hierarchy levels.

Why this module exists (proposal, 'Preparation issues in the data'):
  * From June 2023 Dataset 1 drops the leading zero in divisions 01-09
    ('1.1' instead of '01.1'), while Dataset 2 keeps it. Without fixing this,
    the same category would appear as two different series and joins between
    the datasets would silently fail.
  * The headline row is labelled differently in each file.
  * Some names are misspelt.
"""
from __future__ import annotations

import re

import pandas as pd

from . import config


def normalise_code(raw) -> str | None:
    """Return a COICOP code in canonical form, or None if it is empty.

    '1.1' -> '01.1', '4' -> '04', '01.1.2' -> '01.1.2', '0' / '00' -> '0'.
    Only the division part (before the first dot) is padded; deeper parts
    are kept as published.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip().strip("'\"")
    if text == "" or text.lower() in {"nan", "none", "-"}:
        return None
    if text.lower() in {"cpi", "total", "all items"}:
        return config.HEADLINE_CODE
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        return text  # unknown format: keep it, the quality report will list it
    head, *rest = text.split(".")
    if int(head) == 0 and not rest:
        return config.HEADLINE_CODE
    return ".".join([head.zfill(2), *rest])


def code_level(code: str) -> int:
    """Hierarchy level from the code: 0 headline, 1 division, 2 group, 3 class."""
    if code == config.HEADLINE_CODE:
        return 0
    return code.count(".") + 1


def division_of(code: str) -> str | None:
    """Two-digit division a code belongs to (None for the headline)."""
    if code == config.HEADLINE_CODE:
        return None
    return code.split(".")[0]


def clean_name(raw, fix_spelling: bool = True) -> str:
    """Whitespace/line-break clean-up plus the documented spelling fixes."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    text = re.sub(r"\s+", " ", str(raw)).strip()
    return config.NAME_FIXES.get(text, text) if fix_spelling else text


def is_headline_label(name: str) -> bool:
    text = (name or "").strip().lower()
    return any(re.search(p, text) for p in config.HEADLINE_LABEL_PATTERNS)


def resolve_code(raw_code, raw_name) -> str | None:
    """Canonical code, falling back to the label for the headline row."""
    code = normalise_code(raw_code)
    if code is None and is_headline_label(clean_name(raw_name)):
        return config.HEADLINE_CODE
    if code is not None and code != config.HEADLINE_CODE and is_headline_label(clean_name(raw_name)):
        # e.g. Dataset 2 labels the headline 'Consumer Price Indexs' at level 1
        # with a code such as '00'; treat any headline label as the headline.
        if code.lstrip("0") in {"", "."}:
            return config.HEADLINE_CODE
    return code


def canonical_names(frame: pd.DataFrame) -> dict[str, str]:
    """One name per code.

    Divisions take the official COICOP name; other codes take the most
    frequent cleaned label across all months (ties -> latest month), so a
    one-off misspelling never becomes the displayed name.
    """
    names: dict[str, str] = {}
    for code, grp in frame.groupby("code"):
        if code == config.HEADLINE_CODE:
            names[code] = config.HEADLINE_NAME
        elif code in config.DIVISION_NAMES:
            names[code] = config.DIVISION_NAMES[code]
        else:
            counts = grp.sort_values("period", ascending=False).groupby("raw_name", sort=False).size()
            names[code] = counts.idxmax() if len(counts) else code
    return names
