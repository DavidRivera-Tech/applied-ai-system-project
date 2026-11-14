from pathlib import Path

import pytest

from src.recommender import (
    Song,
    UserProfile,
    Recommender,
    get_strategy,
    load_songs,
    recommend_songs,
    score_song,
)

SONGS_CSV = Path(__file__).resolve().parent.parent / "data" / "songs.csv"

HIGH_ENERGY_POP = {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}
CLASSICAL_HIGH_ENERGY = {
    "genre": "classical", "mood": "melancholic", "energy": 0.9, "likes_acoustic": True,
}


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(SONGS_CSV))

def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    # Starter expectation: the pop, happy, high energy song should score higher
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


def test_load_songs_converts_types(songs):
    song = songs[0]

    assert isinstance(song["id"], int)
    assert isinstance(song["energy"], float)
    assert isinstance(song["tempo_bpm"], float)
    assert isinstance(song["popularity"], int)
    assert isinstance(song["release_decade"], int)
    assert isinstance(song["mood_tags"], list)
    assert song["mood_tags"] == ["euphoric", "uplifting"]


def test_closer_energy_scores_higher():
    close = {"energy": 0.78}
    far = {"energy": 0.30}

    close_score, _ = score_song({"energy": 0.8}, close)
    far_score, _ = score_song({"energy": 0.8}, far)

    assert close_score > far_score


def test_energy_closeness_never_negative(songs):
    # A target of 2.0 is outside 0-1, so every song is more than 1.0 away.
    for song in songs:
        score, _ = score_song({"energy": 2.0}, song)
        assert score >= 0


def test_recommendations_sorted_high_to_low(songs):
    results = recommend_songs(HIGH_ENERGY_POP, songs, k=5)
    scores = [score for _, score, _ in results]

    assert len(results) == 5
    assert scores == sorted(scores, reverse=True)


# The four ranking modes, checked by behavior (not by song names) so they survive catalog changes.
# The request is a clash on purpose: classical + melancholic, but with a very high energy target.

def test_balanced_mode_returns_results_sorted_high_to_low(songs):
    results = recommend_songs(CLASSICAL_HIGH_ENERGY, songs, k=5, mode="balanced")
    scores = [score for _, score, _ in results]
    assert len(results) == 5 and scores == sorted(scores, reverse=True)


def test_genre_boost_number_one_is_in_the_requested_genre(songs):
    assert any(s["genre"] == "classical" for s in songs)  # the catalog must offer the genre for this to mean anything
    top = recommend_songs(CLASSICAL_HIGH_ENERGY, songs, k=5, mode="genre-boost")[0][0]
    assert top["genre"] == "classical"


def test_mood_first_number_one_has_the_requested_mood(songs):
    assert any(s["mood"] == "melancholic" for s in songs)
    top = recommend_songs(CLASSICAL_HIGH_ENERGY, songs, k=5, mode="mood-first")[0][0]
    assert top["mood"] == "melancholic"


def test_energy_focused_number_one_has_the_closest_energy(songs):
    target = CLASSICAL_HIGH_ENERGY["energy"]
    top = recommend_songs(CLASSICAL_HIGH_ENERGY, songs, k=5, mode="energy-focused")[0][0]
    closest_gap = min(abs(s["energy"] - target) for s in songs)
    assert abs(top["energy"] - target) == pytest.approx(closest_gap)


def test_every_mode_returns_sorted_results(songs):
    for mode in ("balanced", "genre-boost", "mood-first", "energy-focused"):
        scores = [score for _, score, _ in recommend_songs(CLASSICAL_HIGH_ENERGY, songs, k=5, mode=mode)]
        assert scores == sorted(scores, reverse=True), mode


def test_unknown_mode_raises_value_error(songs):
    with pytest.raises(ValueError, match="Unknown mode"):
        get_strategy("nope")
    with pytest.raises(ValueError):
        recommend_songs(HIGH_ENERGY_POP, songs, mode="nope")


def test_diversity_removes_repeated_artist_from_pop_top_five(songs):
    def titles(results):
        return [song["title"] for song, _, _ in results]

    def neon_echo_count(results):
        return sum(1 for song, _, _ in results if song["artist"] == "Neon Echo")

    plain = recommend_songs(HIGH_ENERGY_POP, songs, k=5)
    diverse = recommend_songs(HIGH_ENERGY_POP, songs, k=5, diversity=True)

    assert "Afterglow Avenue" in titles(plain)
    assert neon_echo_count(plain) == 2

    assert "Afterglow Avenue" not in titles(diverse)
    assert neon_echo_count(diverse) == 1
    assert titles(diverse)[0] == "Sunrise City"
