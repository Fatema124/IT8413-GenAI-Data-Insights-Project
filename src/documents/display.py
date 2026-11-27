"""Showing the document passages behind an answer (F5: citations that can be verified).

Used by the Ask tab (src/dashboard/ask.py): every passage the tool returned is
listed under the answer with its citation, its status (in force, or changed
by Law No. 28 of 2026) and the full text, Arabic shown right to left.
"""
from __future__ import annotations

import html

import streamlit as st

from .tool import SEARCH

STATUS_TEXT = {
    "superseded": "replaced by Law No. 28 of 2026",
    "amended": "changed by Law No. 28 of 2026",
    "amending": "Law No. 28 of 2026: text in force",
    "guidance": "Ministry guidance (2016)",
    "statistics": "iGA release (September 2023)",
}


def retrieved_passages(ans) -> list[dict]:
    """Every distinct passage returned by search_documents for this answer, in order."""
    seen, out = set(), []
    for call in getattr(ans, "tool_calls", []):
        if call.name == SEARCH and call.result.get("status") == "ok":
            for p in call.result["passages"]:
                if p["id"] not in seen:
                    seen.add(p["id"]); out.append(p)
    return out


@st.cache_resource(show_spinner="Loading the document collection...")
def load_document_tools():
    """The document tool, or None when the documents have not been prepared on this computer,
    or when the search package (fastembed) is not installed, e.g. on Python 3.14+ where it has
    no wheel yet. The app then answers from the data only, exactly as before."""
    from .retrieve import Retriever
    from .tool import DocumentTools
    try:
        return DocumentTools(Retriever.load())
    except (FileNotFoundError, ImportError):
        return None


def show_sources(ans) -> None:
    passages = retrieved_passages(ans)
    if not passages:
        return
    with st.expander(f"Document passages used ({len(passages)})"):
        for p in passages:
            status = STATUS_TEXT.get(p["status"])
            st.markdown(f"**{html.escape(p['citation'])}**" + (f" · _{status}_" if status else ""))
            if p.get("note"):
                st.caption(p["note"])
            direction = "rtl" if p["language"] == "ar" else "ltr"
            st.markdown(f"<div dir='{direction}' style='white-space:pre-wrap;font-size:0.92rem'>"
                        f"{html.escape(p['text'])}</div>", unsafe_allow_html=True)
            st.divider()
