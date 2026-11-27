"""Compare two scored runs on every metric (brief 7.3, 7.5), e.g. v1 and v2 on the development set.

    python -m scripts.compare_runs v1-dev v2-dev
    python -m scripts.compare_runs v1-dev v2-dev --input-price 0.10 --output-price 0.40

Reads results/<run>.jsonl and results/<run>_scores.csv for each run. Prices are
USD per million tokens from the provider's published pricing page; without them,
cost is shown in tokens only. Writes results/compare_<a>_<b>.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from statistics import mean

from src.pipeline import config

RESULTS = config.REPO_ROOT / "results"
METRICS = {"accuracy": ("correct", "partial", "incorrect"),
           "groundedness": ("grounded", "ungrounded", "n/a"),
           "refusal": ("appropriate", "correct_refusal", "wrong_refusal", "wrong_answer"),
           "completeness": ("complete", "partial", "not_addressed")}


def load(run: str) -> tuple[dict, dict]:
    with open(RESULTS / f"{run}.jsonl", encoding="utf-8") as fh:
        recs = {r["question"]: r["record"] for r in map(json.loads, fh)}
    with open(RESULTS / f"{run}_scores.csv", encoding="utf-8-sig") as fh:
        scores = {r["question"]: r for r in csv.DictReader(fh)}
    return recs, scores


def summary(run: str, inp: float | None, out: float | None) -> dict:
    recs, scores = load(run)
    row = {"run": run, "questions": len(recs)}
    for m, values in METRICS.items():
        c = Counter(s[m].strip().lower() for s in scores.values())
        for v in values:
            row[f"{m}: {v}"] = c.get(v, 0)
    prompt = [r["tokens"].get("prompt", 0) for r in recs.values()]
    output = [r["tokens"].get("output", 0) + r["tokens"].get("thinking", 0) for r in recs.values()]
    row["mean tokens (prompt)"] = round(mean(prompt))
    row["mean tokens (output)"] = round(mean(output))
    row["mean latency (s)"] = round(mean(r["latency_s"] for r in recs.values()), 2)
    if inp is not None and out is not None:
        row["cost per 1,000 questions (USD)"] = round(1000 * (mean(prompt) * inp + mean(output) * out) / 1e6, 2)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--input-price", type=float); ap.add_argument("--output-price", type=float)
    a = ap.parse_args()
    rows = [summary(r, a.input_price, a.output_price) for r in (a.a, a.b)]
    path = RESULTS / f"compare_{a.a}_{a.b}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    width = max(map(len, rows[0]))
    print(f"{'':<{width}}  {a.a:>10}  {a.b:>10}")
    for k in rows[0]:
        if k != "run":
            print(f"{k:<{width}}  {rows[0][k]!s:>10}  {rows[1][k]!s:>10}")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
