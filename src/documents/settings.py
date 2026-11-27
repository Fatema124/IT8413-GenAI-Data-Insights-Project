"""Retrieval settings for questions over the documents (F5), in one place.

Like src/qa/settings.py, `as_dict()` is shown in the app and stored with
every answer (F10). The intervention (v2) may change exactly one of these.
"""
from __future__ import annotations

VERSION = "v1"

# Local, open-source multilingual model (revised proposal, Section 5): the questions are in
# English and Docs 5-8 are in Arabic. Run through fastembed (ONNX, no PyTorch), so it fits a
# small server; the weights are downloaded once (about 0.22 GB) and no API quota is used.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

TOP_K = 4                 # passages given to the model for one question
MIN_SCORE = 0.40          # below this cosine similarity a passage is not passed on at all.
                          # Set on the development set (27/11/2026): the lowest-scoring expected passage
                          # scored 0.485; out-of-scope questions still reach 0.41-0.49, so refusal relies
                          # on the prompt rules, not on this cut-off (docs/document_retrieval.md).
FOLLOW_AMENDMENTS = True  # with a 2012 article that Law 28/2026 changed, also give the 2026 text

# The intervention (v2, brief 7.5) changes this one setting. The failure analysis of the
# development run (27/11/2026) traced the "wrong passage" failures to the model's short
# keyword query: the user's own question ranked the missing article higher (Q6: Executive
# Regulation Art. 16 rank 9 -> rank 2). v2 also searches with the user's question and adds
# its top passages to those of the model's query (docs/failure_analysis.md).
SEARCH_QUESTION_TOO = False

VERSIONS = {"v1": {"SEARCH_QUESTION_TOO": False}, "v2": {"SEARCH_QUESTION_TOO": True}}


def use_version(version: str) -> None:
    """Switch to the settings of v1 or v2 (evaluation runs; v2 differs from v1 in one setting)."""
    global VERSION
    for name, value in VERSIONS[version].items():
        globals()[name] = value
    VERSION = version


def as_dict() -> dict:
    return {"retrieval_version": VERSION, "embedding_model": EMBEDDING_MODEL, "top_k": TOP_K,
            "min_score": MIN_SCORE, "follow_amendments": FOLLOW_AMENDMENTS,
            "search_question_too": SEARCH_QUESTION_TOO}
