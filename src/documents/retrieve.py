"""Find the passages that answer a question (F5), with citations.

    from src.documents.retrieve import Retriever
    hits = Retriever.load().search("How long does a supplier have to provide spare parts?")

Each hit carries the passage, its citation and its similarity score, so the
app can show which passages the answer is based on (F5 "available for
verification") and the evaluation can trace a failure to retrieval (brief 7.4).
When a hit is a 2012 article that Law No. 28 of 2026 replaced or changed, the
2026 text is added next to it (FOLLOW_AMENDMENTS), so the model is never left
with only the old wording.

The passage embeddings are cached in data/documents/index.npz and rebuilt
when the passages or the model change.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from . import settings
from .passages import PASSAGES_FILE, Passage

INDEX_FILE = PASSAGES_FILE.parent / "index.npz"


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


class FastEmbedder:
    """The multilingual sentence-transformers model, run locally with fastembed."""

    def __init__(self, model: str = settings.EMBEDDING_MODEL):
        from fastembed import TextEmbedding      # imported here so tests do not need it
        self.name = model
        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(list(self._model.embed(list(texts))), dtype=np.float32)


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


def passage_text_for_embedding(p: Passage) -> str:
    """What is embedded: the citation label in English, then the passage itself."""
    return f"{p.source}, {p.label}.\n{p.text}"


@dataclass
class Hit:
    passage: Passage
    score: float
    rank: int                 # 1 = best; 0 for a passage added through an amendment link
    reason: str = "retrieved"  # retrieved | amendment | question (v2: found by the user's question)

    def to_record(self) -> dict:
        p = self.passage
        return {"id": p.id, "citation": p.citation(), "score": round(self.score, 4), "rank": self.rank,
                "reason": self.reason, "status": p.status, "lang": p.lang}


class Retriever:
    def __init__(self, passages: list[Passage], embedder: Embedder, vectors: np.ndarray | None = None):
        self.passages = passages
        self.by_id = {p.id: p for p in passages}
        self.embedder = embedder
        self.vectors = _unit(vectors if vectors is not None
                             else embedder.embed([passage_text_for_embedding(p) for p in passages]))

    @classmethod
    def load(cls, embedder: Embedder | None = None) -> "Retriever":
        passages = load_passages()
        embedder = embedder or FastEmbedder()
        key = _cache_key(passages, embedder.name)
        if INDEX_FILE.exists():
            cached = np.load(INDEX_FILE, allow_pickle=False)
            if str(cached["key"]) == key:
                return cls(passages, embedder, cached["vectors"])
        r = cls(passages, embedder)
        np.savez(INDEX_FILE, key=key, vectors=r.vectors)
        return r

    def search_both(self, query: str, question: str) -> list[Hit]:
        """v2: the passages for the model's query, then those for the user's question that are not
        already there (each search with the same top_k and min_score; reason "question")."""
        hits = self.search(query)
        have = {h.passage.id for h in hits}
        for h in self.search(question):
            if h.passage.id not in have:
                hits.append(Hit(h.passage, h.score, h.rank, "question" if h.reason == "retrieved" else h.reason))
                have.add(h.passage.id)
        return hits

    def search(self, question: str, top_k: int = settings.TOP_K, min_score: float = settings.MIN_SCORE,
               follow_amendments: bool = settings.FOLLOW_AMENDMENTS) -> list[Hit]:
        q = _unit(self.embedder.embed([question]))[0]
        scores = self.vectors @ q
        order = np.argsort(-scores)[:top_k]
        hits = [Hit(self.passages[i], float(scores[i]), r) for r, i in enumerate(order, 1)
                if scores[i] >= min_score]
        if follow_amendments:
            have = {h.passage.id for h in hits}
            for h in list(hits):
                if h.passage.status in ("amended", "superseded"):
                    for link in h.passage.links:
                        if link not in have:
                            hits.append(Hit(self.by_id[link], float(scores[self.passages.index(self.by_id[link])]),
                                            0, "amendment"))
                            have.add(link)
        return hits


def load_passages() -> list[Passage]:
    if not PASSAGES_FILE.exists():
        raise FileNotFoundError("Run `python -m src.documents.prepare` and `python -m src.documents.passages` first.")
    with open(PASSAGES_FILE, encoding="utf-8") as fh:
        return [Passage(**json.loads(line)) for line in fh]


def _cache_key(passages: list[Passage], model: str) -> str:
    h = hashlib.sha256(model.encode())
    for p in passages:
        h.update(p.id.encode()); h.update(passage_text_for_embedding(p).encode())
    return h.hexdigest()
