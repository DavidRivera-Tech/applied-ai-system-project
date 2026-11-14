"""Friendly mood labels and the valence mood hint. Offline only."""

from pathlib import Path
from statistics import mean

import pytest
from streamlit.testing.v1 import AppTest

from src import assistant
from src.explain import MOOD_LABELS, friendly_mood, pick_reasons, scarcity_note
from src.retriever import add_mood_valence, mood_valence_target

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, tmp_path):
    monkeypatch.setattr(assistant, "LOG_PATH", tmp_path / "traces.jsonl")


def songs():
    return assistant.load_songs(assistant.SONGS_PATH)


def submit(text):
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.text_input(key="request").set_value(text).run()
    assert not at.exception
    return at


def split_page(at):
    """(everything a person sees outside Technical details, the Technical details text)."""
    outer, nested = at.expander[0], at.expander[1]
    values, technical = [m.value for m in outer.markdown], [m.value for m in nested.markdown]
    nested_ids = {id(m) for m in nested.markdown}
    outside = [m.value for m in at.markdown if id(m) not in nested_ids] + [c.value for c in at.caption]
    return "\n".join(outside), "\n".join(technical)


# ---------------------------------------------------------------- friendly labels

def test_friendly_mood_mapping_lives_in_one_place_and_only_renames_melancholic():
    assert MOOD_LABELS == {"melancholic": "sad"}
    assert friendly_mood("melancholic") == "sad"
    for mood in ("happy", "wistful", "romantic", "chill", "bittersweet"):
        assert friendly_mood(mood) == mood
    assert friendly_mood(None) is None


def test_sad_rock_shows_sad_not_melancholic_on_the_page():
    at = submit("sad rock")
    outside, technical = split_page(at)
    assert "We don’t have any sad rock songs in our catalog, so these are the closest matches." in outside
    assert "Mood: sad · Genre: rock" in outside
    assert "melancholic" not in outside.lower()
    assert "melancholic" in technical  # internal labels stay in Technical details


def test_internal_label_is_unchanged_in_the_profile_and_scoring():
    result = assistant.run("sad rock", offline=True)
    assert result["profile"]["mood"] == "melancholic"
    assert scarcity_note({"genre": "rock", "mood": "melancholic"}, songs()).startswith("We don’t have any sad rock")


def test_reasons_use_the_friendly_word_for_both_the_song_and_the_request():
    sad_song = {"genre": "blues", "mood": "melancholic", "valence": 0.25, "energy": 0.3, "instrumentalness": 0.1}
    reasons = [t for _, t in pick_reasons({"mood": "melancholic"}, sad_song)]
    assert reasons == ["Mood: sad, like you asked"]
    wistful = dict(sad_song, mood="wistful")
    assert pick_reasons({"mood": "melancholic"}, wistful) == [("~", "Wistful, close to sad")]
    happy = dict(sad_song, mood="happy")
    assert pick_reasons({"mood": "melancholic"}, happy) == [("✗", "Mood: happy, not sad")]


# ---------------------------------------------------------------- valence hint

def test_target_valence_is_the_catalog_average_for_that_mood():
    expected = mean(s["valence"] for s in songs() if s["mood"] == "melancholic")
    hint = mood_valence_target("melancholic", songs())
    assert hint["valence"] == pytest.approx(expected, abs=0.001)
    assert hint["songs"] == sum(s["mood"] == "melancholic" for s in songs())
    assert mood_valence_target("not-a-mood", songs()) is None


def test_valence_added_only_for_an_asked_mood_and_never_overrides():
    profile, hint = add_mood_valence({"mood": "happy"}, songs())
    assert profile["valence"] == hint["valence"] and profile["mood"] == "happy"
    own, hint = add_mood_valence({"mood": "happy", "valence": 0.9}, songs())
    assert own["valence"] == 0.9 and hint is None
    assert add_mood_valence({"genre": "jazz"}, songs()) == ({"genre": "jazz"}, None)
    assert add_mood_valence({"popularity": 100}, songs()) == ({"popularity": 100}, None)


def test_requests_without_a_mood_get_no_valence():
    for request in ("jazz", "some pop", "instrumental music", "play me something", "anything"):
        result = assistant.run(request, offline=True)
        assert "valence" not in result["profile"] and result["mood_hint"] is None, request


def test_a_default_mood_chosen_for_a_vague_request_gets_no_valence():
    for request in ("something good", "something bad"):
        result = assistant.run(request, offline=True)
        assert "valence" not in result["profile"] and result["mood_hint"] is None, request


def test_the_derived_valence_is_in_the_profile_for_an_asked_mood():
    result = assistant.run("happy songs", offline=True)
    expected = mean(s["valence"] for s in songs() if s["mood"] == "happy")
    assert result["profile"]["valence"] == pytest.approx(expected, abs=0.001)
    assert result["mood_hint"]["mood"] == "happy"


def test_valence_counts_in_the_best_possible_score_and_percent_match():
    assert assistant.max_possible_score({"mood": "happy"}) == 1.0
    assert assistant.max_possible_score({"mood": "happy", "valence": 0.7}) == 1.5
    assert assistant.match_percent({"mood": "happy", "valence": 0.7}, 1.5) == 100
    assert assistant.match_percent({"mood": "happy", "valence": 0.7}, 1.0) == 67


def test_sad_rock_drops_the_most_upbeat_rock_song_and_orders_by_how_happy_it_sounds():
    result = assistant.run("sad rock", offline=True)
    rock = {s["title"]: s["valence"] for s in songs() if s["genre"] == "rock"}
    happiest = max(rock, key=rock.get)
    assert happiest == "Highway Thunder"
    picks = [p["title"] for p in result["answer"]["picks"]]
    assert happiest not in picks
    assert all(title in rock for title in picks)  # the picks are rock songs
    valences = [rock[title] for title in picks]
    assert valences == sorted(valences)  # least to most happy-sounding


def test_sound_reasons_are_plain_words_with_no_numbers():
    song = {"genre": "rock", "mood": "intense", "valence": 0.52, "energy": 0.9, "instrumentalness": 0.1}
    texts = {t for _, t in pick_reasons({"genre": "rock", "mood": "melancholic", "valence": 0.255}, song)}
    assert "Sounds much brighter than you asked" in texts
    near = dict(song, valence=0.3)
    assert ("✓", "Sounds sad, like you asked") in pick_reasons({"mood": "melancholic", "valence": 0.255}, near)
    darker = dict(song, valence=0.05)
    assert ("~", "Sounds a bit darker than you asked") in pick_reasons({"mood": "happy", "valence": 0.2}, darker)
    for profile in ({"mood": "melancholic", "valence": 0.255}, {"mood": "happy", "valence": 0.2}):
        text = " ".join(t for _, t in pick_reasons(profile, song))
        assert "valence" not in text.lower() and not any(ch.isdigit() for ch in text)


def test_the_word_valence_never_appears_outside_technical_details():
    for request in ("sad rock", "happy songs", "jazz", "something good", "play me something", "chill lofi",
                    "sad but happy songs", "romantic dinner music"):
        outside, _ = split_page(submit(request))
        assert "valence" not in outside.lower(), request


def test_technical_details_show_the_derived_valence_for_the_demo():
    _, technical = split_page(submit("sad rock"))
    assert "Derived valence target" in technical and "average valence of the 4 catalog songs" in technical
    assert "valence" in technical.lower()
    _, plain_technical = split_page(submit("jazz"))
    assert "Derived valence target" not in plain_technical
