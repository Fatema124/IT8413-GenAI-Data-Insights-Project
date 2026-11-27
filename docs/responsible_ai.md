# Responsible AI use and impact (brief Section 9)

Lead: Member 3 (Abrar Alawadhi); support: Fatema Alashiri (revised proposal, allocation table).
This assessment is about PriceLens BH **as built**: Gemini 3.5 Flash-Lite calling 13 data tools and a document
search over Docs 4-10, used by a consumer affairs department that answers ministers, journalists and members of
the public. Evidence comes from the development runs of 27/11/2026 (`docs/failure_analysis.md`). Figures marked
**[final]** are to be filled in from the final evaluation on the full test set.

## 1. Potential harm

| Who relies on the answer | What a wrong or ungrounded answer could do | How serious |
|---|---|---|
| A consumer asking about their rights | Miss a deadline or a right. In the v1 development run the tool said spare parts must be provided for "a reasonable period" and left out the legal maximum of 15 working days (Q6). A consumer could wait too long or accept a refusal. | High for the individual: money lost, a complaint filed too late |
| A shop owner asking what the law requires | Follow an old rule. Law 35/2012 was amended by Law 28/2026, and the Ministry's guidance (2016) predates it. Relying on the 2012 text of the sanctions article (Article 23, replaced in 2026) would understate today's sanctions. | High: fines, closure |
| A minister or analyst | A wrong inflation figure or ranking could steer attention to the wrong category of spending. | Medium to high: a policy decision |
| A journalist | A figure the group computed could be quoted as an official iGA statistic. | Medium: public misinformation |

**Design features that limit this exposure (all in the current build):**
- **The model never calculates in its head.** Every figure comes from a data tool (`get_series`, `get_change`,
  `calculate`), and a number check after the answer flags any number that no tool returned (`verified` in the log).
  In the development runs no answer contained an unsupported number.
- **Every document statement carries a citation** in the form "Executive Regulation (MD 66/2014), Article 16
  (p. 18)", and the app shows the full passages used under each answer, so the reader can check the source.
- **Fixed refusal.** When the sources do not hold the answer, the tool says "This is not available in the sources."
  All 3 development questions that must be declined (governorate CPI, milk price in a shop, CPI in 2009) were
  declined in both v1 and v2; **[final]** held-out refusals.
- **Amendments are linked.** A 2012 article changed by Law 28/2026 is always delivered with the 2026 text, and
  the prompt tells the model to use the text in force. The 2016 guidance carries a note that it predates the law.
- **Computed figures are labelled** as the group's own calculation from iGA's index numbers, not official
  figures (licence clause 3.3b).
- **The failure analysis is part of the tool.** Every answer is logged with the passages it saw, so a wrong
  answer can be traced (`scripts/failure_analysis.py`). This is how the missing 15-working-day rule was found
  and fixed in v2.

**Remaining exposure.** On the development set, v2 still left out a qualification in 1 of 5 document answers
(Q25), and in another answer it slightly overstated a rule (it said the consumer's consent must be in writing).
**[final]** accuracy and groundedness on the held-out questions.

## 2. Bias in the sources

What the published data does not record, and how it shows in answers:

- **Only national figures and a nationality split.** The CPI is national; Dataset 2 splits it only into Bahraini
  and non-Bahraini households, only for the 12 divisions and only from May 2019. There are no figures by
  governorate, income level, household size or age. The tool therefore cannot say how prices changed for
  low-income families, pensioners or a particular area, and it declines such questions (development Q16).
  A user may still read a national average as if it applied to everyone.
- **One basket for everyone.** The weights come from the Household Income and Expenditure Survey 2014/2015
  (CPI release, p. 6), and iGA publishes one national basket, with no weights by nationality. A household whose
  spending differs from the average, for example one that spends a larger share on food or rent, experiences a
  different inflation rate from the one the tool reports.
- **The only explanation is from 2023.** The September 2023 release is the latest published explanation of price
  movements. The tool can show that prices rose in 2026 but cannot say why, and it is instructed never to apply
  the 2023 reasons to other months.
- **Language.** Four of the seven documents are only in Arabic, and the English law is an unofficial translation
  (the Arabic text prevails). The search model matches English questions to Arabic articles less well: in the
  development runs, the Arabic article holding the answer ranked 9th for Q6 and scored below the cut-off for
  Q25, while English passages ranked first. Rules that exist only in Arabic are therefore more likely to be
  missed. The tool also answers in English only, which disadvantages Arabic-speaking members of the public.
- **What is not recorded at all.** There are no prices of individual products or shops, no forecasts, and no
  complaint statistics. The tool declines these questions rather than estimate.

## 3. Data governance

| Stage | Where it runs | Terms | Why appropriate |
|---|---|---|---|
| Data preparation (Datasets 1-3) | Locally, on the user's computer (pandas) | Datasets 1-2: Bahrain Open Government Data License v1.0; Dataset 3: iGA website Terms of Use | Public statistics. The licence allows use in applications with the set statement, the extraction date and a label on our own analysis, which the app shows. |
| Document preparation and search (Docs 4-10) | Locally: OCR, passages and the multilingual search model (fastembed, about 0.22 GB, no API) | MOIC and iGA website Terms of Use: no republishing without permission | The files and their text are used only inside the tool, are not committed to the public repository (`data/documents/` and `results/*.jsonl` are git-ignored) and are submitted on Moodle, as the tutor advised. |
| Answering (Gemini) | Google's servers, outside Bahrain, through the Gemini API with free-tier keys from Google AI Studio | Gemini API Additional Terms of Service | What is sent: the user's question, the tool results (published aggregate index numbers) and the retrieved passages of public laws and releases (4 per search in v1, up to 8 in v2, plus linked 2026 amendments). None of this is personal data. Under the free tier, Google may use submitted content to improve its products and human reviewers may read it, so users must not type personal information into the question box (see Limits of use). A paid tier would be required before handling any non-public material. Check the current terms at ai.google.dev before submission. |
| Credentials | `.streamlit/secrets.toml` on each computer | | Git-ignored; no key in the repository or its history. |
| Query log (F10) and evaluation runs | Locally, as files | | Hold questions, answers and the passages used; because they contain document text, the raw run files (`results/*.jsonl`) stay out of the repository and only the scores are committed. |

## 4. Societal and environmental impact

**At the department's scale.** The department receives a continuous stream of requests from ministers,
journalists and the public. A tool that answers in seconds with citations could shorten response times and make
answers more consistent. The risks grow with scale: staff and the public may trust a fluent answer without
opening the cited passage (automation bias), and one systematic error, such as an out-of-date rule, would be
repeated in every answer until it is found. The query log and the failure analysis allow such errors to be found,
but only if someone reviews them regularly. The tool supports analysts; it does not replace a legal opinion or
the Consumer Protection Directorate's own decisions.

**Computational resources (measured).** Mean tokens per question in the development runs: about 4,400 for a
question that is declined, 10,000 for a document question and 23,000 to 27,000 for the combined data and document
question. The v2 change added about 7.6% to the prompt tokens. At 1,000 questions a day, that is roughly 10
million tokens a day processed in Google's data centres, plus a small local embedding model that runs on a normal
CPU. Each question also makes 1 to 4 model calls. The free tier's limit of 500 requests a day per project would not
cover the department's volume, so a paid tier would be needed, with its cost (**[final]** cost per 1,000
questions from the evaluation). Ways to reduce the footprint: answer repeated questions from the log, keep
top_k small, and use the smallest model that keeps accuracy, which is why Flash-Lite was chosen.

## 5. Limits of use: instructions for users

1. **Do not use PriceLens BH as legal advice.** For a dispute, a complaint or a penalty, check the cited article
   in the official Arabic text and contact the Consumer Protection Directorate.
2. **Always open "Document passages used"** and check that the cited passage says what the answer says before
   you act on it or quote it.
3. **Do not quote a percentage change from the tool as an official iGA figure.** The tool computes changes from
   iGA's index numbers; official figures are in iGA's own releases.
4. **Do not use the tool for one region, income group or household type.** The figures are national averages
   (and Bahraini / non-Bahraini by division from May 2019 only).
5. **Do not use it for prices of specific products or shops, for forecasts, or for causes of price changes after
   September 2023.** The sources do not contain them.
6. **Treat the 2016 "Know Your Right" guidance as background only.** Where it differs from Law 28/2026 or the
   Executive Regulation, the law applies.
7. **Do not type personal information** (names, ID numbers, phone numbers, complaint details) into the question
   box. Questions are sent to Google's servers.
8. **The data end in August 2026** (CPI) and the documents are the versions listed in `docs/sources.md`. Later
   changes to prices or laws are not covered.
9. **If the answer says "This is not available in the sources", do not rephrase the question to force an
   answer.** The refusal is the correct result.
