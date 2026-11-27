"""Run the DEVELOPMENT questions that use the documents through the full tool (v1 settings)
and write the answers for scoring and failure analysis.

    python -m scripts.run_dev_documents                  # v1 settings, run name "v1-dev"
    python -m scripts.run_dev_documents --version v2     # v2 (one setting changed), "v2-dev"

Writes results/<run>.jsonl (one Answer.to_record() per question) and
results/<run>_scores.csv: one row per question with the ground truth and the
answer side by side, and empty columns for the four judged metrics (brief 7.3).
Fill those in, then run `python -m scripts.failure_analysis <run>`.

Held-out questions are not run (brief 7.1). 8 questions = 8 short Gemini sessions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tomllib
from pathlib import Path

from src.documents import settings as doc_settings
from src.documents.retrieve import Retriever
from src.documents.tool import DocumentTools
from src.evaluation.dev_documents import ITEMS
from src.pipeline import config
from src.pipeline.run import load_prepared
from src.qa import settings
from src.qa.engine import DataQA, make_client

RESULTS = config.REPO_ROOT / "results"
SCORE_COLUMNS = ["accuracy", "groundedness", "refusal", "completeness", "ambiguous", "notes", "category"]


def api_key() -> str:
    secrets = config.REPO_ROOT / ".streamlit" / "secrets.toml"
    key = tomllib.loads(secrets.read_text(encoding="utf-8")).get(settings.API_KEY_NAME) if secrets.exists() else None
    key = key or os.environ.get(settings.API_KEY_NAME)
    if not key:
        sys.exit(f"No {settings.API_KEY_NAME}: add it to .streamlit/secrets.toml first.")
    return key


def citations(record: dict) -> str:
    seen = []
    for c in record.get("tool_calls", []):
        for p in c.get("result", {}).get("passages", []):
            if p["citation"] not in seen:
                seen.append(p["citation"])
    return " | ".join(seen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1", choices=sorted(doc_settings.VERSIONS))
    ap.add_argument("--run", default=None, help="run name (default: <version>-dev)")
    a = ap.parse_args()
    run = a.run or f"{a.version}-dev"
    doc_settings.use_version(a.version)
    settings.VERSION = a.version                   # the version shown with every answer
    print(f"Run {run}: {doc_settings.as_dict()}")
    qa = DataQA(load_prepared(), make_client(api_key()), documents=DocumentTools(Retriever.load()))
    RESULTS.mkdir(exist_ok=True)
    out, scores = RESULTS / f"{run}.jsonl", RESULTS / f"{run}_scores.csv"
    rows = []
    with open(out, "w", encoding="utf-8") as fh:
        for item in ITEMS:
            ans = qa.ask(item.question)
            rec = ans.to_record()
            fh.write(json.dumps({"run": run, "question": item.qid, "split": item.split, "record": rec},
                                ensure_ascii=False) + "\n")
            print(f"Q{item.qid}: {rec['status']}, {rec['latency_s']:.1f} s, {rec['tokens'].get('total', '?')} tokens")
            rows.append({"run": run, "question": item.qid, "type": item.kind, "status": rec["status"],
                         "question text": item.question, "ground truth": item.ground_truth,
                         "answer": rec["answer"], "passages shown": citations(rec),
                         "tokens": rec["tokens"].get("total", ""), "latency_s": rec["latency_s"],
                         **{c: "" for c in SCORE_COLUMNS}})
    with open(scores, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out}\nWrote {scores}  <- fill in the score columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
