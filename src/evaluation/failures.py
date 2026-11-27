"""Failure analysis (brief 7.4): find the failed answers of a run, trace each one
through the pipeline and suggest one of the brief's categories.

A failure (brief 7.4) is any question that a run
  * answers incorrectly (accuracy "incorrect" or "partial"),
  * declines when it should have been answered, or
  * answers with a citation that does not support the answer (groundedness "ungrounded").
An answer to a question that must be declined is also a failure (refusal behaviour).

The trace uses only what the answer record (Answer.to_record(), src/qa/engine.py)
already holds: the tools called and their status, the passages retrieved
(ids, ranks, scores), the numbers the number check could not find, the status.
The suggested category is a starting point; a group member confirms or changes
it in the `category` column and writes the reason. The counts per category
then pick the intervention (brief 7.5: the category with the most failures).
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# The brief's categories (7.4), in its order and wording.
WRONG_PASSAGE = "Retrieval returned the wrong passage"
NOT_USED = "Retrieval returned the right passage, and the model did not use it"
AMBIGUOUS = "The question was ambiguous"
NOT_IN_SOURCES = "The sources do not contain the answer"
CALCULATION = "The calculation was wrong"
OTHER = "Other"
CATEGORIES = (WRONG_PASSAGE, NOT_USED, AMBIGUOUS, NOT_IN_SOURCES, CALCULATION, OTHER)

SEARCH = "search_documents"
CALC_TOOLS = {"calculate", "get_change"}


@dataclass(frozen=True)
class Item:
    """One test-set question, as needed for the analysis."""
    qid: str
    split: str                                   # development | held-out
    kind: str                                    # document | combined | data | unanswerable | counter
    question: str
    ground_truth: str
    expected_passages: frozenset[str] = field(default_factory=frozenset)   # passage ids, e.g. D6-A16
    must_decline: bool = False


@dataclass
class Scores:
    """The four judged metrics (brief 7.3) for one answer, entered by a group member."""
    accuracy: str = ""          # correct | partial | incorrect
    groundedness: str = ""      # grounded | ungrounded | n/a (nothing cited, e.g. a refusal)
    refusal: str = ""           # appropriate | correct_refusal | wrong_refusal | wrong_answer
    completeness: str = ""      # complete | partial | not_addressed
    ambiguous: bool = False     # the judge read the question in more than one reasonable way
    notes: str = ""
    category: str = ""          # optional: the judge's confirmed category (one of CATEGORIES)


def failure_reasons(item: Item, record: dict, s: Scores) -> list[str]:
    """Why this answer counts as a failure (empty list: not a failure)."""
    declined = record.get("status") == "declined"
    why = []
    if item.must_decline:
        if not declined:
            why.append("answered a question that must be declined")
        return why
    if declined or s.refusal == "wrong_refusal":
        why.append("declined a question that should have been answered")
    if s.accuracy in ("incorrect", "partial"):
        why.append(f"accuracy: {s.accuracy}")
    if s.groundedness == "ungrounded":
        why.append("citation does not support the answer")
    return why


def _base(pid: str) -> str:
    """Window passages of a legal article share the article id (D6-A4-p2 -> D6-A4)."""
    return pid.rsplit("-p", 1)[0] if pid[:2] in ("D4", "D5", "D6", "D7", "D8") else pid


def _covers(expected: str, pid: str) -> bool:
    """An expected id matches the passage itself, its article, or (D9-P7) every window of that page."""
    return expected in (pid, _base(pid)) or (expected[:2] in ("D9", "D1") and pid.startswith(expected + "-"))


def trace(item: Item, record: dict) -> dict:
    """Where the answer went in the pipeline, from the answer record only."""
    calls = record.get("tool_calls", [])
    retrieved: list[str] = []
    for search in record.get("retrieval", []):
        retrieved += [h["id"] for h in search.get("hits", [])]
    found = sorted(e for e in item.expected_passages if any(_covers(e, p) for p in retrieved))
    return {
        "status": record.get("status", ""),
        "tools": "; ".join(f"{c['name']}:{c.get('result', {}).get('status', '')}" for c in calls),
        "searched": any(c["name"] == SEARCH for c in calls),
        "retrieved": "; ".join(dict.fromkeys(retrieved)),
        "expected": "; ".join(sorted(item.expected_passages)),
        "expected_found": "; ".join(found),
        "expected_missing": "; ".join(sorted(item.expected_passages - set(found))),
        "unsupported_numbers": "; ".join(record.get("unsupported_numbers", [])),
        "calc_errors": any(c["name"] in CALC_TOOLS and c.get("result", {}).get("status") in ("bad_input", "error")
                           for c in calls),
    }


def suggest(item: Item, record: dict, s: Scores, t: dict) -> tuple[str, str]:
    """(category, reason) suggested from the trace. Checked in pipeline order."""
    if item.must_decline:
        return NOT_IN_SOURCES, "The question must be declined and the tool answered it."
    if s.ambiguous:
        return AMBIGUOUS, "Marked ambiguous by the judge: check which reading the tool answered."
    if t["unsupported_numbers"]:
        return CALCULATION, f"The answer has numbers no tool returned: {t['unsupported_numbers']}."
    if t["calc_errors"]:
        return CALCULATION, "A calculation tool was called with bad input or failed."
    if s.groundedness == "ungrounded" and s.accuracy == "correct" and record.get("status") != "declined":
        return OTHER, ("Citation error: the facts are right but are cited to a source that does not hold "
                       "them (e.g. data-tool figures cited to a document passage).")
    if item.expected_passages:
        if not t["searched"]:
            return WRONG_PASSAGE, "The model never searched the documents, so no passage was supplied."
        if not t["expected_found"]:
            return WRONG_PASSAGE, f"None of the expected passages ({t['expected']}) was retrieved."
        if t["expected_missing"]:
            return WRONG_PASSAGE, (f"Only part of the needed passages was supplied: retrieved {t['expected_found']}, "
                                   f"not {t['expected_missing']}. If the wrong or missing part of the answer is in "
                                   "the retrieved passages, change this to 'did not use it'.")
        return NOT_USED, f"All expected passages were retrieved ({t['expected_found']}); the answer did not use them."
    return OTHER, "Data question: check the tool results against the answer."


@dataclass
class Failure:
    run: str
    qid: str
    split: str
    kind: str
    reasons: str
    suggested: str
    suggested_reason: str
    category: str = ""          # confirmed by a group member (defaults to the suggestion)
    trace: dict = field(default_factory=dict)

    def row(self) -> dict:
        return {"run": self.run, "question": self.qid, "split": self.split, "type": self.kind,
                "why it failed": self.reasons, "suggested category": self.suggested,
                "trace": self.suggested_reason, "category (confirmed)": self.category or self.suggested,
                **{f"trace: {k}": v for k, v in self.trace.items()}}


def analyse(run: str, results: list[tuple[Item, dict, Scores]]) -> list[Failure]:
    out = []
    for item, record, s in results:
        why = failure_reasons(item, record, s)
        if not why:
            continue
        t = trace(item, record)
        cat, reason = suggest(item, record, s, t)
        confirmed = next((c for c in CATEGORIES if s.category and s.category.lower().startswith(c.lower()[:20])), "")
        out.append(Failure(run, item.qid, item.split, item.kind, "; ".join(why), cat, reason, confirmed, trace=t))
    return out


def counts(failures: list[Failure]) -> Counter:
    return Counter(f.category or f.suggested for f in failures)


def largest(failures: list[Failure]) -> str | None:
    """The category with the most failures (brief 7.5). Ties: brief order."""
    c = counts(failures)
    if not c:
        return None
    top = max(c.values())
    return next(cat for cat in CATEGORIES if c.get(cat) == top)


def write_csv(failures: list[Failure], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f.row() for f in failures]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:     # utf-8-sig: opens cleanly in Excel
        if not rows:
            fh.write("no failures\n")
            return
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
