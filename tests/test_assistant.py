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


def test_template_text_is_friendly_with_no_numbers_or_scoring_terms():
    for request in (REQUEST, "high energy workout music", "something good", "play me something",
                    "romantic dinner music", "sad songs for a rainy day"):
        result = assistant.run(request, offline=True)
        text = " ".join(p["why"] for p in result["answer"]["picks"]) + " " + result["answer"]["summary"]
        assert not re.search(r"\d", text), text
        for banned in ("energy", "score", "target", "points", "(+", "tempo", "acousticness", "valence"):
            assert banned not in text.lower(), (request, banned, text)
        assert all(c["passed"] for c in result["verification"])


def test_template_uses_vibe_words_only_when_the_user_hinted_a_vibe():
    hinted = assistant.run("chill lofi", offline=True)["answer"]["picks"][0]["why"]
    plain = assistant.run("romantic dinner music", offline=True)["answer"]["picks"][0]["why"]
    assert any(word in hinted for word in ("calm", "easygoing", "upbeat", "hype"))
    assert not any(word in plain for word in ("calm", "easygoing", "upbeat", "hype"))


# ---- confidence adjustments for vague and conflicting requests

def test_conflict_penalty_lowers_confidence_by_point_two():
    result = assistant.run("calm but super high energy metal", offline=True)
    assert "conflicting cues detected" in result["parse_fixes"]
    plain = assistant.compute_confidence(result["profile"], result["retrieved"], "offline", "template")[0]
    assert result["confidence"] == round(plain - 0.2, 2)


def test_vague_request_confidence_is_capped():
    result = assistant.run("something good", offline=True)
    assert result["profile"] == {"mood": "happy", "energy": 0.45}
    assert "Your request was general, so I went with something positive and easygoing." in result["parse_fixes"]
    assert result["answer"] is not None and result["confidence"] <= 0.5


def test_every_kind_of_vague_request_is_capped_at_half():
    for text in ("something good", "something bad", "play me something", "anything", "rough day", "fun"):
        result = assistant.run(text, offline=True)
        assert result["confidence"] <= 0.5, text


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


def test_result_includes_trace_steps_matching_the_log(tmp_path):
    result = assistant.run(REQUEST, offline=True)
    names = [s["step"] for s in result["trace_steps"]]
    assert names[:3] == ["validate", "parse", "retrieve"] and names[-1] == "fallback"
    assert all("ms" in s and "ok" in s for s in result["trace_steps"])
    logged = json.loads((tmp_path / "logs" / "traces.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert logged["steps"] == result["trace_steps"]  # log file content unchanged


def test_rejected_request_still_has_trace_steps():
    result = assistant.run("", offline=True)
    assert result["error"] and [s["step"] for s in result["trace_steps"]] == ["validate", "parse"]


# ---- recommendations without invented energy

def catalog():
    return assistant.load_songs(assistant.SONGS_PATH)


def test_happy_songs_have_no_energy_and_all_three_picks_are_happy():
    result = assistant.run("happy songs", offline=True)
    assert "energy" not in result["profile"] and result["profile"]["mood"] == "happy"
    moods = [next(s["mood"] for s in catalog() if s["title"] == p["title"]) for p in result["answer"]["picks"]]
    assert len(moods) == 3 and moods == ["happy"] * 3


def test_something_good_is_happy_and_relaxed():
    result = assistant.run("something good", offline=True)
    assert result["profile"]["mood"] == "happy" and 0.35 <= result["profile"]["energy"] <= 0.55


def test_something_bad_is_melancholic_and_calm():
    result = assistant.run("something bad", offline=True)
    assert result["profile"]["mood"] == "melancholic" and result["profile"]["energy"] < 0.35


def test_play_me_something_returns_the_most_popular_songs():
    result = assistant.run("play me something", offline=True)
    assert result["profile"] == {"popularity": 100}
    assert "Here are some of the popular songs in our catalog." in result["parse_fixes"]
    top3 = [s["title"] for s in sorted(catalog(), key=lambda s: -s["popularity"])[:3]]
    assert [p["title"] for p in result["answer"]["picks"]] == top3
    assert result["confidence"] <= 0.5


def test_popularity_counts_toward_the_best_possible_score_and_zero_is_guarded():
    assert assistant.max_possible_score({"popularity": 100}) == 0.5
    assert assistant.match_percent({"popularity": 100}, 0.44) == 88
    assert assistant.match_percent({}, 1.0) == 0  # nothing to score: no division by zero
    assert assistant.match_percent({"mood": "happy"}, 5.0) == 100  # clamped
    score, _ = assistant.compute_confidence({}, [], "offline", "template")
    assert 0 <= score <= 1
