"""Plain-English wording for results: vibe words, per-pick reasons, fix notes, confidence sentence.

Nothing here changes how songs are scored. It only describes results for people. The word
"energy" is deliberately never produced: the vibe is described as calm, relaxed, upbeat or
hype instead.
"""

import re
from typing import Dict, List, Optional, Tuple

from src.profile_parser import CONFLICT_NOTE, NOTE_BITTERSWEET, POPULAR_NOTE, VAGUE_NOTES
from src.recommender import mood_family


# ---------------------------------------------------------------- friendly mood labels

# Internal catalog label -> the word people see. Add a pair here to rename another mood.
MOOD_LABELS = {"melancholic": "sad"}


def friendly_mood(mood: Optional[str]) -> str:
    """The user-facing word for a mood. The internal label stays unchanged everywhere else."""
    return MOOD_LABELS.get(mood, mood) if mood else mood


# ---------------------------------------------------------------- vibe words

def vibe_name(level: float) -> str:
    """The user-facing vibe word for a 0-1 level: calm and low-key / relaxed / upbeat / hype."""
    if level < 0.35:
        return "calm and low-key"
    if level <= 0.55:
        return "relaxed"
    if level <= 0.8:
        return "upbeat"
    return "hype"


def song_adjective(level: float) -> str:
    """A single adjective describing a song's vibe, for use inside a sentence."""
    if level < 0.35:
        return "calm"
    if level <= 0.55:
        return "easygoing"
    if level <= 0.8:
        return "upbeat"
    return "hype"


def wants_vibe(profile: Dict) -> bool:
    """True only if the user's words hinted at a vibe (the profile has an energy level)."""
    return profile is not None and profile.get("energy") is not None


def is_popular_profile(profile: Dict) -> bool:
    return bool(profile) and profile.get("popularity") is not None


# ---------------------------------------------------------------- template sentences

_SOUNDS_LIKE_VOWEL = {"r&b", "edm"}  # spoken as letters: "an R&B track", "an EDM track"


def _display_genre(genre: str) -> str:
    return genre.upper() if genre in _SOUNDS_LIKE_VOWEL else genre


def _a_or_an(word: str) -> str:
    return "an" if word[0].lower() in "aeiou" or word in ("R&B", "EDM") else "a"


def friendly_why(song: Dict, profile: Optional[Dict]) -> str:
    """One friendly sentence about why a song fits. No numbers, no scoring terms."""
    profile = profile or {}
    words = []
    if wants_vibe(profile):
        words.append(song_adjective(song["energy"]))
    words += [_display_genre(song["genre"]), "track"]
    phrase = " ".join(words)
    head = f"{_a_or_an(words[0]).capitalize()} {phrase} with {_a_or_an(song['mood'])} {song['mood']} feel"

    if is_popular_profile(profile):
        return f"{head}, one of the most popular songs in our catalog."
    asked_genre, asked_mood = profile.get("genre"), profile.get("mood")
    matched = ((asked_genre is None or song["genre"] == asked_genre)
               and (asked_mood is None or song["mood"] == asked_mood)
               and (not wants_vibe(profile) or abs(song["energy"] - profile["energy"]) <= 0.3))
    if (asked_genre or asked_mood) and not matched:
        return f"{head}, a close match for what you asked."
    return f"{head}, a good fit for what you asked."


# ---------------------------------------------------------------- reasons for one pick

def pick_reasons(profile: Dict, song: Dict) -> List[Tuple[str, str]]:
    """Up to four (mark, text) reasons: ✓ matched, ~ close, ✗ didn't match. Vibe only if the user hinted."""
    if is_popular_profile(profile):
        return [("✓", "One of the most popular songs in our catalog.")]

    reasons: List[Tuple[str, str]] = []
    if profile.get("genre"):
        if song["genre"] == profile["genre"]:
            reasons.append(("✓", f"Genre: {song['genre']}, like you asked"))
        else:
            reasons.append(("✗", f"Genre: {song['genre']}, not {profile['genre']}"))
    if profile.get("mood"):
        if song["mood"] == profile["mood"]:
            reasons.append(("✓", f"Mood: {friendly_mood(song['mood'])}, like you asked"))
        elif mood_family(profile["mood"]) is not None and mood_family(profile["mood"]) == mood_family(song["mood"]):
            reasons.append(("~", f"{friendly_mood(song['mood']).capitalize()}, close to {friendly_mood(profile['mood'])}"))
        else:
            reasons.append(("✗", f"Mood: {friendly_mood(song['mood'])}, not {friendly_mood(profile['mood'])}"))
    if profile.get("mood") and profile.get("valence") is not None and song.get("valence") is not None:
        gap = song["valence"] - profile["valence"]  # how bright the song sounds vs. the requested mood's usual sound
        if abs(gap) <= 0.12:
            reasons.append(("✓", f"Sounds {friendly_mood(profile['mood'])}, like you asked"))
        else:
            size = "a bit" if abs(gap) <= 0.25 else "much"
            reasons.append(("~" if size == "a bit" else "✗",
                            f"Sounds {size} {'brighter' if gap > 0 else 'darker'} than you asked"))
    if wants_vibe(profile):
        gap = song["energy"] - profile["energy"]
        wanted = vibe_name(profile["energy"])
        if abs(gap) <= 0.15:
            reasons.append(("✓", f"{wanted[0].upper()}{wanted[1:]}, like you asked"))
        else:
            size = "A bit" if abs(gap) <= 0.3 else "Much"
            reasons.append(("~" if size == "A bit" else "✗",
                            f"{size} {'livelier' if gap > 0 else 'calmer'} than you asked"))
    if len(reasons) < 3 and profile.get("instrumental") is not None:
        wants = profile["instrumental"]
        has = song["instrumentalness"] >= 0.5
        reasons.append(("✓" if wants == has else "✗",
                        "Mostly instrumental, no vocals" if has else "Has vocals"))
    return reasons[:4] or [("~", "A general match for your request")]


# ---------------------------------------------------------------- "only N like this"

def scarcity_note(profile: Dict, songs: List[Dict]) -> Optional[str]:
    """A line for when the catalog has fewer than 3 songs matching BOTH the requested genre and mood."""
    genre, mood = profile.get("genre"), profile.get("mood")
    if not genre or not mood:
        return None  # only a genre, or only a mood: nothing to report
    n = sum(1 for s in songs if s["genre"] == genre and s["mood"] == mood)
    if n >= 3:
        return None
    if n == 0:
        return f"We don’t have any {friendly_mood(mood)} {genre} songs in our catalog, so these are the closest matches."
    return (f"We only have {n} {friendly_mood(mood)} {genre} song{'s' if n != 1 else ''} in our catalog, "
            "so the other picks are the closest matches.")


# ---------------------------------------------------------------- fix notes and confidence

def plain_fix(note: str) -> str:
    """Rewrite one parse note as a plain sentence for people."""
    typo = re.fullmatch(r"typo corrected: '(.+)' -> '(.+)'", note)
    if typo:
        return f"I fixed a typo: {typo.group(1)} → {typo.group(2)}"
    if note == CONFLICT_NOTE:
        return "Your request had mixed signals (calm and hype)"
    if note in VAGUE_NOTES or note == NOTE_BITTERSWEET:
        return note
    return "I adjusted one detail to match what our catalog knows."


def confidence_sentence(strength: float, parse_source: str, answer_source: str, retried: bool,
                        fixes: List[str], capped: bool) -> str:
    """One sentence on why confidence is what it is, from the factors that feed it."""
    match = "very strong" if strength >= 0.8 else "decent" if strength >= 0.5 else "loose"
    parts = [f"the best song in our catalog is a {match} match for what you described"]
    parts.append("Gemini understood your request" if parse_source == "llm"
                 else "keyword rules (offline) understood your request, which is less flexible than Gemini")
    if answer_source == "llm":
        parts.append("Gemini's answer passed every check " + ("only after a retry" if retried else "on the first try"))
    else:
        parts.append("the explanations came from a template, not Gemini")
    text = f"{parts[0][0].upper()}{parts[0][1:]}, {parts[1]}, and {parts[2]}."
    if capped:
        text += " Because your request was general, confidence is capped at 50%."
    if CONFLICT_NOTE in fixes:
        text += " The mixed signals in your request lowered it a little."
    return text
