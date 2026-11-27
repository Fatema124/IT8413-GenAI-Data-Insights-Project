"""The model's tool for questions over the documents (F5, F7).

`DocumentTools.call(name, args)` follows the same contract as
src/pipeline/tools.Toolbox.call: it always returns a JSON-safe dict with a
"status" of "ok", "not_available", "bad_input" or "error", so the question
answering loop (src/qa/engine.py) can run it like any other tool.

A result holds, for each passage: its id, the citation to show, whether the
text is in force or was changed in 2026, the passage text (Arabic for Docs
5-8) and the figures written out in Arabic words (for example "fifteen" = 15), so
the app's number check (src/qa/numbers.py) can accept "15 days" from an
Arabic article.
"""
from __future__ import annotations

import re

from .retrieve import Hit, Retriever

OK, NOT_AVAILABLE, BAD_INPUT, ERROR = "ok", "not_available", "bad_input", "error"
SEARCH = "search_documents"

DECLARATION = {
    "name": SEARCH,
    "description": (
        "Search the document collection for the passages that answer a question about sellers' "
        "obligations, consumer rights, sanctions, sales and discounts, advertised prices, or how iGA "
        "compiles the CPI. Sources: Law No. 35 of 2012 (English), Law No. 28 of 2026 amending it, the "
        "Executive Regulation (2014), Ministerial Orders 51/2007 (sales) and 14/2008 (advertised prices), "
        "all in Arabic; iGA's CPI release for September 2023; MOIC's 'Know Your Right' guidance (2016). "
        "Returns passages with citations. Call it once per distinct topic; write the query in English."),
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "What to look for, in English, e.g. 'return period for a defective product'"},
    }, "required": ["query"]},
}

# Arabic number words used in the documents (cardinals as written in the gazette texts).
_UNITS = {"واحد": 1, "اثنين": 2, "اثنان": 2, "ثلاث": 3, "ثلاثة": 3, "أربع": 4, "أربعة": 4, "خمس": 5,
          "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7, "ثمان": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9,
          "عشر": 10, "عشرة": 10}
_TENS = {"عشرين": 20, "عشرون": 20, "ثلاثين": 30, "ثلاثون": 30, "أربعين": 40, "خمسين": 50, "ستين": 60,
         "تسعين": 90}
_THOUSANDS = {"ألف": 1000, "ألفي": 2000, "ألفا": 1000}


def arabic_number_words(text: str) -> list[int]:
    """Numbers written as Arabic words in a legal text: "fifteen days" -> 15, "twenty thousand
    dinars" -> 20000, "two thousand dinars" -> 2000 (tests/test_retrieval.py has the Arabic
    examples). Digits are left to the number check."""
    found = []
    words = re.findall(r"[ء-ي]+", text)
    known = _UNITS.keys() | _TENS.keys() | _THOUSANDS.keys()
    words = [w[1:] if w[:1] in ("و", "ب") and w[1:] in known else w for w in words]   # drop the prefix "and" / "with" before a number word
    i = 0
    while i < len(words):
        w = words[i]
        value = None
        if w in _UNITS and i + 1 < len(words) and words[i + 1] == "عشر":        # 11-19
            value, i = _UNITS[w] + 10, i + 1
        elif w in _UNITS or w in _TENS:
            value = _UNITS.get(w) or _TENS.get(w)
        if value is not None and i + 1 < len(words) and words[i + 1] in ("ألف", "آلاف"):
            value, i = value * 1000, i + 1
        elif value is None and w in _THOUSANDS:
            value = _THOUSANDS[w]
        if value is not None:
            found.append(value)
        i += 1
    return sorted(set(found))


class DocumentTools:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever
        # Scores and ranks of the last search, for the query log (F10) and the failure analysis.
        # They are kept out of the tool result, because every number in a result counts as
        # evidence in the number check, and a similarity score is not a fact from the sources.
        self.last_search: list[dict] = []

    def call(self, name: str, args: dict | None = None) -> dict:
        args = dict(args or {})
        if name != SEARCH:
            return {"status": BAD_INPUT, "tool": name, "message": f"Unknown tool '{name}'.", "arguments": args}
        query = str(args.get("query", "")).strip()
        if not query or set(args) - {"query"}:
            return {"status": BAD_INPUT, "tool": name, "arguments": args,
                    "message": "Give one argument, 'query': what to look for, in English."}
        try:
            hits = self.retriever.search(query)
            self.last_search = [h.to_record() for h in hits]
        except Exception as exc:                    # a bug or a missing index: report it, never an answer
            return {"status": ERROR, "tool": name, "arguments": args, "message": f"{exc.__class__.__name__}: {exc}"}
        if not hits:
            return {"status": NOT_AVAILABLE, "tool": name, "arguments": args,
                    "message": "No passage in the documents is close enough to this question."}
        return {"status": OK, "tool": name, "arguments": args, "passages": [self._passage(h) for h in hits]}

    @staticmethod
    def _passage(h: Hit) -> dict:
        p = h.passage
        out = {"id": p.id, "citation": p.citation(), "status": p.status, "language": p.lang, "text": p.text}
        if h.reason == "amendment":
            out["added_because"] = "the 2012 article above was changed by Law No. 28 of 2026; this is the text in force"
        if p.note:
            out["note"] = p.note
        if p.lang == "ar" and (nums := arabic_number_words(p.text)):
            out["numbers_in_words"] = nums
        return out
