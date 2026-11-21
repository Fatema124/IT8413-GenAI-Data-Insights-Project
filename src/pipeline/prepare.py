"""Step 2 of the pipeline: turn the raw tables into one clean, checked table.

Every rule below answers one of the three things F1 asks us to handle:

  MISSING VALUES  A value that is blank or not a number is kept as missing
                  (NaN) and counted. It is never filled or interpolated,
                  because an invented index value would end up in an answer
                  quoted in the press. Months absent from a series are listed.
  UNITS           Index values are kept at the precision stored in the file
                  (e.g. 76.02); rounding happens only when a figure is shown.
                  Every series is checked against the base (April 2019 = 100).
                  Weights are checked to add up to ~100% of the basket.
  CATEGORY LABELS Codes are re-padded ('1.1' -> '01.1'), the headline row is
                  given one code ('0') and one name, and each code gets one
                  canonical name. Nationality labels are unified.

Output: a long ('tidy') table with one row per month x category x population.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config, labels


@dataclass
class QualityLog:
    """Collects what each preparation step found and changed (for the report)."""
    entries: list[dict] = field(default_factory=list)

    def add(self, source: str, check: str, result, detail: str = "", status: str = "ok"):
        self.entries.append({"source": source, "check": check, "result": result,
                             "detail": detail, "status": status})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries, columns=["source", "check", "result", "detail", "status"])


def _to_number(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip()
    return pd.to_numeric(text.where(~text.isin(["", "-", "..", "n/a", "NA", "nan", "None"])), errors="coerce")


def _tidy_codes(raw: pd.DataFrame, source: str, log: QualityLog) -> pd.DataFrame:
    df = raw.copy()
    df["published_label"] = df["raw_name"].map(lambda v: labels.clean_name(v, fix_spelling=False))
    df["raw_name"] = df["raw_name"].map(labels.clean_name)
    df["code"] = [labels.resolve_code(c, n) for c, n in zip(df["raw_code"], df["published_label"])]
    if df["code"].isna().any():
        bad = df.loc[df["code"].isna(), "raw_name"].unique()[:5]
        raise ValueError(f"{source}: {df['code'].isna().sum()} rows have no usable code, e.g. {list(bad)}")
    raw_text = df["raw_code"].astype(str).str.strip()
    repadded = (raw_text != df["code"]) & (df["code"] != config.HEADLINE_CODE)
    if repadded.any():
        first = df.loc[repadded, "period"].min()
        per_month = df.loc[repadded].groupby("period").size()
        log.add(source, "COICOP codes re-padded with leading zero", int(repadded.sum()),
                f"from {first:%b %Y}; {per_month.median():.0f} codes per affected month "
                f"(e.g. '{raw_text[repadded].iloc[0]}' -> '{df.loc[repadded, 'code'].iloc[0]}')",
                "fixed")
    headline_labels = sorted(df.loc[df["code"] == config.HEADLINE_CODE, "published_label"].unique())
    log.add(source, "Headline row labels unified to code '0'", len(headline_labels),
            "'" + "'; '".join(headline_labels) + f"' -> '{config.HEADLINE_NAME}'", "fixed")
    df["level"] = df["code"].map(labels.code_level)
    df["division"] = df["code"].map(labels.division_of)
    return df


def _tidy_values(df: pd.DataFrame, source: str, log: QualityLog, value_name: str = "index") -> pd.DataFrame:
    df = df.copy()
    df[value_name] = _to_number(df["raw_value"])
    zero = df[value_name] <= 0
    if zero.any():
        # An index cannot be 0. iGA uses 0.0 for series that did not exist yet
        # (imputed rent, accommodation and social protection start May 2019).
        spans = (df[zero].groupby("code")["period"].agg(["min", "max"])
                 .apply(lambda r: f"{r.name} {r['min']:%b %Y}-{r['max']:%b %Y}", axis=1))
        log.add(source, "Zero index values treated as missing (series not yet published)",
                int(zero.sum()), "; ".join(spans), "fixed")
        df.loc[zero, value_name] = np.nan
    n_missing = int(df[value_name].isna().sum())
    examples = df.loc[df[value_name].isna(), ["period", "code"]].head(5)
    detail = ", ".join(f"{p:%b %Y} {c}" for p, c in examples.itertuples(index=False)) if n_missing else ""
    log.add(source, "Missing values after preparation (kept as missing, not filled)", n_missing, detail,
            "info" if n_missing else "ok")
    decimals = df["raw_value"].astype(str).str.extract(r"\.(\d+)$")[0].str.len().fillna(0)
    by_month = decimals.groupby(df["period"]).max()
    high = by_month[by_month > 2]
    log.add(source, "Stored precision (decimal places)",
            f"{int(decimals.min())}-{int(decimals.max())}",
            ("unrounded values in " + ", ".join(f"{p:%b %Y}" for p in high.index[:6])) if len(high) else "",
            "info")
    return df


def _check_duplicates(df: pd.DataFrame, keys: list[str], source: str, log: QualityLog) -> pd.DataFrame:
    dup = df.duplicated(keys, keep=False)
    if not dup.any():
        log.add(source, "Duplicate rows", 0)
        return df
    conflicting = df[dup].groupby(keys)["index"].nunique(dropna=False)
    if (conflicting > 1).any():
        raise ValueError(f"{source}: conflicting duplicate values for {conflicting[conflicting > 1].index[:3].tolist()}")
    log.add(source, "Duplicate rows (identical, dropped)", int(dup.sum() // 2), status="fixed")
    return df.drop_duplicates(keys)


def _check_months(df: pd.DataFrame, source: str, log: QualityLog) -> None:
    """Every series should have every month between the dataset's first and last month."""
    first, last = df["period"].min(), df["period"].max()
    expected = pd.date_range(first, last, freq="MS")
    gaps = []
    for keys, grp in df.groupby(["population", "code"]):
        missing = expected.difference(grp["period"])
        if len(missing):
            gaps.append(f"{keys[0]} {keys[1]}: {len(missing)} months (first {missing[0]:%b %Y})")
    log.add(source, "Months covered", f"{first:%b %Y} - {last:%b %Y} ({len(expected)} months)")
    log.add(source, "Series with missing months", len(gaps), "; ".join(gaps[:5]),
            "warning" if gaps else "ok")


def _check_base(df: pd.DataFrame, source: str, log: QualityLog) -> None:
    base = df[(df["period"] == pd.Timestamp(config.BASE_PERIOD)) & df["index"].notna()]
    if base.empty:
        log.add(source, "Base period April 2019 = 100", "not in range", status="info")
        return
    off = base[(base["index"] - config.BASE_VALUE).abs() > 0.05]
    later = sorted(set(df["code"]) - set(base["code"]))
    detail = "; ".join(f"{r.code}={r.index}" for r in off.head(5).itertuples())
    if later:
        detail += (" " if detail else "") + f"({len(later)} series start after April 2019: {', '.join(later)})"
    log.add(source, "Base period April 2019 = 100", f"{len(base) - len(off)}/{len(base)} series with a base value",
            detail, "warning" if len(off) else "ok")


def _apply_cutoff(df: pd.DataFrame, source: str, log: QualityLog) -> pd.DataFrame:
    """Keep the working copy to the proposal's coverage (config.DATA_END)."""
    end = pd.Timestamp(config.DATA_END)
    later = df["period"] > end
    log.add(source, "Rows read from file", len(df),
            f"{df['period'].min():%b %Y} - {df['period'].max():%b %Y}", "info")
    if later.any():
        months = sorted(df.loc[later, "period"].unique())
        log.add(source, f"Rows after {end:%b %Y} removed (working-copy cut-off)", int(later.sum()),
                ", ".join(f"{pd.Timestamp(m):%b %Y}" for m in months), "fixed")
    return df.loc[~later].copy()


def _check_rows(df: pd.DataFrame, source: str, log: QualityLog, n_raw: int) -> None:
    expected = config.SOURCES[source]["expected_rows"]
    status = "ok" if expected is None or n_raw == expected else "warning"
    log.add(source, "Rows in working copy", n_raw, f"proposal records {expected}" if expected else "", status)


# --------------------------------------------------------------------------
# Public functions
# --------------------------------------------------------------------------
def prepare_d1(raw: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    raw = _apply_cutoff(raw, "D1", log)
    _check_rows(raw, "D1", log, len(raw))
    df = _tidy_codes(raw, "D1", log)
    df = _tidy_values(df, "D1", log)
    df["population"] = config.NATIONAL
    df = _check_duplicates(df, ["period", "code", "population"], "D1", log)
    n_series = df["code"].nunique()
    log.add("D1", "Distinct series", n_series, "proposal: 69 (headline + 68 items)",
            "ok" if n_series == 69 else "warning")
    _check_months(df, "D1", log)
    _check_base(df, "D1", log)
    return df


def prepare_d2(raw: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    raw = _apply_cutoff(raw, "D2", log)
    _check_rows(raw, "D2", log, len(raw))
    df = _tidy_codes(raw, "D2", log)
    df = _tidy_values(df, "D2", log)
    key = df["raw_nationality"].astype(str).str.strip().str.lower().str.replace("_", " ")
    df["population"] = key.map(config.NATIONALITY_MAP)
    if df["population"].isna().any():
        raise ValueError(f"D2: unknown nationality labels {sorted(key[df['population'].isna()].unique())}; "
                         f"add them to config.NATIONALITY_MAP")
    log.add("D2", "Nationality labels unified", ", ".join(sorted(df["raw_nationality"].unique())),
            "-> Bahraini / Non-Bahraini", "fixed")
    df = _check_duplicates(df, ["period", "code", "population"], "D2", log)
    _check_months(df, "D2", log)
    _check_base(df, "D2", log)
    return df


def prepare_weights(raw: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    df = raw.copy()
    df["raw_name"] = df["raw_name"].map(labels.clean_name)
    df["code"] = [labels.resolve_code(c, n) for c, n in zip(df["raw_code"], df["raw_name"])]
    df = df[df["code"].notna()]
    df["weight"] = _to_number(df["raw_value"])
    df = df[df["weight"].notna()].copy()
    df["level"] = df["code"].map(labels.code_level)
    df["division"] = df["code"].map(labels.division_of)
    divisions = df[df["level"] == 1]
    total = divisions["weight"].sum()
    if total <= 1.5:          # stored as shares (0.2502) rather than percent
        df["weight"] *= 100
        total *= 100
        log.add("D3", "Weights converted from share to percent", "x100", status="fixed")
    status = "ok" if abs(total - 100) <= 0.1 else "warning"
    log.add("D3", "Division weights add up to 100%", round(total, 2),
            f"{len(divisions)} divisions", status)
    df["name"] = [config.DIVISION_NAMES.get(c, n) for c, n in zip(df["code"], df["raw_name"])]
    return df[["code", "name", "level", "division", "weight", "source_sheet", "source_row"]].reset_index(drop=True)


def prepare_history(raw: pd.DataFrame, d1: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    """Headline 2011-2016 from Dataset 3, checked against Dataset 1 where they overlap."""
    df = raw.copy()
    df["index"] = _to_number(df["raw_value"])
    df = df.dropna(subset=["period"])
    overlap = df.merge(d1[d1["code"] == config.HEADLINE_CODE][["period", "index"]],
                       on="period", suffixes=("_d3", "_d1"))
    if len(overlap):
        diff = (overlap["index_d3"] - overlap["index_d1"]).abs()
        bad = overlap.loc[diff > 0.05, "period"]
        years = sorted({p.year for p in bad})
        kept = set(range(pd.Timestamp(config.D3_HISTORY_KEEP[0]).year, pd.Timestamp(config.D3_HISTORY_KEEP[1]).year + 1))
        log.add("D3", "Table 1 headline matches Dataset 1 where both exist",
                f"{int((diff <= 0.05).sum())}/{len(diff)} months",
                (f"differences only in {', '.join(map(str, years))} (max {diff.max():.1f}); "
                 "Table 2.01 agrees with Dataset 1 there, so those Table 1 rows are not used") if len(bad) else "",
                "ok" if not len(bad) else ("info" if not set(years) & kept else "warning"))
    lo, hi = (pd.Timestamp(p) for p in config.D3_HISTORY_KEEP)
    df = df[(df["period"] >= lo) & (df["period"] <= hi)].copy()
    log.add("D3", "Headline history rows kept (2011-2016)", len(df),
            "only the years before Dataset 1 starts are used", "info")
    df["code"] = config.HEADLINE_CODE
    df["level"] = 0
    df["division"] = None
    df["population"] = config.NATIONAL
    df["raw_name"] = config.HEADLINE_NAME
    return df


def crosscheck_table_201(raw_idx: pd.DataFrame, d1: pd.DataFrame, log: QualityLog) -> None:
    """Every Dataset 1 value vs iGA's own Table 2.01 for the months both cover."""
    t = raw_idx.copy()
    t["code"] = [labels.resolve_code(c, labels.clean_name(n, False)) if pd.notna(c) or pd.notna(n) else None
                 for c, n in zip(t["raw_code"], t["raw_name"])]
    t.loc[t["raw_name"].astype(str).str.strip().str.lower().eq("all divisions"), "code"] = config.HEADLINE_CODE
    t["d3"] = _to_number(t["raw_value"])
    t = t.dropna(subset=["code", "d3", "period"])
    t = t[t["d3"] > 0]
    m = t.merge(d1[["period", "code", "index"]].dropna(), on=["period", "code"])
    if m.empty:
        return
    diff = (m["d3"] - m["index"]).abs()
    log.add("D1+D3", "Dataset 1 values match iGA Table 2.01 (all codes, overlapping months)",
            f"{int((diff <= 0.05).sum())}/{len(m)} values",
            f"{m['period'].min():%b %Y} - {m['period'].max():%b %Y}, max difference {diff.max():.3f}",
            "ok" if (diff <= 0.05).mean() >= 0.99 else "warning")


def crosscheck_table_3(raw_nat: pd.DataFrame, d2: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    """Dataset 2 vs iGA's own Table 3 (Sep 2023 publication) for the months both cover.

    Returns the values that differ by more than 0.15 index points. Dataset 2
    stays the working source (as in the proposal); differences are reported,
    and the dashboard warns when a selection includes them.
    """
    cols = ["code", "name", "period", "population", "dataset2", "iga_table3", "difference"]
    if raw_nat is None or raw_nat.empty:
        return pd.DataFrame(columns=cols)
    t = raw_nat.copy()
    t["published"] = t["raw_name"].map(lambda v: labels.clean_name(v, fix_spelling=False))
    t["code"] = [config.HEADLINE_CODE if pd.isna(c) and str(n).strip().lower() == "all divisions"
                 else (labels.normalise_code(c) if pd.notna(c) else None)
                 for c, n in zip(t["raw_code"], t["published"])]
    t["iga_table3"] = _to_number(t["raw_value"])
    t = t.dropna(subset=["code", "iga_table3", "period"])
    m = t.merge(d2[["period", "code", "population", "index"]].dropna(), on=["period", "code", "population"])
    if m.empty:
        return pd.DataFrame(columns=cols)
    m["difference"] = m["index"] - m["iga_table3"]
    big = m[m["difference"].abs() > 0.15].copy()
    detail = ""
    if len(big):
        parts = []
        for (year, pop), g in big.groupby([big["period"].dt.year, "population"]):
            parts.append(f"{year} {pop}: {g['code'].nunique()} series, {len(g)} values")
        detail = "; ".join(parts) + f"; largest {big['difference'].abs().max():.1f} points"
    log.add("D2+D3", "Dataset 2 matches iGA Table 3 (nationality, overlapping months)",
            f"{int((m['difference'].abs() <= 0.15).sum())}/{len(m)} values",
            detail or f"{m['period'].min():%b %Y} - {m['period'].max():%b %Y}",
            "warning" if len(big) else "ok")
    big = big.rename(columns={"index": "dataset2"})
    big["name"] = big["published"]
    return big[cols].sort_values(["population", "code", "period"]).reset_index(drop=True)


def build_cpi_table(d1: pd.DataFrame, d2: pd.DataFrame, history: pd.DataFrame | None,
                    log: QualityLog) -> pd.DataFrame:
    """Join everything into the single tidy table used by the app and the tools."""
    parts = [d1, d2] + ([history] if history is not None and len(history) else [])
    keep = ["period", "code", "raw_name", "level", "division", "population", "index", "source", "source_row"]
    cpi = pd.concat([p.reindex(columns=keep) for p in parts], ignore_index=True)
    names = labels.canonical_names(pd.concat([d1, d2])[["period", "code", "raw_name"]])
    cpi["name"] = cpi["code"].map(names).fillna(cpi["raw_name"])
    variants = (pd.concat([d1, d2]).groupby("code")["published_label"].nunique())
    log.add("D1+D2", "Codes with more than one published label (one name kept)",
            int((variants > 1).sum()), ", ".join(variants[variants > 1].index[:8]), "fixed")
    shared = set(d1["code"]) & set(d2["code"])
    log.add("D1+D2", "Shared codes for the national vs nationality join", len(shared),
            "headline + 12 divisions expected (13)", "ok" if len(shared) >= 13 else "warning")
    cpi["year"] = cpi["period"].dt.year.astype(int)
    cpi["month"] = cpi["period"].dt.month.astype(int)
    cpi["index"] = cpi["index"].astype(float)
    cols = ["period", "year", "month", "code", "name", "level", "division", "population",
            "index", "source", "source_row"]
    return cpi[cols].sort_values(["population", "code", "period"]).reset_index(drop=True)


def labels_table(cpi: pd.DataFrame, weights: pd.DataFrame | None) -> pd.DataFrame:
    lab = (cpi.groupby("code").agg(name=("name", "first"), level=("level", "first"),
                                   division=("division", "first"),
                                   first_month=("period", "min"), last_month=("period", "max"),
                                   populations=("population", lambda s: ", ".join(sorted(s.unique()))))
           .reset_index())
    if weights is not None:
        lab = lab.merge(weights[["code", "weight"]], on="code", how="left")
    return lab.sort_values(["level", "code"]).reset_index(drop=True)


def weighted_headline_check(cpi: pd.DataFrame, weights: pd.DataFrame, log: QualityLog) -> None:
    """Units check: the weighted sum of division indices should track the headline.

    A large gap would mean the weights or the indices were read in the wrong
    unit. A small gap is expected (published rounding, chain-linking).
    """
    w = weights[weights["level"] == 1].set_index("code")["weight"]
    nat = cpi[cpi["population"] == config.NATIONAL]
    div = nat[nat["level"] == 1].pivot(index="period", columns="code", values="index")
    common = [c for c in w.index if c in div.columns]
    if len(common) < 12:
        return
    implied = (div[common] * w[common]).sum(axis=1, min_count=12) / w[common].sum()
    head = nat[nat["code"] == config.HEADLINE_CODE].set_index("period")["index"]
    gap = (implied - head).dropna().abs()
    if len(gap):
        log.add("D1+D3", "Weighted divisions vs headline (mean |gap|, index points)",
                round(float(gap.mean()), 3), f"max {gap.max():.3f}",
                "ok" if gap.mean() < 1.0 else "info")
