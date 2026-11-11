from src.profile_parser import VOCAB, parse_offline, validate_profile, validate_request


def test_vocab_comes_from_csv():
    assert "lofi" in VOCAB["genres"] and "chill" in VOCAB["moods"] and VOCAB["mood_tags"]


def test_validate_request_rejects_empty():
    assert validate_request("")[0] is False
    assert validate_request("   \n ")[0] is False


def test_validate_request_rejects_too_long():
    ok, msg = validate_request("music " * 100)
    assert ok is False and "too long" in msg


def test_validate_request_rejects_non_music():
    assert validate_request("what is the capital of France")[0] is False


def test_validate_request_normalizes_whitespace():
    assert validate_request("  chill   music \n for  study ") == (True, "chill music for study")


def test_offline_chill_study_no_vocals():
    p = parse_offline("something chill to study to, no vocals")
    assert p["genre"] == "lofi" and p["energy"] < 0.5 and p["instrumental"] is True


def test_offline_workout_high_energy():
    assert parse_offline("high energy workout music")["energy"] >= 0.8


def test_offline_sad_rainy():
    p = parse_offline("sad songs for a rainy day")
    assert p["mood"] == "melancholic" and p["energy"] < 0.5


def test_offline_explicit_genre_and_alias():
    assert parse_offline("some indie pop please")["genre"] == "indie pop"
    assert parse_offline("hip hop for the gym")["genre"] == "hip-hop"


def test_validate_profile_lowercases_and_clamps():
    clean, fixes = validate_profile({"genre": "LoFi", "mood": "Chill", "energy": 1.7})
    assert clean == {"genre": "lofi", "mood": "chill", "energy": 1.0}
    assert any("clamped" in f for f in fixes)


def test_validate_profile_unknown_values_and_keys():
    clean, fixes = validate_profile({"genre": "polka", "mood": "chil", "energy": -2, "bogus": 1})
    assert clean["genre"] is None
    assert clean["mood"] == "chill"  # obvious near-match
    assert clean["energy"] == 0.0
    assert "bogus" not in clean
    assert any("bogus" in f for f in fixes)


def test_validate_profile_bad_types_dropped():
    clean, _ = validate_profile({"energy": "loud", "instrumental": "yes", "mood_tags": ["calm", "xyz"]})
    assert "energy" not in clean and "instrumental" not in clean
    assert clean["mood_tags"] == ["calm"]


def test_validate_profile_maps_close_mood_tags_and_records_fixes():
    clean, fixes = validate_profile({"mood_tags": ["Calm", "nostalgc", "xyz", "calm"]})
    assert clean["mood_tags"] == ["calm", "nostalgic"]
    assert any("nostalgc" in f and "mapped" in f for f in fixes)
    assert any("xyz" in f and "dropped" in f for f in fixes)
