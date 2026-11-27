"""The document tool inside the question-answering loop (F5, F6, F7).

Uses the fake Gemini client and the planted data from tests/test_qa.py, and a
small document collection with the word-count embedder from test_retrieval.py,
so it runs without an API key, the PDFs or the embedding model.
"""
from __future__ import annotations

import pytest

from src.documents.retrieve import Retriever
from src.documents.tool import DocumentTools
from src.qa.engine import ANSWERED, DECLINED, DataQA
from tests.test_qa import FakeClient, call, data, function_responses, text, turn  # noqa: F401 (fixture)
from tests.test_retrieval import WordEmbedder, _p


@pytest.fixture
def docs():
    return DocumentTools(Retriever([
        _p("D6-A16", 6, "spare parts خلال مدة أقصاها خمسة عشر يوم عمل", lang="ar"),
        _p("D4-A23", 4, "Sanction: closure.", "superseded", ["D5-A23"]),
        _p("D5-A23", 5, "closure fine", "amending", ["D4-A23"], lang="ar"),
    ], WordEmbedder()))


def declared(request):
    return {d.name for t in request["config"].tools for d in t.function_declarations}


def test_without_documents_nothing_changes(data):
    client = FakeClient(turn(text("Hello.")))
    DataQA(data, client).ask("hi")
    req = client.models.requests[0]
    assert "search_documents" not in declared(req)
    assert "RULES FOR DOCUMENT ANSWERS" not in req["config"].system_instruction


def test_with_documents_the_tool_rules_and_settings_are_added(data, docs):
    client = FakeClient(turn(text("Hello.")))
    ans = DataQA(data, client, documents=docs).ask("hi")
    req = client.models.requests[0]
    assert "search_documents" in declared(req) and "get_change" in declared(req)
    assert "RULES FOR DOCUMENT ANSWERS" in req["config"].system_instruction
    assert ans.settings["top_k"] >= 1 and ans.settings["prompt"].endswith("+docs-v1")


def test_document_answer_is_cited_logged_and_its_number_supported(data, docs):
    cite = docs.retriever.by_id["D6-A16"].citation()        # what the tool returns as the citation
    client = FakeClient(
        turn(call("search_documents", query="spare parts period")),
        turn(text(f"Within 15 working days [{cite}].")))
    ans = DataQA(data, client, documents=docs).ask("How long does a supplier have to provide spare parts?")
    sent = function_responses(client.models.requests[1])[0].response
    assert sent["passages"][0]["id"] == "D6-A16"
    assert sent["passages"][0]["numbers_in_words"] == [15]
    assert ans.status == ANSWERED and ans.unsupported_numbers == []     # 15 comes from the Arabic words,
                                                                        # the citation's numbers from the result
    assert ans.retrieval[0]["query"] == "spare parts period" and ans.retrieval[0]["hits"][0]["id"] == "D6-A16"


def test_superseded_article_reaches_the_model_with_its_2026_text(data, docs):
    client = FakeClient(turn(call("search_documents", query="closure sanction")), turn(text("Closure.")))
    DataQA(data, client, documents=docs).ask("What sanctions apply?")
    ids = [p["id"] for p in function_responses(client.models.requests[1])[0].response["passages"]]
    assert ids[:2] == ["D4-A23", "D5-A23"]


def test_nothing_found_leads_to_a_declined_answer(data, docs):
    client = FakeClient(turn(call("search_documents", query="e-commerce penalties")),
                        turn(text("This is not available in the sources. The documents cover ...")))
    ans = DataQA(data, client, documents=docs).ask("What penalties does the e-commerce law set?")
    assert function_responses(client.models.requests[1])[0].response["status"] == "not_available"
    assert ans.status == DECLINED


def test_engine_passes_the_users_question_to_the_search(data, docs):
    from src.documents import settings as s
    s.use_version("v2")
    try:
        client = FakeClient(turn(call("search_documents", query="closure")), turn(text("Done.")))
        ans = DataQA(data, client, documents=docs).ask("How long for spare parts?")
    finally:
        s.use_version("v1")
    reasons = {h["id"]: h["reason"] for h in ans.retrieval[0]["hits"]}
    assert reasons.get("D6-A16") == "question" and ans.settings["retrieval_version"] == "v2"
