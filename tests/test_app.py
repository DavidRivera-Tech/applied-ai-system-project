"""Tests for the AIMA Streamlit page, driven headlessly in offline mode. No network, no API calls."""

import csv
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, tmp_path):
    from src import assistant
    monkeypatch.setattr(assistant, "LOG_PATH", tmp_path / "traces.jsonl")


def start():
    at = AppTest.from_file(APP, default_timeout=15).run()
    assert not at.exception
    return at


def submit(at, text):
    """Type into the box and press Enter (a changed value triggers the on_change run)."""
    at.text_input(key="request").set_value(text).run()
    assert not at.exception
    return at


def text_of(at):
    return " ".join(m.value for m in at.markdown)


def test_every_song_has_a_cover_file():
    with open(ROOT / "data" / "songs.csv", newline="", encoding="utf-8") as f:
        ids = [int(row["id"]) for row in csv.DictReader(f)]
    missing = [i for i in ids if not (ROOT / "assets" / "covers" / f"{i:02d}.png").is_file()]
    assert ids and not missing, f"missing covers for song ids: {missing}"


def test_page_is_a_simple_product_page():
    at = start()
    assert at.title[0].value == "🎵 AIMA (AI Music Assistant)"
    assert at.text_input(key="request").label == "Tell me your mood, activity, or genre, and I’ll find songs for you."
    assert at.text_input(key="request").placeholder == "e.g. sad songs for a rainy day"
    assert at.toggle[0].label == "Offline mode (no AI)" and at.toggle[0].value is True
    assert len(at.toggle) == 1 and len(at.button) == 0 and len(at.sidebar.children) == 0
    assert "GenreFirst" not in text_of(at)
    assert len(at.get("image")) == 0 and len(at.expander) == 0  # nothing until a request is submitted


def scenes(at):
    """Text of 'Behind the scenes' split into (plain-English part, technical-details part)."""
    outer, nested = at.expander[0], at.expander[1]
    everything = [m.value for m in outer.markdown]
    technical = [m.value for m in nested.markdown]
    assert everything[len(everything) - len(technical):] == technical  # the nested block is rendered last
    return "\n".join(everything[:len(everything) - len(technical)]), "\n".join(technical)


def page_text_outside_technical(at):
    """Everything a person sees on the page except the technical-details expander."""
    technical = {id(m) for m in at.expander[1].markdown} if len(at.expander) > 1 else set()
    parts = [m.value for m in at.markdown if id(m) not in technical] + [c.value for c in at.caption]
    return "\n".join(parts)


def test_normal_request_shows_three_covers_and_a_closed_behind_the_scenes():
    at = submit(start(), "something chill to study to, no vocals")
    assert len(at.get("image")) == 3
    assert [e.label for e in at.expander] == ["🔍 Behind the scenes", "Technical details (raw data)"]
    assert at.expander[0].proto.expanded is False and at.expander[1].proto.expanded is False
    plain, technical = scenes(at)
    for heading in ("✅ Request check", "🧠 What I understood", "🎯 Why these 3 songs",
                    "📚 Background knowledge used", "🛡️ Safety checks", "📊 Confidence"):
        assert heading in plain
    assert "Looks like a music request." in plain
    assert "Mood: chill · Genre: lofi · Vibe: relaxed" in plain
    assert "Understood by: keyword rules, offline" in plain
    assert "**4/4 passed**" in plain and "right number of picks" in plain
    assert "Offline mode is on" in plain
    assert "Good match" in plain or "Great match" in plain
    assert plain.count("% match") == 3
    assert "Timeline" in technical and "Top 5 candidates" in technical and "Explanation for each pick" in technical
    assert len(at.warning) == 0


def test_vague_positive_request_shows_note_and_vibe():
    at = submit(start(), "something good")
    assert len(at.get("image")) == 3
    plain, _ = scenes(at)
    assert "Mood: happy · Genre: any · Vibe: relaxed" in plain
    assert "Your request was general, so I went with something positive and easygoing." in plain
    assert "Good match" in plain or "Loose match" in plain  # capped at 50%, never "Great"
    assert "capped at 50%" in plain


def test_vague_negative_request_is_calm_and_reflective():
    plain, _ = scenes(submit(start(), "something bad"))
    assert "Mood: sad · Genre: any · Vibe: calm and low-key" in plain
    assert "something calm and reflective" in plain


def test_popular_picks_line_is_shown_above_the_cards_only_for_no_clue_requests():
    at = submit(start(), "play me something")
    assert [c.value for c in at.caption] == ["Here are some of the popular songs in our catalog."]
    assert len(at.get("image")) == 3
    plain, _ = scenes(at)
    assert plain.count("✓ One of the most popular songs in our catalog.") == 3
    assert "Vibe" not in plain
    assert [c.value for c in submit(start(), "something good").caption] == []


def test_vibe_only_appears_when_the_users_words_hinted_at_it():
    plain, _ = scenes(submit(start(), "happy songs"))
    assert "Mood: happy · Genre: any" in plain and "Vibe" not in plain
    assert not any(w in plain for w in ("livelier", "calmer", "Upbeat", "Relaxed, like", "High-intensity"))
    hinted, _ = scenes(submit(start(), "chill lofi"))
    assert "Vibe: relaxed" in hinted


def test_the_word_energy_is_never_shown_outside_technical_details():
    requests = ["something chill to study to, no vocals", "high energy workout music", "calm but super high energy metal",
                "happy songs", "something good", "something bad", "play me something", "chil lofy beats",
                "sad songs for a rainy day"]
    for request in requests:
        at = submit(start(), request)
        plain, _ = scenes(at)
        assert "energy" not in plain.lower(), (request, plain)
        assert "energy" not in page_text_outside_technical(at).lower(), request


def test_mixed_signals_and_typos_are_explained_in_plain_sentences():
    plain, _ = scenes(submit(start(), "calm but super high energy metal"))
    assert "Your request had mixed signals (calm and hype)" in plain
    plain, _ = scenes(submit(start(), "chil lofy beats"))
    assert "I fixed a typo: chil → chill" in plain and "I fixed a typo: lofy → lofi" in plain


EMPTY_MSG = "Tell me your mood, activity, or genre, and I’ll find songs for you."
LONG_MSG = "That’s a bit long. Try describing what you want in one short sentence."
OFF_TOPIC = ("I can only recommend music based on your mood, activity, or genre. "
             "I’m not sure ‘{}’ is a genre. Try something like ‘upbeat songs for a road trip’!")


def assert_rejected(at, message):
    # Streamlit lifts the message's leading 🎵 out of the text and shows it as the alert's icon.
    assert [w.value for w in at.warning] == [message] and at.warning[0].icon == "🎵"
    assert len(at.get("image")) == 0 and len(at.expander) == 0  # no cards, no Behind the scenes


def test_off_topic_request_message():
    at = submit(start(), "what is 1 + 1")
    assert_rejected(at, OFF_TOPIC.format(r"what is 1 \+ 1"))  # shown literally; '+' escaped for markdown


def test_empty_request_message():
    at = start()
    submit(at, "chill lofi")  # a real request first...
    assert len(at.get("image")) == 3
    submit(at, "")            # ...then clearing the box and pressing Enter
    assert_rejected(at, EMPTY_MSG)
    submit(at, "   ")         # whitespace only counts as empty too
    assert_rejected(at, EMPTY_MSG)


def test_too_long_request_message():
    assert_rejected(submit(start(), "music " * 100), LONG_MSG)


def test_long_off_topic_request_is_shortened_to_about_40_characters():
    at = submit(start(), "tell me about the history of the roman empire and its many emperors")
    assert_rejected(at, OFF_TOPIC.format("tell me about the history of the roman e…"))


def test_markdown_in_the_request_is_shown_as_plain_text():
    text = "**bold** [a](b) `c` :red[x] $y$ <b>h</b>"
    assert len(text) <= 40  # not shortened, so every special character is under test
    at = submit(start(), text)
    shown = at.warning[0].value
    # Every markdown/HTML-significant character is backslash-escaped, so nothing is formatted.
    assert "**bold**" not in shown and r"\*\*bold\*\*" in shown
    assert "](b)" not in shown and r"\]\(b\)" in shown
    assert "`c`" not in shown and r"\`c\`" in shown
    assert "<b>" not in shown and r"\<b\>h\<\/b\>" in shown
    assert r"\:red\[x\]" in shown and r"\$y\$" in shown
    assert len(at.get("image")) == 0 and len(at.expander) == 0


def test_missing_cover_falls_back_to_a_gray_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMA_COVERS_DIR", str(tmp_path))  # an empty folder: no covers at all
    at = submit(start(), "high energy workout music")
    assert not at.exception and len(at.get("image")) == 3
