"""RAG assistant: plain-English request -> profile -> retrieved songs + guide notes -> answer."""

import argparse
import json
from typing import Dict, List, Optional

from src.llm_client import LLMError, ask_llm, is_llm_available
from src.profile_parser import parse_request
from src.recommender import load_songs
from src.retriever import GUIDE_PATH, retrieve_guide_notes, retrieve_songs  # noqa: F401

SONGS_PATH = "data/songs.csv"
N_PICKS = 3


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
        f"Pick {N_PICKS} of the candidate songs and explain why each fits in 2-3 friendly sentences "
        "total across the answer. Use exact titles from the list. Reply with ONLY JSON in this shape:",
        '{"picks": [{"title": "...", "why": "..."}], "summary": "..."}',
    ]
    return "\n".join(lines)


def template_answer(retrieved: List) -> Dict:
    """Fallback answer built from the top retrieved songs and their reasons."""
    picks = []
    for song, _, reasons in retrieved[:N_PICKS]:
        why = reasons.replace(";", ",") if reasons else "it was one of the closest matches"
        picks.append({"title": song["title"], "why": f"{song['artist']}'s {song['genre']} track fits because: {why}."})
    titles = ", ".join(p["title"] for p in picks)
    return {"picks": picks, "summary": f"Based on your request, the best matches in the catalog are: {titles}."}


def _parse_llm_answer(raw: str, retrieved: List) -> Dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON in answer")
    data = json.loads(raw[start:end + 1])
    picks = data["picks"]
    if not isinstance(picks, list) or not picks:
        raise ValueError("no picks")
    clean = [{"title": str(p["title"]), "why": str(p["why"])} for p in picks]
    return {"picks": clean, "summary": str(data.get("summary", ""))}


def run(request: str, k: int = 5, offline: bool = False, use_guide: bool = True) -> Dict:
    profile, parse_source, fixes = parse_request(request, offline=offline)
    result: Dict = {
        "request": request, "profile": profile, "parse_source": parse_source, "parse_fixes": fixes,
        "retrieved": [], "guide_notes": {}, "answer": None, "answer_source": None,
    }
    if profile is None:  # rejected by the input guardrail
        result["error"] = fixes[0]
        return result

    songs = load_songs(SONGS_PATH)
    retrieved = retrieve_songs(profile, songs, k=k)
    notes = retrieve_guide_notes(profile, retrieved) if use_guide else {}
    result["retrieved"], result["guide_notes"] = retrieved, notes

    answer: Optional[Dict] = None
    if not offline and is_llm_available():
        try:
            answer = _parse_llm_answer(ask_llm(build_answer_prompt(request, retrieved, notes)), retrieved)
            result["answer_source"] = "llm"
        except (LLMError, ValueError, KeyError, TypeError):
            answer = None
    if answer is None:
        answer = template_answer(retrieved)
        result["answer_source"] = "template"
    result["answer"] = answer
    return result


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
    print(f"\n  {answer['summary']}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Plain-English music recommendation assistant")
    ap.add_argument("request")
    ap.add_argument("--offline", action="store_true", help="skip the LLM; use rules and a template")
    ap.add_argument("--no-guide", action="store_true", help="don't include guide notes")
    args = ap.parse_args()
    print_result(run(args.request, offline=args.offline, use_guide=not args.no_guide))


if __name__ == "__main__":
    main()
