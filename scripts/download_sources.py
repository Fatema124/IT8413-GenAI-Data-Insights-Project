"""Download the sources that may not be stored in the public repository.

    python -m scripts.download_sources

Datasets 1-2 (Bahrain Open Government Data License) are committed in
data/raw/. Dataset 3, iGA's "Consumer Price Index - Tables, January 2020 -
October 2023" (XLSX), is protected by the iGA website Terms of Use, so it is
not committed; this script fetches it from iGA instead (proposal Section 2,
"Repository and licence handling").

After downloading, the file is fingerprinted (SHA-256) and compared with the
copy the group used, so a changed file on iGA's site is reported, not
silently used.

Documents 4-10 (MOIC and iGA terms of use) are not committed either. Each one
is looked for in data/documents/raw/ and its SHA-256 compared with the copy
the test-set answers were taken from (src/documents/config.py). Doc 10 has a
direct link and is downloaded; Docs 4-9 sit behind MOIC/iGA listing pages, so
the script says where to get each one and under which file name to save it.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

import pandas as pd

from src.pipeline import config


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(path: Path) -> bool:
    """Same version as the group's copy, and readable with the expected sheets."""
    sheets = pd.ExcelFile(path).sheet_names
    needed = [s for s in (config.D3_WEIGHTS_SHEET, config.D3_HISTORY_SHEET) if s]
    missing = [s for s in needed if s not in sheets]
    if missing:
        print(f"  Sheets {missing} not found (sheets: {sheets}). Not the expected file.")
        return False
    digest = sha256(path)
    if digest == config.D3_SHA256:
        print("  Same version as the group's copy (SHA-256 matches).")
    else:
        print("  WARNING: the file differs from the group's copy. "
              "Run the pipeline and check_dev_answers before using it.")
    return True


def ensure_dataset3(verbose: bool = True) -> tuple[bool, str]:
    """Make sure Dataset 3 is in data/raw/: use it if present, else download it from iGA.

    Returns (available, message). Used by this script and by the app when it
    starts on a server where the file is not present (e.g. Streamlit Cloud).
    A downloaded file that is not the expected workbook is deleted again.
    """
    say = print if verbose else (lambda *a, **k: None)
    target = config.RAW_DIR / config.RAW_FILES["D3"]
    say(f"Dataset 3 -> {target}")
    if target.exists():
        say("  Already present.")
        return check(target), "present"
    if not config.D3_DOWNLOAD_URL:
        say("  No direct link set. Download it by hand:\n"
            f"  1. Open {config.D3_PAGE_URL}\n"
            "  2. Economic Statistics -> Consumer Price Index -> September 2023 release\n"
            "  3. Download 'Consumer Price Index - Tables, January 2020 - October 2023' (XLSX)\n"
            f"  4. Save it as {target}")
        return False, "no download link set"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(config.D3_DOWNLOAD_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            target.write_bytes(resp.read())
        say(f"  Downloaded {target.stat().st_size:,} bytes from iGA.")
    except Exception as exc:          # network blocked, site down, moved file ...
        target.unlink(missing_ok=True)
        say(f"  Download failed: {exc}")
        return False, f"download failed ({exc.__class__.__name__})"
    try:
        ok = check(target)
    except Exception as exc:          # not an Excel workbook (e.g. an HTML error page)
        say(f"  The downloaded file is not the expected workbook: {exc}")
        ok = False
    if not ok:
        target.unlink(missing_ok=True)
        return False, "downloaded file was not the expected workbook"
    return True, "downloaded"


# Documents 4-10: direct file links, where the publisher gives a stable one.
DOCUMENT_URLS = {10: "https://moic.gov.bh/sites/default/files/2021-09/Know%20your%20right.pdf"}


def _document_page(n: int) -> str:
    """The listing page from docs/sources.md (src/pipeline/config.py) for document n."""
    return next(d["url"] for d in config.DOCUMENTS if d["n"] == n)


def ensure_documents(verbose: bool = True) -> dict[int, str]:
    """Check Documents 4-10 in data/documents/raw/; download Doc 10, explain the others.

    Returns {document number: "same" | "different" | "downloaded" | "missing" | "failed"}.
    A file with a different fingerprint is kept but reported: the passages and the
    test-set answers were made from the group's copy.
    """
    from src.documents.config import DOCUMENTS, RAW_DIR
    say = print if verbose else (lambda *a, **k: None)
    status: dict[int, str] = {}
    for doc in DOCUMENTS:
        target = RAW_DIR / doc.file
        say(f"Document {doc.id} ({doc.short}) -> {target}")
        if not target.exists() and doc.id in DOCUMENT_URLS:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                req = urllib.request.Request(DOCUMENT_URLS[doc.id], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    target.write_bytes(resp.read())
                say(f"  Downloaded {target.stat().st_size:,} bytes.")
                status[doc.id] = "downloaded"
            except Exception as exc:          # network blocked, site down, moved file ...
                target.unlink(missing_ok=True)
                say(f"  Download failed: {exc}")
                status[doc.id] = "failed"
        if not target.exists():
            say(f"  Missing. Download '{doc.title}' ({doc.version}) from\n"
                f"  {_document_page(doc.id)}\n  and save it as {target}")
            status.setdefault(doc.id, "missing")
            continue
        if sha256(target) == doc.sha256:
            say("  Same version as the group's copy (SHA-256 matches).")
            status[doc.id] = "same" if status.get(doc.id) != "downloaded" else "downloaded"
        else:
            say("  WARNING: the file differs from the group's copy (SHA-256). "
                "Prepare it again and run scripts.check_retrieval_dev before using it.")
            status[doc.id] = "different"
    return status


def main() -> int:
    ok, _ = ensure_dataset3()
    print()
    docs = ensure_documents()
    ready = sum(v in ("same", "downloaded") for v in docs.values())
    print(f"\nDocuments ready: {ready}/{len(docs)}. Then: python -m src.documents.prepare "
          "and python -m src.documents.passages")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
