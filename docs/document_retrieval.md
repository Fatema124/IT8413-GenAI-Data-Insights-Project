# Questions over the documents (F5), refusal (F7): design decisions

Lead: Abrar Alawadhi (revised proposal, Section 4). This page records how passages are made, found, cited
and shown, and why, for the report's design section (brief Section 3: prompting, retrieval, tool use) and
for reproducing every result. Preparing the text from the PDFs is described in
[`document_preparation.md`](document_preparation.md).

## How a document question is answered

1. The question goes to Gemini with the data tools (F4) **and** one more tool, `search_documents`, and the
   document rules added to the system prompt ([`src/documents/prompt.py`](../src/documents/prompt.py)).
2. Gemini calls `search_documents(query=...)` in English.
3. The app embeds the query with a local multilingual model, compares it with every passage and returns the
   best passages ([`src/documents/retrieve.py`](../src/documents/retrieve.py)), each with its citation, its
   status and its full text ([`src/documents/tool.py`](../src/documents/tool.py)).
4. Gemini writes the answer in English with a citation after each statement, or declines (F7).
5. Under the answer, *Document passages used* lists every returned passage with its citation, its status and
   its full text, Arabic shown right to left ([`src/documents/display.py`](../src/documents/display.py)), so a
   supervisor can check the answer against the passage (F5: "available for verification").
6. The answer record keeps, for each search, the query and the rank and similarity score of every passage
   (`Answer.retrieval`), for the query log (F10) and for tracing failures to retrieval (brief 7.4).

## Decisions and reasons

| Decision | Reason |
|---|---|
| **Passages are articles** for the legal texts (Docs 4-8); a long article is split into parts at paragraph breaks (at most 1,600 characters), each keeping the article label | A citation names an article, and the test set's source locations are articles. An article is also the unit a reader checks. 125 passages in all. |
| **Windows of whole paragraphs on one page** for the CPI release and the guidance (Docs 9-10), about 900 characters, one paragraph of overlap | They have no articles. A window never crosses a page, so its citation names one page; the overlap keeps a sentence with its context. |
| **Official Gazette page numbers** in citations for Docs 5-8 (PDF page + offset in `config.py`) | The test set cites the gazette pages (for example Executive Regulation Article 14, pp. 17-18), and a reader looks those up. |
| **Law No. 28 of 2026 linked to the 2012 articles it changes** (Articles 1, 5, 8, 22 amended; 23 replaced in full; 11 bis new) | Tutor's note: "the law has been edited/updated since that copy was printed". A retrieved 2012 article that was changed always brings the 2026 text with it (`FOLLOW_AMENDMENTS`), and the prompt says to state the rule in force. Test question 5 depends on this. |
| **The Arabic documents are not translated** | The revised proposal states that the Arabic originals prevail. A machine translation would have to be checked in full and could differ from the original. The model answers in English and the original passage is shown for checking. |
| **Local multilingual embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` through fastembed (ONNX) | English questions over Arabic passages need a model that places both languages in one space (revised proposal, Section 5). Running it locally uses no API quota. fastembed avoids PyTorch, so the app still fits Streamlit Community Cloud. |
| **What is embedded**: the citation label in English, then the passage | Gives Arabic passages an English anchor ("Executive Regulation, Article 14"). |
| **Top 4 passages, minimum similarity 0.40** | Most document questions need one to three articles. The minimum was set on the development questions (below): it keeps every expected passage (lowest 0.485) and drops weak matches. It cannot separate answerable from out-of-scope questions (those also score 0.41-0.49), so refusal relies on the prompt rules (rule 20) and the data tools, not on the score. |
| **One tool, called by the model**, not retrieval before every question | Data questions need no passages; combined questions (F6) need both. Letting the model call the tool, like the data tools, keeps one loop and records every search. |
| **Same tool contract as the data tools** (`status` ok / not_available / bad_input / error) | The engine runs it like any other tool, and "not available" leads to the same refusal sentence (F7) that the evaluation counts. |
| **Numbers written in Arabic words are listed with the passage** (`numbers_in_words`, for example the Arabic words for "fifteen" = 15) | The app's number check (`src/qa/numbers.py`) accepts a number only if a tool result holds it. Arabic legal texts write periods and amounts in words, so without this a correct "15 days" would be flagged. |
| **Similarity scores are logged, not sent as evidence** | Every number in a tool result counts as evidence for the number check; a score is not a fact from the sources. |
| **Document rules kept in a separate prompt block** (`docs-v1`) | The data prompt (v1) stays exactly as measured; the stored prompt version is `v1+docs-v1`. |

## Refusal (F7)

The model declines with the same sentence as for the data ("This is not available in the sources.") when
the tool finds nothing close enough, or when the passages it finds do not state what the question asks.
The prompt also forbids filling a gap from general knowledge of consumer law, using the September 2023
release to explain other months (test question 17), and following the 2016 guidance where the law or the
regulation says otherwise.

## Settings (shown in the app and stored with every answer)

From [`src/documents/settings.py`](../src/documents/settings.py):

| Setting | v1 value |
|---|---|
| Embedding model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Passages returned (top k) | 4 |
| Minimum similarity | 0.40 |
| Follow 2026 amendments | yes |
| Document prompt | docs-v1 |

Candidates for the intervention (brief 7.5), depending on what the failure analysis finds: top k, the
minimum similarity, passage size, or a second (lexical) ranking for the English passages.

## Development check with the real model (27/11/2026)

Run with `python -m scripts.check_retrieval_dev` on Abrar's computer (Windows 11, Python 3.12.10, the model
above, top k 4). Development questions only; the held-out questions were not run.

| Question | Expected passages (test set source location) | Found in the top 4 | Rank and score of the expected passage |
|---|---|---|---|
| 2 (used phone in instalments: invoice) | Exec. Regulation Art. 4 | yes | 2nd, 0.485 |
| 4 (advertised TV price charged higher) | MO 14/2008 Art. 1-3 | Art. 3 only | 1st, 0.581 (Art. 1 and 2 missing) |
| 6 (spare parts period) | Law 35 Art. 9, Exec. Regulation Art. 16 | both | 1st 0.696, 2nd 0.577 |
| 12 (education prices: collection, weight) | CPI Sep 2023 pp. 7-8 | both | 1st 0.613, 3rd 0.547 |
| 25 (change of mind, no fault) | Know Your Right p. 8, Exec. Regulation Art. 14 | guidance only | 1st, 0.540 (Art. 14 missing) |

**5/5** questions retrieve at least one expected passage; **2/5** miss part of what a complete answer
cites (questions 4 and 25). The out-of-scope development questions 16, 19 and 20 (data questions) score
0.494, 0.427 and 0.413 on their best passage, above any useful cut-off, so a score cut-off cannot decline
them; they are declined by the data tools and the prompt's refusal rule.

What this means for the evaluation: questions that need several articles, especially Arabic articles found
from an English question, may get only part of their passages. This is recorded as a likely failure
category ("retrieval returned the wrong passage", brief 7.4) and a candidate for the intervention (for
example more passages per search, or an English title for each Arabic article). v1 keeps top k = 4, so
that the effect of any change can be measured in v2.

## Integration with questions over the data

The engine (`src/qa/engine.py`, Eman) and the Ask tab (`src/dashboard/ask.py`) need small additive
changes, given as `integration_eman.patch` for Eman to review: `DataQA(..., documents=None)` stays the
default, so nothing changes when the documents are not prepared; with documents, the extra tool, the prompt
block, the routing and the retrieval log are added. All 165 existing tests pass with the patch.

## Tests

`tests/test_retrieval.py` (passages, ranking, amendment links, refusal, number words, citations on the real
passages), `tests/test_documents_qa.py` (the tool inside the question-answering loop with the fake Gemini
client: declarations, prompt, citations, number check, retrieval log, refusal).

## End-to-end check in the app (27/11/2026, Abrar's PC, Gemini 3.5 Flash-Lite)

Run with the integration patch applied locally (not committed). Development questions only.

| Question | Result | Evidence |
|---|---|---|
| Spare parts period and release (dev Q6) | Correct: 15 working days (ER Art. 16, number written in Arabic words), release on written notice plus consent (Law 35 Art. 9, ER Art. 16). Every sentence cited; 2 passages shown. | q1_answer.png, q1_passages.png |
| Combined: CPI Sep 2023 food + defective product | Correct: food +7.9% (CPI Sep 2023 p. 3); replacement/refund (Law 35 Art. 8, ER Art. 10). Both parts cited; 9 passages. Gap: Law 28/2026 added a new item 1 to Art. 8(a), so the right is now item 2; the answer did not mention the amendment. Logged for failure analysis (7.4). | q2_*.png |
| Milk price in Manama (dev Q19, must decline) | Declined with the fixed sentence "This is not available in the sources." 0 tool calls. | q3_refusal.png |

## v2 setting (intervention, docs/failure_analysis.md)

`SEARCH_QUESTION_TOO` (False in v1, True in v2): each document search also searches with the user's own
question and adds its top passages that the model's query did not find (marked `question` in the log).
`settings.use_version("v1" | "v2")` switches between the two; `as_dict()` records the value with every answer.
