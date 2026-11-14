"""RAG assistant: plain-English request -> profile -> retrieved songs + guide notes -> verified answer."""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.llm_client import LLMError, ask_llm, is_llm_available
from src.explain import friendly_why
from src.profile_parser import CONFLICT_NOTE, VAGUE_NOTES, parse_request, validate_request
from src.recommender import get_strategy, load_songs
from src.retriever import retrieve_guide_notes, retrieve_songs

SONGS_PATH = "data/songs.csv"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "traces.jsonl"
N_PICKS = 3


# ---------------------------------------------------------------- trace

class Trace:
    """Collects timed steps for one run and appends them as one JSON line."""

    def __init__(self, request: str):
        self.request = request
        self.steps: List[Dict] = []
        self.errors: List[Dict] = []

    def add(self, step: str, ok: bool, started: float, **detail) -> None:
        self.steps.append({"step": step, "ok": ok, "ms": round((time.perf_counter() - started) * 1000, 1), **detail})

    def error(self, step: str, exc: Exception) -> None:
        # Type and message only. LLMError messages never contain the API key.
        self.errors.append({"step": step, "type": type(exc).__name__, "message": str(exc)})

    def write(self, result: Dict) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": self.request,
            "steps": self.steps,
            "errors": self.errors,
            "answer_source": result.get("answer_source"),
            "confidence": result.get("confidence"),
        }
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError:
            pass  # logging must never break the assistant


# ---------------------------------------------------------------- prompt / template

def build_answer_prompt(request: str, retrieved: List, notes: Dict[str, str]) -> str:
    lines = [
        "You are a friendly music assistant. Recommend songs ONLY from the candidate list below.",
        f'The listener asked: "{request}"',
        "",
        "Candidate songs:",
    ]
    for i, (song, score, reasons) in enumerate(retrieved, 1):
        lines.append(f"{i}. \"{song['title']}\" by {song['artist']} | genre: {song['genre']} | "
                     f"score: {score:.2f} | reasons: {reasons}")
    if notes:
        lines += ["", "Background notes:"]
        lines += [f"- {name}: {text}" for name, text in notes.items()]
    lines += [
        "",
        f"Pick {N_PICKS} different candidate songs and explain why each fits in 2-3 friendly sentences "
        "total across the answer. Use exact titles from the list, and do not mention any other song. "
        "Reply with ONLY JSON in this shape:",
        '{"picks": [{"title": "...", "why": "..."}], "summary": "..."}',
    ]
    return "\n".join(lines)


def template_answer(retrieved: List, profile: Optional[Dict] = None) -> Dict:
    """Fallback answer built from the top retrieved songs: friendly sentences, no scoring jargon."""
    picks = [{"title": song["title"], "why": friendly_why(song, profile)} for song, _, _ in retrieved[:N_PICKS]]
    titles = ", ".join(p["title"] for p in picks)
    return {"picks": picks, "summary": f"Based on your request, the best matches in the catalog are: {titles}."}


def _parse_llm_answer(raw: str) -> Dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("response contained no JSON object")
    try:
        data = json.loads(raw[start:end + 1])
        picks = data["picks"]
        if not isinstance(picks, list) or not picks:
            raise ValueError("'picks' must be a non-empty list")
        clean = [{"title": str(p["title"]), "why": str(p["why"])} for p in picks]
        return {"picks": clean, "summary": str(data.get("summary", ""))}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"invalid answer JSON ({type(exc).__name__}: {exc})") from None


# ---------------------------------------------------------------- verification

def _fields(answer: Dict) -> Dict[str, str]:
    """Every free-text field of an answer, keyed by where it came from."""
    fields = {f"picks[{i}].why": p["why"] for i, p in enumerate(answer["picks"])}
    fields["summary"] = answer.get("summary", "")
    return fields


def verify_answer(answer: Dict, retrieved: List, all_songs: List[Dict]) -> List[Dict]:
    """Four checks on an answer. Returns [{check, passed, detail}]."""
    retrieved_titles = [s["title"] for s, _, _ in retrieved]
    picked = [p["title"] for p in answer["picks"]]

    unknown = [t for t in picked if t not in retrieved_titles]
    dupes = sorted({t for t in picked if picked.count(t) > 1})

    outsiders = [s["title"] for s in all_songs if s["title"] not in retrieved_titles]
    leaks = []  # (field, title)
    for field, text in _fields(answer).items():
        for title in outsiders:
            if re.search(rf"(?<!\w){re.escape(title)}(?!\w)", text, flags=re.IGNORECASE):
                leaks.append((field, title))

    expected = min(N_PICKS, len(retrieved))
    return [
        {"check": "titles_match_retrieved", "passed": not unknown,
         "detail": f"not retrieved: {unknown}" if unknown else "all picks were retrieved"},
        {"check": "no_duplicate_picks", "passed": not dupes,
         "detail": f"duplicates: {dupes}" if dupes else "no duplicates"},
        {"check": "text_names_only_retrieved", "passed": not leaks,
         "detail": ("un-retrieved songs named: " + ", ".join(f"{t!r} in {f}" for f, t in leaks))
         if leaks else "picks' explanations and summary are clean"},
        {"check": "correct_pick_count", "passed": len(picked) == expected,
         "detail": f"expected {expected} picks, got {len(picked)}"},
    ]


def _problems(checks: List[Dict]) -> List[str]:
    return [f"{c['check']}: {c['detail']}" for c in checks if not c["passed"]]


# ---------------------------------------------------------------- confidence

def max_possible_score(profile: Dict, mode: str = "balanced") -> float:
    """Best score a song could earn for the preferences actually present in the profile."""
    w = get_strategy(mode).weights
    total = 0.0
    for key, weight_key in (("genre", "genre"), ("mood", "mood"), ("energy", "energy"),
                            ("likes_acoustic", "acoustic"), ("tempo_bpm", "tempo"),
                            ("instrumental", "instrumental"), ("popularity", "popularity")):
        if profile.get(key) is not None:
            total += w[weight_key]
    total += w["mood_tag"] * min(3, len(profile.get("mood_tags") or []))
    return total


VAGUE_CONFIDENCE_CAP = 0.5
CONFLICT_PENALTY = 0.2


def match_percent(profile: Dict, score: float) -> int:
    """A song's score as a 0-100 percentage of the best possible score for this profile (0 if nothing to score)."""
    best = max_possible_score(profile)
    if best <= 0:
        return 0
    return max(0, min(100, round(100 * score / best)))


def compute_confidence(profile: Dict, retrieved: List, parse_source: str, verify_state: str,
                       fixes: Optional[List[str]] = None) -> Tuple[float, str]:
    """0-1 confidence from retrieval strength (50%), parse source (20%), verification (30%).

    Parse notes adjust it: a vague request caps it at 0.5, conflicting cues subtract 0.2.
    """
    top = retrieved[0][1] if retrieved else 0.0
    best = max_possible_score(profile)
    strength = min(1.0, top / best) if best else 0.0
    parse = 1.0 if parse_source == "llm" else 0.5
    verify = {"first_try": 1.0, "after_retry": 0.5, "template": 0.5}[verify_state]
    score = round(0.5 * strength + 0.2 * parse + 0.3 * verify, 2)
    verify_text = {"first_try": "passed on the first try", "after_retry": "passed only after a retry",
                   "template": "answer built from a template (not LLM-checked)"}[verify_state]
    explanation = (f"top score {top:.2f} of a possible {best:.2f}; request parsed by {parse_source}; "
                   f"verification {verify_text}.")
    fixes = fixes or []
    if CONFLICT_NOTE in fixes:
        score = round(max(0.0, score - CONFLICT_PENALTY), 2)
        explanation += f" Lowered by {CONFLICT_PENALTY} because the request had conflicting cues."
    if any(note in fixes for note in VAGUE_NOTES) and score > VAGUE_CONFIDENCE_CAP:
        score = VAGUE_CONFIDENCE_CAP
        explanation += f" Capped at {VAGUE_CONFIDENCE_CAP} because the request was vague."
    return score, explanation


# ---------------------------------------------------------------- generation with retries

def _call_llm(prompt: str, trace: Trace) -> str:
    """One LLM call, retried once if the error is transient (timeout, 429, 5xx)."""
    for attempt in (1, 2):
        started = time.perf_counter()
        try:
            raw = ask_llm(prompt)
            trace.add("generate", True, started, api_try=attempt)
            return raw
        except LLMError as exc:
            trace.add("generate", False, started, api_try=attempt, error=type(exc).__name__)
            trace.error("generate", exc)
            if attempt == 1 and exc.transient:
                trace.add("retry", True, time.perf_counter(), reason="transient API error")
                continue
            raise
    raise AssertionError("unreachable")


def _generate_verified(request, retrieved, notes, all_songs, trace) -> Tuple[Optional[Dict], List[Dict], str]:
    """Ask the LLM, verify, retry once with feedback. Returns (answer|None, checks, verify_state)."""
    base = build_answer_prompt(request, retrieved, notes)
    prompt, checks = base, []
    for attempt in (1, 2):
        try:
            raw = _call_llm(prompt, trace)
        except LLMError:
            return None, checks, "failed"

        started = time.perf_counter()
        try:
            answer = _parse_llm_answer(raw)
            checks = verify_answer(answer, retrieved, all_songs)
            problems = _problems(checks)
        except ValueError as exc:
            answer, checks, problems = None, [], [f"bad JSON: {exc}"]
            trace.error("verify", exc)
        trace.add("verify", not problems, started, attempt=attempt,
                  checks={c["check"]: c["passed"] for c in checks}, problems=problems)

        if not problems:
            return answer, checks, "first_try" if attempt == 1 else "after_retry"
        if attempt == 1:
            trace.add("retry", True, time.perf_counter(), reason="; ".join(problems))
            prompt = (base + "\n\nYour previous reply was rejected for these problems:\n- "
                      + "\n- ".join(problems)
                      + "\nFix them. Use only exact titles from the candidate list, no duplicates, "
                        "and reply with ONLY the JSON.")
    return None, checks, "failed"


# ---------------------------------------------------------------- main entry point

def run(request: str, k: int = 5, offline: bool = False, use_guide: bool = True) -> Dict:
    trace = Trace(request)
    result: Dict = {
        "request": request, "profile": None, "parse_source": None, "parse_fixes": [],
        "retrieved": [], "guide_notes": {}, "answer": None, "answer_source": None,
        "verification": [], "confidence": None, "confidence_explanation": "",
        "trace_steps": trace.steps,  # same list the log line is built from; filled in as the run proceeds
    }

    started = time.perf_counter()
    ok, cleaned = validate_request(request)
    trace.add("validate", ok, started, **({} if ok else {"error": cleaned}))

    started = time.perf_counter()
    profile, parse_source, fixes = parse_request(request, offline=offline)
    trace.add("parse", profile is not None, started, source=parse_source, fixes=fixes, profile=profile)
    result.update(profile=profile, parse_source=parse_source, parse_fixes=fixes)
    if profile is None:  # rejected by the input guardrail
        result["error"] = fixes[0]
        trace.write(result)
        return result

    started = time.perf_counter()
    songs = load_songs(SONGS_PATH)
    retrieved = retrieve_songs(profile, songs, k=k)
    notes = retrieve_guide_notes(profile, retrieved) if use_guide else {}
    trace.add("retrieve", True, started, titles=[s["title"] for s, _, _ in retrieved], guide_notes=list(notes))
    result["retrieved"], result["guide_notes"] = retrieved, notes

    answer, checks, verify_state = None, [], "template"
    if not offline and is_llm_available():
        answer, checks, verify_state = _generate_verified(cleaned, retrieved, notes, songs, trace)
        if answer is not None:
            result["answer_source"] = "llm"
    if answer is None:
        started = time.perf_counter()
        answer = template_answer(retrieved, profile)
        checks = verify_answer(answer, retrieved, songs)
        verify_state = "template"
        result["answer_source"] = "template"
        trace.add("fallback", True, started, reason="offline mode" if offline else "LLM unavailable or answer failed verification")

    result["answer"], result["verification"] = answer, checks
    result["confidence"], result["confidence_explanation"] = compute_confidence(
        profile, retrieved, parse_source, verify_state, result["parse_fixes"])
    trace.write(result)
    return result


# ---------------------------------------------------------------- CLI

def print_result(result: Dict) -> None:
    print(f"Request: {result['request']}")
    if result.get("error"):
        print(f"Rejected: {result['error']}")
        return
    print(f"\nProfile ({result['parse_source']}): {result['profile']}")
    if result["parse_fixes"]:
        print(f"  fixes: {result['parse_fixes']}")
    print("\nRetrieved songs:")
    for i, (song, score, reasons) in enumerate(result["retrieved"], 1):
        print(f"  {i}. {song['title']} - {song['artist']} [{song['genre']}] score {score:.2f}")
        print(f"       {reasons}")
    print(f"\nGuide notes used: {', '.join(result['guide_notes']) or 'none'}")
    answer = result["answer"]
    print(f"\nAnswer ({result['answer_source']}):")
    for pick in answer["picks"]:
        print(f"  * {pick['title']}: {pick['why']}")
    print(f"\n  {answer['summary']}")
    print("\nVerification:")
    for c in result["verification"]:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}: {c['detail']}")
    print(f"\nConfidence: {result['confidence']:.2f} ({result['confidence_explanation']})\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Plain-English music recommendation assistant")
    ap.add_argument("request")
    ap.add_argument("--offline", action="store_true", help="skip the LLM; use rules and a template")
    ap.add_argument("--no-guide", action="store_true", help="don't include guide notes")
    args = ap.parse_args()
    print_result(run(args.request, offline=args.offline, use_guide=not args.no_guide))


if __name__ == "__main__":
    main()
