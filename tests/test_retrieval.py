"""Tests for passages, retrieval and the search_documents tool (F5, F7).

Retrieval is tested with a small word-count embedder, so the tests need
neither the model download nor the PDFs. Tests on the real passages are
skipped until `python -m src.documents.passages` has been run.
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from src.documents import passages as P
from src.documents.passages import Passage
from src.documents.retrieve import Retriever
from src.documents.tool import SEARCH, DocumentTools, arabic_number_words


class WordEmbedder:
    """Bag of words over a fixed vocabulary: enough to test ranking and links."""
    name = "test-words"
    VOCAB = ["return", "refund", "defect", "days", "spare", "parts", "sanction", "fine", "closure",
             "sale", "discount", "licence", "price", "advertised", "weights", "survey"]

    def embed(self, texts):
        rows = []
        for t in texts:
            words = re.findall(r"[a-z]+", t.lower())
            rows.append([sum(w.startswith(v) for w in words) for v in self.VOCAB])
        return np.asarray(rows, dtype=np.float32)


def _p(pid, doc, text, status="in force", links=None, lang="en"):
    return Passage(pid, doc, f"Doc {doc}", pid, [1], lang, text, "v", status, "", links or [])


@pytest.fixture
def tools():
    ps = [
        _p("D4-A7", 4, "Supplier shall return or refund a product with a defect."),
        _p("D4-A9", 4, "Supplier shall provide spare parts within a period."),
        _p("D4-A23", 4, "Sanction: closure of the establishment.", "superseded", ["D5-A23"]),
        _p("D5-A23", 5, "fine fine closure", "amending", ["D4-A23"], lang="ar"),
        _p("D9-P6-w1", 9, "Weights come from the household survey."),
    ]
    return DocumentTools(Retriever(ps, WordEmbedder()))


def test_best_passage_first(tools):
    out = tools.call(SEARCH, {"query": "refund for a defect"})
    assert out["status"] == "ok"
    assert out["passages"][0]["id"] == "D4-A7"


def test_superseded_article_brings_the_2026_text(tools):
    out = tools.call(SEARCH, {"query": "closure sanction"})
    ids = [p["id"] for p in out["passages"]]
    assert "D4-A23" in ids and "D5-A23" in ids


def test_nothing_close_enough_is_not_available(tools):
    out = tools.call(SEARCH, {"query": "what will inflation be next year"})
    assert out["status"] == "not_available"


def test_bad_arguments(tools):
    assert tools.call(SEARCH, {})["status"] == "bad_input"
    assert tools.call(SEARCH, {"query": "x", "k": 3})["status"] == "bad_input"
    assert tools.call("get_index", {"query": "x"})["status"] == "bad_input"


def test_arabic_number_words():
    assert arabic_number_words("خلال خمسة عشر يوما") == [15]
    assert arabic_number_words("لا يجاوز عشرين ألف دينار") == [20000]
    assert arabic_number_words("ألف دينار يوميا وألفي دينار") == [1000, 2000]
    assert arabic_number_words("مهلة لا تتجاوز سبعة أيام") == [7]


# ---------------------------------------------------------------- real passages
@pytest.fixture(scope="module")
def real():
    if not P.PASSAGES_FILE.exists():
        pytest.skip("passages not built (python -m src.documents.passages)")
    return {p.id: p for p in P.build()}


def test_citations_use_gazette_pages(real):
    assert real["D6-A14"].citation() == "Executive Regulation (MD 66/2014), Article 14 (pp. 17-18)"
    assert real["D6-A16"].pages == [18]
    assert real["D8-A2"].pages == [7]
    assert real["D4-A7"].pages == [5]


def test_2026_amendments_are_linked(real):
    assert real["D4-A23"].status == "superseded" and "D5-A23-p1" in real["D4-A23"].links
    assert real["D4-A22"].status == "amended"
    assert real["D5-A11bis"].status == "amending"
    assert real["D4-A7"].status == "in force"


def test_every_article_is_a_passage(real):
    assert {f"D4-A{n}" for n in range(1, 26)} - {k.rsplit("-p", 1)[0] for k in real} == set()
    assert {f"D6-A{n}" for n in range(1, 46)} - {k.rsplit("-p", 1)[0] for k in real} == set()
    assert {f"D7-A{n}" for n in range(1, 9)} <= set(real) and "D7-Aform" in real


def test_passages_are_not_too_long(real):
    assert max(len(p.text) for p in real.values()) <= 1800


def test_scores_are_logged_but_not_given_as_evidence(tools):
    out = tools.call(SEARCH, {"query": "refund for a defect"})
    assert "score" not in out["passages"][0]
    assert tools.last_search[0]["id"] == "D4-A7" and "score" in tools.last_search[0]
