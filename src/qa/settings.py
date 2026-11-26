"""Settings for question answering (F4), in one place so every result can be reproduced (F10).

The evaluation compares v1 with v2, and v2 changes exactly one of these
settings (brief 7.5). `as_dict()` is what the app shows and what each answer
record stores, so a logged answer always says which settings produced it.
"""
from __future__ import annotations

VERSION = "v1"
PROMPT_VERSION = "v1"      # src/qa/prompts.py

# Proposal Section 5: Gemini 3.5 Flash-Lite (stable) through the Gemini API, free tier.
MODEL = "gemini-3.5-flash-lite"
MODEL_LABEL = "Gemini 3.5 Flash-Lite"

TEMPERATURE = 0.0          # the same question should get the same answer
MAX_OUTPUT_TOKENS = 1024   # answers are short replies, not reports
MAX_TOOL_ROUNDS = 6        # model -> tools -> model steps before the app gives up
HISTORY_TURNS = 3          # earlier questions and answers sent with a new question (follow-ups, F8)
MAX_QUESTION_CHARS = 500

# A busy model (503) or a per-minute limit (429) is retried after these waits, in seconds.
RETRY_WAITS_S = (3, 10)
RETRY_CODES = (429, 500, 503, 504)

# Name of the key in .streamlit/secrets.toml or the environment.
API_KEY_NAME = "GEMINI_API_KEY"

# The exact sentence the model must use when the sources cannot answer (F7).
# The app detects a refusal by this sentence, so it must not be reworded.
NOT_AVAILABLE_SENTENCE = "This is not available in the sources."


def as_dict() -> dict:
    return {"version": VERSION, "model": MODEL, "temperature": TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS, "max_tool_rounds": MAX_TOOL_ROUNDS,
            "history_turns": HISTORY_TURNS, "prompt": PROMPT_VERSION}
