"""Split the prepared documents into passages for retrieval (F5).

    python -m src.documents.passages

Legal texts (Docs 4-8) are split at their articles, because an article is
what a citation names and what an analyst checks. A long article is split
into parts at paragraph breaks, and every part keeps the article label.
The CPI release and the Ministry's guidance (Docs 9-10) have no articles,
so they are split into windows of whole paragraphs on one page, with one
paragraph of overlap so that a sentence is never cut away from its context.

Law No. 28 of 2026 changes the 2012 law. Its passages say which article
they amend, and the 2012 articles it replaces or changes are marked, so the
retriever can always show the text in force next to the old one (3.4).

Writes data/documents/passages.jsonl (rebuilt from the prepared text, not committed).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field

from .config import BY_ID, DOCUMENTS, TEXT_DIR

PASSAGES_FILE = TEXT_DIR.parent / "passages.jsonl"

MAX_CHARS = 1600        # a longer article is split into parts
WINDOW_CHARS = 900      # target size of a window in Docs 9-10

ORDINALS = {"الأولى": 1, "الثانية": 2, "الثالثة": 3, "الرابعة": 4, "الخامسة": 5,
            "السادسة": 6, "السابعة": 7, "الثامنة": 8, "التاسعة": 9, "العاشرة": 10}

# How Law No. 28 of 2026 (Doc 5) changes Law No. 35 of 2012 (Doc 4), from its Articles 1 and 2.
AMENDMENTS_2026 = {
    "1": ("amended", "The definition of 'competent administrative authority' was replaced by Law No. 28 of 2026."),
    "5": ("amended", "Law No. 28 of 2026 added paragraph (c): a Cabinet-approved ministerial resolution will "
                     "regulate licences for promotions, discounts and clearance sales, and their fees."),
    "8": ("amended", "Law No. 28 of 2026 added item (1) to paragraph (a) (delivery as agreed with the "
                     "consumer) and renumbered the other items."),
    "22": ("amended", "The first paragraph was replaced by Law No. 28 of 2026 (publication of the judgement "
                      "in licensed media instead of two daily newspapers)."),
    "23": ("superseded", "Replaced in full by Law No. 28 of 2026 (new administrative sanctions and fines)."),
}


@dataclass
class Passage:
    id: str                    # e.g. "D6-A14", "D6-A14-p2", "D9-P6-w1"
    doc: int
    source: str                # short name used in citations
    label: str                 # English label: "Article 14", "Page 6"
    pages: list[int]           # printed pages (Official Gazette page numbers for Docs 5-8)
    lang: str
    text: str
    version: str
    status: str = "in force"   # in force | amended | superseded | amending | guidance | statistics
    note: str = ""
    links: list[str] = field(default_factory=list)   # passages to show with this one

    def citation(self) -> str:
        pages = f"p. {self.pages[0]}" if len(self.pages) == 1 else f"pp. {self.pages[0]}-{self.pages[-1]}"
        return f"{self.source}, {self.label} ({pages})"


def load_pages(doc_id: int) -> list[dict]:
    with open(TEXT_DIR / f"doc{doc_id}.jsonl", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def _lines_with_pages(doc_id: int):
    for pg in load_pages(doc_id):
        for line in pg["text"].split("\n"):
            if line.strip():
                yield pg["page"], line.strip()


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n"):
        if cur and len(cur) + len(para) > MAX_CHARS:
            parts.append(cur); cur = ""
        cur = f"{cur}\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


def _heading(doc_id: int, line: str) -> str | None:
    """The article a line opens, as a key ("14", "11 bis", "preamble-2"), or None."""
    if doc_id == 4:
        m = re.match(r"Article\s*\((\d+)\)", line)
        return m.group(1) if m else None
    if doc_id == 5:
        if m := re.match(r"مادة \((\d+)( مكررا)?\)", line):
            return f"{m.group(1)} bis" if m.group(2) else m.group(1)
        if m := re.match(r"المادة (\S+)", line):
            return f"law-{ORDINALS.get(m.group(1), m.group(1))}"
        return None
    if doc_id == 6:
        if m := re.match(r"مادة \((\d+)\)", line):
            return m.group(1)
        if m := re.match(r"المادة (\S+)", line):        # articles of the issuing decision, page 1
            return f"decision-{ORDINALS.get(m.group(1), m.group(1))}"
        return None
    if doc_id in (7, 8):
        if m := re.match(r"المادة (\S+)", line):
            return str(ORDINALS.get(m.group(1), m.group(1)))
        if line.startswith("مملكة البحرين"):        # the annexed application form (Doc 7, page 3)
            return "form"
        return None
    return None


def _label(doc_id: int, key: str) -> str:
    if key == "preamble":
        return "Preamble"
    if key == "form":
        return "Application form (annex)"
    if key.startswith("law-"):
        return f"Article {key[4:]} of the amending law"
    if key.startswith("decision-"):
        return f"Article {key[9:]} of Ministerial Decision 66/2014"
    if doc_id == 5:
        return f"Article {key} of Law 35/2012 as amended"
    return f"Article {key}"


def legal_passages(doc_id: int) -> list[Passage]:
    doc = BY_ID[doc_id]
    blocks: list[tuple[str, list[int], list[str]]] = [("preamble", [], [])]
    for page, line in _lines_with_pages(doc_id):
        key = _heading(doc_id, line)
        if key is not None:
            blocks.append((key, [], []))
        k, pages, lines = blocks[-1]
        if page not in pages:
            pages.append(page)
        lines.append(line)
    out = []
    for key, pages, lines in blocks:
        if not lines:
            continue
        parts = _split_long("\n".join(lines))
        for n, text in enumerate(parts, 1):
            pid = f"D{doc_id}-A{key.replace(' ', '')}" + (f"-p{n}" if len(parts) > 1 else "")
            label = _label(doc_id, key) + (f", part {n} of {len(parts)}" if len(parts) > 1 else "")
            out.append(Passage(pid, doc_id, doc.short, label, [doc.printed_page(p) for p in pages],
                               doc.language, text, doc.version))
    return out


def window_passages(doc_id: int) -> list[Passage]:
    doc = BY_ID[doc_id]
    status = "statistics" if doc_id == 9 else "guidance"
    out = []
    for pg in load_pages(doc_id):
        paras = [p for p in pg["text"].split("\n") if p.strip()]
        start, w = 0, 1
        while start < len(paras):
            end, size = start, 0
            while end < len(paras) and (size < WINDOW_CHARS or end == start):
                size += len(paras[end]); end += 1
            text = "\n".join(paras[start:end])
            out.append(Passage(f"D{doc_id}-P{pg['page']}-w{w}", doc_id, doc.short,
                               f"excerpt {w}", [pg["page"]], doc.language, text,
                               doc.version, status))
            if end >= len(paras):
                break
            start, w = max(end - 1, start + 1), w + 1        # one paragraph of overlap
    return out


def link_amendments(passages: list[Passage]) -> None:
    """Mark the 2012 articles that Law No. 28 of 2026 changed, and link both ways."""
    by_id = {p.id: p for p in passages}
    for p in passages:
        if p.doc == 5 and not p.id.startswith("D5-Alaw") and p.id != "D5-Apreamble":
            art = p.id.split("-A")[1].split("-")[0].replace("bis", " bis")
            p.status = "amending"
            target = f"Law 35/2012 Article {art}" + (" (new article)" if "bis" in art else "")
            p.note = f"Text in force since 2026: replaces or adds to {target}."
            for q in passages:
                if q.doc == 4 and q.id.split("-A")[1].split("-")[0] == art:
                    q.links.append(p.id); p.links.append(q.id)
        if p.doc == 4:
            art = p.id.split("-A")[1].split("-")[0]
            if art in AMENDMENTS_2026:
                p.status, p.note = AMENDMENTS_2026[art]
    # The Ministry's 2016 guidance predates the 2026 amendments.
    for p in passages:
        if p.doc == 10:
            p.note = "Guidance dated 2016: it predates Law No. 28 of 2026; the law and regulation prevail."
        if p.doc == 7 and p.id != "D7-Aform":
            p.note = ("Law No. 28 of 2026 added Article 5(c) to Law 35/2012: a future resolution will regulate "
                      "sale licences; no such resolution is in the sources.")
        if p.doc == 9:
            p.note = "Explains September 2023 only; it says nothing about later months."
    assert all(l in by_id for p in passages for l in p.links)


def build() -> list[Passage]:
    passages: list[Passage] = []
    for doc in DOCUMENTS:
        passages += legal_passages(doc.id) if doc.id <= 8 else window_passages(doc.id)
    link_amendments(passages)
    ids = [p.id for p in passages]
    assert len(ids) == len(set(ids)), "duplicate passage ids"
    return passages


def main() -> int:
    passages = build()
    with open(PASSAGES_FILE, "w", encoding="utf-8") as fh:
        for p in passages:
            fh.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
    for doc in DOCUMENTS:
        mine = [p for p in passages if p.doc == doc.id]
        print(f"  Doc {doc.id} {doc.short}: {len(mine)} passages, "
              f"longest {max(len(p.text) for p in mine):,} characters")
    print(f"  {len(passages)} passages -> {PASSAGES_FILE.relative_to(TEXT_DIR.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
