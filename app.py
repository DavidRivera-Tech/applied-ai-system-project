"""AIMA (AI Music Assistant): a Streamlit front end for assistant.run().

Run with:  python -m streamlit run app.py
"""

import os
import string
import sys
from pathlib import Path

import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the assistant loads data/ files relative to the project root

from src import assistant  # noqa: E402
from src.explain import (confidence_sentence, friendly_mood, pick_reasons, plain_fix, scarcity_note,
                         vibe_name, wants_vibe)  # noqa: E402
from src.profile_parser import MAX_LEN, POPULAR_NOTE, VAGUE_NOTES  # noqa: E402

# Covers are looked up next to app.py, so it works from any launch directory.
COVERS_DIR = Path(os.environ.get("AIMA_COVERS_DIR", ROOT / "assets" / "covers"))

CHECK_EXPLANATIONS = {
    "titles_match_retrieved": "Every picked song must be one of the retrieved candidates, so nothing is made up.",
    "no_duplicate_picks": "The same song can't be picked twice.",
    "text_names_only_retrieved": "The explanations and summary may only mention songs that were retrieved.",
    "correct_pick_count": "The answer must contain exactly the right number of picks.",
}


# ---------------------------------------------------------------- helpers

def on_enter() -> None:
    """Runs when the text box changes (Enter pressed): remember what to look up."""
    st.session_state["submitted"] = True
    st.session_state["query"] = st.session_state["request"]


def plain_text(text: str) -> str:
    """Escape every ASCII punctuation character so Streamlit's markdown shows the text literally.

    This also defuses links, emphasis, :emoji: shortcodes, $math$ and :color[...] directives.
    HTML is never rendered anyway (unsafe_allow_html is off), and escaping keeps it visible as text.
    """
    return "".join("\\" + ch if ch in string.punctuation else ch for ch in text)


def shorten(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def rejection_message(request: str) -> str:
    """A friendly message for a request the input guardrail rejected."""
    collapsed = " ".join(request.split())
    if not collapsed:
        return "🎵 Tell me your mood, activity, or genre, and I’ll find songs for you."
    if len(collapsed) > MAX_LEN:
        return "🎵 That’s a bit long. Try describing what you want in one short sentence."
    return ("🎵 I can only recommend music based on your mood, activity, or genre. "
            f"I’m not sure ‘{plain_text(shorten(collapsed))}’ is a genre. "
            "Try something like ‘upbeat songs for a road trip’!")


def cover_for(song_id: int):
    """The cover image for a song, or a plain gray square if the file is missing or unreadable."""
    path = COVERS_DIR / f"{int(song_id):02d}.png"
    if path.is_file():
        try:
            return Image.open(path)
        except OSError:
            pass
    return Image.new("RGB", (512, 512), (200, 200, 200))


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "Great match"
    if score >= 0.5:
        return "Good match"
    return "Loose match: try being more specific"


def show_cards(result: dict) -> None:
    by_title = {song["title"]: song for song, _, _ in result["retrieved"]}
    picks = result["answer"]["picks"]
    if POPULAR_NOTE in result["parse_fixes"]:
        st.caption(POPULAR_NOTE)
    scarcity = scarcity_note(result["profile"], assistant.load_songs(assistant.SONGS_PATH))
    if scarcity:
        st.caption(scarcity)
    for col, pick in zip(st.columns(len(picks)), picks):
        song = by_title[pick["title"]]  # verified: every pick is a retrieved song
        with col.container(border=True):
            st.image(cover_for(song["id"]), width="stretch")
            st.markdown(f"**{pick['title']}**")


def process_notes(result: dict) -> list:
    """Plain-English lines about any retry or fallback that happened while writing the answer."""
    lines = []
    for step in result["trace_steps"]:
        if step["step"] == "retry":
            if "transient" in step["reason"]:
                lines.append("Gemini hit a hiccup, so I tried again.")
            else:
                lines.append("Gemini's first answer didn't pass a safety check, so I asked it again.")
        elif step["step"] == "fallback":
            if step["reason"] == "offline mode":
                lines.append("Offline mode is on, so the explanations came from a template instead of Gemini.")
            else:
                lines.append("Gemini wasn't available or its answer didn't pass, so I used a template instead.")
    return lines


def show_technical_details(result: dict) -> None:
    """The raw data behind the plain-English summary. Raw numbers are fine here."""
    with st.expander("Technical details (raw data)", expanded=False):
        hint = result.get("mood_hint")
        if hint:
            st.write(f"Derived valence target: {hint['valence']:.3f} = average valence of the {hint['songs']} "
                     f"catalog songs with mood '{hint['mood']}' (computed from songs.csv)")
        st.write("Profile")
        st.json(result["profile"])
        st.write("Top 5 candidates")
        for i, (song, score, reasons) in enumerate(result["retrieved"], 1):
            st.write(f"{i}. **{song['title']}** by {song['artist']} ({song['genre']}) · score {score:.2f}  \n"
                     f"   _{reasons}_")
        st.write("Genre guide notes")
        if result["guide_notes"]:
            for name, text in result["guide_notes"].items():
                st.write(f"- **{name}**: {text}")
        else:
            st.write("None.")
        st.write("Explanation for each pick")
        for pick in result["answer"]["picks"]:
            st.write(f"- **{pick['title']}**: {pick['why']}")
        st.write("Checks")
        for check in result["verification"]:
            st.write(f"{'✅' if check['passed'] else '❌'} `{check['check']}`: "
                     f"{CHECK_EXPLANATIONS.get(check['check'], '')} ({check['detail']})")
        st.write("Confidence")
        st.write(f"{result['confidence']:.2f}: {result['confidence_explanation']}")
        st.write("Timeline")
        st.dataframe([{"step": s["step"], "ok": "✅" if s["ok"] else "❌", "ms": s["ms"]}
                      for s in result["trace_steps"]], hide_index=True, width="stretch")


def show_behind_the_scenes(result: dict) -> None:
    profile, steps, fixes = result["profile"], result["trace_steps"], result["parse_fixes"]
    by_title = {song["title"]: song for song, _, _ in result["retrieved"]}
    scores = {song["title"]: score for song, score, _ in result["retrieved"]}

    with st.expander("🔍 Behind the scenes", expanded=False):
        st.markdown("#### ✅ Request check")
        st.write("Looks like a music request.")

        st.markdown("#### 🧠 What I understood")
        understood = f"Mood: {friendly_mood(profile.get('mood')) or 'any'} · Genre: {profile.get('genre') or 'any'}"
        if wants_vibe(profile):  # only when the user's words hinted at a vibe
            understood += f" · Vibe: {vibe_name(profile['energy'])}"
        st.write(understood)
        st.write("Understood by: " + ("Gemini" if result["parse_source"] == "llm" else "keyword rules, offline"))
        for fix in fixes:
            st.write(f"- {plain_fix(fix)}")

        st.markdown("#### 🎯 Why these 3 songs")
        for pick in result["answer"]["picks"]:
            song = by_title[pick["title"]]
            percent = assistant.match_percent(profile, scores[pick["title"]])
            st.write(f"**{pick['title']}** by {song['artist']} · {percent}% match")
            for mark, text in pick_reasons(profile, song):
                st.write(f"{mark} {text}")

        st.markdown("#### 📚 Background knowledge used")
        st.write(", ".join(friendly_mood(name) for name in result["guide_notes"]) or "None for this request.")

        st.markdown("#### 🛡️ Safety checks")
        passed = sum(c["passed"] for c in result["verification"])
        total = len(result["verification"])
        st.markdown(f"**{passed}/{total} passed**" if passed == total else f"**:red[{passed}/{total} passed]**")
        st.write("All picks are real songs from the catalog · no repeats · no made-up songs mentioned · "
                 "right number of picks.")
        for line in process_notes(result):
            st.write(f"- {line}")

        st.markdown("#### 📊 Confidence")
        st.write(f"**{confidence_label(result['confidence'])} ({round(result['confidence'] * 100)}%)**")
        verifies = [s for s in steps if s["step"] == "verify"]
        retried = result["answer_source"] == "llm" and len(verifies) > 1
        top_score = result["retrieved"][0][1] if result["retrieved"] else 0.0
        st.write(confidence_sentence(assistant.match_percent(profile, top_score) / 100, result["parse_source"],
                                     result["answer_source"], retried, fixes,
                                     capped=any(note in fixes for note in VAGUE_NOTES)))

        show_technical_details(result)


# ---------------------------------------------------------------- page

st.set_page_config(page_title="AIMA", page_icon="🎵")
st.title("🎵 AIMA (AI Music Assistant)")

st.text_input("Tell me your mood, activity, or genre, and I’ll find songs for you.", key="request",
              on_change=on_enter, placeholder="e.g. sad songs for a rainy day")
offline = st.toggle("Offline mode (no AI)", value=True, key="offline")

if st.session_state.get("submitted"):
    cache_key = (st.session_state["query"], offline)
    if st.session_state.get("cache_key") != cache_key:
        with st.spinner("Finding songs..."):
            st.session_state["result"] = assistant.run(st.session_state["query"], offline=offline, use_guide=True)
        st.session_state["cache_key"] = cache_key
    result = st.session_state["result"]

    if result.get("error"):
        st.warning(rejection_message(st.session_state["query"]))
    else:
        show_cards(result)
        show_behind_the_scenes(result)
