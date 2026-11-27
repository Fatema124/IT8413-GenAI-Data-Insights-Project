"""Repair the Arabic text layer of the Official Gazette PDFs (Docs 5 and 6).

The gazette PDFs keep every digit and article number correctly, but their
text layer breaks Arabic words in four ways:
  * a stray replacement character before some letters;
  * the lam-alef ligature comes out reversed (alef before lam);
  * a few words are split and two letters swapped;
  * a short vowel is printed before its letter, or after a space.
OCR of the same pages reads the words correctly but misreads digits.
So the text layer is kept (digits stay exact) and each broken word is
replaced by the spelling that OCR of the same document confirms.
Words that OCR cannot confirm are kept as they are and counted, so the
quality of every document is measured, not assumed.

Code points are written with chr() so that no invisible character sits in
the source code.
"""
from __future__ import annotations

import itertools
import re

LETTERS = f"{chr(0x621)}-{chr(0x64A)}"            # Arabic letters
MARKS = f"{chr(0x64B)}-{chr(0x652)}"              # short vowels, tanween, shadda, sukun
TATWEEL = chr(0x640)
LRE, RLE, PDF_ = chr(0x202A), chr(0x202B), chr(0x202C)
REPLACEMENT = chr(0xFFFD)
COMMA, SEMICOLON = chr(0x60C), chr(0x61B)
ALEFS = chr(0x627) + chr(0x623) + chr(0x625) + chr(0x622)
LAM = chr(0x644)
ALEF_LAM = chr(0x627) + LAM          # broken form of the word "la" (no, not)
NEGATION = LAM + chr(0x627)

STRIP = re.compile(f"[{MARKS}{TATWEEL}]")
BIDI = re.compile(f"[{chr(0x202A)}-{chr(0x202E)}{chr(0x200E)}{chr(0x200F)}]")
ARABIC_WORD = re.compile(f"[{LETTERS}{MARKS}{TATWEEL}]+")
LAMALEF = re.compile(f"[{ALEFS}]{LAM}")
LTR_RUN = re.compile(f"{LRE}([^{LRE}{PDF_}]*){PDF_}")


def norm(word: str) -> str:
    """Comparison form: no short vowels, no tatweel."""
    return STRIP.sub("", word)


def vocabulary(ocr_text: str) -> set[str]:
    return {norm(w) for w in ARABIC_WORD.findall(ocr_text) if len(norm(w)) > 1}


def _fix_ltr_runs(line: str) -> str:
    """pdftotext writes numbers inside Arabic lines as left-to-right runs in
    visual order: "(" + run(")7") is "(7)", and run(" -1") is the item "1-"."""
    def run(m):
        s = m.group(1)
        if mm := re.fullmatch(f"\\s*([:{MARKS}]*)\\s*\\)\\s*(\\S+?)\\s*", s):   # ")7", ":)23", mark + ")8"
            return f"{mm.group(2)}){':' if ':' in mm.group(1) else ''} "
        if mm := re.fullmatch(r"\s*-(\d+)\s*", s):
            return f" {mm.group(1)}- "
        return s
    return LTR_RUN.sub(run, line)


def _lamalef_candidates(word: str):
    spots = [m.start() for m in LAMALEF.finditer(word)]
    for k in range(1, len(spots) + 1):
        for chosen in itertools.combinations(spots, k):
            w = list(word)
            for i in chosen:
                w[i], w[i + 1] = w[i + 1], w[i]
            yield "".join(w)


def _swap_candidates(word: str):
    for i in range(len(word) - 1):
        yield word[:i] + word[i + 1] + word[i] + word[i + 2:]


def _join(parts: list[str], vocab: set[str]) -> str | None:
    """A split word: join the parts, then allow up to two swapped letter pairs."""
    cat = norm("".join(parts))
    for cand in itertools.chain([cat], _lamalef_candidates(cat), _swap_candidates(cat)):
        if len(cand) > 3 and cand in vocab:
            return cand
        for c2 in _swap_candidates(cand):
            if len(c2) > 3 and c2 in vocab:
                return c2
    return None


def repair_word(word: str, vocab: set[str]) -> tuple[str, str]:
    """Return (spelling, how): how is 'ok', 'fixed' or 'unconfirmed'."""
    base = norm(word.replace(REPLACEMENT, ""))
    if len(base) <= 1:                       # item letters (a), (b) and lone marks
        return base, "ok"
    if base in vocab:
        return base, ("ok" if base == norm(word) else "fixed")
    for cand in _lamalef_candidates(base):
        if cand in vocab:
            return cand, "fixed"
    return base, "unconfirmed"


def repair_line(line: str, vocab: set[str], stats: dict) -> str:
    line = _fix_ltr_runs(line)
    line = BIDI.sub("", line).replace(REPLACEMENT, "")
    line = re.sub(f"(^|\\s)[{MARKS}]+(?=[{LETTERS}])", r"\1", line)   # mark printed before its letter
    line = re.sub(f"\\s+([{MARKS}])", r"\1", line)                     # mark printed after a space
    line = re.sub(f"\\s*([{COMMA}{SEMICOLON}:])\\s*", r"\1 ", line)    # "word ,next" -> "word, next"
    line = re.sub(r"\(\s*\)\s*(\d+)", r"(\1)", line)                 # "( )8" -> "(8)"
    line = re.sub(r"\(\s+", "(", line)
    line = re.sub(r"(^|\s)-(\d+)(?=\S)", r"\1\2- ", line)             # "-5word" -> "5- word"
    line = re.sub(f"(\\d)([{LETTERS}])", r"\1 \2", line)              # "11word" -> "11 word"
    tokens = [NEGATION if t == ALEF_LAM else t for t in line.split()]   # a lone alef-lam is the word "la" (not), broken
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if ARABIC_WORD.fullmatch(tok):
            for n in (3, 2):
                parts = tokens[i:i + n]
                tail = ""
                if parts and (pm := re.fullmatch(f"(.*?)([^{LETTERS}{MARKS}{TATWEEL}]+)", parts[-1])):
                    parts = parts[:-1] + [pm.group(1)]       # keep "," or "." after the last part
                    tail = pm.group(2)
                if (len(parts) == n and all(ARABIC_WORD.fullmatch(p) for p in parts)
                        and any(norm(p) not in vocab or len(norm(p)) <= 2 for p in parts)
                        and (joined := _join(parts, vocab))):
                    out.append(joined + tail)
                    stats["joined"] = stats.get("joined", 0) + 1
                    stats["words"] = stats.get("words", 0) + 1
                    i += n
                    break
            else:
                joined = None
            if joined:
                continue
        m = ARABIC_WORD.search(tok)
        if m:
            fixed, how = repair_word(m.group(0), vocab)
            stats[how] = stats.get(how, 0) + 1
            stats["words"] = stats.get("words", 0) + 1
            if how == "unconfirmed":
                stats.setdefault("unconfirmed_words", []).append(m.group(0))
            tok = tok[:m.start()] + fixed + tok[m.end():]
        out.append(tok)
        i += 1
    return " ".join(out)
