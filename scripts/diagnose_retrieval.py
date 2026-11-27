"""Where did the expected passages rank for the searches the model actually made?
(failure analysis, brief 7.4; DEVELOPMENT questions only)

    python -m scripts.diagnose_retrieval v1-dev

For every document search logged in results/<run>.jsonl, the full ranking is
computed again (no cut-off) and the rank and similarity of each expected passage
is shown, plus the same for the question text itself. It shows which setting
kept a needed passage out (top_k or min_score), or whether the model's query
was the problem. Only the retriever runs: no Gemini call.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from src.documents import settings
from src.documents.retrieve import Retriever, _unit
from src.evaluation.dev_documents import BY_ID
from src.pipeline import config

RESULTS = config.REPO_ROOT / "results"


def ranking(r: Retriever, query: str) -> tuple[list[str], np.ndarray]:
    q = _unit(r.embedder.embed([query]))[0]
    scores = r.vectors @ q
    order = np.argsort(-scores)
    return [r.passages[i].id for i in order], scores[order]


def show(r: Retriever, label: str, query: str, expected: set[str]) -> None:
    ids, scores = ranking(r, query)
    base = [i.rsplit("-p", 1)[0] if i[:2] in ("D4", "D5", "D6", "D7", "D8") else i for i in ids]
    print(f"  {label}: \"{query}\"")
    for e in sorted(expected):
        k = base.index(e)
        s = scores[k]
        within = f"in top {settings.TOP_K}" if k < settings.TOP_K else f"rank {k + 1} > top_k {settings.TOP_K}"
        cut = "above" if s >= settings.MIN_SCORE else "BELOW"
        print(f"     {e:<10} rank {k + 1:>3}  score {s:.3f}  ({within}; {cut} min_score {settings.MIN_SCORE})")


def main(argv: list[str]) -> int:
    run = argv[0] if argv else "v1-dev"
    r = Retriever.load()
    print(f"Settings: {settings.as_dict()}\n")
    with open(RESULTS / f"{run}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            item = BY_ID[row["question"]]
            if not item.expected_passages:
                continue
            print(f"Q{item.qid} ({item.kind})")
            for s in row["record"].get("retrieval", []):
                show(r, "model's query", s["query"], set(item.expected_passages))
            show(r, "question text", item.question, set(item.expected_passages))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
