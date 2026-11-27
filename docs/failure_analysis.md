# Failure analysis and intervention (brief 7.4, 7.5)

Lead: Member 3 (Abrar Alawadhi). Tools: `src/evaluation/failures.py`, `scripts/failure_analysis.py`,
`scripts/diagnose_retrieval.py`, `scripts/compare_runs.py`.

## How a failure is found and classified

A failure (brief 7.4) is any answer that is incorrect or partial, declines a question that should have been
answered, answers a question that must be declined, or cites a passage that does not support it. For each
failure, `scripts/failure_analysis.py` traces the answer record (the tools called, the passages retrieved with
their ranks and scores, the numbers the number check could not find) and suggests a category, checked in
pipeline order:

| Order | Evidence in the record | Suggested category |
|---|---|---|
| 1 | The question must be declined and the tool answered | The sources do not contain the answer |
| 2 | The judge marked the question ambiguous | The question was ambiguous |
| 3 | Numbers in the answer that no tool returned, or a failed calculation | The calculation was wrong |
| 4 | Facts correct, citation does not hold them | Other: citation error |
| 5 | No search, or none / only part of the expected passages retrieved | Retrieval returned the wrong passage |
| 6 | All expected passages retrieved, answer still wrong | Retrieval returned the right passage, and the model did not use it |

The judge confirms or changes each suggestion (column `category` of the scores file). The expected passages
are the ground-truth source locations of the test set.

## Development run v1 (27/11/2026, Gemini 3.5 Flash-Lite, 8 development questions that use the documents)

Held-out questions were not run (brief 7.1). Scores were drafted against the proposal's ground truth with AI
assistance (see the AI-use record) and confirmed by Abrar; the reasons are in `results/v1-dev_scores.csv`.

| Q | Accuracy | Grounded | Refusal | Complete | Failure |
|---|---|---|---|---|---|
| 2 | correct | yes | appropriate | complete | - |
| 4 | correct | yes | appropriate | complete | - |
| 6 | partial | yes | appropriate | partial | the 15-working-day limit (Exec. Regulation Art. 16) is missing |
| 12 | correct | **no** | appropriate | complete | Dataset 1 figures cited to the CPI Sep 2023 release |
| 25 | partial | yes | appropriate | partial | "unless the shop's own policy offers it" and Exec. Regulation Art. 14 missing |
| 16, 19, 20 | correct | n/a | correct refusal | complete | - |

**Categories:** Retrieval returned the wrong passage: 2 (Q6, Q25). Other (citation error): 1 (Q12).

## Tracing the retrieval failures

`scripts/diagnose_retrieval.py` ranked every passage again for the search the model actually made, and for the
user's question:

| Q | Needed passage | Model's query | User's question |
|---|---|---|---|
| 6 | Exec. Regulation Art. 16 | rank 9, 0.477 | **rank 2, 0.577** |
| 25 | Exec. Regulation Art. 14 | rank 13, 0.303 (below 0.40) | rank 10, 0.354 (below 0.40) |
| 12 | CPI Sep 2023 p. 7 (w2) | rank 48, 0.127 | rank 11, 0.413 |
| 4 | MO 14/2008 Art. 1, 2 | ranks 2, 1 | ranks 6, 8 |

The model rewrites the question into a short English keyword query ("spare parts and maintenance after a
consumer asks released from duty"). For the Arabic articles this query ranks the needed article lower than the
user's full question does. For Q4 the opposite holds, so the question alone is not better than the query.

## Intervention v2: also search with the user's question

**Changed (one setting):** `SEARCH_QUESTION_TOO` in `src/documents/settings.py`, False in v1, True in v2.
Each document search returns the top passages for the model's query, then adds the top passages for the
user's question that are not already there (same top_k and minimum score for both).

**Category targeted:** Retrieval returned the wrong passage (the largest category).

**Reasoning:** the trace shows the needed passage was in the collection and ranked well for the user's
question, but the model's shorter query pushed it out of the top 4. Adding the question's results keeps the
passages the model's query finds (Q4) and adds those the question finds (Q6).

**Expected effect, stated before the v2 run:** Q6 fixed (Art. 16 at rank 2). Q25 not fixed: Art. 14 scores
below the 0.40 minimum for both queries, so this is a different cause (a cross-language gap) and a candidate
for a later intervention (v3), not this one. Q12's citation error is not a retrieval failure and should not
change. Prompt tokens for document questions should rise, because up to twice as many passages are sent.

## Measured effect: v1 and v2 on the 8 development questions (27/11/2026)

`python -m scripts.compare_runs v1-dev v2-dev`; scores and reasons in `results/v1-dev_scores.csv` and
`results/v2-dev_scores.csv`.

| Metric | v1 | v2 |
|---|---|---|
| Accuracy: correct / partial / incorrect | 6 / 2 / 0 | 7 / 1 / 0 |
| Groundedness: grounded / ungrounded (n/a = refusals) | 4 / 1 | 5 / 0 |
| Refusal behaviour: appropriate (of 8) | 8 | 8 |
| Completeness: complete / partial | 6 / 2 | 7 / 1 |
| Failures | 3 (2 wrong passage, 1 citation) | 1 (wrong passage) |
| Mean prompt tokens per question | 9,318 | 10,030 (+7.6%) |
| Mean prompt tokens, 5 answerable document questions | 12,284 | 13,423 (+9.3%) |
| Passages supplied, 5 answerable document questions | 15 | 27 |
| Mean output tokens | 242 | 235 |
| Mean latency (s) | 2.24 | 2.78 (median 2.02 in both; one v2 answer took 9.7 s) |

Cost per 1,000 questions follows from the token counts and the provider's published price
(`--input-price`, `--output-price`).

**What matched the expectation.** Q6 was fixed for the reason predicted: Executive Regulation Art. 16 was added by
the search with the question and the answer now gives "at most 15 working days" with its citation. Q25 was not
fixed, as predicted: Art. 14 again scored below 0.40 for both searches. Prompt tokens rose.

**What the expectation did not cover.** In v2 the model wrote different queries from v1 for Q2 and Q25, and
those queries found no passage above 0.40. All passages for these two questions came from the search with the
question, including Executive Regulation Art. 4 for Q2. Under v1 settings that query would have returned
nothing, so v2 also protects against the model's query varying between runs.

**What is not an effect of the intervention.** Q12 moved from ungrounded to grounded because the model stopped
citing the CPI 2023 release for the Dataset 1 figures. The change touched only the documents search, and the
passage that held the needed facts was the same, so this is run-to-run variation in how the model cites, even at
temperature 0. It shows that a difference of one question on 8 questions is within that variation; the final
evaluation on the full test set is the measure that counts.

**Remaining failure and next candidate (v3).** Q25: Executive Regulation Art. 14 scores 0.30 to 0.35 for English
queries, a gap between English questions and Arabic articles. A separate intervention could give each Arabic
article an English title for the search, evaluated on its own after v2. Minor, not a failure: in Q4 the model
reworded the citation ("Ministerial Order 14/2008" instead of "MO 14/2008"); in Q6 it said the consumer's
consent must be in writing, which the sources do not say.

## Final evaluation

**What Member 3 provides for the four runs (Eman's evaluation script):**
- **Baseline document text:** `from src.documents.baseline import baseline_text`; `baseline_text()` returns Docs
  4-10 exactly as the tool uses them, each page headed with the tool's citation, to place in the baseline prompt
  with the datasets a question needs. `python -m src.documents.baseline --count` gives the exact token count.
  The text is built on each computer and never committed.
- **v1 and v2 settings:** `src.documents.settings.use_version("v1" | "v2")`; v2 differs in `SEARCH_QUESTION_TOO` only.
- **Failure analysis on the full test set:** export the test-set spreadsheet as CSV with the columns
  `question, split, type, question text, ground truth, source location`, save each run's answers as
  `results/<run>.jsonl` and its scores as `results/<run>_scores.csv` (format of `scripts/run_dev_documents.py`), then
  `python -m scripts.failure_analysis v1 --testset results/test_set.csv`. The expected passages are read from
  the source locations (`src/evaluation/testset.py`), and failures are counted separately for development and
  held-out questions.

v2 was designed on the development set only. In the final evaluation all four configurations (control,
baseline, v1, v2) run on the full test set, with development and held-out results reported separately (brief
7.1, 7.2). The failure analysis above is then repeated on the v1 and v2 results of the full test set.
