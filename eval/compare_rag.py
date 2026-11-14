"""Does the genre guide (the retrieval-augmented part) change the LLM's answers?

For each request: parse offline (0 LLM calls), retrieve songs, then generate the answer twice,
once with the genre guide notes in the prompt and once without. 2 LLM calls per request.

Usage:
    python eval/compare_rag.py              # live: 3 requests x 2 = 6 Gemini calls, 6 s apart
    python eval/compare_rag.py --offline    # no API calls; template answers (script test only)
    python eval/compare_rag.py --requests "jazz for a rainy cafe afternoon"
"""

import argparse
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src import assistant  # noqa: E402
from src.llm_client import is_llm_available  # noqa: E402
from src.profile_parser import parse_request, validate_request  # noqa: E402
from src.recommender import load_songs  # noqa: E402
from src.retriever import retrieve_guide_notes, retrieve_songs  # noqa: E402

DEFAULT_REQUESTS = ["sad songs for a rainy day", "romantic dinner music", "lofi for late night coding"]
PAUSE_SECONDS = 6
STOPWORDS = {
    "about", "after", "also", "because", "being", "between", "could", "every", "from", "have",
    "into", "more", "most", "much", "often", "other", "over", "some", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "through", "very", "when", "where",
    "which", "while", "with", "without", "your", "music", "songs", "song", "tracks", "track", "feel",
}


def words_in(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in STOPWORDS}


def guide_words_used(answer: dict, notes: dict) -> list:
    """Distinct content words from the retrieved guide notes that appear in the picks' 'why' text."""
    note_words = set().union(*(words_in(t) for t in notes.values())) if notes else set()
    why_words = words_in(" ".join(p["why"] for p in answer["picks"]))
    return sorted(note_words & why_words)


def avg_words(answer: dict) -> float:
    lengths = [len(p["why"].split()) for p in answer["picks"]]
    return sum(lengths) / len(lengths) if lengths else 0.0


def generate(request, profile, parse_fixes, songs, retrieved, notes, use_guide, offline):
    """One arm. Returns a record dict; api_failed is True if a Gemini call errored."""
    prompt_notes = notes if use_guide else {}
    trace = assistant.Trace(request)
    answer, checks, state = None, [], "template"
    if not offline:
        answer, checks, state = assistant._generate_verified(request, retrieved, prompt_notes, songs, trace)
    api_failed = any(e["step"] == "generate" for e in trace.errors)
    source = "llm"
    if answer is None:  # offline mode, API failure, or the answer failed verification twice
        answer = assistant.template_answer(retrieved, profile)
        checks = assistant.verify_answer(answer, retrieved, songs)
        state, source = "template", "template"
    confidence, _ = assistant.compute_confidence(profile, retrieved, "offline", state, parse_fixes)
    return {
        "use_guide": use_guide, "answer": answer, "source": source, "checks": checks,
        "retries": sum(s["step"] == "retry" for s in trace.steps), "confidence": confidence,
        "guide_words": guide_words_used(answer, notes), "avg_words": avg_words(answer),
        "api_failed": api_failed, "errors": [f"{e['type']}: {e['message']}"[:140] for e in trace.errors],
    }


def md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def arm_cell(r: dict) -> str:
    picks = "<br>".join(f"**{md(p['title'])}**: {md(p['why'])}" for p in r["answer"]["picks"])
    passed = sum(c["passed"] for c in r["checks"])
    return (f"{picks}<br><br>source: {r['source']}; checks {passed}/{len(r['checks'])}; retries {r['retries']}; "
            f"confidence {r['confidence']:.2f}; guide words used {len(r['guide_words'])}"
            + (f" ({', '.join(r['guide_words'])})" if r["guide_words"] else "")
            + f"; avg explanation {r['avg_words']:.1f} words"
            + (f"<br>API ERROR: {md('; '.join(r['errors']))}" if r["errors"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare answers with and without the genre guide")
    ap.add_argument("--offline", action="store_true", help="no API calls; template answers (script test)")
    ap.add_argument("--requests", nargs="+", default=DEFAULT_REQUESTS, help="requests to compare")
    args = ap.parse_args()
    if not args.offline and not is_llm_available():
        sys.exit("GEMINI_API_KEY is required for a live run (or use --offline)")

    songs = load_songs(assistant.SONGS_PATH)
    results, first_call = [], True
    for request in args.requests:
        ok, cleaned = validate_request(request)
        if not ok:
            sys.exit(f"request rejected by the input guardrail: {request!r} ({cleaned})")
        profile, _, fixes = parse_request(cleaned, offline=True)  # parsing never calls the LLM here
        retrieved = retrieve_songs(profile, songs, k=5)
        notes = retrieve_guide_notes(profile, retrieved)  # also used to *measure* the no-guide arm
        arms = {}
        for use_guide in (True, False):
            if not args.offline and not first_call:
                time.sleep(PAUSE_SECONDS)
            first_call = False
            arms[use_guide] = generate(cleaned, profile, fixes, songs, retrieved, notes, use_guide, args.offline)
            print(f"{request!r} guide={use_guide}: source={arms[use_guide]['source']} "
                  f"conf={arms[use_guide]['confidence']:.2f}", flush=True)
        results.append({"request": request, "notes": list(notes), "arms": arms})

    failures = sum(r["arms"][g]["api_failed"] for r in results for g in (True, False))
    n = len(results)

    def mean(g, fn):
        return sum(fn(r["arms"][g]) for r in results) / n

    def total(g, fn):
        return sum(fn(r["arms"][g]) for r in results)

    rows = [
        ("Avg confidence", mean, lambda a: a["confidence"], "{:.2f}"),
        ("Avg guide words used", mean, lambda a: len(a["guide_words"]), "{:.1f}"),
        ("Avg explanation length (words)", mean, lambda a: a["avg_words"], "{:.1f}"),
        ("Total retries", total, lambda a: a["retries"], "{:.0f}"),
        ("Answers from the LLM", total, lambda a: a["source"] == "llm", "{:.0f}"),
        ("Verification checks passed (4 per request)", total, lambda a: sum(c["passed"] for c in a["checks"]), "{:.0f}"),
    ]
    summary = ["| metric | with guide | without guide |", "|---|---|---|"]
    for name, agg, fn, f in rows:
        summary.append(f"| {name} | {f.format(agg(True, fn))} | {f.format(agg(False, fn))} |")

    per = ["| request | guide sections retrieved | with guide | without guide |", "|---|---|---|---|"]
    for r in results:
        per.append(f"| {md(r['request'])} | {', '.join(r['notes']) or 'none'} | "
                   f"{arm_cell(r['arms'][True])} | {arm_cell(r['arms'][False])} |")

    if args.offline:
        verdict = ("OFFLINE TEST ONLY: both columns are template answers, which ignore the guide, so this "
                   "shows the script works, not whether the guide helps.")
    elif failures:
        verdict = (f"INCONCLUSIVE: {failures} of {2 * n} LLM calls failed with API errors, so the two "
                   f"columns are not a fair comparison. Re-run when the quota has reset.")
    else:
        verdict = f"Conclusions: to be written from the numbers above (n={n} requests, so small differences are noise)."

    mode = "offline test (template answers)" if args.offline else "live (Gemini)"
    command = " ".join(["python", "eval/compare_rag.py"] + sys.argv[1:])
    doc = (f"# RAG comparison: answers with vs without the genre guide\n\n- Mode: {mode}\n- Command: `{command}`\n"
           f"- Date: {date.today().isoformat()}\n- Requests parsed with the offline parser (0 LLM calls); "
           f"each answer generated once with guide notes and once without.\n"
           f"- \"Guide words used\" = distinct content words (5+ letters, minus a small stopword list) from "
           f"the retrieved guide notes that appear in the picks' explanations. It is a crude measure.\n\n"
           f"## Summary\n\n" + "\n".join(summary) + "\n\n## Side by side\n\n" + "\n".join(per) +
           f"\n\n## Verdict\n\n{verdict}\n")
    name = "rag_comparison_offline.md" if args.offline else "rag_comparison.md"
    out = ROOT / "docs" / "evidence" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print("\n" + "\n".join(summary) + f"\n\n{verdict}\nSaved {out}")


if __name__ == "__main__":
    main()
