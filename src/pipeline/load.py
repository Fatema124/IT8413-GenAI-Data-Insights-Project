"""Step 1 of the pipeline: read the raw files exactly as published.

Nothing is corrected here except what is needed to *read* the files:
header line breaks, the CSV delimiter and the Excel layout. All real
preparation decisions are made in `prepare.py`, so that every change to
the data is visible in one place.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

from . import config

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9


class SourceFormatError(ValueError):
    """Raised when a raw file does not have the structure we expect."""


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------
def normalise_header(col) -> str:
    """'Index\\nNumber ' -> 'index number' (both CSV headers contain a line break)."""
    return re.sub(r"\s+", " ", str(col)).strip().lower()


def read_csv_any(path: Path) -> pd.DataFrame:
    """Read a portal CSV, detecting ';' or ',' and keeping every cell as text.

    Opendatasoft portals export with ';' by default; a re-saved file may use
    ','. Text is kept so codes such as '01.1' are not turned into 1.1.
    """
    raw = Path(path).read_text(encoding="utf-8-sig")
    sample = raw[:5000]
    try:
        sep = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        sep = ";" if sample.count(";") > sample.count(",") else ","
    df = pd.read_csv(io.StringIO(raw), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [normalise_header(c) for c in df.columns]
    return df


def parse_month(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower().rstrip(".")
    if text.isdigit() and 1 <= int(text) <= 12:
        return int(text)
    m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)", text)       # '01 January' (both CSVs)
    if m:
        num, word = int(m.group(1)), MONTHS.get(m.group(2)) or MONTHS.get(m.group(2)[:3])
        return word if word == num else None                # reject inconsistent labels
    if not text.isalpha():
        return None
    return MONTHS.get(text) or MONTHS.get(text[:3])


def to_period(year, month) -> pd.Timestamp | None:
    m = parse_month(month)
    try:
        y = int(float(str(year).strip()))
    except (TypeError, ValueError):
        return None
    if m is None:
        return None
    return pd.Timestamp(year=y, month=m, day=1)


def parse_period_text(value) -> pd.Timestamp | None:
    """'2026-08', '2026/08', 'Aug 2026', 'August-2026', datetime -> month start."""
    if isinstance(value, pd.Timestamp):
        return value.to_period("M").to_timestamp()
    if hasattr(value, "year") and hasattr(value, "month"):
        return pd.Timestamp(year=value.year, month=value.month, day=1)
    text = str(value).strip()
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?(?:[ T].*)?", text)
    if m:
        return to_period(m.group(1), m.group(2))
    m = re.fullmatch(r"([A-Za-z]+)[\s\-/,]*(\d{4})", text)
    if m:
        return to_period(m.group(2), m.group(1))
    return None


# --------------------------------------------------------------------------
# Column recognition for Datasets 1 and 2
# --------------------------------------------------------------------------
_RULES = {
    "year": lambda c: c == "year" or c.startswith("year"),
    "month": lambda c: c == "month" or c.startswith("month"),
    "period": lambda c: c in {"date", "period", "time", "month/year", "year-month"},
    "code": lambda c: "code" in c or c == "coicop",
    "level": lambda c: "level" in c,
    "nationality": lambda c: "nationality" in c,
    "value": lambda c: ("index" in c and ("number" in c or "value" in c)) or c in {"value", "index", "cpi", "point", "points"},
    "name": lambda c: any(k in c for k in ("division", "group", "description", "item", "name", "category"))
                      and "code" not in c and "nationality" not in c,
}


def resolve_columns(df: pd.DataFrame, source: str, required: tuple[str, ...]) -> dict[str, str]:
    """Map our field names (year, month, code, ...) to the file's columns."""
    found: dict[str, str] = {}
    overrides = {k: normalise_header(v) for k, v in config.COLUMN_OVERRIDES.get(source, {}).items()}
    for field, rule in _RULES.items():
        if field in overrides:
            found[field] = overrides[field]
            continue
        hits = [c for c in df.columns if rule(c) and c not in found.values()]
        if len(hits) == 1:
            found[field] = hits[0]
        elif len(hits) > 1 and field in required:
            raise SourceFormatError(
                f"{source}: column '{field}' is ambiguous {hits}. "
                f"Set config.COLUMN_OVERRIDES['{source}']['{field}']. Columns: {list(df.columns)}")
    has_time = ("year" in found and "month" in found) or "period" in found
    missing = [f for f in required if f not in found]
    if not has_time:
        missing.append("year+month or period")
    if missing:
        raise SourceFormatError(
            f"{source}: could not find {missing}. Columns in file: {list(df.columns)}. "
            f"Set config.COLUMN_OVERRIDES['{source}'].")
    return found


def _standardise(df: pd.DataFrame, cols: dict[str, str], source: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "raw_code": df[cols["code"]] if "code" in cols else "",
        "raw_name": df[cols["name"]] if "name" in cols else "",
        "raw_level": df[cols["level"]] if "level" in cols else "",
        "raw_value": df[cols["value"]],
    })
    if "year" in cols and "month" in cols:
        out["period"] = [to_period(y, m) for y, m in zip(df[cols["year"]], df[cols["month"]])]
    else:
        out["period"] = [parse_period_text(v) for v in df[cols["period"]]]
    if "nationality" in cols:
        out["raw_nationality"] = df[cols["nationality"]]
    out["source"] = source
    out["source_row"] = range(2, len(df) + 2)  # spreadsheet row number, for tracing
    bad = out["period"].isna().sum()
    if bad:
        raise SourceFormatError(f"{source}: {bad} rows have a year/month that cannot be read.")
    return out


def load_d1(path: Path | None = None) -> pd.DataFrame:
    """Dataset 1: national index, headline + 68 COICOP items, monthly."""
    path = path or config.RAW_DIR / config.RAW_FILES["D1"]
    df = read_csv_any(path)
    cols = resolve_columns(df, "D1", required=("code", "name", "value"))
    return _standardise(df, cols, "D1")


def load_d2(path: Path | None = None) -> pd.DataFrame:
    """Dataset 2: headline + 12 divisions for Bahraini / non-Bahraini households.

    Handles both layouts: a nationality column (long) or one value column
    per nationality (wide).
    """
    path = path or config.RAW_DIR / config.RAW_FILES["D2"]
    df = read_csv_any(path)
    nat_cols = [c for c in df.columns if normalise_header(c).replace("_", " ") in config.NATIONALITY_MAP]
    if nat_cols and not any("nationality" in c for c in df.columns):
        id_cols = [c for c in df.columns if c not in nat_cols]
        df = df.melt(id_vars=id_cols, value_vars=nat_cols,
                     var_name="nationality", value_name="index number")
    cols = resolve_columns(df, "D2", required=("name", "value", "nationality"))
    return _standardise(df, cols, "D2")


# --------------------------------------------------------------------------
# Dataset 3 (iGA XLSX tables)
# --------------------------------------------------------------------------
def _sheet_text(frame: pd.DataFrame, rows: int = 12) -> str:
    return " ".join(str(v) for v in frame.head(rows).to_numpy().ravel() if pd.notna(v)).lower()


def _find_sheet(book: dict[str, pd.DataFrame], wanted: str | None, keywords: tuple[str, ...]) -> str:
    if wanted:
        if wanted not in book:
            raise SourceFormatError(f"D3: sheet '{wanted}' not found. Sheets: {list(book)}")
        return wanted
    for name, frame in book.items():
        text = name.lower() + " " + _sheet_text(frame)
        if all(k in text for k in keywords):
            return name
    raise SourceFormatError(
        f"D3: no sheet contains {keywords}. Sheets: {list(book)}. "
        f"Set config.D3_WEIGHTS_SHEET / D3_HISTORY_SHEET.")


def load_d3_weights(book: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Table 2.01: expenditure weight of each division and group (% of basket)."""
    sheet = _find_sheet(book, config.D3_WEIGHTS_SHEET, ("weight",))
    raw = book[sheet]
    header_row = next((i for i, row in raw.iterrows()
                       if any("weight" in str(v).lower() for v in row.values)
                       and row.notna().sum() >= 2), None)  # skip the table title
    if header_row is None:
        raise SourceFormatError(f"D3[{sheet}]: no header row containing 'weight'.")
    header = [normalise_header(v) for v in raw.loc[header_row].values]
    body = raw.loc[header_row + 1:].copy()
    body.columns = header
    weight_col = next(c for c in header if "weight" in c)
    code_col = next((c for c in header if c == "code" or "code" in c), None)
    name_col = next((c for c in header if any(k in c for k in ("division", "group", "name", "description"))
                     and c not in {weight_col, code_col}), None)
    out = pd.DataFrame({
        "raw_code": body[code_col] if code_col else "",
        "raw_name": body[name_col] if name_col else "",
        "raw_value": body[weight_col],
    })
    out["source"] = "D3"
    out["source_sheet"] = sheet
    out["source_row"] = body.index + 1  # Excel row number
    out = out[out["raw_value"].astype(str).str.strip().ne("") & out["raw_value"].notna()]
    return out


def load_d3_history(book: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Table 1: headline CPI with months laid out as columns -> one row per month."""
    sheet = _find_sheet(book, config.D3_HISTORY_SHEET, ("2011",))
    raw = book[sheet]
    records = []
    # Layout C (iGA Table 1): a row holding only the year, then one row per
    # month with the month name in column B and the April 2019 = 100 value in
    # column C. 'Yearly' rows (annual averages) are skipped.
    year = None
    for i, row in raw.iterrows():
        v = list(row.values) + [None, None, None]
        first = str(v[0]).strip().split(".")[0] if pd.notna(v[0]) else ""
        if re.fullmatch(r"(19|20)\d{2}", first):
            year = first if pd.isna(v[1]) else None    # '2011 Yearly' is an annual row
            continue
        if year and pd.notna(v[1]) and parse_month(v[1]) and pd.notna(v[2]):
            records.append((to_period(year, v[1]), v[2], i + 1))
    if records:
        out = pd.DataFrame(records, columns=["period", "raw_value", "source_row"])
        out["source"], out["source_sheet"] = "D3", sheet
        return out
    for i, row in raw.iterrows():
        values = list(row.values)
        # Layout A: a year in the first cell and 12 month columns after it.
        year = str(values[0]).strip().split(".")[0] if len(values) else ""
        if re.fullmatch(r"(19|20)\d{2}", year):
            header = None
            for j in range(i - 1, -1, -1):  # find the month header above
                cand = [parse_month(v) for v in raw.loc[j].values]
                if sum(c is not None for c in cand) >= 6:
                    header = cand
                    break
            if header:
                for col, month in enumerate(header):
                    if month is not None and col < len(values):
                        records.append((to_period(year, month), values[col], i + 2))
                continue
    if not records:
        # Layout B: a header row of dates/month labels and a headline row beneath.
        for i, row in raw.iterrows():
            periods = [parse_period_text(v) for v in row.values]
            if sum(p is not None for p in periods) >= 6:
                for k in range(i + 1, len(raw)):
                    label = " ".join(str(v) for v in raw.loc[k].values[:3])
                    if re.search(r"general|all items|headline|consumers? price", label, re.I):
                        for col, period in enumerate(periods):
                            if period is not None:
                                records.append((period, raw.loc[k].values[col], k + 2))
                        break
                break
    if not records:
        raise SourceFormatError(f"D3[{sheet}]: could not find the monthly headline series.")
    out = pd.DataFrame(records, columns=["period", "raw_value", "source_row"])
    out["source"] = "D3"
    out["source_sheet"] = sheet
    return out


def load_d3_index_table(book: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Table 2.01 index numbers (one column per month) -> long, for cross-checking Dataset 1."""
    sheet = config.D3_WEIGHTS_SHEET or _find_sheet(book, None, ("weight",))
    raw = book[sheet]
    hdr_i = next(i for i, row in raw.iterrows()
                 if any("weight" in str(v).lower() for v in row.values) and row.notna().sum() >= 2)
    header = list(raw.loc[hdr_i].values)
    date_cols = [(j, parse_period_text(h)) for j, h in enumerate(header)
                 if isinstance(h, (pd.Timestamp,)) or hasattr(h, "year")]
    code_j = next(j for j, h in enumerate(header) if "code" in str(h).lower())
    name_j = next(j for j, h in enumerate(header) if "division" in str(h).lower())
    rows = []
    for i in range(hdr_i + 1, len(raw)):
        code, name = raw.iat[i, code_j], raw.iat[i, name_j]
        if pd.isna(code) and pd.isna(name):
            continue
        for j, period in date_cols:
            rows.append((code, name, period, raw.iat[i, j]))
    return pd.DataFrame(rows, columns=["raw_code", "raw_name", "period", "raw_value"])


def load_d3_nationality_table(book: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Table 3: division index by nationality (a date row, then a Bahraini /
    Non-Bahraini row under it) -> long. Used only to cross-check Dataset 2."""
    cols = ["raw_code", "raw_name", "period", "population", "raw_value"]
    sheet = config.D3_NATIONALITY_SHEET
    if not sheet or sheet not in book:
        return pd.DataFrame(columns=cols)
    raw = book[sheet]
    hdr = next((i for i in range(min(20, len(raw)))
                if sum(parse_period_text(v) is not None for v in raw.iloc[i].values if pd.notna(v)) >= 6), None)
    if hdr is None or hdr + 1 >= len(raw):
        return pd.DataFrame(columns=cols)
    dates, nats = list(raw.iloc[hdr].values), list(raw.iloc[hdr + 1].values)
    code_j = next((j for j, h in enumerate(raw.iloc[hdr].values) if "code" in str(h).lower()), 0)
    name_j = next((j for j, h in enumerate(raw.iloc[hdr].values) if "division" in str(h).lower()), 2)
    columns, current = [], None
    for j in range(len(dates)):
        p = parse_period_text(dates[j]) if pd.notna(dates[j]) else None
        if p is not None:
            current = p
        label = str(nats[j]).strip().lower()
        if current is not None and label in config.NATIONALITY_MAP:
            columns.append((j, current, config.NATIONALITY_MAP[label]))
    rows = []
    for i in range(hdr + 2, len(raw)):
        code, name = raw.iat[i, code_j], raw.iat[i, name_j]
        if pd.isna(code) and pd.isna(name):
            continue
        for j, period, pop in columns:
            rows.append((code, name, period, pop, raw.iat[i, j]))
    return pd.DataFrame(rows, columns=cols)


def load_d3(path: Path | None = None):
    """Weights, headline history, Table 2.01 index numbers and Table 3 (nationality)."""
    path = path or config.RAW_DIR / config.RAW_FILES["D3"]
    book = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    return (load_d3_weights(book), load_d3_history(book), load_d3_index_table(book),
            load_d3_nationality_table(book))
