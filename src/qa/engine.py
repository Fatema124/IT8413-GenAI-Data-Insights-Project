"""Questions over the data (F4): Gemini writes the answer, the tools compute every number.

How one question is answered:

    question --> Gemini (system prompt + tool declarations)
                   | asks for a tool, e.g. get_change(category="food", month="2026-08", measure="yoy")
                   v
                 Toolbox (src/pipeline/tools.py) computes it from the stored data
                   | JSON result: the figure, the two stored values used, the source
                   v
                 Gemini (may ask for more tools, up to MAX_TOOL_ROUNDS)
                   | final answer in plain English
                   v
                 number check (src/qa/numbers.py): every number must appear in a tool result

Usage:

    from src.qa.engine import DataQA, make_client
    qa = DataQA(prepared_data, make_client(api_key))
    first = qa.ask("What was the headline CPI in March 2026?")
    second = qa.ask("And in April?", history=[first])      # follow-up (F8)
    first.answer, first.status, first.tool_calls, first.tokens, first.latency_s

`ask` never raises: an API failure comes back as status "error" with a
message for the user. Every Answer has `to_record()`, a JSON-safe dict with
the question, answer, tool calls, tokens, time and settings, ready for the
query log (F10).
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.pipeline import config
from src.pipeline.tools import BAD_INPUT, NOT_AVAILABLE, OK, TOOL_DECLARATIONS, Toolbox, to_json

from . import numbers as N
from . import settings
from .prompts import SYSTEM_PROMPT

ANSWERED, DECLINED, ERROR = "answered", "declined", "error"
# Tool results whose numbers count as computed: a figure ("ok"), or what the data covers
# ("not_available"). "bad_input" and "error" messages can repeat the model's own numbers.
EVIDENCE = (OK, NOT_AVAILABLE)
# Facts the answer may always state: the index base (April 2019 = 100) and the latest month.
FIXED_FACTS = N.numbers_in_result([config.BASE_PERIOD, config.BASE_VALUE, config.DATA_END])

# --------------------------------------------------------------------------
# One extra tool: arithmetic on figures the data tools already returned
# --------------------------------------------------------------------------
CALCULATE = "calculate"
_OPERATIONS = {
    "difference": "a - b",
    "percent_change": "(b - a) / a x 100, the % change from a to b",
    "ratio": "a / b",
}
CALCULATE_DECLARATION = {
    "name": CALCULATE,
    "description": ("Arithmetic on two figures that earlier tool results returned, for example the gap in "
                    "index points between Bahraini and non-Bahraini households. Both numbers must come "
                    "from tool results. For changes over time use get_change instead, which uses the "
                    "stored (unrounded) values."),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": list(_OPERATIONS),
                          "description": "; ".join(f"{k}: {v}" for k, v in _OPERATIONS.items())},
            "a": {"type": "number", "description": "First figure, copied from a tool result."},
            "b": {"type": "number", "description": "Second figure, copied from a tool result."},
        },
        "required": ["operation", "a", "b"],
    },
}


def calculate(operation: str, a: float, b: float, known: set[float]) -> dict:
    """Run one calculation. `known` holds the numbers earlier tool results returned."""
    args = {"operation": operation, "a": a, "b": b}
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return {"status": BAD_INPUT, "tool": CALCULATE, "message": "a and b must be numbers.", "arguments": args}
    if operation not in _OPERATIONS:
        return {"status": BAD_INPUT, "tool": CALCULATE, "arguments": args,
                "message": f"Unknown operation '{operation}'. Use one of: {', '.join(_OPERATIONS)}."}
    missing = [str(x) for x in (a, b) if not N.matches(x, _decimals(x), known)]
    if missing:
        return {"status": BAD_INPUT, "tool": CALCULATE, "arguments": args,
                "message": (f"{', '.join(missing)} did not come from a tool result in this conversation. "
                            "Call the data tools first and copy their figures.")}
    if (operation == "ratio" and b == 0) or (operation == "percent_change" and a == 0):
        return {"status": BAD_INPUT, "tool": CALCULATE, "arguments": args, "message": "Division by zero."}
    if operation == "difference":
        value = a - b
    elif operation == "ratio":
        value = a / b
    else:
        value = (b - a) / a * 100
    shown = {"difference": f"{value:.1f}", "ratio": f"{value:.2f}", "percent_change": f"{value:+.1f}%"}[operation]
    return {"status": OK, "tool": CALCULATE, "operation": operation, "formula": _OPERATIONS[operation],
            "value": round(value, 4), "display": shown, "arguments": args,
            "note": "Computed by the app from the figures above; not an official iGA figure."}


def _decimals(x: float) -> int:
    """Decimals written in a number the model sent (119.6 -> 1, 122.96 -> 2, 2026.0 -> 0)."""
    text = repr(float(x))
    return 0 if "e" in text or text.endswith(".0") else len(text.split(".")[1])


TOOL_LIST = TOOL_DECLARATIONS + [CALCULATE_DECLARATION]


def gemini_declarations(extra: list | tuple = ()) -> list:
    """TOOL_LIST in the Gemini SDK's form.

    A tool without arguments (data_coverage) is declared with no parameters at all, because
    the Gemini API rejects an object schema whose "properties" is empty. An empty
    "required" list is left out for the same reason.
    """
    from google.genai import types
    out = []
    for d in [*TOOL_LIST, *extra]:
        params = dict(d["parameters"])
        if not params.get("required"):
            params.pop("required", None)
        out.append(types.FunctionDeclaration(name=d["name"], description=d["description"],
                                             parameters=params if params.get("properties") else None))
    return out


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: dict

    @property
    def status(self) -> str:
        return self.result.get("status", "")


@dataclass
class Answer:
    question: str
    answer: str
    status: str                                   # answered / declined / error
    tool_calls: list[ToolCall] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    tokens: dict = field(default_factory=dict)    # prompt, output, thinking, total
    latency_s: float = 0.0
    model_calls: int = 0
    retries: int = 0                              # busy-model retries (their wait is in latency_s)
    error: str | None = None
    retrieval: list[dict] = field(default_factory=list)   # ranks and scores of each document search (F5, F10)
    settings: dict = field(default_factory=settings.as_dict)
    asked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def verified(self) -> bool:
        """Every number in the answer was found in a tool result."""
        return self.status != ERROR and not self.unsupported_numbers

    def known_numbers(self) -> set[float]:
        found = N.question_numbers(self.question)
        for c in self.tool_calls:
            if c.status in EVIDENCE:
                found |= N.numbers_in_result(c.result)
        return found

    def to_record(self) -> dict:
        """JSON-safe dict for the query log (F10) and the evaluation spreadsheet."""
        rec = asdict(self)
        rec["verified"] = self.verified
        return json.loads(json.dumps(rec, ensure_ascii=False, default=str))


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------
def make_client(api_key: str):
    """A Gemini API client. Imported here so the rest of the app runs without the package."""
    from google import genai
    return genai.Client(api_key=api_key)


class DataQA:
    """Answers questions over the prepared data with Gemini and the Toolbox."""

    def __init__(self, data, client, model: str = settings.MODEL, sleep=time.sleep, documents=None):
        self.toolbox = Toolbox(data)
        self.documents = documents                # src.documents.tool.DocumentTools, or None (data only)
        self.client = client
        self.model = model
        self._sleep = sleep                       # replaced in tests so retries do not wait

    # ------------------------------------------------------------------ public
    def ask(self, question: str, history: list[Answer] | None = None) -> Answer:
        started = time.perf_counter()
        question = (question or "").strip()
        run_settings = {**settings.as_dict(), "model": self.model}
        if self.documents is not None:
            from src.documents import prompt as doc_prompt, settings as doc_settings
            run_settings.update(doc_settings.as_dict(), prompt=f"{settings.PROMPT_VERSION}+{doc_prompt.PROMPT_VERSION}")
        ans = Answer(question=question, answer="", status=ERROR, settings=run_settings)
        if not question:
            ans.error = ans.answer = "Please type a question."
            return ans
        if len(question) > settings.MAX_QUESTION_CHARS:
            ans.error = ans.answer = f"Please keep the question under {settings.MAX_QUESTION_CHARS} characters."
            return ans
        try:
            self._run(ans, list(history or []))
        except Exception as exc:                  # API or network failure: tell the user, never guess
            ans.status, ans.error, ans.answer = ERROR, f"{exc.__class__.__name__}: {exc}", explain_error(exc)
        ans.latency_s = round(time.perf_counter() - started, 3)
        return ans

    # ------------------------------------------------------------------ internals
    def _config(self):
        from google.genai import types
        prompt, extra = SYSTEM_PROMPT, ()
        if self.documents is not None:
            from src.documents.prompt import DOCUMENT_RULES
            from src.documents.tool import DECLARATION
            prompt, extra = SYSTEM_PROMPT + DOCUMENT_RULES, (DECLARATION,)
        return types.GenerateContentConfig(
            system_instruction=prompt,
            temperature=settings.TEMPERATURE,
            max_output_tokens=settings.MAX_OUTPUT_TOKENS,
            tools=[types.Tool(function_declarations=gemini_declarations(extra))],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    @staticmethod
    def _history(history: list[Answer]):
        """Earlier turns (already filtered and cut to HISTORY_TURNS) as plain text messages."""
        from google.genai import types
        contents = []
        for turn in history:
            contents.append(types.Content(role="user", parts=[types.Part(text=turn.question)]))
            contents.append(types.Content(role="model", parts=[types.Part(text=turn.answer)]))
        return contents

    def _run(self, ans: Answer, history: list[Answer]) -> None:
        from google.genai import types
        history = [h for h in history if h.status != ERROR][-settings.HISTORY_TURNS:]
        known: set[float] = N.question_numbers(ans.question) | FIXED_FACTS
        for turn in history:
            known |= turn.known_numbers()
        contents = self._history(history) + [types.Content(role="user", parts=[types.Part(text=ans.question)])]
        config = self._config()
        tokens = ans.tokens = {"prompt": 0, "output": 0, "thinking": 0, "total": 0}   # kept if a call fails

        for step in range(settings.MAX_TOOL_ROUNDS + 1):
            response = self._generate(ans, contents, config)
            ans.model_calls += 1
            _add_usage(tokens, getattr(response, "usage_metadata", None))
            content = _first_content(response)
            if content is None:
                ans.error = f"The model returned no answer ({_finish_reason(response)})."
                ans.answer = "The model did not return an answer. Please try again or rephrase the question."
                break
            calls = [p.function_call for p in (content.parts or []) if getattr(p, "function_call", None)]
            if not calls:
                text = "".join(p.text for p in (content.parts or [])
                               if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()
                if not text:
                    ans.error = f"The model returned an empty answer ({_finish_reason(response)})."
                    ans.answer = "The model did not return an answer. Please try again or rephrase the question."
                    break
                ans.answer = text
                # declined = the answer opens with the refusal sentence; a partial answer that uses it
                # later for one missing part counts as answered
                ans.status = DECLINED if text.lower().startswith(settings.NOT_AVAILABLE_SENTENCE.lower()) else ANSWERED
                ans.unsupported_numbers = N.unsupported_numbers(text, known)
                break
            if step == settings.MAX_TOOL_ROUNDS:
                ans.error = f"Stopped after {settings.MAX_TOOL_ROUNDS} rounds of tool calls without an answer."
                ans.answer = ("The question needed more steps than the app allows, so no answer is given. "
                              "Please ask about one figure at a time.")
                break
            contents.append(content)              # keeps the model's own parts (and thought signatures)
            replies = []
            for call in calls:
                args = _plain(dict(call.args or {}))
                result = self._call_tool(call.name, args, known, ans)
                ans.tool_calls.append(ToolCall(name=call.name, arguments=args, result=result))
                if result.get("status") in EVIDENCE:
                    known |= N.numbers_in_result(result)
                replies.append(types.Part(function_response=types.FunctionResponse(
                    id=getattr(call, "id", None), name=call.name, response=for_model(result))))
            contents.append(types.Content(role="user", parts=replies))

    def _generate(self, ans: Answer, contents, config):
        """One model call, retried when the model is busy or a per-minute limit is hit."""
        for attempt in range(len(settings.RETRY_WAITS_S) + 1):
            try:
                return self.client.models.generate_content(model=self.model, contents=contents, config=config)
            except Exception as exc:
                if getattr(exc, "code", None) not in settings.RETRY_CODES or attempt == len(settings.RETRY_WAITS_S):
                    raise
                ans.retries += 1
                self._sleep(settings.RETRY_WAITS_S[attempt])

    def _call_tool(self, name: str, args: dict, known: set[float], ans: Answer | None = None) -> dict:
        if self.documents is not None and name == "search_documents":
            result = self.documents.call(name, args, question=ans.question if ans is not None else None)
            if ans is not None:
                ans.retrieval.append({"query": args.get("query"), "hits": self.documents.last_search})
            return result
        if name == CALCULATE:
            try:
                return to_json(calculate(known=known, **args))
            except TypeError as exc:
                return {"status": BAD_INPUT, "tool": CALCULATE, "message": f"Wrong arguments: {exc}",
                        "arguments": to_json(args)}
        return self.toolbox.call(name, args)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
_INDEX_KEYS = ("current_index", "previous_index")


def for_model(result):
    """The tool result as the model sees it: stored index values rounded to one decimal place.

    The proposal quotes index values to 1 d.p.; the source stores some with more decimals (76.0154).
    Changes are already computed from the unrounded values by the tool, so rounding here only
    changes what the model can quote. The record keeps the full result.
    """
    if isinstance(result, dict):
        return {k: round(v, config.DISPLAY_DECIMALS)
                if isinstance(v, float) and (k in _INDEX_KEYS or k.startswith("average_")) else for_model(v)
                for k, v in result.items()}
    if isinstance(result, list):
        return [for_model(v) for v in result]
    return result


def _first_content(response):
    candidates = getattr(response, "candidates", None) or []
    return candidates[0].content if candidates and candidates[0].content is not None else None


def _finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if candidates and getattr(candidates[0], "finish_reason", None):
        return str(candidates[0].finish_reason)
    feedback = getattr(response, "prompt_feedback", None)
    return f"blocked: {feedback.block_reason}" if feedback and getattr(feedback, "block_reason", None) else "no reason given"


def _add_usage(tokens: dict, usage) -> None:
    if usage is None:
        return
    for key, attr in [("prompt", "prompt_token_count"), ("output", "candidates_token_count"),
                      ("thinking", "thoughts_token_count"), ("total", "total_token_count")]:
        tokens[key] += int(getattr(usage, attr, None) or 0)


def _plain(obj: Any):
    """Model arguments as plain Python (whole floats such as 2026.0 become ints)."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, float) and math.isfinite(obj) and obj.is_integer():
        return int(obj)
    return obj


def explain_error(exc: Exception) -> str:
    """A short message for the user. The full error stays in Answer.error."""
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    if code == 429 or "resource_exhausted" in text or "quota" in text:
        return ("The free Gemini limit was reached (15 questions a minute, 500 a day). "
                "Wait a minute and ask again.")
    if code in (401, 403) or "api key" in text or "api_key" in text:
        return "The Gemini API key was not accepted. Check GEMINI_API_KEY in .streamlit/secrets.toml."
    if code == 404 or "not found" in text:
        return f"The model '{settings.MODEL}' was not found for this API key."
    if code is not None and 500 <= int(code) < 600:
        return "Gemini is not responding right now. Please try again in a moment."
    return "The question could not be answered because of a technical problem. Please try again."
