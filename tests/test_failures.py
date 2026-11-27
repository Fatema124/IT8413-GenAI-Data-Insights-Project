"""Failure analysis (brief 7.4): failures found, traced and categorised from the answer record."""
from src.evaluation import failures as F
from src.evaluation.dev_documents import BY_ID, ITEMS

DOC_Q = BY_ID["6"]          # expects D6-A16 and D4-A9
DECLINE_Q = BY_ID["19"]


def record(status="answered", hits=(), unsupported=(), calls=None):
    calls = calls if calls is not None else ([{"name": "search_documents", "result": {"status": "ok"}}] if hits else [])
    return {"status": status, "tool_calls": calls, "unsupported_numbers": list(unsupported),
            "retrieval": [{"query": "q", "hits": [{"id": h} for h in hits]}] if hits else []}


def run(item, rec, **scores):
    return F.analyse("v1-dev", [(item, rec, F.Scores(**scores))])


def test_correct_grounded_answer_is_not_a_failure():
    assert run(DOC_Q, record(hits=["D6-A16", "D4-A9"]), accuracy="correct", groundedness="grounded") == []


def test_correct_refusal_is_not_a_failure():
    assert run(DECLINE_Q, record(status="declined"), refusal="correct_refusal") == []


def test_answering_an_unanswerable_question():
    [f] = run(DECLINE_Q, record(status="answered"))
    assert f.suggested == F.NOT_IN_SOURCES


def test_expected_passage_not_retrieved_is_wrong_passage():
    [f] = run(DOC_Q, record(hits=["D6-A12", "D10-P7-w2"]), accuracy="incorrect")
    assert f.suggested == F.WRONG_PASSAGE and "D6-A16" in f.trace["expected_missing"]


def test_never_searching_is_wrong_passage():
    [f] = run(DOC_Q, record(status="declined"), refusal="wrong_refusal")
    assert f.suggested == F.WRONG_PASSAGE and "declined" in f.reasons


def test_passage_supplied_but_answer_wrong_is_not_used():
    [f] = run(DOC_Q, record(hits=["D6-A16", "D4-A9"]), accuracy="partial")
    assert f.suggested == F.NOT_USED


def test_window_passages_count_as_their_article():
    [f] = run(BY_ID["2"], record(hits=["D6-A4-p2"]), accuracy="partial")
    assert f.trace["expected_found"] == "D6-A4" and f.suggested == F.NOT_USED


def test_part_of_the_needed_passages_missing_is_wrong_passage():
    [f] = run(DOC_Q, record(hits=["D4-A9", "D6-A12"]), accuracy="partial", completeness="partial")
    assert f.suggested == F.WRONG_PASSAGE and f.trace["expected_missing"] == "D6-A16"


def test_judge_category_in_scores_file_is_used():
    [f] = run(DOC_Q, record(hits=["D4-A9"]), accuracy="partial", category="The question was ambiguous")
    assert f.category == F.AMBIGUOUS and F.counts([f]) == {F.AMBIGUOUS: 1}


def test_ungrounded_citation_is_a_failure():
    [f] = run(DOC_Q, record(hits=["D6-A16", "D4-A9"]), accuracy="correct", groundedness="ungrounded")
    assert "citation" in f.reasons and f.suggested == F.OTHER and "Citation error" in f.suggested_reason


def test_number_never_computed_is_calculation():
    [f] = run(BY_ID["12"], record(hits=["D9-P8-w1"], unsupported=["2.9"]), accuracy="incorrect")
    assert f.suggested == F.CALCULATION


def test_ambiguous_mark_wins_over_retrieval():
    [f] = run(DOC_Q, record(hits=["D6-A12"]), accuracy="incorrect", ambiguous=True)
    assert f.suggested == F.AMBIGUOUS


def test_largest_category_and_ties_follow_brief_order():
    fails = run(DOC_Q, record(hits=["D6-A12"]), accuracy="incorrect") + \
        run(DECLINE_Q, record()) + run(BY_ID["2"], record(hits=["D6-A4"]), accuracy="partial")
    assert F.largest(fails) == F.WRONG_PASSAGE           # 1-1-1 tie: first in the brief's list
    assert F.largest([]) is None


def test_confirmed_category_overrides_suggestion(tmp_path):
    [f] = run(DOC_Q, record(hits=["D6-A12"]), accuracy="incorrect")
    f.category = F.AMBIGUOUS
    assert F.counts([f]) == {F.AMBIGUOUS: 1}
    F.write_csv([f], tmp_path / "f.csv")
    assert "category (confirmed)" in (tmp_path / "f.csv").read_text(encoding="utf-8-sig")


def test_only_development_questions_are_listed():
    assert {i.split for i in ITEMS} == {"development"}
    assert {i.qid for i in ITEMS} == {"2", "4", "6", "12", "25", "16", "19", "20"}
