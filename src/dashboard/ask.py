"""The "Ask a question" section of the app (F4).

    from src.dashboard.ask import render_ask
    render_ask(data)                  # data = PreparedData, the same data the dashboard uses

The user types a question, Gemini answers it by calling the data tools, and
the app shows:
  * the answer, with a warning if it holds a number no tool returned;
  * "How this answer was worked out": every tool call, its arguments and the
    figures it returned, so every number can be checked;
  * the model, the time taken and the tokens used (F10).

Earlier questions stay on screen and are sent with the next question, so a
follow-up such as "and for Bahraini households?" works (F8). "Start a new
conversation" clears them.

The section needs GEMINI_API_KEY in .streamlit/secrets.toml (or in the
environment). Without it the dashboard still works and this section says how
to add the key.
"""
from __future__ import annotations

import os

import streamlit as st

from src.qa import settings
from src.qa.engine import DECLINED, ERROR, Answer, DataQA, make_client

TURNS_KEY = "qa_turns"
EXAMPLES = [                       # not taken from the test set (proposal Section 3)
    "What was the headline CPI in June 2024?",
    "How did transport prices change year on year in July 2026?",
    "Compare Bahraini and non-Bahraini households for clothing in May 2026.",
]
TOOL_NAMES = {
    "list_categories": "Looked up the spending categories",
    "data_coverage": "Checked what the data covers",
    "get_index": "Read an index value",
    "get_change": "Computed a % change",
    "get_series": "Read monthly values",
    "get_annual_average": "Computed an annual average",
    "compare_annual_averages": "Compared two annual averages",
    "compare_households": "Compared households",
    "rank_categories": "Ranked the categories",
    "get_weight": "Read an expenditure weight",
    "get_contributions": "Computed contributions to inflation",
    "get_priorities": "Read the monitoring criteria",
    "calculate": "Calculated from the figures above",
}


# --------------------------------------------------------------------------
# Plain helpers (tested without Streamlit)
# --------------------------------------------------------------------------
def api_key() -> str | None:
    """GEMINI_API_KEY from .streamlit/secrets.toml, else from the environment."""
    try:
        key = st.secrets.get(settings.API_KEY_NAME)
    except Exception:                      # no secrets file at all
        key = None
    key = key or os.environ.get(settings.API_KEY_NAME)
    return str(key).strip() if key and str(key).strip() else None


def safe_markdown(text: str) -> str:
    """Model text shown as Markdown without Streamlit turning '$' into maths."""
    return (text or "").replace("$", r"\$")


def model_line(ans: Answer) -> str:
    t = ans.tokens or {}
    calls = len(ans.tool_calls)
    parts = [f"{settings.MODEL_LABEL} ({ans.settings.get('model', settings.MODEL)})",
             f"{ans.latency_s:.1f} s",
             f"{t.get('total', 0):,} tokens (prompt {t.get('prompt', 0):,}, answer {t.get('output', 0):,}"
             + (f", thinking {t['thinking']:,}" if t.get("thinking") else "") + ")",
             f"{calls} tool call{'s' if calls != 1 else ''}"]
    return " · ".join(parts)


def call_summary(name: str, result: dict) -> str:
    """One line per tool call: what was done and the main figure it returned."""
    label = TOOL_NAMES.get(name, name)
    status = result.get("status")
    if status != "ok":
        return f"{label}: {status.replace('_', ' ') if status else 'no result'}. {result.get('message', '')}".strip()
    what = " · ".join(str(result[k]) for k in ("name", "population", "period") if result.get(k))
    figure = result.get("display")
    return f"{label}: {what} → **{figure}**" if figure and what else f"{label}: **{figure}**" if figure else label


# --------------------------------------------------------------------------
# Streamlit section
# --------------------------------------------------------------------------
def _show_answer(ans: Answer) -> None:
    if ans.status == ERROR:
        st.error(ans.answer)
    else:
        st.markdown(safe_markdown(ans.answer))
        if ans.status == DECLINED:
            st.caption("The app declined because the data does not hold this answer.")
        if ans.unsupported_numbers:
            st.warning("Check this answer: these numbers were not produced by the app's calculations: "
                       + ", ".join(ans.unsupported_numbers) + ". Do not quote them without checking.")
    if ans.tool_calls:
        with st.expander(f"How this answer was worked out ({len(ans.tool_calls)} step"
                         f"{'s' if len(ans.tool_calls) != 1 else ''})"):
            for i, call in enumerate(ans.tool_calls, 1):
                st.markdown(f"{i}. {safe_markdown(call_summary(call.name, call.result))}")
                st.json({"tool": call.name, "arguments": call.arguments, "result": call.result}, expanded=False)
    st.caption(model_line(ans))


def render_ask(data) -> None:
    st.markdown("<p class='pl-section'>Ask a question about the data</p>"
                "<p class='pl-section-sub'>Ask in plain English about Bahrain's CPI. Every number in the "
                "answer is computed by the app from iGA's published data; the model only writes the words.</p>",
                unsafe_allow_html=True)
    st.caption(f"Model: {settings.MODEL_LABEL} (`{settings.MODEL}`) · temperature {settings.TEMPERATURE} · "
               f"settings {settings.VERSION}")
    key = api_key()
    if not key:
        st.info("To ask questions, add your free Gemini API key. Create the file `.streamlit/secrets.toml` with "
                f"the line `{settings.API_KEY_NAME} = \"your-key-here\"` and restart the app. "
                "The README explains each step. The rest of the dashboard works without it.")
        return

    turns: list[Answer] = st.session_state.setdefault(TURNS_KEY, [])
    for ans in turns:
        with st.chat_message("user"):
            st.markdown(safe_markdown(ans.question))
        with st.chat_message("assistant"):
            _show_answer(ans)

    if not turns:
        st.caption("Examples: " + " · ".join(f"“{q}”" for q in EXAMPLES))
    with st.form("qa_form", clear_on_submit=True):
        question = st.text_input("Your question", max_chars=settings.MAX_QUESTION_CHARS,
                                 placeholder="For example: How much did food prices rise in the year to August 2026?")
        asked = st.form_submit_button("Ask", type="primary")
    if turns and st.button("Start a new conversation"):
        st.session_state[TURNS_KEY] = []
        st.rerun()
    if asked and question.strip():
        with st.spinner("Working out the answer..."):
            ans = DataQA(data, make_client(key)).ask(question, history=turns)
        turns.append(ans)
        st.rerun()
