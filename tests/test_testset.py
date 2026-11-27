"""Test-set loading for the final failure analysis, and the baseline document text.
Synthetic locations only: the held-out questions are not used here."""
import json

from src.documents import baseline, config
from src.evaluation.failures import Scores, analyse
from src.evaluation.testset import expected_passages, load_items


def test_articles_ranges_and_lists():
    assert expected_passages("Doc 8 (MO 14/2008, OG 2833), Art. 1–3, p. 7") == {"D8-A1", "D8-A2", "D8-A3"}
    assert expected_passages("Doc 6 (X), Art. 10–11 and 19, pp. 17–18") == {"D6-A10", "D6-A11", "D6-A19"}


def test_several_documents_and_a_dataset():
    loc = "Dataset 1: code 10; Doc 6 (Exec. Regulation, OG 3165), Art. 16, p. 18; Doc 4 (Law 35/2012, EN), Art. 9, p. 6"
    assert expected_passages(loc) == {"D6-A16", "D4-A9"}


def test_amending_law_uses_the_article_it_inserts():
    assert expected_passages("Doc 5 (Law 28/2026, OG 3889), Art. 1 (new Art. 22), p. 34") == {"D5-A22"}
    assert expected_passages("Doc 5 (Law 28/2026), Art. 2 (new Art. 11 bis), p. 35") == {"D5-A11bis"}


def test_releases_are_matched_by_page():
    assert expected_passages("Doc 9 (iGA CPI Sep 2023), §2, p. 5 and §4, p. 9") == {"D9-P5", "D9-P9"}
    assert expected_passages("Doc 10 (MOIC, Know Your Right), PDF pp. 7–8") == {"D10-P7", "D10-P8"}
    assert expected_passages("None") == frozenset()


def test_page_ids_cover_their_windows_in_the_trace():
    items = {"x": __import__("src.evaluation.failures", fromlist=["Item"]).Item(
        "x", "development", "document", "q", "gt", frozenset({"D9-P8"}))}
    rec = {"status": "answered", "unsupported_numbers": [],
           "tool_calls": [{"name": "search_documents", "result": {"status": "ok"}}],
           "retrieval": [{"hits": [{"id": "D9-P8-w2"}]}]}
    [f] = analyse("r", [(items["x"], rec, Scores(accuracy="partial"))])
    assert f.trace["expected_found"] == "D9-P8"


def test_load_items_from_csv(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("question,split,type,question text,ground truth,source location\n"
                 "99,Development,Document,Q?,A.,\"Doc 8 (MO 14/2008), Art. 2, p. 7\"\n"
                 "98,Held-out,Unanswerable,Q2?,Not answerable.,None\n", encoding="utf-8")
    items = load_items(p)
    assert items["99"].expected_passages == {"D8-A2"} and items["99"].split == "development"
    assert items["98"].must_decline and items["98"].split == "held-out"


def test_baseline_text_uses_the_prepared_pages_and_tool_citations(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "TEXT_DIR", tmp_path)
    doc = config.BY_ID[8]
    (tmp_path / "doc8.jsonl").write_text(json.dumps({"doc": 8, "page": 1, "lang": "ar", "text": "نص"}) + "\n",
                                         encoding="utf-8")
    text = baseline.baseline_text([8])
    assert text.startswith("=== Document 8:") and f"[{doc.short}, p. 7]" in text and "نص" in text
