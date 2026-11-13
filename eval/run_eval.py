"""Evaluation harness: runs eval/cases.json through assistant.run() and checks each expectation.

Usage:
    python eval/run_eval.py            # offline (default): deterministic, free, fast
    python eval/run_eval.py --live     # use Gemini, 4 s pause between cases
"""

import argparse
import json
import os
import sys
import time
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # assistant.py loads data/songs.csv relative to the project root

from src import assistant  # noqa: E402
from src.llm_client import is_llm_available  # noqa: E402

CASES_PATH = ROOT / "eval" / "cases.json"
EVIDENCE = ROOT / "docs" / "evidence"
PAUSE_SECONDS = 4


# ---------------------------------------------------------------- running one case

def run_case(case: dict, offline: bool):
    """Run one case; also capture the trace record that assistant.run() writes."""
    captured = {}
    original = assistant.Trace.write

    def capture(self, result):
        captured.update(request=self.request, steps=self.steps, errors=self.errors)
        original(self, result)

    assistant.Trace.write = capture
    try:
        result = assistant.run(case["request"], offline=offline)
    finally:
        assistant.Trace.write = original
    return result, captured


def check_case(case: dict, result: dict) -> list:
    """Return a list of failure reasons (empty = pass)."""
    exp = case["expectations"]
    fails = []
    rejected = bool(result.get("error"))

    if "expect_rejected" in exp and exp["expect_rejected"] != rejected:
        fails.append(f"expected rejected={exp['expect_rejected']}, got rejected={rejected}"
                     + (f" ({result['error']})" if rejected else ""))
    if rejected:
        return fails  # nothing else to check on a rejected request

    profile = result["profile"] or {}
    answer = result["answer"]
    picked = [p["title"] for p in answer["picks"]]
    by_title = {s["title"]: s for s, _, _ in result["retrieved"]}

    # always: picks are real retrieved songs, and all verification checks passed
    fake = [t for t in picked if t not in by_title]
    if fake:
        fails.append(f"picks not retrieved: {fake}")
    failed = [c["check"] for c in result["verification"] if not c["passed"]]
    if failed:
        fails.append(f"verification failed: {failed}")

    if "genre_in" in exp and profile.get("genre") not in exp["genre_in"]:
        fails.append(f"genre {profile.get('genre')!r} not in {exp['genre_in']}")
    if "mood_in" in exp and profile.get("mood") not in exp["mood_in"]:
        fails.append(f"mood {profile.get('mood')!r} not in {exp['mood_in']}")
    if "pick_energy_between" in exp:
        lo, hi = exp["pick_energy_between"]
        bad = [f"{t} ({float(by_title[t]['energy']):.2f})" for t in picked
               if t in by_title and not lo <= float(by_title[t]["energy"]) <= hi]
        if bad:
            fails.append(f"picks outside energy [{lo}, {hi}]: {', '.join(bad)}")
    if "must_not_pick_genres" in exp:
        bad = [f"{t} [{by_title[t]['genre']}]" for t in picked
               if t in by_title and by_title[t]["genre"] in exp["must_not_pick_genres"]]
        if bad:
            fails.append(f"picked forbidden genres: {', '.join(bad)}")
    if "min_confidence" in exp and result["confidence"] < exp["min_confidence"]:
        fails.append(f"confidence {result['confidence']:.2f} < {exp['min_confidence']}")
    if "must_not_mention" in exp:
        text = " ".join([p["title"] + " " + p["why"] for p in answer["picks"]] + [answer.get("summary", "")]).lower()
        hit = [s for s in exp["must_not_mention"] if s.lower() in text]
        if hit:
            fails.append(f"answer mentions {hit}")
    return fails


# ---------------------------------------------------------------- reporting

def build_table(rows) -> str:
    lines = ["| id | category | result | confidence | failure reason |",
             "|----|----------|--------|------------|----------------|"]
    for r in rows:
        conf = "-" if r["confidence"] is None else f"{r['confidence']:.2f}"
        reason = "; ".join(r["fails"]).replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | {conf} | {reason} |")
    return "\n".join(lines)


def build_summary(rows) -> str:
    total = len(rows)
    passed = sum(r["passed"] for r in rows)
    cats = OrderedDict()
    for r in rows:
        c = cats.setdefault(r["category"], [0, 0])
        c[0] += r["passed"]
        c[1] += 1
    confs = [r["confidence"] for r in rows if r["confidence"] is not None]
    avg = sum(confs) / len(confs) if confs else 0.0
    llm = sum(r["source"] == "llm" for r in rows)
    tmpl = sum(r["source"] == "template" for r in rows)
    retries = sum(r["retried"] for r in rows)
    lines = [f"- **{passed}/{total} passed** ({passed / total:.0%})"]
    lines += [f"- {cat}: {p}/{n} ({p / n:.0%})" for cat, (p, n) in cats.items()]
    lines += [f"- Average confidence (answered cases, n={len(confs)}): {avg:.2f}",
              f"- Answers from the LLM: {llm}; from the template: {tmpl}; rejected (no answer): {total - llm - tmpl}",
              f"- Cases that needed a retry: {retries}"]
    return "\n".join(lines)


def redact(text: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return text.replace(key, "[REDACTED]") if key else text


def save_sample_traces(rows) -> None:
    """Live mode: full traces for a clean pass, a retry (if any), and a guardrail rejection."""
    picks = []
    clean = next((r for r in rows if r["passed"] and r["source"] == "llm" and not r["retried"]), None)
    retry = next((r for r in rows if r["retried"]), None)
    reject = next((r for r in rows if r["rejected"] and r["category"] == "guardrail"), None)
    for label, r in (("Clean pass", clean), ("Retry", retry), ("Guardrail rejection", reject)):
        if r:
            picks.append((label, r))
    out = ["# Sample traces (live run)", "",
           f"Generated {date.today().isoformat()} by `python eval/run_eval.py --live`. "
           "Full per-step traces as logged by the assistant; no API key is included.", ""]
    if retry is None:
        out += ["_No case needed a retry in this run, so there is no retry trace._", ""]
    for label, r in picks:
        record = {"request": r["trace"]["request"], "answer_source": r["source"], "confidence": r["confidence"],
                  "steps": r["trace"]["steps"], "errors": r["trace"]["errors"]}
        out += [f"## {label}: {r['id']}", "", "```json", json.dumps(record, indent=2, default=str), "```", ""]
    (EVIDENCE / "sample_traces.md").write_text(redact("\n".join(out)), encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the music assistant against eval/cases.json")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="deterministic, no LLM (default)")
    mode.add_argument("--live", action="store_true", help="use Gemini; pauses 4 s between cases")
    args = ap.parse_args()
    live = args.live
    if live and not is_llm_available():
        sys.exit("--live needs GEMINI_API_KEY in the environment or .env")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    rows = []
    for i, case in enumerate(cases):
        if live and i:
            time.sleep(PAUSE_SECONDS)
        result, trace = run_case(case, offline=not live)
        fails = check_case(case, result)
        rows.append({
            "id": case["id"], "category": case["category"], "passed": not fails, "fails": fails,
            "confidence": result["confidence"], "source": result["answer_source"],
            "rejected": bool(result.get("error")),
            "retried": any(s["step"] == "retry" for s in trace.get("steps", [])),
            "trace": trace,
        })

    table, summary = build_table(rows), build_summary(rows)
    print(table + "\n\n## Summary\n" + summary)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    name = "eval_results_live.md" if live else "eval_results_offline.md"
    command = "python " + " ".join(["eval/run_eval.py"] + sys.argv[1:])
    doc = (f"# Evaluation results ({'live, Gemini' if live else 'offline, deterministic'})\n\n"
           f"- Command: `{command}`\n- Date: {date.today().isoformat()}\n"
           f"- Cases: `eval/cases.json` ({len(cases)} cases)\n\n"
           f"## Results\n\n{table}\n\n## Summary\n\n{summary}\n")
    (EVIDENCE / name).write_text(doc, encoding="utf-8")
    print(f"\nSaved {EVIDENCE / name}")
    if live:
        save_sample_traces(rows)
        print(f"Saved {EVIDENCE / 'sample_traces.md'}")


if __name__ == "__main__":
    main()
