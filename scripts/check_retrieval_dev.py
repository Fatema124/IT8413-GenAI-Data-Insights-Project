"""Check retrieval on the DEVELOPMENT questions that use the documents (F5, F7).

    python -m scripts.check_retrieval_dev

For each development question, the article or page in its ground-truth source
location (revised proposal, Section 3) must be among the passages returned.
For the development questions that must be declined, the best score is shown,
to set the minimum similarity. Only the retriever runs: no model call, no quota.

The held-out questions are deliberately left out (brief 7.1): they are not run
or used to tune retrieval before the final evaluation.
"""
from __future__ import annotations

import sys

from src.documents import settings
from src.documents.retrieve import Retriever

# question number, question (as in the test set), passages that hold the answer
ANSWERABLE = [
    (2, "A shop sells a used phone in instalments. What must its invoice contain?", {"D6-A4"}),
    (4, "A shop advertised a television at a set price in a newspaper, then charged a higher price at the "
        "till. Which obligations does this breach and what penalty does the order refer to?",
     {"D8-A1", "D8-A2", "D8-A3"}),
    (6, "How long does a supplier have to provide spare parts and maintenance after a consumer asks, and when "
        "is it released from this duty?", {"D6-A16", "D4-A9"}),
    (12, "what does iGA's method say about how often education prices are collected and their weight?",
     {"D9-P8-w1", "D9-P7-w2"}),
    (25, "A customer changes their mind about a jacket bought yesterday that has no fault. Must the shop "
         "exchange it or give a refund?", {"D10-P8-w1", "D6-A14"}),
]
MUST_DECLINE = [
    (16, "What was the CPI for Muharraq Governorate in August 2026?"),
    (19, "What is the current price of a litre of fresh milk at a supermarket in Manama?"),
    (20, "What was the headline CPI in December 2009?"),
]


def base(pid: str) -> str:
    return pid.rsplit("-p", 1)[0] if pid.startswith(("D4", "D5", "D6", "D7", "D8")) else pid


def main() -> int:
    r = Retriever.load()
    print(f"Settings: {settings.as_dict()}\n")
    found_all = 0
    for n, q, expected in ANSWERABLE:
        hits = r.search(q)
        got = [h.passage.id for h in hits]
        found = expected & {base(g) for g in got}
        found_all += bool(found)
        mark = "✓" if found else "✗"
        print(f"{mark} Q{n}: expected {sorted(expected)}; found {sorted(found) or 'none'}")
        for h in hits:
            print(f"     {h.rank or '+'}  {h.score:.3f}  {h.passage.citation()}")
    print(f"\n{found_all}/{len(ANSWERABLE)} development document questions retrieve an expected passage.\n")
    for n, q in MUST_DECLINE:
        hits = r.search(q, min_score=-1.0)
        print(f"Q{n} (must decline): best score {hits[0].score:.3f} ({hits[0].passage.citation()}); "
              f"{'nothing passed on' if hits[0].score < settings.MIN_SCORE else 'ABOVE the minimum'}")
    return 0 if found_all == len(ANSWERABLE) else 1


if __name__ == "__main__":
    sys.exit(main())
