"""Mood families, the popularity tie-break, bittersweet, and the 'only N like this' line. Offline only."""

import pytest

from src import assistant
from src.explain import pick_reasons, scarcity_note
from src.profile_parser import build_prompt, parse_request
from src.recommender import (
    MOOD_FAMILIES,
    STRATEGIES,
    get_strategy,
    mood_family,
    recommend_songs,
    score_song,
)

ALL_MODES = list(STRATEGIES)
BITTERSWEET_NOTE = "Your request mixed happy and sad, so I went with something bittersweet."


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, tmp_path):
    monkeypatch.setattr(assistant, "LOG_PATH", tmp_path / "traces.jsonl")


def bare_song(title, mood, popularity=50):
    return {"title": title, "artist": "A", "genre": "pop", "mood": mood, "popularity": popularity}


# ---------------------------------------------------------------- mood families

def test_mood_families_are_as_specified():
    assert MOOD_FAMILIES == {
        "happy": {"happy", "euphoric"},
        "intense": {"energetic", "intense", "aggressive", "confident"},
        "calm": {"chill", "relaxed", "serene", "focused"},
        "reflective": {"melancholic", "wistful", "bittersweet", "nostalgic", "moody"},
        "romantic": {"romantic"},
    }
    assert mood_family("wistful") == "reflective" and mood_family("nope") is None and mood_family(None) is None


@pytest.mark.parametrize("mode", ALL_MODES)
def test_same_family_mood_earns_half_of_that_modes_mood_weight(mode):
    weight = get_strategy(mode).weights["mood"]
    exact, _ = score_song({"mood": "melancholic"}, bare_song("a", "melancholic"), mode)
    related, reasons = score_song({"mood": "melancholic"}, bare_song("b", "wistful"), mode)
    unrelated, none_reasons = score_song({"mood": "melancholic"}, bare_song("c", "happy"), mode)
    assert exact == pytest.approx(weight)
    assert related == pytest.approx(weight / 2)
    assert unrelated == 0 and none_reasons == []
    assert reasons == [f"related mood: wistful (+{weight / 2:.2f})"]


@pytest.mark.parametrize("mode", ALL_MODES)
def test_an_exact_mood_beats_a_same_family_mood(mode):
    ranked = recommend_songs({"mood": "chill"}, [bare_song("related", "serene"), bare_song("exact", "chill")],
                             k=2, mode=mode)
    assert [song["title"] for song, _, _ in ranked] == ["exact", "related"]
    assert ranked[0][1] > ranked[1][1] > 0


def test_every_pair_in_a_family_gets_half_credit_and_other_pairs_get_none():
    half = get_strategy("balanced").weights["mood"] / 2
    for moods in MOOD_FAMILIES.values():
        for wanted in moods:
            for other in moods - {wanted}:
                assert score_song({"mood": wanted}, bare_song("x", other))[0] == pytest.approx(half)
    assert score_song({"mood": "romantic"}, bare_song("x", "happy"))[0] == 0
    assert score_song({"mood": "happy"}, bare_song("x", "romantic"))[0] == 0


# ---------------------------------------------------------------- popularity tie-break

def test_equal_scores_are_ranked_by_popularity_then_title():
    songs = [bare_song("Charlie", "happy", 50), bare_song("Alpha", "happy", 50),
             bare_song("Bravo", "happy", 90), bare_song("Delta", "happy", 10)]
    ranked = recommend_songs({"mood": "happy"}, songs, k=4)
    assert len({round(score, 6) for _, score, _ in ranked}) == 1  # a genuine tie on score
    assert [song["title"] for song, _, _ in ranked] == ["Bravo", "Alpha", "Charlie", "Delta"]


def test_popularity_tie_break_does_not_override_a_higher_score():
    songs = [bare_song("Popular but off", "romantic", 100), bare_song("Obscure but right", "happy", 1)]
    ranked = recommend_songs({"mood": "happy"}, songs, k=2)
    assert ranked[0][0]["title"] == "Obscure but right"


# ---------------------------------------------------------------- sad but happy -> bittersweet

def test_mixed_happy_and_sad_becomes_bittersweet_with_a_note():
    for text in ("sad but happy songs", "joyful but heartbroken indie", "cheerful and melancholy jazz",
                 "upbeat feelings but feeling down"):
        profile, _, fixes = parse_request(text, offline=True)
        assert profile["mood"] == "bittersweet" and BITTERSWEET_NOTE in fixes, text


def test_a_single_feeling_is_not_bittersweet():
    for text in ("happy songs", "sad songs", "joyful pop", "heartbroken songs"):
        profile, _, fixes = parse_request(text, offline=True)
        assert profile.get("mood") != "bittersweet" and not any("bittersweet" in f for f in fixes), text


def test_bittersweet_also_applies_on_the_gemini_path(monkeypatch):
    monkeypatch.setattr("src.profile_parser.is_llm_available", lambda: True)
    monkeypatch.setattr("src.profile_parser.ask_llm", lambda prompt: '{"mood": "happy"}')  # Gemini got it wrong
    profile, source, fixes = parse_request("sad but happy songs")
    assert source == "llm" and profile["mood"] == "bittersweet" and BITTERSWEET_NOTE in fixes


def test_gemini_prompt_tells_it_to_use_bittersweet_for_mixed_requests():
    assert 'use "bittersweet" as the mood' in build_prompt("sad but happy songs")


def test_sad_but_happy_gets_bittersweet_picks_and_no_penalty():
    result = assistant.run("sad but happy songs", offline=True)
    assert result["profile"]["mood"] == "bittersweet" and BITTERSWEET_NOTE in result["parse_fixes"]
    assert "conflicting cues detected" not in result["parse_fixes"]
    unadjusted = assistant.compute_confidence(result["profile"], result["retrieved"], "offline", "template", [])[0]
    assert result["confidence"] == unadjusted  # no 0.2 penalty and no cap
    songs = assistant.load_songs(assistant.SONGS_PATH)
    moods = [next(s["mood"] for s in songs if s["title"] == p["title"]) for p in result["answer"]["picks"]]
    assert moods == ["bittersweet"] * 3


# ---------------------------------------------------------------- 'only N like this' and related-mood reasons

def cat(*pairs):
    return [{"genre": g, "mood": m} for g, m in pairs]


def test_scarcity_note_singular_plural_and_zero():
    one = cat(("rock", "romantic"), ("rock", "intense"))
    assert scarcity_note({"genre": "rock", "mood": "romantic"}, one) == \
        "We only have 1 romantic rock song in our catalog, so the other picks are the closest matches."
    two = cat(("rock", "romantic"), ("rock", "romantic"))
    assert scarcity_note({"genre": "rock", "mood": "romantic"}, two) == \
        "We only have 2 romantic rock songs in our catalog, so the other picks are the closest matches."
    assert scarcity_note({"genre": "metal", "mood": "happy"}, one) == \
        "We don’t have any happy metal songs in our catalog, so these are the closest matches."


def test_scarcity_note_is_silent_with_three_or_more_or_for_a_single_attribute():
    three = cat(("rock", "romantic")) * 3
    assert scarcity_note({"genre": "rock", "mood": "romantic"}, three) is None
    assert scarcity_note({"genre": "rock"}, []) is None
    assert scarcity_note({"mood": "romantic"}, []) is None
    assert scarcity_note({"popularity": 100}, []) is None


def test_related_mood_reason_reads_close_to_requested_mood():
    song = {"genre": "folk", "mood": "wistful", "energy": 0.4, "mood_tags": [], "instrumentalness": 0.1}
    assert pick_reasons({"mood": "melancholic"}, song) == [("~", "Wistful, close to sad")]
    assert pick_reasons({"mood": "romantic"}, song) == [("✗", "Mood: wistful, not romantic")]
