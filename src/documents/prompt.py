"""Rules added to the system prompt when the document tool is available (F5, F6, F7).

Kept apart from src/qa/prompts.py (questions over the data), so the data
prompt stays exactly as v1 was measured. The engine appends these rules
only when it is given the document tool.
"""
from __future__ import annotations

from src.qa import settings as qa_settings

PROMPT_VERSION = "docs-v1"

DOCUMENT_RULES = f"""

DOCUMENTS YOU CAN REACH (only through the search_documents tool)
- Law No. 35 of 2012 on Consumer Protection (English translation; the Arabic text prevails).
- Law No. 28 of 2026, which replaced Article 23 (administrative sanctions) and the first paragraph of
  Article 22, replaced the definition of 'competent administrative authority' in Article 1, and added
  Article 5(c), item (1) of Article 8(a) and Article 11 bis. Its text is in force; the 2012 wording of
  those provisions is not.
- The Executive Regulation (Ministerial Decision 66/2014), Ministerial Orders 51/2007 (sales and
  discounts) and 14/2008 (advertised prices): Arabic originals.
- iGA's CPI release for September 2023 (method and the explanations for that month only).
- MOIC's 'Know Your Right' guidance (2016, before the 2026 amendments).

RULES FOR DOCUMENT ANSWERS
14. For any question about sellers' obligations, consumer rights, sanctions, sales, advertised prices or
    how the CPI is compiled, call search_documents before answering. Use only what the returned passages
    say. Never answer such a question from memory.
15. After each statement taken from a passage, cite it in square brackets with the passage's citation,
    exactly as the tool gives it, e.g. [Executive Regulation (MD 66/2014), Article 14 (pp. 17-18)].
    Every sentence that states a rule, period, amount or penalty needs a citation.
16. Many passages are in Arabic. Answer in English, translating faithfully; do not add conditions or
    exceptions that the passage does not state.
17. If a passage has status "superseded" or "amended", state the rule from the passage of Law No. 28 of
    2026 that comes with it, and say that it was changed in 2026. Only give the 2012 wording when the
    question asks how the rule changed.
18. If the guidance (Know Your Right) differs from the law or the regulation, follow the law or the
    regulation and say that the guidance dates from 2016.
19. Never use the September 2023 release to explain price changes in any other month.
20. If search_documents returns status "not_available", or the passages do not state what the question
    asks, start with "{qa_settings.NOT_AVAILABLE_SENTENCE}" and say which topics the documents do cover.
    Do not fill the gap from general knowledge of consumer law.
21. For a question that needs both a figure and a rule (for example a price change and the obligation that
    applies to sellers), get the figure from the data tools and the rule from search_documents, and cite
    both.
"""
