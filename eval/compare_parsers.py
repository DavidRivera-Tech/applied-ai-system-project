"""Compare three request parsers: offline rules, zero-shot Gemini, few-shot Gemini.

Usage: python eval/compare_parsers.py      (needs GEMINI_API_KEY; makes 24 LLM calls)
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.llm_client import LLMError, is_llm_available  # noqa: E402
from src.profile_parser import parse_offline, parse_with_llm, validate_profile  # noqa: E402

PAUSE_SECONDS = 4
METHODS = ["offline", "zero-shot", "few-shot"]


def load_cases():
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    return [c for c in cases if c["category"] != "guardrail" or c["id"] == "G4"]


def parse(method: str, text: str) -> dict:
    """Returns {ok, profile, fixes, seconds, error}. ok = a usable JSON profile came back."""
    started = time.perf_counter()
    try:
        if method == "offline":
            raw = parse_offline(text)
        else:
            try:
                raw = parse_with_llm(text, few_shot=(method == "few-shot"))
            except LLMError as exc:
                if not exc.transient:
                    raise
                time.sleep(PAUSE_SECONDS)  # one retry for 429/5xx; the retry's time is what we record
                started = time.perf_counter()
                raw = parse_with_llm(text, few_shot=(method == "few-shot"))
        profile, fixes = validate_profile(raw)
        return {"ok": True, "profile": profile, "fixes": fixes, "api_error": False,
                "seconds": time.perf_counter() - started, "error": None}
    except (LLMError, ValueError) as exc:
        # An LLMError is an API/network problem, not the parser's fault: tracked separately.
        return {"ok": False, "api_error": isinstance(exc, LLMError), "profile": None, "fixes": [],
                "seconds": time.perf_counter() - started, "error": f"{type(exc).__name__}: {exc}"[:120]}


def score(case: dict, r: dict) -> dict:
    """Which expectations this parse satisfies. None = case has no such expectation."""
    exp, p = case["expectations"], r["profile"] or {}
    out = {"genre": None, "mood": None, "energy": None}
    if r["api_error"]:
        return out  # no parse happened; excluded from the denominators
    if "genre_in" in exp:
        out["genre"] = r["ok"] and p.get("genre") in exp["genre_in"]
    if "mood_in" in exp:
        out["mood"] = r["ok"] and p.get("mood") in exp["mood_in"]
    if "pick_energy_between" in exp:
        lo, hi = exp["pick_energy_between"]
        out["energy"] = r["ok"] and p.get("energy") is not None and lo <= p["energy"] <= hi
    return out


def fmt(p):
    return "FAILED" if p is None else json.dumps(p, separators=(",", ":"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare offline, zero-shot and few-shot parsers")
    ap.add_argument("--limit", type=int, help="only use the first N requests (each costs 2 LLM calls)")
    args = ap.parse_args()
    if args.limit is not None and args.limit < 1:
        sys.exit("--limit must be at least 1")
    if not is_llm_available():
        sys.exit("GEMINI_API_KEY is required (environment or .env)")
    cases = load_cases()[:args.limit]
    results = {m: [] for m in METHODS}
    first_llm_call = True
    for case in cases:
        for m in METHODS:
            if m != "offline":
                if not first_llm_call:
                    time.sleep(PAUSE_SECONDS)
                first_llm_call = False
            r = parse(m, case["request"])
            r["score"] = score(case, r)
            results[m].append(r)
            print(f"{case['id']:3} {m:9} ok={r['ok']} {r['seconds']:.2f}s", flush=True)

    # ---- per-request table
    per = ["| id | request | " + " | ".join(METHODS) + " |", "|---|---|" + "---|" * len(METHODS)]
    for i, case in enumerate(cases):
        req = case["request"].replace("|", "\\|")
        cells = [f"`{fmt(results[m][i]['profile'])}`" if results[m][i]["ok"] else
                 f"FAILED ({results[m][i]['error']})" for m in METHODS]
        per.append(f"| {case['id']} | {req} | " + " | ".join(cells) + " |")

    # ---- summary table
    n = len(cases)

    def frac(m, key):
        vals = [r["score"][key] for r in results[m] if r["score"][key] is not None]
        return f"{sum(vals)}/{len(vals)}"

    rows = {
        "API errors (429/5xx, excluded below)": lambda m: f"{sum(r['api_error'] for r in results[m])}/{n}",
        "Valid JSON profile": lambda m: f"{sum(r['ok'] for r in results[m])}/{n - sum(r['api_error'] for r in results[m])}",
        "Needed fixes from validate_profile": lambda m: f"{sum(bool(r['fixes']) for r in results[m])}/{n - sum(r['api_error'] for r in results[m])}",
        "Genre matched genre_in": lambda m: frac(m, "genre"),
        "Mood matched mood_in": lambda m: frac(m, "mood"),
        "Energy in target range": lambda m: frac(m, "energy"),
        "Avg time per successful parse": lambda m: (lambda t: f"{sum(t) / len(t):.3f} s" if t else "n/a")([r["seconds"] for r in results[m] if r["ok"]]),
    }
    summ = ["| metric | " + " | ".join(METHODS) + " |", "|---|" + "---|" * len(METHODS)]
    summ += [f"| {name} | " + " | ".join(fn(m) for m in METHODS) + " |" for name, fn in rows.items()]

    fix_lines = [f"- {c['id']} / {m}: {'; '.join(results[m][i]['fixes'])}"
                 for i, c in enumerate(cases) for m in METHODS if results[m][i]["fixes"]]

    api_errs = sum(r["api_error"] for m in METHODS[1:] for r in results[m])
    if api_errs:
        conclusion = (f"INCONCLUSIVE: {api_errs} of {2 * n} LLM calls failed with API errors (rate limit or server "
                      f"errors), so the LLM columns are too sparse to compare zero-shot with few-shot. Re-run when "
                      f"the quota has reset.")
    else:
        conclusion = "CONCLUSIONS_PLACEHOLDER"
    command = " ".join(["python", "eval/compare_parsers.py"] + sys.argv[1:])
    doc = (f"# Parser comparison: offline vs zero-shot vs few-shot\n\n- Command: `{command}`\n"
           f"- Date: {date.today().isoformat()}\n- Requests: {n} (the first N of the 11 non-guardrail cases from "
           f"`eval/cases.json` plus G4, the injection)\n- Profiles are shown after `validate_profile`. "
           f"Genre/mood/energy rows only count cases that have that expectation (denominators shown).\n\n"
           f"## Summary\n\n" + "\n".join(summ) + "\n\n## Per-request profiles\n\n" + "\n".join(per) +
           "\n\n## Fixes applied by validate_profile\n\n" + ("\n".join(fix_lines) or "None.") +
           "\n\n## Conclusions\n\nCONCLUSIONS_PLACEHOLDER\n")
    out = ROOT / "docs" / "evidence" / ("parser_comparison_subset.md" if args.limit else "parser_comparison.md")
    out.write_text(doc, encoding="utf-8")
    print("\n" + "\n".join(summ) + f"\n\nSaved {out}")


if __name__ == "__main__":
    main()
