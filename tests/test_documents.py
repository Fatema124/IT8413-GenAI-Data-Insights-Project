"""Tests for the document collection (F5): Arabic repair, config and prepared text.

The repair tests use short made-up lines, so they run without the PDFs.
The last tests check the prepared text and are skipped until
`python -m src.documents.prepare` has been run.
"""
from __future__ import annotations

import json
import re

import pytest

from src.documents import arabic
from src.documents.config import DOCUMENTS, TEXT_DIR

LRE, PDF_, RLE = chr(0x202A), chr(0x202C), chr(0x202B)
BAD = chr(0xFFFD)
DAMMA, FATHATAN = chr(0x64F), chr(0x64B)


def repair(line, vocab):
    return arabic.repair_line(line, set(vocab), {})


def test_stray_character_removed():
    assert repair(f"مضل{BAD}ل", {"مضلل"}) == "مضلل"


def test_reversed_lam_alef_fixed_when_ocr_confirms_it():
    assert repair("إعالن", {"إعلان"}) == "إعلان"          # broken "إعلان"
    assert repair("األحوال", {"الأحوال"}) == "الأحوال"


def test_word_kept_when_ocr_does_not_confirm_a_fix():
    stats = {}
    assert arabic.repair_line("الدستور", set(), stats) == "الدستور"
    assert stats["unconfirmed"] == 1


def test_split_and_swapped_word_joined():
    assert repair(f"الوزير ق ار ا{FATHATAN}ر بتحديد", {"الوزير", "قرارا", "بتحديد"}) == "الوزير قرارا بتحديد"
    assert repair("لدى الو ازرة، يمنحون", {"لدى", "الوزارة", "يمنحون"}) == "لدى الوزارة، يمنحون"


def test_lone_alef_lam_is_the_word_la():
    assert repair("بما ال يجاوز", {"بما", "لا", "يجاوز"}) == "بما لا يجاوز"


def test_numbers_in_visual_order_are_restored():
    assert repair(f"مادة ({LRE})7{PDF_}", {"مادة"}) == "مادة (7)"
    assert repair(f"مادة ({LRE}:)23{PDF_}", {"مادة"}) == "مادة (23):"
    assert repair(f"{LRE} -1{PDF_}طبيعة المنتج", {"طبيعة", "المنتج"}) == "1- طبيعة المنتج"


def test_short_vowel_printed_before_its_letter():
    assert repair(f"كما {DAMMA}يستبدل", {"كما", "يستبدل"}) == "كما يستبدل"


def test_digits_are_never_changed():
    line = f"{RLE}مدة أقصاها {LRE}15{PDF_} يوم عمل{PDF_}"
    assert "15" in repair(line, {"مدة", "أقصاها", "يوم", "عمل"})


def test_config_ids_and_fingerprints():
    ids = [d.id for d in DOCUMENTS]
    assert ids == list(range(4, 11))                     # docs/sources.md numbers 4-10
    assert all(re.fullmatch(r"[0-9a-f]{64}", d.sha256) for d in DOCUMENTS)
    assert all(d.pages and d.method in {"text_layer", "ocr_eng", "arabic_repair", "transcribed"} for d in DOCUMENTS)


def _prepared(doc_id):
    f = TEXT_DIR / f"doc{doc_id}.jsonl"
    if not f.exists():
        pytest.skip("prepared text not built (python -m src.documents.prepare)")
    return "\n".join(json.loads(l)["text"] for l in f.open(encoding="utf-8"))


def test_law_35_has_all_25_articles():
    found = {int(n) for n in re.findall(r"Article\s*\((\d+)\)", _prepared(4))}
    assert found == set(range(1, 26))


def test_executive_regulation_has_all_45_articles():
    found = {int(n) for n in re.findall(r"مادة \((\d+)\)", _prepared(6))}
    assert found == set(range(1, 46))


def test_amendment_keeps_its_figures():
    text = _prepared(5)
    for words in ("ألف دينار", "عشرين ألف دينار", "سبعة أيام", "(11 مكررا)"):
        assert words in text


def test_ministerial_orders_hold_their_articles():
    assert all(w in _prepared(7) for w in ("المادة الأولى", "المادة الثامنة", "15 يوما", "ثلاثين يوما"))
    assert all(w in _prepared(8) for w in ("المادة الأولى", "المادة الرابعة", "(18) لسنة 1975"))
