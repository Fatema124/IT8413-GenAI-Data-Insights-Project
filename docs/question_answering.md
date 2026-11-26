# Questions over the data (F4): design decisions

Lead: Eman Khamdan (proposal Section 4). This page records how F4 is built and why, for the report's
design section (brief Section 3: prompting, retrieval, tool use) and for reproducing every result.

## How one question is answered

1. The question is sent to **Gemini 3.5 Flash-Lite** with the system prompt
   ([`src/qa/prompts.py`](../src/qa/prompts.py)) and the declarations of 13 tools.
2. Gemini does not see the data. To give a figure it must call a tool, for example
   `get_change(category="food", month="2026-08", measure="yoy")`.
3. The app runs the tool ([`src/pipeline/tools.py`](../src/pipeline/tools.py)) over the prepared data and sends
   the JSON result back: the figure, the two stored index values it used and the dataset it came from.
4. Gemini may call more tools (at most 6 rounds), then writes the answer.
5. The app checks every number in the answer against the tool results
   ([`src/qa/numbers.py`](../src/qa/numbers.py)) and shows a warning beside any number that no tool returned.
6. The answer is shown with *How this answer was worked out* (every tool call, its arguments and its result),
   the model, the time taken and the tokens used.

Code: [`src/qa/engine.py`](../src/qa/engine.py) (the loop), [`src/dashboard/ask.py`](../src/dashboard/ask.py)
(the *Ask a question* tab). Tests: [`tests/test_qa.py`](../tests/test_qa.py).

## Decisions and reasons

| Decision | Reason |
|---|---|
| **Tool use for every number**, not the data placed in the prompt | Brief F4: "Any numeric figure that is given in an answer must be produced by code running over the data." Dataset 1 alone is about 134,800 tokens (proposal Section 5), and a model reading a long table can copy the wrong row. Placing the sources in the prompt is the *baseline* run, so v1 must differ from it. |
| **The model never sees the data** | It has no figures of its own to quote, so a figure in an answer either came from a tool or is visibly unsupported. |
| **The app runs the tools itself** (automatic function calling off) | Every call, its arguments and its result are recorded, shown to the user and kept for the query log (F10). |
| **A `calculate` tool** for differences, ratios and % changes between figures already returned | Some questions need a gap, e.g. development question 13: the Bahraini index is 18.0 points above the non-Bahraini one. Without this tool the model would subtract in its head. `calculate` refuses any number that no earlier tool result returned. For changes over time the prompt points to `get_change`, which uses the unrounded stored values. |
| **Number check after the answer** | The prompt asks for tool figures only; the check proves it. A number counts as supported if a tool result (or the question, or an earlier turn) holds a value that rounds to it at the decimals shown. Signs are ignored ("fell 1.1%"). Whole numbers up to 12 used as words ("12 months") are skipped unless written as % or points. Numbers the model itself sent (tool arguments, and messages that repeat them) do not count as evidence. Flagged numbers are shown, not hidden, and are recorded for the failure analysis ("the calculation was wrong", brief 7.4). |
| **One fixed refusal sentence**: "This is not available in the sources." | The app detects a refusal by this sentence, so refusal behaviour can be counted in the evaluation (brief 7.3). The prompt lists what the data never holds: forecasts, causes, prices at shops or of single products, governorates, anything before 2010. The brief (Brief A) warns that the series "carries no information about where [prices] are going next". |
| **The measure is always named** | The brief warns that month-on-month, year-on-year and since-base readings differ for the same category and month. With no measure in the question, the model uses year-on-year for "inflation" and says so; with no month it uses August 2026 and says so. |
| **Warnings are passed on** | Tool results carry `caution` (the 179 Dataset 2 values from 2022 that differ from iGA's Table 3) and `derived_note` (2010 values derived from 12-month changes). The prompt requires the answer to repeat them. |
| **Temperature 0** | The same question should give the same answer, so results can be reproduced. |
| **Last 3 questions and answers sent as context** | Follow-up questions (F8), such as "and for Bahraini households?". Figures from those turns also count as supported. Failed turns are not sent. |
| **Errors never become answers** | A rate limit, a wrong key or an empty reply is shown as a short message; the full error is kept in the record. |
| **Busy model retried** | Gemini sometimes answers "503: high demand". The app retries after 3 s and 10 s (also for a per-minute 429) and counts the retries in the record. Other errors are not retried. |
| **Partial answers** | If one part of a question cannot be answered, the app answers the other parts and uses the refusal sentence for the missing part. Only an answer that *opens* with the sentence counts as declined. |

## Settings (shown in the app; v2 changes exactly one)

From [`src/qa/settings.py`](../src/qa/settings.py), stored with every answer:

| Setting | v1 value |
|---|---|
| Model | `gemini-3.5-flash-lite` |
| Temperature | 0.0 |
| Max output tokens | 1024 |
| Max tool rounds | 6 |
| History turns | 3 |
| Retries when busy | 2 (after 3 s and 10 s) |
| Prompt | v1 (`src/qa/prompts.py`) |

Candidates for the intervention (brief 7.5), depending on what the failure analysis finds: a repair step that
asks the model to rewrite an answer whose numbers fail the check (this also fits the "self-verification"
enhancement in brief Section 10), more specific tool descriptions, or a change to the system prompt's rules.

## How the prompt was refined on the development set

Before v1 was fixed, the 12 development questions that use the data were run on Gemini (26/11/2026). The held-out
questions were not run. What the first run showed, and the prompt rule added for it:

| What happened | Rule added |
|---|---|
| Q28: "137.5, so 37.5% higher than April 2019". The model did the sum itself; the number check flagged it. | Never turn an index level into a %; use `get_change` with measure "base". |
| Q12: "the data does not record a change" between September 2025 and August 2026. | For other spans, use `get_series` and report the first and last values. |
| Q13(b): household values given, but not the gap or the order. | When comparing, give every value, the highest and lowest, and the gap with `calculate`. |
| Q21: correct "fell 2.9%" but without the two averages. | When giving a change, also give the two values it compares. |
| Q8: a stored value shown unrounded (76.0154). | Index values and averages to one decimal place; the app also rounds stored index values and averages to 1 d.p. in what the model sees (`for_model`), while the record keeps the full values. |
| Q16: "68" quoted from the prompt's own description of the data. | Numbers removed from the prompt's data description; coverage comes from `data_coverage`. |
| Q20: Gemini returned "503 high demand". | Retry (see above). |
| "April 2019 = 100" flagged when a tool result did not repeat it. | The base period and the latest month are always allowed in the number check. |

Final run (26/11/2026, after these changes): the 10 development data questions that this run could answer were
all correct, with no unsupported numbers and no retries (Q8, 12, 13a, 13b, 21, 23, 28 answered; Q16, 19, 20
declined). Q10 and Q30 need Dataset 3's weights, which were not loaded in that run; both declined the weight. Open point for the
failure analysis: when expenditure weights were not loaded (Q10, run without Dataset 3), the model declined the
weight but then offered a different figure (the highest index level) in its place, despite the rule against it.

## What each answer records

`Answer.to_record()` returns a JSON-ready dict: question, answer, status (`answered`, `declined`, `error`),
every tool call with arguments and result, unsupported numbers, tokens (prompt, output, thinking, total),
response time, number of model calls, busy-model retries, settings (including the prompt version) and time asked. The query log (F10) writes these records.

## Not covered here

Questions over the documents (F5), combined questions (F6, which needs F5) and the query log file (F10) are
separate components. Follow-ups (F8) work through the history above; their evidence comes from the evaluation.
