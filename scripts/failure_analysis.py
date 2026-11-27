"""Failure analysis (brief 7.4) for one scored run.

    python -m scripts.failure_analysis v1-dev

Reads results/<run>.jsonl (the answers) and results/<run>_scores.csv (the
judged metrics), finds the failures, traces each one and suggests a category.
Writes results/<run>_failures.csv and prints the count per category and the
largest category, which the intervention (v2) targets (brief 7.5).
To confirm or change a suggestion, write the category in the optional "category"
column of the scores file and run this again.
"""
from __future__ import annotations

import csv
import json
import sys

from src.evaluation import failures as F
from src.evaluation.dev_documents import BY_ID
from src.pipeline import config

RESULTS = config.REPO_ROOT / "results"


def load(run: str) -> list[tuple[F.Item, dict, F.Scores]]:
    records = {}
    with open(RESULTS / f"{run}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            records[r["question"]] = r["record"]
    out = []
    with open(RESULTS / f"{run}_scores.csv", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            s = F.Scores(row["accuracy"].strip().lower(), row["groundedness"].strip().lower(),
                         row["refusal"].strip().lower(), row["completeness"].strip().lower(),
                         row["ambiguous"].strip().lower() in ("y", "yes", "true", "1"), row["notes"],
                         row.get("category", "").strip())
            out.append((BY_ID[row["question"]], records[row["question"]], s))
    return out


def main(argv: list[str]) -> int:
    run = argv[0] if argv else "v1-dev"
    fails = F.analyse(run, load(run))
    path = RESULTS / f"{run}_failures.csv"
    F.write_csv(fails, path)
    print(f"{len(fails)} failure(s) in {run}:")
    for f in fails:
        print(f"  Q{f.qid}: {f.reasons}\n     -> {f.suggested}: {f.suggested_reason}")
    print("\nCount per category:")
    for cat, n in F.counts(fails).most_common():
        print(f"  {n}  {cat}")
    print(f"\nLargest category (target of the next intervention): {F.largest(fails)}\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
