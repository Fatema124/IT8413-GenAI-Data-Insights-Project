# Evaluation plan and results (brief 7.1 – 7.5)

Lead: Eman Khamdan (test set and evaluation runs). Failure analysis and the v2 intervention: Abrar Alawadhi
([`failure_analysis.md`](failure_analysis.md)). This page sets out how PriceLens BH is evaluated: the test set,
the four configurations, the metrics, the order in which the runs were made, and the results.

All scores and answers are in the results workbook
[`results/IT8413 - Group Project Test Set and Results (G2).xlsx`](../results/IT8413%20-%20Group%20Project%20Test%20Set%20and%20Results%20%28G2%29.xlsx) (sheets *Test Set*, *Results*,
*Runs* and *Summary*). The run script is [`scripts/run_evaluation.py`](../scripts/run_evaluation.py).

## 1 · Test set (brief 7.1)

31 questions, written by the group from the approved proposal (Section 3), each with a ground-truth answer and
its source location (dataset and code, or document, article and page). Every ground truth was checked again
against Datasets 1 – 3 and the document passages before the final runs.

| Type | Development | Held-out | Total |
|---|---|---|---|
| Direct lookups (data) | 3 | 3 | 6 |
| Answerable only from the documents | 3 | 4 | 7 |
| Requiring information to be combined (data + documents) | 4 | 3 | 7 |
| Correct answer contradicts a common expectation | 3 | 2 | 5 |
| Not answerable from any of the sources (must be declined) | 3 | 3 | 6 |
| **Total** | **16** | **15** | **31** |

**Rules for the split.**
- The **16 development questions** were used to build and tune the tool: prompt wording, retrieval settings,
  the failure analysis on v1 and the choice of the v2 intervention.
- The **15 held-out questions** were not run, read into a prompt or used for any design decision before v2
  was frozen. They were run **once**, in the final evaluation, and are reported separately.
- Question 13 is a follow-up pair (F8): parts (a) and (b) are asked in one conversation and scored as one answer.

## 2 · Configurations (brief 7.2)

All four use the same model and settings, so the only difference is what the model is given.

| Run | What the model gets | Settings |
|---|---|---|
| **Control** | The question exactly as asked. No system prompt, no data, no documents, no tools. | temperature 0; max output 1,024 tokens |
| **Baseline** | Plain prompting: answering rules (cite every statement, fixed refusal sentence) plus the full text of Docs 4 – 10 and of every dataset the question's source location names (Datasets 1 and 2 for unanswerable questions). No retrieval, no tools. | as control; `BASELINE_RULES` prompt |
| **v1** | The app (`src/qa/engine.py`): data tools over Datasets 1 – 3 and the document search tool (retrieval with citations). | as control; max 6 tool rounds; last 3 turns as context; top k 4; minimum similarity 0.40; follow 2026 amendments on; `SEARCH_QUESTION_TOO` off |
| **v2** | v1 with **one** change: the document search also searches with the user's own question. | as v1; `SEARCH_QUESTION_TOO` on |

**Model:** Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) through the Gemini API (`google-genai`).
**Embeddings (v1, v2):** `paraphrase-multilingual-MiniLM-L12-v2` through fastembed, run locally.
**Date of the final runs:** 28/11/2026 (Bahrain time).

## 3 · Metrics (brief 7.3)

Each answer is scored by hand in the *Results* sheet against the ground truth. The Summary sheet computes the
rates per run, separately for development and held-out questions.

| Metric | Scored as | Rate reported |
|---|---|---|
| **Accuracy** | Correct / Partially correct / Incorrect | share of answers scored Correct |
| **Groundedness** | Grounded / Ungrounded / Not applicable (refusals) | share of applicable answers whose statements are supported by the cited source |
| **Refusal behaviour** | Answered an answerable question / Correct refusal / Declined an answerable question / Answered an unanswerable question | share of answers with the right behaviour (the first two) |
| **Completeness** | Complete / Partial / Not addressed | share of answers scored Complete |
| **Tokens** | input and output tokens, as reported by the API (thinking tokens counted as output) | mean per question |
| **Latency** | seconds from sending the question to the final answer, all tool rounds included | mean per question |
| **Cost** | (input tokens × input price + output tokens × output price) / 1,000,000 | USD per 1,000 questions |

**Prices used:** USD 0.30 per 1M input tokens and USD 2.50 per 1M output tokens (Gemini 3.5 Flash-Lite, paid
tier, Standard requests), from Google's Gemini API pricing page, checked on 28 Nov 2026. The runs themselves
used the free tier; the paid price is used so that cost can be compared between configurations.

## 4 · Procedure

1. **Development runs of v1** on the development questions only (27/11/2026): `scripts/check_dev_answers.py`,
   `scripts/check_retrieval_dev.py`, `scripts/run_dev_documents.py`.
2. **Failure analysis of v1** on the development questions (brief 7.4), then **one intervention** aimed at the
   largest category (brief 7.5), with its expected effect written down before v2 was run
   ([`failure_analysis.md`](failure_analysis.md)).
3. **v2 measured on the development questions** (`scripts/compare_runs.py`) and then **frozen**: no setting,
   prompt or code changed after this point.
4. **Final evaluation:** control, baseline, v1 and v2 each run once on all 31 questions
   (`python -m scripts.run_evaluation all`). Questions that hit the free tier's per-minute limit were re-run on
   their own (`--only`) so that every row holds a real answer; no question was re-run to get a better score.
5. **Scoring** of the 124 answers in the *Results* sheet, with a reason for every score and a failure category
   for every failure. The scores were drafted with AI assistance (recorded in the AI-use log) and reviewed by the
   group.
6. **Failure analysis repeated** on the v1 and v2 results of the full test set.

## 5 · Failure categories (brief 7.4)

A failure is any answer that is incorrect or partial, declines an answerable question, answers an unanswerable
one, or cites a source that does not support it. Each failure gets one category:

1. Retrieval returned the wrong passage
2. Retrieval returned the right passage, and the model did not use it
3. The question was ambiguous
4. The sources do not contain the answer
5. The calculation was wrong
6. Other cause (described in the Reasoning column)

For control and baseline there is no retrieval step. A baseline answer that declines although the needed text
was in its prompt is counted under category 2 ("the right text was given and the model did not use it").

## 6 · Results (final evaluation, 28/11/2026)

**Held-out questions (15), the measure that counts:**

| Run | Accuracy | Groundedness | Refusal behaviour | Completeness | Cost per 1,000 questions | Mean latency |
|---|---|---|---|---|---|---|
| Control | 20% | 0% | 53% | 20% | $0.68 | 3.5 s |
| Baseline | 80% | 100% | 80% | 80% | $71.28 | 43.7 s |
| v1 | 80% | 100% | 100% | 80% | $4.55 | 5.6 s |
| v2 | **87%** | 100% | 100% | **87%** | $4.33 | 4.8 s |

**Development questions (16):**

| Run | Accuracy | Groundedness | Refusal behaviour | Completeness | Cost per 1,000 questions | Mean latency |
|---|---|---|---|---|---|---|
| Control | 19% | 0% | 50% | 19% | $0.66 | 1.4 s |
| Baseline | 69% | 100% | 81% | 69% | $85.53 | 61.7 s |
| v1 | 88% | 100% | 94% | 88% | $4.40 | 2.9 s |
| v2 | 88% | 100% | 94% | 88% | $4.08 | 5.3 s |

**Failures per category (all 31 questions):**

| Category | Control | Baseline | v1 | v2 |
|---|---|---|---|---|
| Retrieval returned the wrong passage | – | – | 4 | 3 |
| Right passage, model did not use it | – | 7 | 1 | 1 |
| The calculation was wrong | – | 1 | – | – |
| Other cause | 25 | – | – | – |
| **Total** | **25** | **8** | **5** | **4** |

**What the results show.**
- **The control** answers from general knowledge: mostly generic or non-Bahraini rules and no figures from the
  datasets, so nothing it says is grounded in our sources.
- **Training-data exposure (brief 4.3).** The control answered only **1 of the 25 answerable questions**
  correctly (Q25, a general consumer-rights point) and gave **no correct figure** from the datasets. Its other
  5 correct scores are refusals of unanswerable questions, where it cited its knowledge cutoff rather than the
  sources. So the model had not memorised our sources: a correct answer from v1 or v2 comes from the tool's
  retrieval and computation, not from training data.
- **The baseline** gets most document questions right, but it declines data questions even though the numbers
  were in its prompt (it does not compute year-on-year changes or annual averages from a long table). Placing
  every source in the prompt makes it about 16 – 21 times as expensive as v1 and v2, and about 8 – 20 times as slow.
- **v1 and v2** decline every unanswerable question correctly and never answer one, because the data tools
  return "not in the sources" instead of a guess. Their remaining failures are almost all retrieval: the needed
  article was not among the passages returned.
- **v2 vs v1** on held-out questions: 13 vs 12 correct. v2 fixed Q05 and Q07 and lost Q01; on the development
  set it fixed Q12, moved Q25 from incorrect to partially correct, and lost Q02, which it declined although the right passage was retrieved.
  With 15 held-out questions one question is 6.7 points, so the gain is real but small, and part of the change
  between runs is run-to-run variation (see [`failure_analysis.md`](failure_analysis.md)).
- **Next candidate (v3):** the remaining retrieval failures are English questions over Arabic articles that score
  below the 0.40 minimum (for example Executive Regulation Art. 14 and MO 51/2007 Art. 2). Giving each Arabic
  article an English title for the search is the next intervention to test, on its own, after v2.

## 7 · Limits of this evaluation

- 31 questions is a small set: each held-out question moves a rate by 6.7 points.
- Answers were scored by the group with AI assistance, not by independent judges.
- Even at temperature 0 the model does not always give the same answer twice (for example the way it cites).
- Costs use the published paid price on 28 Nov 2026; prices change.
- v1 and v2 were run on the answering features (F4 – F8). The report export (F9) and the query log file (F10)
  were not finished at the time of the runs; they do not change how an answer is produced, but the brief
  defines v1 as the tool with all 10 features, so this is recorded here.

## 8 · Reproducing the runs

See [Evaluation](../README.md#-evaluation-and-benchmark) in the README. The full answer records
(`results/final/*.jsonl`) quote MOIC document text and are kept out of the repository; the answers and scores
are in the results workbook.
