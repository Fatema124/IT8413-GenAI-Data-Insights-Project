"""The documents as plain text for the BASELINE run (brief 7.2: "the relevant sources are placed
directly into the prompt as text and the model answers from that text alone").

    python -m src.documents.baseline            # sizes per document (characters, estimated tokens)
    python -m src.documents.baseline --count    # exact tokens with the Gemini token counter (free call)

`baseline_text()` returns Docs 4-10 exactly as prepared for the tool (the same pages, the same
repaired Arabic and hand transcriptions), each page headed with the citation the tool would use,
so baseline and v1 differ only in how the text reaches the model. The text is built from
data/documents/text/ on each computer and is never written into the repository (MOIC/iGA terms).
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import DOCUMENTS, TEXT_DIR, Document


def pages(doc: Document) -> list[dict]:
    path = TEXT_DIR / f"doc{doc.id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `python -m src.documents.prepare` first.")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def document_text(doc: Document) -> str:
    head = f"=== Document {doc.id}: {doc.title} ({doc.version}) ==="
    if doc.note:
        head += f"\nNote: {doc.note}"
    body = [f"[{doc.short}, p. {doc.printed_page(p['page'])}]\n{p['text'].strip()}" for p in pages(doc)]
    return "\n\n".join([head, *body])


def baseline_text(ids: list[int] | None = None) -> str:
    """Docs 4-10 (or the ids given), in order, as one block of text."""
    chosen = [d for d in DOCUMENTS if ids is None or d.id in ids]
    return "\n\n\n".join(document_text(d) for d in chosen)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true", help="count tokens with the Gemini API (needs the key)")
    a = ap.parse_args(argv)
    client = None
    if a.count:
        from scripts.run_dev_documents import api_key
        from src.qa import settings
        from src.qa.engine import make_client
        client, model = make_client(api_key()), settings.MODEL
    total_chars = total_tokens = 0
    print(f"{'Document':<38} {'chars':>8} {'est. tokens':>12}" + (f" {'tokens (API)':>13}" if client else ""))
    for d in DOCUMENTS:
        text = document_text(d)
        est = len(text) // 4
        line = f"{d.id:>2} {d.short:<35} {len(text):>8,} {est:>12,}"
        if client:
            n = client.models.count_tokens(model=model, contents=text).total_tokens
            total_tokens += n
            line += f" {n:>13,}"
        total_chars += len(text)
        print(line)
    print(f"{'All documents':<38} {total_chars:>8,} {total_chars // 4:>12,}" + (f" {total_tokens:>13,}" if client else ""))
    print("\nEstimate: 4 characters per token (Google's guide). Arabic text usually takes more tokens per "
          "character, so use --count for the figure reported in the evaluation.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
