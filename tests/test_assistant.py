"""Assistant reliability tests. The LLM is always faked; no real API calls are made."""

import json
import re

import pytest

from src import assistant
from src.llm_client import LLMError

REQUEST = "something chill to study to, no vocals"


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    monkeypatch.setattr(assistant, "is_llm_available", lambda: True)
    monkeypatch.setattr("src.profile_parser.is_llm_available", lambda: False)  # parse offline
    monkeypatch.setattr(assistant, "LOG_PATH", tmp_path / "logs" / "traces.jsonl")


def retrieved_titles(prompt):
    return re.findall(r'^\d+\. "([^"]+)" by', prompt, flags=re.MULTILINE)


def good_reply(prompt, summary="Three calm picks for studying."):
    titles = retrieved_titles(prompt)[:3]
    return json.dumps({"picks": [{"title": t, "why": "fits the mood"} for t in titles], "summary": summary})


def test_clean_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant, "ask_llm", lambda p: calls.append(p) or good_reply(p))
    result = assistant.run(REQUEST)
    assert result["answer_source"] == "llm" and len(calls) == 1
    assert all(c["passed"] for c in result["verification"]) and len(result["verification"]) == 4
    assert 0 < result["confidence"] <= 1


def test_made_up_song_is_caught_retried_then_falls_back(monkeypatch):
    calls = []

    def fake(prompt):
        calls.append(prompt)
        # Right count, no duplicates, clean text: only one title is made up.
        titles = retrieved_titles(prompt)[:2] + ["Totally Made Up Song"]
        return json.dumps({"picks": [{"title": t, "why": "fits"} for t in titles], "summary": "s"})

    monkeypatch.setattr(assistant, "ask_llm", fake)
    result = assistant.run(REQUEST)
    assert len(calls) == 2
    assert "rejected" in calls[1] and "Totally Made Up Song" in calls[1]  # retry tells the LLM what was wrong
    assert result["answer_source"] == "template"
    assert all(p["title"] in [s["title"] for s, _, _ in result["retrieved"]] for p in result["answer"]["picks"])
    trace = json.loads(assistant.LOG_PATH.read_text().splitlines()[-1])
    first_verify = next(s for s in trace["steps"] if s["step"] == "verify")
    failed = [name for name, ok in first_verify["checks"].items() if not ok]
    assert failed == ["titles_match_retrieved"]  # it failed for the right reason, and only that one
    steps = [s["step"] for s in trace["steps"]]
    assert "retry" in steps and "fallback" in steps


def test_bad_json_retries_then_falls_back(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant, "ask_llm", lambda p: calls.append(p) or "sorry, no json here")
    result = assistant.run(REQUEST)
    assert len(calls) == 2 and result["answer_source"] == "template"


def test_bad_json_then_good_reply_succeeds_after_retry(monkeypatch):
    replies = iter(["{not json"])
    monkeypatch.setattr(assistant, "ask_llm", lambda p: next(replies, None) or good_reply(p))
    result = assistant.run(REQUEST)
    assert result["answer_source"] == "llm"
    full = assistant.compute_confidence(result["profile"], result["retrieved"], "offline", "first_try")[0]
    assert result["confidence"] < full  # retry lowers confidence


def test_duplicate_picks_and_leaked_summary_are_caught(monkeypatch):
    songs = assistant.load_songs(assistant.SONGS_PATH)
    result = assistant.run(REQUEST, offline=True)
    retrieved = result["retrieved"]
    outsider = next(s["title"] for s in songs if s["title"] not in [r[0]["title"] for r in retrieved])
    t = retrieved[0][0]["title"]
    checks = assistant.verify_answer(
        {"picks": [{"title": t, "why": ""}, {"title": t, "why": ""}], "summary": f"Also try {outsider.lower()}!"},
        retrieved, songs)
    failed = {c["check"]: c["detail"] for c in checks if not c["passed"]}
    # Two identical picks also means the pick count is wrong (2, not 3).
    assert set(failed) == {"no_duplicate_picks", "text_names_only_retrieved", "correct_pick_count"}
    assert "'" in failed["text_names_only_retrieved"] and "in summary" in failed["text_names_only_retrieved"]


def test_transient_error_retried_once(monkeypatch):
    calls = []

    def fake(prompt):
        calls.append(1)
        if len(calls) == 1:
            raise LLMError("Gemini API call failed (ServerError, code=504)", code=504, transient=True)
        return good_reply(prompt)

    monkeypatch.setattr(assistant, "ask_llm", fake)
    result = assistant.run(REQUEST)
    assert len(calls) == 2 and result["answer_source"] == "llm"


def test_non_transient_error_falls_back_without_retry(monkeypatch):
    calls = []

    def fake(prompt):
        calls.append(1)
        raise LLMError("bad key", code=401, transient=False)

    monkeypatch.setattr(assistant, "ask_llm", fake)
    result = assistant.run(REQUEST)
    assert len(calls) == 1 and result["answer_source"] == "template"


def test_trace_line_has_expected_fields(monkeypatch):
    monkeypatch.setattr(assistant, "ask_llm", lambda p: good_reply(p))
    assistant.run(REQUEST)
    record = json.loads(assistant.LOG_PATH.read_text().splitlines()[-1])
    assert {"timestamp", "request", "steps", "errors", "answer_source", "confidence"} <= record.keys()


def _outsider_and_retrieved():
    songs = assistant.load_songs(assistant.SONGS_PATH)
    retrieved = assistant.run(REQUEST, offline=True)["retrieved"]
    outsider = next(s["title"] for s in songs if s["title"] not in [r[0]["title"] for r in retrieved])
    return songs, retrieved, outsider


def test_why_text_naming_unretrieved_song_fails():
    songs, retrieved, outsider = _outsider_and_retrieved()
    picks = [{"title": r[0]["title"], "why": "fits"} for r in retrieved[:3]]
    picks[1]["why"] = f"Much like {outsider}, it is calm."
    checks = {c["check"]: c for c in assistant.verify_answer({"picks": picks, "summary": "clean"}, retrieved, songs)}
    assert not checks["text_names_only_retrieved"]["passed"]
    assert "picks[1].why" in checks["text_names_only_retrieved"]["detail"]  # reports which field leaked
    assert checks["titles_match_retrieved"]["passed"] and checks["correct_pick_count"]["passed"]


def test_single_pick_fails_correct_pick_count():
    songs, retrieved, _ = _outsider_and_retrieved()
    answer = {"picks": [{"title": retrieved[0][0]["title"], "why": "fits"}], "summary": "ok"}
    checks = {c["check"]: c for c in assistant.verify_answer(answer, retrieved, songs)}
    assert not checks["correct_pick_count"]["passed"]
    assert "expected 3 picks, got 1" in checks["correct_pick_count"]["detail"]
    assert all(c["passed"] for name, c in checks.items() if name != "correct_pick_count")


def test_expected_pick_count_shrinks_when_few_songs_retrieved():
    songs = assistant.load_songs(assistant.SONGS_PATH)
    retrieved = assistant.run(REQUEST, k=2, offline=True)["retrieved"]
    answer = {"picks": [{"title": r[0]["title"], "why": "fits"} for r in retrieved], "summary": "ok"}
    checks = assistant.verify_answer(answer, retrieved, songs)
    assert next(c for c in checks if c["check"] == "correct_pick_count")["passed"]


def test_cleaned_request_is_used_in_prompt(monkeypatch):
    seen = []
    monkeypatch.setattr(assistant, "ask_llm", lambda p: seen.append(p) or good_reply(p))
    assistant.run("  something   chill\n to study to,   no vocals  ")
    assert 'The listener asked: "something chill to study to, no vocals"' in seen[0]


def test_template_possessive():
    song = {"title": "T", "artist": "Paper Lanterns", "genre": "lofi"}
    other = {"title": "U", "artist": "LoRoom", "genre": "lofi"}
    picks = assistant.template_answer([(song, 1.0, "r"), (other, 1.0, "r")])["picks"]
    assert "Paper Lanterns' lofi" in picks[0]["why"] and "LoRoom's lofi" in picks[1]["why"]


# ---- confidence adjustments for vague and conflicting requests

def test_conflict_penalty_lowers_confidence_by_point_two():
    result = assistant.run("calm but super high energy metal", offline=True)
    assert "conflicting cues detected" in result["parse_fixes"]
    plain = assistant.compute_confidence(result["profile"], result["retrieved"], "offline", "template")[0]
    assert result["confidence"] == round(plain - 0.2, 2)


def test_vague_request_confidence_is_capped():
    result = assistant.run("something good", offline=True)
    assert result["profile"] == {"energy": 0.6}
    assert "vague request: using a broad default" in result["parse_fixes"]
    assert result["answer"] is not None and result["confidence"] <= 0.5


def test_clean_request_confidence_is_not_adjusted():
    result = assistant.run(REQUEST, offline=True)
    assert result["confidence"] == assistant.compute_confidence(
        result["profile"], result["retrieved"], "offline", "template")[0]


def test_conflict_penalty_applies_on_the_llm_path_too(monkeypatch):
    text = "calm but super high energy metal"
    llm_profile = json.dumps({"genre": "metal", "mood": "aggressive", "energy": 0.9})

    def fake_llm(prompt):
        return llm_profile if "Convert the music request" in prompt else good_reply(prompt)

    monkeypatch.setattr("src.profile_parser.is_llm_available", lambda: True)
    monkeypatch.setattr("src.profile_parser.ask_llm", fake_llm)
    monkeypatch.setattr(assistant, "ask_llm", fake_llm)

    result = assistant.run(text)
    assert result["parse_source"] == "llm" and result["answer_source"] == "llm"
    assert "conflicting cues detected" in result["parse_fixes"]
    plain = assistant.compute_confidence(result["profile"], result["retrieved"], "llm", "first_try")[0]
    assert result["confidence"] == round(plain - 0.2, 2)

    clean = assistant.run("high energy workout music")
    assert "conflicting cues detected" not in clean["parse_fixes"]
