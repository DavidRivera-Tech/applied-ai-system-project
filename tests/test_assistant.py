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
    assert all(c["passed"] for c in result["verification"]) and len(result["verification"]) == 3
    assert 0 < result["confidence"] <= 1


def test_made_up_song_is_caught_retried_then_falls_back(monkeypatch):
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return json.dumps({"picks": [{"title": "Totally Made Up Song", "why": "x"}], "summary": "s"})

    monkeypatch.setattr(assistant, "ask_llm", fake)
    result = assistant.run(REQUEST)
    assert len(calls) == 2
    assert "rejected" in calls[1] and "Totally Made Up Song" in calls[1]  # retry tells the LLM what was wrong
    assert result["answer_source"] == "template"
    assert all(p["title"] in [s["title"] for s, _, _ in result["retrieved"]] for p in result["answer"]["picks"])
    steps = [s["step"] for s in json.loads(assistant.LOG_PATH.read_text().splitlines()[-1])["steps"]]
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
    failed = {c["check"] for c in checks if not c["passed"]}
    assert failed == {"no_duplicate_picks", "summary_names_only_retrieved"}


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


def test_trace_line_written_without_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-123")
    monkeypatch.setattr(assistant, "ask_llm", lambda p: good_reply(p))
    assistant.run(REQUEST)
    text = assistant.LOG_PATH.read_text()
    record = json.loads(text.splitlines()[-1])
    assert {"timestamp", "request", "steps", "errors", "answer_source", "confidence"} <= record.keys()
    assert "SECRET-KEY-123" not in text


def test_template_possessive():
    song = {"title": "T", "artist": "Paper Lanterns", "genre": "lofi"}
    other = {"title": "U", "artist": "LoRoom", "genre": "lofi"}
    picks = assistant.template_answer([(song, 1.0, "r"), (other, 1.0, "r")])["picks"]
    assert "Paper Lanterns' lofi" in picks[0]["why"] and "LoRoom's lofi" in picks[1]["why"]
