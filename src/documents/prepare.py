"""Prepare the document collection: one clean text per page, with a quality record.

    python -m src.documents.prepare

Run once after saving the PDFs under data/documents/raw/ (see README).
Needs poppler (pdftotext, pdftoppm) and Tesseract 5 with the 'eng' and 'ara'
languages; the app itself does not, because it only reads the prepared text.

Writes data/documents/text/doc<ID>.jsonl (one line per page) and
data/documents/text/quality.json. Both are rebuilt from the PDFs, so neither
is committed.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import arabic
from .config import DOCUMENTS, RAW_DIR, TEXT_DIR, Document

TRANSCRIBED_DIR = RAW_DIR.parent / "transcribed"
DPI = 300

# Running headers and footers that carry no content.
NOISE = [
    re.compile(r"^\s*Public Document\s*$"),
    re.compile(r"^\s*\d{1,3}\s*$"),                                   # page number
    re.compile(r"^\s*[A-Za-z]{1,3}\s*$"),                              # OCR specks ("Vv", "Ca")
    re.compile(r"legalaffairs\.gov\.bh", re.I),
    re.compile(r"Legislation\s*&\s*Legal Opinion Commission", re.I),
    re.compile(r"هيئة التشريع والإفتاء القانوني"),
    re.compile(r"^\s*العدد\s*:?\s*-?\s*\d{4}.*(يوليو|يونيو|مارس|سبتمبر)"),  # gazette running header
]


COMMON = {"the", "of", "and", "to", "in", "or", "for", "by", "with", "shall", "be", "any", "on",
          "law", "article", "chapter", "consumer", "is", "as", "this", "that", "from", "its"}


def _drop_logo_line(text: str) -> str:
    """The LLOC letterhead (Arabic logo text and "Kingdom of Bahrain") is read by
    English OCR as one or two lines of nonsense at the top of every page.
    In the first three lines of a page, a line is dropped when it names the
    letterhead or holds fewer than two common English words (headings and numbered items excepted)."""
    lines = text.splitlines()
    seen = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        seen += 1
        if seen > 3:
            break
        words = {w.lower() for w in re.findall(r"[A-Za-z]+", line)}
        heading = words & {"law", "article", "chapter"} or re.match(r"\s*(\d+\.|\([a-z]\))", line)
        if ("kingdom" in words and "bahrain" in words and len(words) < 10) or (
                not heading and len(words & COMMON) < 2):
            lines[i] = ""
    return "\n".join(lines)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def text_layer(pdf: Path, page: int, layout: bool = True) -> str:
    return _run(["pdftotext", *(["-layout"] if layout else []), "-f", str(page), "-l", str(page),
                 str(pdf), "-"])


def ocr(pdf: Path, page: int, lang: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        stem = Path(tmp) / "p"
        _run(["pdftoppm", "-r", str(DPI), "-png", "-singlefile", "-f", str(page), "-l", str(page),
              str(pdf), str(stem)])
        return _run(["tesseract", f"{stem}.png", "-", "-l", lang, "--psm", "4" if lang == "ara" else "3"])


def clean(text: str) -> str:
    """Drop running headers/footers; join wrapped lines into paragraphs."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200e\u200f]", "", text)   # control and direction marks
    lines = [l.rstrip() for l in text.splitlines()]
    lines = [l for l in lines if not any(p.search(l) for p in NOISE)]
    paras, cur = [], []
    for l in lines:
        s = re.sub(r"\s+", " ", l).strip()
        if not s:
            if cur:
                paras.append(" ".join(cur)); cur = []
            continue
        # a new article, bullet or numbered item starts a new paragraph
        if cur and re.match(r"^(Article\s*\(|مادة\s*\(|المادة\s|•|\(?[a-z]\)\s|\d+[.-]\s)", s):
            paras.append(" ".join(cur)); cur = []
        cur.append(s)
    if cur:
        paras.append(" ".join(cur))
    return "\n".join(p.replace("‘", "'").replace("’", "'") for p in paras)


def prepare(doc: Document) -> tuple[list[dict], dict]:
    pdf = RAW_DIR / doc.file
    if not pdf.exists():
        raise FileNotFoundError(f"Doc {doc.id}: save {doc.file} in {RAW_DIR}")
    got = sha256(pdf)
    if got != doc.sha256:
        raise ValueError(f"Doc {doc.id}: {doc.file} is not the group's copy (SHA-256 {got[:12]}...)")

    quality: dict = {"doc": doc.id, "method": doc.method, "pages": len(doc.pages)}
    vocab: set[str] = set()
    if doc.method == "arabic_repair":
        for p in doc.pages:
            vocab |= arabic.vocabulary(ocr(pdf, p, "ara"))
    stats: dict = {}
    pages = []
    for p in doc.pages:
        if doc.method == "text_layer":
            raw = text_layer(pdf, p)
        elif doc.method == "ocr_eng":
            raw = _drop_logo_line(ocr(pdf, p, "eng"))
        elif doc.method == "arabic_repair":
            raw = "\n".join(arabic.repair_line(l, vocab, stats) for l in text_layer(pdf, p, layout=False).splitlines())
        elif doc.method == "transcribed":
            f = TRANSCRIBED_DIR / f"doc{doc.id}_p{p}.txt"
            if not f.exists():
                raise FileNotFoundError(f"Doc {doc.id} page {p}: missing transcription {f.name}")
            raw = f.read_text(encoding="utf-8")
        else:
            raise ValueError(doc.method)
        pages.append({"doc": doc.id, "page": p, "lang": doc.language, "text": clean(raw)})

    if doc.method == "arabic_repair":
        words = stats.get("words", 0)
        unconf = stats.get("unconfirmed_words", [])
        quality.update(words=words, already_correct=stats.get("ok", 0),
                       repaired=stats.get("fixed", 0) + stats.get("joined", 0),
                       unconfirmed=len(unconf),
                       confirmed_share=round(1 - len(unconf) / words, 4) if words else None,
                       unconfirmed_sample=sorted(set(unconf))[:40])
    quality["characters"] = sum(len(pg["text"]) for pg in pages)
    return pages, quality


def main(argv: list[str] | None = None) -> int:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    report = []
    for doc in DOCUMENTS:
        try:
            pages, q = prepare(doc)
        except (FileNotFoundError, ValueError) as e:
            print(f"  ✗ {e}")
            report.append({"doc": doc.id, "error": str(e)})
            continue
        with open(TEXT_DIR / f"doc{doc.id}.jsonl", "w", encoding="utf-8") as fh:
            for pg in pages:
                fh.write(json.dumps(pg, ensure_ascii=False) + "\n")
        extra = f", {q['confirmed_share']:.1%} of Arabic words confirmed by OCR" if "confirmed_share" in q else ""
        print(f"  ✓ Doc {doc.id} {doc.short}: {q['pages']} pages, {q['characters']:,} characters{extra}")
        report.append(q)
    (TEXT_DIR / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if any("error" in r for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
