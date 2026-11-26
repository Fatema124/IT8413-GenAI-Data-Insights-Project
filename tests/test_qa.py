"""Tests for questions over the data (F4). They need no API key and no network.

A fake Gemini client replays scripted model turns (built from the real
google-genai types), so the tests check everything the app does around the
model: the request it sends, running the tools, passing the results back,
the number check, refusals, follow-ups, limits and errors.
"""
from __future__ import annotations

import json

import pytest
from google.genai import types

from src.qa import numbers as N
from src.qa import settings
from src.qa.engine import (ANSWERED, CALCULATE, DECLINED, ERROR, TOOL_LIST, DataQA, calculate,
                           explain_error, for_model, gemini_declarations)
from src.qa.prompts import SYSTEM_PROMPT
from tests.fixtures import make_all


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    from src.pipeline.run import build
    return build(make_all(tmp_path_factory.mktemp("raw_qa")))


# --------------------------------------------------------------------------
# A fake Gemini client
# --------------------------------------------------------------------------
def call(name, call_id=None, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args, id=call_id))


def text(t):
    return types.Part(text=t)


def turn(*parts, prompt=100, output=20, thinking=None):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)), finish_reason="STOP")],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt, candidates_token_count=output, thoughts_token_count=thinking,
            total_token_count=prompt + output + (thinking or 0)))


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": list(contents), "config": config})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class FakeClient:
    def __init__(self, *script):
        self.models = FakeModels(script)


def function_responses(request):
    return [p.function_response for c in request["contents"] for p in (c.parts or []) if p.function_response]


# --------------------------------------------------------------------------
# The request sent to Gemini
# --------------------------------------------------------------------------
def test_request_uses_the_proposal_model_prompt_and_all_tools(data):
    client = FakeClient(turn(text("The headline CPI was 102.4 in March 2026.")))
    DataQA(data, client).ask("What was the headline CPI in March 2026?")
    req = client.models.requests[0]
    cfg = req["config"]
    assert req["model"] == settings.MODEL == "gemini-3.5-flash-lite"
    assert cfg.system_instruction == SYSTEM_PROMPT
    assert cfg.temperature == settings.TEMPERATURE == 0.0
    assert cfg.automatic_function_calling.disable is True          # the app runs the tools itself
    names = [d.name for d in cfg.tools[0].function_declarations]
    assert names == [d["name"] for d in TOOL_LIST] and CALCULATE in names and "get_change" in names
    assert req["contents"][-1].role == "user"
    assert req["contents"][-1].parts[0].text == "What was the headline CPI in March 2026?"


def test_prompt_states_the_rules_the_brief_asks_for():
    p = SYSTEM_PROMPT
    assert settings.NOT_AVAILABLE_SENTENCE in p                     # F7 refusal sentence
    assert "Every number in your answer must come from a tool result" in p    # F4
    for word in ["month-on-month", "year-on-year", "April 2019 = 100", "forecasts", "causes",
                 'measure "base"', "get_series", 'operation "difference"']:
        assert word in p
    assert "August 2026" in p


def test_tool_declarations_are_valid_for_the_gemini_sdk():
    decls = gemini_declarations()
    assert [d.name for d in decls] == [d["name"] for d in TOOL_LIST]
    by_name = {d.name: d for d in decls}
    assert by_name["data_coverage"].parameters is None          # the API rejects empty "properties"
    assert by_name["list_categories"].parameters.required is None
    assert by_name["get_change"].parameters.required == ["category", "month", "measure"]
    assert by_name["get_change"].parameters.properties["measure"].enum == ["index", "mom", "yoy", "base"]
    assert by_name["calculate"].parameters.properties["a"].type == types.Type.NUMBER
    for d in decls:
        assert d.description


# --------------------------------------------------------------------------
# Answering with tools
# --------------------------------------------------------------------------
def test_direct_lookup_runs_the_tool_and_passes_the_result_back(data):
    # Development question 26: headline CPI in March 2026 = 102.4
    client = FakeClient(
        turn(call("get_index", call_id="c1", category="headline", month="2026-03"), prompt=300, output=15),
        turn(text("The headline CPI in March 2026 was 102.4 (April 2019 = 100)."), prompt=500, output=25,
             thinking=10),
    )
    ans = DataQA(data, client).ask("What was the headline CPI in March 2026?")
    assert ans.status == ANSWERED and ans.verified and ans.unsupported_numbers == []
    assert [c.name for c in ans.tool_calls] == ["get_index"]
    assert ans.tool_calls[0].result["status"] == "ok" and ans.tool_calls[0].result["display"] == "102.4"
    assert ans.tokens == {"prompt": 800, "output": 40, "thinking": 10, "total": 850}
    assert ans.model_calls == 2 and ans.latency_s >= 0
    # the second request carries the model's call and the tool's answer, with the same id
    second = client.models.requests[1]
    fr = function_responses(second)
    assert len(fr) == 1 and fr[0].name == "get_index" and fr[0].id == "c1"
    assert fr[0].response["display"] == "102.4"
    assert any(p.function_call for c in second["contents"] for p in (c.parts or []))


def test_model_sees_index_values_to_one_decimal_but_the_record_keeps_them_whole(data):
    r = {"status": "ok", "value": 8.1653, "current_index": 133.0, "previous_index": 122.9565,
         "average_2019": 99.9026, "ranking": [{"previous_index": 76.0154, "value": 17.2134}], "period": "2026-08"}
    m = for_model(r)
    assert m["previous_index"] == 123.0 and m["average_2019"] == 99.9 and m["ranking"][0]["previous_index"] == 76.0
    assert m["value"] == 8.1653 and m["ranking"][0]["value"] == 17.2134 and m["period"] == "2026-08"
    client = FakeClient(turn(call("get_change", category="04.5", month="2026-08", measure="yoy")), turn(text("Done.")))
    ans = DataQA(data, client).ask("Electricity yoy August 2026?")
    sent = function_responses(client.models.requests[1])[0].response
    kept = ans.tool_calls[0].result
    assert sent["previous_index"] == round(kept["previous_index"], 1)
    assert kept["previous_index"] == pytest.approx(76.02, abs=0.005)      # planted fixture value, unrounded


def test_several_tool_calls_in_one_turn_are_all_answered(data):
    client = FakeClient(
        turn(call("get_index", category="04.5", month="2026-08"), call("get_change", category="04.5",
             month="2026-08", measure="mom")),
        turn(text("Electricity, Gas and Other Fuels was 89.1 in August 2026, up 6.3% on July.")),
    )
    ans = DataQA(data, client).ask("Electricity index and monthly change in August 2026?")
    assert [c.name for c in ans.tool_calls] == ["get_index", "get_change"]
    assert len(function_responses(client.models.requests[1])) == 2
    assert ans.verified, ans.unsupported_numbers


def test_a_number_no_tool_returned_is_flagged(data):
    client = FakeClient(
        turn(call("get_index", category="headline", month="2026-03")),
        turn(text("The headline CPI in March 2026 was 102.4, about 3.7% higher than a year before.")),
    )
    ans = DataQA(data, client).ask("What was the headline CPI in March 2026?")
    assert ans.status == ANSWERED
    assert ans.unsupported_numbers == ["3.7"] and not ans.verified


def test_an_answer_without_any_tool_call_cannot_quote_figures(data):
    client = FakeClient(turn(text("Headline CPI was 101.9 in March 2026.")))
    ans = DataQA(data, client).ask("What was the headline CPI in March 2026?")
    assert ans.tool_calls == [] and ans.unsupported_numbers == ["101.9"]     # 2026 and March come from the question


def test_bad_input_is_returned_to_the_model_to_fix(data):
    client = FakeClient(
        turn(call("get_index", category="headline", month="last month")),
        turn(call("get_index", category="headline", month="2026-08")),
        turn(text("I used August 2026, the latest month.")),
    )
    ans = DataQA(data, client).ask("What was the CPI last month?")
    assert [c.status for c in ans.tool_calls] == ["bad_input", "ok"]
    assert "relative" in ans.tool_calls[0].result["message"]


# --------------------------------------------------------------------------
# Refusal (F7)
# --------------------------------------------------------------------------
def test_not_available_result_leads_to_a_declined_answer(data):
    # Development question 20: headline CPI in December 2009 is not in any source
    client = FakeClient(
        turn(call("get_index", category="headline", month="2009-12")),
        turn(text(f"{settings.NOT_AVAILABLE_SENTENCE} The data starts in 2010.")),
    )
    ans = DataQA(data, client).ask("What was the headline CPI in December 2009?")
    assert ans.tool_calls[0].status == "not_available"
    assert ans.status == DECLINED and ans.verified


def test_partial_answer_is_answered_not_declined(data):
    client = FakeClient(turn(text(f"Housing fell. {settings.NOT_AVAILABLE_SENTENCE} (the weights)")))
    assert DataQA(data, client).ask("Weight and change?").status == ANSWERED


def test_refusal_without_a_tool_call_for_a_forecast(data):
    client = FakeClient(turn(text(f"{settings.NOT_AVAILABLE_SENTENCE} The data records past prices only.")))
    ans = DataQA(data, client).ask("What will the headline CPI be in December 2026?")
    assert ans.status == DECLINED and ans.tool_calls == []


# --------------------------------------------------------------------------
# The calculate tool
# --------------------------------------------------------------------------
def test_calculate_gap_between_households(data):
    # Development question 13(b): Bahraini 119.6 is 18.0 points above non-Bahraini 101.6
    client = FakeClient(
        turn(call("compare_households", category="Restaurants and Hotels", month="2026-08", measure="index")),
        turn(call("calculate", operation="difference", a=119.6, b=101.6)),
        turn(text("In August 2026 the Bahraini index was 119.6 and the non-Bahraini index 101.6, "
                  "a gap of 18.0 points; the national figure was 115.0.")),
    )
    ans = DataQA(data, client).ask("How did Restaurants and Hotels compare across households in August 2026?")
    calc = ans.tool_calls[1].result
    assert calc["status"] == "ok" and calc["display"] == "18.0" and calc["value"] == pytest.approx(18.0)
    assert ans.verified, ans.unsupported_numbers


def test_calculate_refuses_numbers_that_no_tool_returned(data):
    client = FakeClient(
        turn(call("calculate", operation="difference", a=119.6, b=101.6)),
        turn(text("I could not compute it.")),
    )
    ans = DataQA(data, client).ask("Gap?")
    assert ans.tool_calls[0].status == "bad_input"
    assert "did not come from a tool result" in ans.tool_calls[0].result["message"]


def test_numbers_the_model_sent_are_not_evidence(data):
    # a refused calculation echoes the model's own numbers; they must not make the answer "verified"
    client = FakeClient(
        turn(call("calculate", operation="difference", a=50.5, b=10.0)),
        turn(text("The gap is 50.5 minus 10, so 40.5 points.")),
    )
    ans = DataQA(data, client).ask("Gap?")
    assert ans.unsupported_numbers == ["50.5", "40.5"]


@pytest.mark.parametrize("op,a,b,display", [
    ("difference", 119.6, 101.6, "18.0"), ("percent_change", 122.96, 133.0, "+8.2%"),
    ("percent_change", 89.93, 88.9, "-1.1%"), ("ratio", 133.0, 122.96, "1.08"),
])
def test_calculate_operations(op, a, b, display):
    r = calculate(op, a, b, known={a, b})
    assert r["status"] == "ok" and r["display"] == display


def test_calculate_rejects_bad_requests():
    assert calculate("power", 1, 2, known={1.0, 2.0})["status"] == "bad_input"
    assert calculate("ratio", 5, 0, known={5.0, 0.0})["status"] == "bad_input"
    assert calculate("difference", "x", 2, known={2.0})["status"] == "bad_input"


def test_calculate_with_wrong_argument_names_does_not_crash(data):
    client = FakeClient(turn(call("calculate", operation="difference", x=1)), turn(text("Sorry.")))
    ans = DataQA(data, client).ask("Gap?")
    assert ans.tool_calls[0].status == "bad_input" and ans.status == ANSWERED


# --------------------------------------------------------------------------
# Follow-up questions (F8 groundwork)
# --------------------------------------------------------------------------
def test_follow_up_sends_the_earlier_turn_and_may_reuse_its_figures(data):
    qa = DataQA(data, FakeClient(
        turn(call("get_index", category="11", month="2026-08")),
        turn(text("The Restaurants and Hotels index was 115.0 in August 2026.")),
    ))
    first = qa.ask("What was the Restaurants and Hotels index in August 2026?")
    client = FakeClient(
        turn(call("compare_households", category="11", month="2026-08", measure="index")),
        turn(text("Bahraini households: 119.6; non-Bahraini: 101.6; national 115.0.")),
    )
    second = DataQA(data, client).ask("How did it compare for Bahraini and non-Bahraini households?",
                                      history=[first])
    contents = client.models.requests[0]["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[0].parts[0].text == first.question and contents[1].parts[0].text == first.answer
    assert second.verified, second.unsupported_numbers


def test_history_is_limited_and_skips_failed_turns(data):
    qa = DataQA(data, FakeClient(*[turn(text(f"Answer {i}.")) for i in range(5)]))
    history = [qa.ask(f"Question {i}?") for i in range(5)]
    history[-1].status = ERROR
    client = FakeClient(turn(text("Fine.")))
    DataQA(data, client).ask("Next?", history=history)
    sent = [c.parts[0].text for c in client.models.requests[0]["contents"] if c.role == "user"]
    assert sent == ["Question 1?", "Question 2?", "Question 3?", "Next?"][-(settings.HISTORY_TURNS + 1):]


# --------------------------------------------------------------------------
# Limits and failures: ask() never raises
# --------------------------------------------------------------------------
def test_too_many_tool_rounds_stops_without_an_answer(data):
    loop = [turn(call("data_coverage")) for _ in range(settings.MAX_TOOL_ROUNDS + 1)]
    ans = DataQA(data, FakeClient(*loop)).ask("Loop forever?")
    assert ans.status == ERROR and "more steps" in ans.answer
    assert ans.model_calls == settings.MAX_TOOL_ROUNDS + 1 and len(ans.tool_calls) == settings.MAX_TOOL_ROUNDS


def test_api_error_becomes_a_friendly_message(data):
    class RateLimited(Exception):
        code = 429
    waits = []
    client = FakeClient(*[RateLimited("RESOURCE_EXHAUSTED")] * 3)
    ans = DataQA(data, client, sleep=waits.append).ask("Anything?")
    assert ans.status == ERROR and "limit" in ans.answer and "RESOURCE_EXHAUSTED" in ans.error
    assert waits == list(settings.RETRY_WAITS_S) and ans.retries == 2 and len(client.models.requests) == 3


def test_a_busy_model_is_retried_and_then_answers(data):
    class Busy(Exception):
        code = 503
    waits = []
    client = FakeClient(Busy("UNAVAILABLE"), turn(text("Hello.")))
    ans = DataQA(data, client, sleep=waits.append).ask("Hi?")
    assert ans.status == ANSWERED and ans.answer == "Hello." and ans.retries == 1 and waits == [3]


def test_other_errors_are_not_retried(data):
    class BadKey(Exception):
        code = 400
    client = FakeClient(BadKey("API key not valid"))
    ans = DataQA(data, client, sleep=lambda s: None).ask("Hi?")
    assert ans.status == ERROR and ans.retries == 0 and "key" in ans.answer


def test_tokens_used_before_a_failure_are_kept(data):
    class Down(Exception):
        code = 503
    client = FakeClient(turn(call("data_coverage"), prompt=100, output=5), *[Down("unavailable")] * 3)
    ans = DataQA(data, client, sleep=lambda s: None).ask("Anything?")
    assert ans.status == ERROR and ans.tokens["prompt"] == 100 and len(ans.tool_calls) == 1


def test_empty_model_reply_is_an_error(data):
    empty = types.GenerateContentResponse(candidates=[], prompt_feedback=None)
    ans = DataQA(data, FakeClient(empty)).ask("Anything?")
    assert ans.status == ERROR and ans.error.startswith("The model returned no answer")


def test_thought_parts_are_not_shown_as_the_answer(data):
    client = FakeClient(turn(types.Part(text="thinking about it", thought=True), text("Done.")))
    assert DataQA(data, client).ask("Hi?").answer == "Done."


@pytest.mark.parametrize("q,msg", [("", "type a question"), ("x" * (settings.MAX_QUESTION_CHARS + 1), "under")])
def test_empty_or_long_question_is_not_sent(data, q, msg):
    client = FakeClient()
    ans = DataQA(data, client).ask(q)
    assert ans.status == ERROR and msg in ans.answer and client.models.requests == []


@pytest.mark.parametrize("code,word", [(429, "limit"), (403, "key"), (404, "not found"), (503, "not responding"),
                                       (None, "technical problem")])
def test_error_messages(code, word):
    exc = Exception("boom")
    exc.code = code
    assert word in explain_error(exc)


def test_record_is_json_ready_for_the_query_log(data):
    client = FakeClient(turn(call("get_index", category="0", month="2026-03")), turn(text("It was 102.4.")))
    rec = DataQA(data, client).ask("Headline March 2026?").to_record()
    json.dumps(rec)
    for key in ["question", "answer", "status", "tool_calls", "tokens", "latency_s", "settings", "asked_at",
                "verified", "unsupported_numbers"]:
        assert key in rec
    assert rec["settings"]["model"] == settings.MODEL and rec["settings"]["version"] == settings.VERSION
    assert rec["settings"]["prompt"] == settings.PROMPT_VERSION and rec["retries"] == 0
    assert rec["tool_calls"][0]["name"] == "get_index"


# --------------------------------------------------------------------------
# The number check
# --------------------------------------------------------------------------
@pytest.mark.parametrize("answer,known,bad", [
    ("rose 8.2%", {8.1653}, []),                       # rounded to the decimals shown
    ("fell 1.1%", {-1.1432}, []),                      # sign written as a word
    ("was 123.0", {122.96}, []),
    ("was 123.1", {122.96}, ["123.1"]),
    ("about 8%", {8.1653}, []),
    ("about 9%", {8.1653}, ["9"]),                     # small numbers still checked when written as %
    ("over 12 months in 3 divisions", set(), []),      # small whole numbers used as words
    ("a gap of 3 points", set(), ["3"]),
    ("1,234.5 and 2026", {1234.5, 2026.0}, []),
    ("version v1 of 47.3", {47.3}, []),
])
def test_unsupported_numbers(answer, known, bad):
    assert N.unsupported_numbers(answer, known) == bad


def test_the_index_base_may_always_be_stated(data):
    client = FakeClient(turn(call("get_change", category="07", month="2026-07", measure="yoy")),
                        turn(text("Transport rose (April 2019 = 100; latest month August 2026).")))
    assert DataQA(data, client).ask("Transport yoy July 2026?").unsupported_numbers == []


def test_a_figure_the_user_wrote_is_not_evidence(data):
    client = FakeClient(turn(text("Yes, inflation was 5% in August 2026.")))
    ans = DataQA(data, client).ask("Was inflation 5% in August 2026?")
    assert ans.unsupported_numbers == ["5"]
    assert N.question_numbers("Code 04.5 in 2026-08, up 5%?") == {4.5, 2026.0, 8.0}


def test_numbers_in_tool_results_include_numbers_inside_text():
    found = N.numbers_in_result({"value": -1.1, "period": "2026-08", "unit": "index points (April 2019 = 100)",
                                 "ok": True, "missing": None, "list": [{"v": 89.93}]})
    assert {1.1, 2026.0, 8.0, 2019.0, 100.0, 89.93} <= found
    assert 1.0 not in found                            # True is not the number 1


# --------------------------------------------------------------------------
# The Streamlit section's helpers
# --------------------------------------------------------------------------
def test_api_key_from_environment(monkeypatch):
    from src.dashboard import ask
    monkeypatch.setenv(settings.API_KEY_NAME, "  test-key  ")
    assert ask.api_key() == "test-key"
    monkeypatch.setenv(settings.API_KEY_NAME, "")
    assert ask.api_key() is None


def test_section_helpers(data):
    from src.dashboard import ask
    assert ask.safe_markdown("costs $5") == r"costs \$5"
    client = FakeClient(turn(call("get_index", category="0", month="2026-03")), turn(text("It was 102.4.")))
    ans = DataQA(data, client).ask("Headline March 2026?")
    line = ask.call_summary(ans.tool_calls[0].name, ans.tool_calls[0].result)
    assert line.startswith("Read an index value") and "**102.4**" in line
    assert ask.call_summary("get_index", {"status": "not_available", "message": "No data."}) == \
        "Read an index value: not available. No data."
    assert "Gemini 3.5 Flash-Lite" in ask.model_line(ans) and "tool call" in ask.model_line(ans)
    assert set(ask.TOOL_NAMES) == {d["name"] for d in TOOL_LIST}


def test_examples_are_not_test_set_questions():
    from src.dashboard import ask
    banned = ["March 2026", "December 2009", "Restaurants and Hotels", "Meat", "December 2025", "January 2026"]
    assert not any(b in q for q in ask.EXAMPLES for b in banned)
