"""Plain-English wording helpers. The word 'energy' must never be produced for people."""

from src import assistant
from src.explain import confidence_sentence, friendly_why, pick_reasons, plain_fix, vibe_name

SONG = {"title": "T", "genre": "indie pop", "mood": "happy", "energy": 0.76, "mood_tags": ["uplifting"],
        "instrumentalness": 0.1}


def test_vibe_bands():
    assert vibe_name(0.2) == "calm and low-key" and vibe_name(0.34) == "calm and low-key"
    assert vibe_name(0.35) == "relaxed" and vibe_name(0.55) == "relaxed"
    assert vibe_name(0.56) == "upbeat" and vibe_name(0.8) == "upbeat"
    assert vibe_name(0.81) == "hype" and vibe_name(1.0) == "hype"


def test_pick_reasons_cover_genre_and_mood_and_vibe_only_when_hinted():
    no_hint = pick_reasons({"genre": "indie pop", "mood": "happy"}, SONG)
    assert [m for m, _ in no_hint] == ["✓", "✓"]
    assert not any("livelier" in t or "calmer" in t or "like you asked" in t and "Genre" not in t and "Mood" not in t
                   for _, t in no_hint)
    hinted = pick_reasons({"genre": "indie pop", "mood": "happy", "energy": 0.3}, SONG)
    assert len(hinted) == 3 and hinted[2][0] == "✗" and "livelier" in hinted[2][1]
    close = pick_reasons({"mood": "happy", "energy": 0.55}, SONG)
    assert close[-1] == ("~", "A bit livelier than you asked")
    match = pick_reasons({"mood": "happy", "energy": 0.8}, SONG)
    assert match[-1] == ("✓", "Upbeat, like you asked")


def test_popular_profile_reason():
    assert pick_reasons({"popularity": 100}, SONG) == [("✓", "One of the most popular songs in our catalog.")]


def test_no_wording_helper_ever_says_energy():
    profiles = [{}, {"mood": "happy"}, {"energy": 0.2}, {"energy": 0.9, "genre": "metal"}, {"popularity": 100}]
    for profile in profiles:
        text = " ".join(t for _, t in pick_reasons(profile, SONG)) + friendly_why(SONG, profile)
        assert "energy" not in text.lower()
    for note in ("typo corrected: 'chil' -> 'chill'", "conflicting cues detected", "clamped energy 1.7 -> 1.0",
                 "unknown genre 'polka' -> None"):
        assert "energy" not in plain_fix(note).lower()
    assert plain_fix("typo corrected: 'chil' -> 'chill'") == "I fixed a typo: chil → chill"
    assert plain_fix("conflicting cues detected") == "Your request had mixed signals (calm and hype)"


def test_friendly_why_examples():
    assert friendly_why(SONG, {"mood": "happy", "energy": 0.7}) == \
        "An upbeat indie pop track with a happy feel, a good fit for what you asked."
    assert friendly_why(SONG, {"genre": "rock"}) == "An indie pop track with a happy feel, a close match for what you asked."
    r_and_b = dict(SONG, genre="r&b", mood="romantic")
    assert friendly_why(r_and_b, {}) == "An R&B track with a romantic feel, a good fit for what you asked."


def test_confidence_sentence_mentions_each_factor():
    text = confidence_sentence(0.9, "offline", "template", False, ["conflicting cues detected"], capped=True)
    assert "very strong" in text and "keyword rules" in text and "template" in text
    assert "capped at 50%" in text and "mixed signals" in text
    llm = confidence_sentence(0.6, "llm", "llm", True, [], capped=False)
    assert "decent" in llm and "Gemini understood" in llm and "only after a retry" in llm
    assert "first try" in confidence_sentence(0.6, "llm", "llm", False, [], capped=False)
    assert "energy" not in text.lower() + llm.lower()
