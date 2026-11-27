"""The final evaluation (brief 7.2): the four configurations on the FULL test set.

    python -m scripts.run_evaluation control
    python -m scripts.run_evaluation baseline
    python -m scripts.run_evaluation v1
    python -m scripts.run_evaluation v2
    python -m scripts.run_evaluation all            # the four, one after the other

Options: --testset results/test_set.csv (default) and --only 2,13,26 (re-run some questions;
their rows are replaced in the output, the others are kept).

Configurations (brief 7.2):
- control:  the model on its own. The question exactly as asked, no system prompt, no data,
            documents, retrieval or tools.
- baseline: plain prompting. Docs 4-10 as text (src/documents/baseline.py, the same pages and
            citations the tool uses) plus the full text of every dataset the question's source
            location names (all of Datasets 1-2 for unanswerable questions) go into the prompt;
            no retrieval and no tools.
- v1 / v2:  the tool (src/qa/engine.py with the document tool), retrieval settings v1 or v2
            (src/documents/settings.py, one setting differs).

Every configuration uses the same model and temperature (src/qa/settings.py). Question 13 is a
follow-up pair (F8): (a) and (b) are asked in one session and recorded as one answer.

Writes results/final/<run>.jsonl (full record per question, kept out of git because it quotes MOIC
text) and results/final/<run>.csv (one row per question in the column order of the Results sheet).
Also writes results/<run>.jsonl and results/<run>_scores.csv in the format of
scripts/run_dev_documents.py, so that after scoring
`python -m scripts.failure_analysis v1 --testset results/test_set.csv` runs on the full test set. Held-out questions are run here, so run this only for the final
evaluation, after v2 is fixed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from scripts.run_dev_documents import api_key
from src.evaluation.testset import load_items
from src.pipeline import config
from src.qa import settings

RESULTS = config.REPO_ROOT / "results"
OUT = RESULTS / "final"
RUNS = ("control", "baseline", "v1", "v2")
RUN_LABEL = {"control": "Control", "baseline": "Baseline", "v1": "v1", "v2": "v2"}
SET_LABEL = {"development": "Development", "held-out": "Held-out"}
# Free tier: per-minute token limits are hit by the long baseline prompts, so wait longer.
WAITS_S = (5, 20, 60, 90)

BASELINE_RULES = f"""Answer the question using only the source text below. After each statement, cite
the source in square brackets as it is labelled in the text (for example [Executive Regulation
(MD 66/2014), p. 18] or [Dataset 1, code 04.5, 2026-08]). If the sources do not contain the answer,
reply with exactly: "{settings.NOT_AVAILABLE_SENTENCE}" and say briefly what is missing."""


# ------------------------------------------------------------------ helpers
def qid_label(qid: str) -> str:
    return f"Q{int(re.match(r'\d+', qid).group()):02d}"


def split_followup(question: str) -> list[str]:
    """'... (a) first? (b) second?' -> ['first?', 'second?']; any other question -> [question]."""
    m = re.search(r"\(a\)\s*(.+?)\s*\(b\)\s*(.+)$", question)
    return [m.group(1).strip(), m.group(2).strip()] if m else [question]


def generate(client, contents, config_):
    for attempt in range(len(WAITS_S) + 1):
        try:
            return client.models.generate_content(model=settings.MODEL, contents=contents, config=config_)
        except Exception as exc:
            if getattr(exc, "code", None) not in settings.RETRY_CODES or attempt == len(WAITS_S):
                raise
            time.sleep(WAITS_S[attempt])


def usage(response) -> tuple[int, int]:
    u = getattr(response, "usage_metadata", None)
    if u is None:
        return 0, 0
    out = (getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
    return getattr(u, "prompt_token_count", 0) or 0, out


def text_of(response) -> str:
    try:
        parts = response.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        return ""
    return "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()


# ------------------------------------------------------------------ baseline sources
def dataset_text(key: str) -> str:
    if key in ("D1", "D2"):
        path = config.RAW_DIR / config.RAW_FILES[key]
        return f"=== Dataset {key[1]}: {path.name} ===\n" + path.read_text(encoding="utf-8-sig")
    import pandas as pd
    path = config.RAW_DIR / config.RAW_FILES["D3"]
    sheets = [s for s in (config.D3_WEIGHTS_SHEET, config.D3_HISTORY_SHEET) if s]
    body = [f"--- sheet: {s} ---\n" + pd.read_excel(path, sheet_name=s, header=None).dropna(how="all")
            .to_csv(index=False, header=False) for s in sheets]
    return f"=== Dataset 3: {path.name} ===\n" + "\n".join(body)


def datasets_for(location: str, must_decline: bool) -> list[str]:
    if must_decline:
        return ["D1", "D2"]
    return [f"D{n}" for n in sorted(set(re.findall(r"Dataset\s*(\d)", location or "")))]


# ------------------------------------------------------------------ the four configurations
class Plain:
    """control (no system prompt, nothing but the question) or baseline (sources in the prompt)."""

    def __init__(self, client, baseline: bool):
        from google.genai import types
        self.types, self.client, self.baseline = types, client, baseline
        self.docs = None
        if baseline:
            from src.documents.baseline import baseline_text
            self.docs = baseline_text()

    def ask(self, item, location: str) -> dict:
        t = self.types
        system = None
        if self.baseline:
            sources = [self.docs] + [dataset_text(k) for k in datasets_for(location, item.must_decline)]
            system = BASELINE_RULES + "\n\nSOURCE TEXT\n\n" + "\n\n\n".join(sources)
        cfg = t.GenerateContentConfig(system_instruction=system, temperature=settings.TEMPERATURE,
                                      max_output_tokens=settings.MAX_OUTPUT_TOKENS)
        contents, answers, tin, tout = [], [], 0, 0
        started = time.perf_counter()
        for q in split_followup(item.question):
            contents.append(t.Content(role="user", parts=[t.Part(text=q)]))
            r = generate(self.client, contents, cfg)
            a, b = usage(r)
            tin, tout = tin + a, tout + b
            text = text_of(r) or "(no answer returned)"
            answers.append(text)
            contents.append(t.Content(role="model", parts=[t.Part(text=text)]))
        answer = "\n\n".join(answers) if len(answers) == 1 else \
            "\n\n".join(f"({k}) {a}" for k, a in zip("ab", answers))
        cites = sorted(set(re.findall(r"\[([^\[\]]{3,120})\]", answer))) if self.baseline else []
        return {"answer": answer, "citations": " | ".join(cites), "input_tokens": tin, "output_tokens": tout,
                "latency_s": round(time.perf_counter() - started, 3)}


class Tool:
    """v1 or v2: the full tool."""

    def __init__(self, client, version: str):
        from src.documents import settings as doc_settings
        from src.documents.retrieve import Retriever
        from src.documents.tool import DocumentTools
        from src.pipeline.run import build, load_prepared
        from src.qa.engine import DataQA
        doc_settings.use_version(version)
        settings.VERSION = version
        try:
            data = load_prepared()
        except FileNotFoundError:
            data = build()
        self.qa = DataQA(data, client, documents=DocumentTools(Retriever.load()))

    def ask(self, item, location: str) -> dict:
        history, answers, records = [], [], []
        for q in split_followup(item.question):
            ans = self.qa.ask(q, history=history)
            history.append(ans)
            records.append(ans.to_record())
            answers.append(ans.answer)
        answer = answers[0] if len(answers) == 1 else "\n\n".join(f"({k}) {a}" for k, a in zip("ab", answers))
        cites = []
        for rec in records:
            for c in rec.get("tool_calls", []):
                res = c.get("result", {})
                for p in res.get("passages", []):
                    if p["citation"] not in cites:
                        cites.append(p["citation"])
                src = res.get("source") or res.get("sources")
                if c.get("name") != "search_documents" and src:
                    label = f"{src} ({c['name']})"
                    if label not in cites:
                        cites.append(label)
        return {"answer": answer, "citations": " | ".join(map(str, cites)),
                "input_tokens": sum(r["tokens"].get("prompt", 0) for r in records),
                "output_tokens": sum(r["tokens"].get("output", 0) + r["tokens"].get("thinking", 0) for r in records),
                "latency_s": round(sum(r["latency_s"] for r in records), 3),
                "status": [r["status"] for r in records], "unsupported_numbers": [r["unsupported_numbers"] for r in records],
                "records": records}


# ------------------------------------------------------------------ failure-analysis format
SCORE_COLUMNS = ["accuracy", "groundedness", "refusal", "completeness", "ambiguous", "notes", "category"]


def analysis_record(rec: dict) -> dict:
    """One record per question as src/evaluation/failures.py reads it (status, tool_calls, retrieval,
    unsupported_numbers, tokens, latency_s); a follow-up pair is merged into one."""
    subs = rec.get("records")
    if not subs:                                   # control / baseline, or a run error
        text = rec["answer"]
        status = "error" if text.startswith("(run error") else \
            "declined" if text.lower().startswith(settings.NOT_AVAILABLE_SENTENCE.lower()) else "answered"
        return {"answer": text, "status": status, "tool_calls": [], "retrieval": [], "unsupported_numbers": [],
                "tokens": {"prompt": rec["input_tokens"] or 0, "output": rec["output_tokens"] or 0},
                "latency_s": rec["latency_s"] or 0}
    statuses = [r["status"] for r in subs]
    status = "error" if "error" in statuses else "declined" if all(x == "declined" for x in statuses) else "answered"
    return {"answer": rec["answer"], "status": status,
            "tool_calls": [c for r in subs for c in r.get("tool_calls", [])],
            "retrieval": [x for r in subs for x in r.get("retrieval", [])],
            "unsupported_numbers": [n for r in subs for n in r.get("unsupported_numbers", [])],
            "tokens": {"prompt": rec["input_tokens"], "output": rec["output_tokens"]},
            "latency_s": rec["latency_s"], "settings": subs[0].get("settings", {})}


def write_analysis_files(name: str, rows: list[dict], items: dict) -> None:
    with open(RESULTS / f"{name}.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"run": name, "question": r["question"], "split": r["split"],
                                 "record": analysis_record(r["record"])}, ensure_ascii=False) + "\n")
    with open(RESULTS / f"{name}_scores.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["run", "question", "type", "status", "question text", "ground truth", "answer",
                    "passages shown", "tokens", "latency_s", *SCORE_COLUMNS])
        for r in rows:
            it, a = items[r["question"]], analysis_record(r["record"])
            w.writerow([name, r["question"], it.kind, a["status"], it.question, it.ground_truth, a["answer"],
                        r["record"]["citations"], (a["tokens"]["prompt"] or 0) + (a["tokens"]["output"] or 0),
                        a["latency_s"], *[""] * len(SCORE_COLUMNS)])


# ------------------------------------------------------------------ main
def run(name: str, client, items: dict, locations: dict, only: set[str] | None) -> None:
    engine = Plain(client, baseline=(name == "baseline")) if name in ("control", "baseline") else Tool(client, name)
    OUT.mkdir(parents=True, exist_ok=True)
    jl = OUT / f"{name}.jsonl"
    done = {}
    if only and jl.exists():
        done = {r["question"]: r for r in map(json.loads, jl.read_text(encoding="utf-8").splitlines())}
    for qid, item in items.items():
        if only and qid not in only:
            continue
        try:
            rec = engine.ask(item, locations[qid])
        except Exception as exc:          # recorded, not hidden: the row says what went wrong
            rec = {"answer": f"(run error: {exc.__class__.__name__}: {exc})", "citations": "",
                   "input_tokens": "", "output_tokens": "", "latency_s": ""}
        done[qid] = {"run": RUN_LABEL[name], "question": qid, "split": item.split, "record": rec,
                     "settings": settings.as_dict()}
        print(f"{name} Q{qid}: {rec['latency_s']} s, {rec['input_tokens']} in / {rec['output_tokens']} out")
    order = list(items)
    rows = [done[q] for q in order if q in done]
    jl.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Run", "QID", "Set", "Question", "Answer (as produced)", "Citation (as produced)",
                    "Input tokens", "Output tokens", "Latency (seconds)"])
        for r in rows:
            it, rec = items[r["question"]], r["record"]
            w.writerow([r["run"], qid_label(r["question"]), SET_LABEL[it.split], it.question, rec["answer"],
                        rec["citations"], rec["input_tokens"], rec["output_tokens"], rec["latency_s"]])
    write_analysis_files(name, rows, items)
    print(f"Wrote {jl}, {OUT / (name + '.csv')}, results/{name}.jsonl and results/{name}_scores.csv")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", choices=RUNS + ("all",))
    ap.add_argument("--testset", default=str(RESULTS / "test_set.csv"))
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    items = load_items(Path(a.testset))
    with open(a.testset, encoding="utf-8-sig") as fh:
        locations = {r["question"].strip(): r.get("source location", "") for r in csv.DictReader(fh)}
    from src.qa.engine import make_client
    client = make_client(api_key())
    only = {q.strip() for q in a.only.split(",") if q.strip()} or None
    for name in (RUNS if a.run == "all" else (a.run,)):
        run(name, client, items, locations, only)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
