"""The document collection (Docs 4-10, docs/sources.md).

The files are not in the repository (MOIC and iGA terms of use forbid
republishing them); they are submitted on Moodle with the datasets and
saved under data/documents/raw/. SHA-256 fingerprints pin the exact copy
the test-set answers were taken from.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "documents" / "raw"
TEXT_DIR = ROOT / "data" / "documents" / "text"


@dataclass(frozen=True)
class Document:
    id: int
    short: str                 # how a citation names it
    title: str
    file: str
    sha256: str
    language: str              # language of the pages used
    method: str                # text_layer | ocr_eng | arabic_repair | transcribed
    pages: tuple[int, ...]     # PDF pages used (1-based)
    version: str               # gazette issue/date or release date
    note: str = ""
    skipped: dict = field(default_factory=dict)
    page_offset: int = 0       # printed page = PDF page + offset (Official Gazette page numbers)

    def printed_page(self, pdf_page: int) -> int:
        return pdf_page + self.page_offset


DOCUMENTS: tuple[Document, ...] = (
    Document(4, "Law 35/2012 (EN)", "Law No. (35) of 2012 with respect to Consumer Protection, "
             "English translation (LLOC; not official, Arabic prevails)",
             "Law_35_2012_Consumer_Protection.pdf",
             "59ef8a250ba3f2b4c0e1b2e1b9fb676c9ea686f4bfb667bfcb922fc970567762",
             "en", "ocr_eng", tuple(range(1, 15)), "2012 text, translation scanned 24/03/2013",
             note="Scanned: no text layer. Does not include the 2026 amendments (Doc 5)."),
    Document(5, "Law 28/2026", "Law No. (28) of 2026 amending certain provisions of Law No. (35) of 2012",
             "Law_28_2026_Amendment.pdf",
             "3d7a39ea43cbf0e6e54fafec6f5fafabb26be98adb0f4d708f2c088843d3171f",
             "ar", "transcribed", (1, 2, 3), "Official Gazette No. 3889, 18/06/2026, pp. 34-36",
             note="Text layer repaired by src/documents/arabic.py, then line order corrected by hand "
                  "against the page images (the PDF mixes up fragments of justified lines).",
             page_offset=33),
    Document(6, "Executive Regulation (MD 66/2014)", "Executive Regulation of Law No. 35 of 2012 "
             "(Ministerial Decision No. 66 of 2014)",
             "Executive_Regulation_Law_35_2012.pdf",
             "59c50dcb074ee4662076a13ecb03461a8356ca59c99bb1e4aca6036a5d4b7d58",
             "ar", "arabic_repair", tuple(range(1, 18)), "Official Gazette No. 3165, 17/07/2014, pp. 11-27",
             page_offset=10),
    Document(7, "MO 51/2007", "Ministerial Order No. 51 of 2007 on sales discount controls",
             "Ministerial_Order_51_2007.pdf",
             "7d1161985bcf0358ae5a875c4cf0c98fb0f501a212e072066b2e367a06177ce4",
             "ar", "transcribed", (1, 2, 3), "Official Gazette No. 2807, 06/09/2007, pp. 10-12",
             note="Scanned Arabic: transcribed by hand and checked against the page images.",
             page_offset=9),
    Document(8, "MO 14/2008", "Ministerial Order No. 14 of 2008 on non-manipulation of advertised prices",
             "Ministerial_Order_14_2008.pdf",
             "add5dfad352d5886e066eef604bc2ec937ca0c85b5f1750babdba01251134e6b",
             "ar", "transcribed", (1,), "Official Gazette No. 2833, 06/03/2008, p. 7",
             note="Scanned Arabic: transcribed by hand and checked against the page image.",
             page_offset=6),
    Document(9, "iGA CPI Sep 2023", "Consumer Price Index, September 2023: monthly release with methodology",
             "CPI_Sep_2023.pdf",
             "bd61bf9d3ffd8e46039ef15e9130a4813bae357a333e963e04edec8ab016d574",
             "en", "text_layer", tuple(range(3, 11)), "released 30/10/2023",
             skipped={(1, 2): "Arabic summary; the same figures are on the English pages 3-4"}),
    Document(10, "Know Your Right (MOIC guidance)", "Know Your Right: guidance for consumers and retailers "
             "on Law No. 35 of 2012 (file dated 12/12/2016; predates Law No. 28 of 2026)",
             "Know_your_right.pdf",
             "7c8822c295a2e3d6740098f67fff2cbafcc8c99bbe0b18f717ae98ba29eff136",
             "en", "text_layer", (7, 8, 9, 10), "file dated 12/12/2016",
             skipped={(1, 2, 11, 12): "covers", (3, 4, 5, 6): "Arabic version of pages 7-10"}),
)

BY_ID = {d.id: d for d in DOCUMENTS}
