"""The DEVELOPMENT questions that use the documents, with their ground truth
(revised proposal, Section 3). Held-out questions are deliberately not here
(brief 7.1): they are not run or used to guide changes before the final evaluation.
"""
from __future__ import annotations

from .failures import Item

DEV = "development"

ITEMS: tuple[Item, ...] = (
    Item("2", DEV, "document", "A shop sells a used phone in instalments. What must its invoice contain?",
         "On the consumer's request, a clear invoice at no extra charge showing: supplier and shop name; date; "
         "price; type, essential features and warranty period; that the product is used (its condition); "
         "quantity; delivery date; signature or stamp. For instalments it must also show the total instalment "
         "amount, the actual annual interest rate and how it is calculated, the date interest starts, the number "
         "and value of instalments, the instalment period, penalties for default or late payment, the parties' "
         "rights over ownership during the period, and the consumer's acknowledgement of these terms. "
         "[Doc 6, Art. 4, pp. 14-15]", frozenset({"D6-A4"})),
    Item("4", DEV, "document", "A shop advertised a television at a set price in a newspaper, then charged a "
         "higher price at the till. Which obligations does this breach and what penalty does the order refer to?",
         "Shops that announce retail prices must keep to them and must not manipulate them, especially at payment. "
         "Anyone advertising goods at a set price in newspapers or on roads must ensure the advertised price is "
         "actual and matches reality. Violators face the penalties in Decree-Law No. 18 of 1975 (as amended by "
         "Decree-Law No. 11 of 1977), as well as closure of the shop where the manipulation took place. "
         "[Doc 8, Art. 1-3, p. 7]", frozenset({"D8-A1", "D8-A2", "D8-A3"})),
    Item("6", DEV, "document", "How long does a supplier have to provide spare parts and maintenance after a "
         "consumer asks, and when is it released from this duty?",
         "Within at most 15 working days of the request. The parties may agree a specific period in writing. The "
         "supplier is released if it notifies the consumer in writing that the parts are unavailable and the "
         "consumer agrees. [Doc 6, Art. 16, p. 18; Doc 4, Art. 9, p. 6]", frozenset({"D6-A16", "D4-A9"})),
    Item("12", DEV, "combined", "How did the Education index change between August and September 2025 and from "
         "then to August 2026, and what does iGA's method say about how often education prices are collected "
         "and their weight?",
         "It rose 2.8% from 108.41 to 111.4 in September 2025 and stayed at 111.4 every month to August 2026. "
         "iGA's method lists education, 8.6% of the basket weight, under annual price collection. "
         "[Dataset 1: code 10; Doc 9, section 5.3, pp. 7-8]", frozenset({"D9-P8-w1", "D9-P7-w2"})),
    Item("25", DEV, "document", "A customer changes their mind about a jacket bought yesterday that has no fault. "
         "Must the shop exchange it or give a refund?",
         "No, unless the shop's own policy offers it, in which case the shop must keep to that policy. The legal "
         "right to exchange or refund applies only where goods have a defect or fault or do not conform to the "
         "approved specifications or the purpose of the contract. The Ministry's guidance lists a change of mind, "
         "finding the item cheaper elsewhere, a defect the consumer was told of at purchase, and damage from "
         "misuse as cases with no refund or replacement. [Doc 10, PDF pp. 7-8; Doc 6, Art. 14, pp. 17-18]",
         frozenset({"D10-P8-w1", "D6-A14"})),
    Item("16", DEV, "unanswerable", "What was the CPI for Muharraq Governorate in August 2026?",
         "Not answerable: all CPI figures are national (and by nationality).", must_decline=True),
    Item("19", DEV, "unanswerable", "What is the current price of a litre of fresh milk at a supermarket in Manama?",
         "Not answerable: the sources contain index numbers, not prices of products at specific shops.",
         must_decline=True),
    Item("20", DEV, "unanswerable", "What was the headline CPI in December 2009?",
         "Not answerable: the earliest index in any source is January 2011 (Dataset 3, Table 1). Its 1-month "
         "and 12-month changes allow 2010 values to be derived, but nothing earlier.", must_decline=True),
)

BY_ID = {i.qid: i for i in ITEMS}
