"""Page tests for the hype vibe word, the 'only N like this' line, and bittersweet. Offline only."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, tmp_path):
    from src import assistant
    monkeypatch.setattr(assistant, "LOG_PATH", tmp_path / "traces.jsonl")


def submit(text):
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.text_input(key="request").set_value(text).run()
    assert not at.exception
    return at


def everything(at):
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def behind_the_scenes(at):
    """The plain-English part of 'Behind the scenes' (technical details excluded)."""
    outer, nested = at.expander[0], at.expander[1]
    values, technical = [m.value for m in outer.markdown], [m.value for m in nested.markdown]
    return "\n".join(values[:len(values) - len(technical)])


def test_hype_is_shown_and_high_intensity_never_is():
    assert "Vibe: hype" in behind_the_scenes(submit("high energy workout music"))
    for request in ("high energy workout music", "calm but super high energy metal", "chill lofi",
                    "something good", "upbeat pop for a road trip"):
        assert "high-intensity" not in everything(submit(request)).lower(), request
    assert "calm and hype" in behind_the_scenes(submit("calm but super high energy metal"))


def test_only_one_like_this_line_for_romantic_rock():
    at = submit("romantic rock")
    assert [c.value for c in at.caption] == [
        "We only have 1 romantic rock song in our catalog, so the other picks are the closest matches."]
    assert len(at.get("image")) == 3


def test_zero_match_line_for_happy_metal():
    at = submit("happy metal")
    assert [c.value for c in at.caption] == [
        "We don’t have any happy metal songs in our catalog, so these are the closest matches."]
    assert len(at.get("image")) == 3


def test_no_catalog_line_for_single_attribute_requests():
    for request in ("happy songs", "jazz", "romantic dinner music", "lofi beats", "something good"):
        assert [c.value for c in submit(request).caption] == [], request


def test_bittersweet_request_explains_itself_without_calling_it_mixed_signals():
    plain = behind_the_scenes(submit("sad but happy songs"))
    assert "Mood: bittersweet" in plain
    assert "Your request mixed happy and sad, so I went with something bittersweet." in plain
    assert "mixed signals" not in plain


def test_related_moods_are_shown_as_close_to_the_requested_mood():
    plain = behind_the_scenes(submit("melancholic jazz"))
    assert "close to sad" in plain


def test_energy_is_still_never_shown_outside_technical_details():
    for request in ("romantic rock", "sad but happy songs", "melancholic jazz", "happy metal"):
        assert "energy" not in behind_the_scenes(submit(request)).lower(), request
