# Document collection: preparation (F5, step 1)

Lead: Abrar Alawadhi (revised proposal, Section 4). This page records how the seven documents
(Docs 4-10 in [`sources.md`](sources.md)) are turned into clean text, page by page, before they are split
into passages for retrieval. It answers the tutor's notes on document versions and on the preparation
issues listed in the revised proposal (Section 2, "Preparation issues in the documents").

## Where the files go

The MOIC and iGA terms of use do not allow the documents to be republished, so they are **not in the
repository**. They are submitted on Moodle with the datasets (deliverable 6.2). Save them as:

```
data/documents/raw/Law_35_2012_Consumer_Protection.pdf      Doc 4
data/documents/raw/Law_28_2026_Amendment.pdf                Doc 5
data/documents/raw/Executive_Regulation_Law_35_2012.pdf     Doc 6
data/documents/raw/Ministerial_Order_51_2007.pdf            Doc 7
data/documents/raw/Ministerial_Order_14_2008.pdf            Doc 8
data/documents/raw/CPI_Sep_2023.pdf                         Doc 9
data/documents/raw/Know_your_right.pdf                      Doc 10
data/documents/transcribed/doc7_p1.txt ... doc8_p1.txt      hand transcriptions (also on Moodle)
```

Then run `python -m src.documents.prepare`. It checks each file's SHA-256 against
[`src/documents/config.py`](../src/documents/config.py), so a different copy (for example a newer upload on
the Ministry's site) is refused instead of silently changing the answers.

Preparation needs poppler (`pdftotext`, `pdftoppm`) and Tesseract 5 with English and Arabic; it was run
with Tesseract 5.3.4 and poppler 24.02. The app does not need either: it reads only the prepared text.

## How each document is read

| Doc | Pages used | Problem in the PDF | Method | Result |
|---|---|---|---|---|
| 4 Law 35/2012 (EN) | 1-14 | Scanned, no text layer | Tesseract OCR (English), 300 dpi | All 25 articles found, in order |
| 5 Law 28/2026 | 1-3 | Arabic text layer breaks words (below) and mixes up fragments of justified lines | Text layer repaired as for Doc 6 (98.1% of words confirmed), then line order corrected by hand against the page images | All three articles and the replaced texts of Articles 1, 22, 23, 5(c), 8(a)(1) and 11 bis |
| 6 Executive Regulation | 1-17 | Same as Doc 5 | Same as Doc 5 | 4,156 words: 3,824 correct, 281 repaired, 51 not confirmed (98.8%); all 45 articles found |
| 7 MO 51/2007 | 1-3 | Scanned Arabic; OCR misreads digits | Transcribed by hand from the page images | 8 articles + the application form |
| 8 MO 14/2008 | 1 | Same as Doc 7 | Same as Doc 7 | 4 articles |
| 9 iGA CPI Sep 2023 | 3-10 | None (clean text layer) | Text layer | Pages 1-2 are the Arabic summary of the same figures, so they are skipped |
| 10 Know Your Right | 7-10 | None | Text layer | Pages 3-6 are the Arabic version of 7-10; pages 1-2, 11-12 are covers |

Running headers and footers (gazette issue line, LLOC header, website footer, page numbers) are removed;
the gazette issue and date are kept in `config.py` instead, so every citation can name the version.

## Repairing the Arabic text layer (Doc 6, and the first pass of Doc 5)

The gazette PDFs store every digit correctly, which matters most here: fines, day counts and article
numbers. Their Arabic words, however, come out broken in four ways:

1. a stray replacement character before some letters;
2. the lam-alef ligature reversed (alef before lam), e.g. the word for "announcement" and the word "la" (not);
3. a few words split in two or three parts with two letters swapped (e.g. the word for "decision");
4. short vowels printed before their letter or after a space.

Tesseract reads the same pages with the words right but the digits wrong. So
[`src/documents/arabic.py`](../src/documents/arabic.py) keeps the text layer and replaces a broken word only
with a spelling that Tesseract found somewhere in the same document. A word that cannot be confirmed is kept
as it is and counted. Short vowels are dropped (legal text does not need them for retrieval). Numbers are never
taken from OCR.

The words still not confirmed are mostly correct words that OCR missed (for example the words for
"constitution" or "supplier"); a few are decorative headings printed with stretched letters. The counts above
are in `data/documents/text/quality.json`, rebuilt on every run.

## Hand transcription (Docs 5, 7 and 8)

The two ministerial orders are short scanned pages. OCR read the words but changed the numbers (for example
"(18) of 1975" became "(18) of 19176"), so they were transcribed from the page images instead. Eastern Arabic
digits are written as 0-9. The transcriptions were made with help from Claude (see the AI-use log) and must be
checked line by line against the page images by a group member before the evaluation; the check is recorded
below.

| Transcription | Checked against the image by | Date |
|---|---|---|
| doc7_p1.txt, doc7_p2.txt, doc7_p3.txt | Abrar Alawadhi | 26/11/2026 |
| doc8_p1.txt | Abrar Alawadhi | 26/11/2026 |
| doc5_p1.txt, doc5_p2.txt, doc5_p3.txt | Abrar Alawadhi | 26/11/2026 |

## Checks

`tests/test_documents.py` (13 tests): the repair rules on made-up lines (they run without the PDFs), the
config, and, once the text is prepared, that Law 35 has articles 1-25, the Executive Regulation articles 1-45,
the amendment keeps its figures (BD 1,000 and BD 20,000, seven days, Article 11 bis) and both orders hold all
their articles.

## Size

The prepared text is 72,502 characters in total (about 18,000 tokens at four characters per token, the rule
used in the proposal; Arabic usually needs more tokens per character, so the real count should be measured
with the Gemini API's token counter before the baseline run).

## Known limits

- Doc 4 is a 2013 translation of the 2012 text; it does not include Law 28/2026. Applying the amendment is
  step 3.2 (passages).
- Doc 10 (2016) predates the 2026 amendment and counts the 15-day return period from purchase, while
  Article 14 of the Executive Regulation counts it from receipt of the goods.
- Doc 9 explains September 2023 only; it must not be used to explain movements in 2024-2026.
