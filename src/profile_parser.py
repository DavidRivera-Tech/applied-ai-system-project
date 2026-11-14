"""Turn a plain-English music request into a taste profile dict for recommend_songs."""

import csv
import difflib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.llm_client import LLMError, ask_llm, is_llm_available

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "songs.csv"
MAX_LEN = 500
ALLOWED_KEYS = {"genre", "mood", "energy", "likes_acoustic", "tempo_bpm", "instrumental", "mood_tags"}


def load_vocabulary(csv_path: Path = CSV_PATH) -> Dict[str, List[str]]:
    """Read the allowed genres, moods and mood_tags from the song catalog."""
    genres, moods, tags = set(), set(), set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            genres.add(row["genre"].strip().lower())
            moods.add(row["mood"].strip().lower())
            tags.update(t.strip().lower() for t in row["mood_tags"].split("|") if t.strip())
    return {"genres": sorted(genres), "moods": sorted(moods), "mood_tags": sorted(tags)}


VOCAB = load_vocabulary()

# ---------------------------------------------------------------- validate_request

MUSIC_WORDS = {
    "music", "song", "songs", "track", "tracks", "playlist", "tune", "tunes", "beat", "beats",
    "vibe", "vibes", "listen", "listening", "sound", "sounds", "album", "artist", "band",
    "chill", "study", "workout", "gym", "run", "running", "party", "sleep", "relax", "focus",
    "sad", "happy", "energy", "energetic", "upbeat", "calm", "dance", "acoustic", "instrumental",
    "vocals", "lyrics", "mood", "drive", "driving", "rainy", "romantic", "cozy", "heavy", "loud",
    "soft", "slow", "fast", "lofi", "lo-fi",
}


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9&'-]+", text.lower()))


GENERIC_WORDS = {
    "something", "anything", "some", "any", "new", "whatever", "stuff", "me", "i", "a", "an", "the", "to",
    "of", "for", "play", "give", "put", "on", "recommend", "suggest", "want", "need", "like", "would",
    "can", "could", "you", "please", "just", "hear", "listen", "listening", "music", "song", "songs",
    "tune", "tunes", "track", "tracks", "feel", "feeling", "day",
}
POSITIVE_WORDS = {"good", "nice", "great", "cool", "decent", "fine", "fun", "feel-good", "awesome"}
NEGATIVE_WORDS = {"bad", "rough", "down", "awful", "terrible"}


def vague_kind(text: str) -> Optional[str]:
    """Classify a short generic request: 'positive', 'negative', 'none' (no clue at all), or None if it isn't vague."""
    words = re.findall(r"[a-z0-9&'-]+", text.lower())
    if not (0 < len(words) <= 6) or not set(words) <= (GENERIC_WORDS | POSITIVE_WORDS | NEGATIVE_WORDS):
        return None
    if set(words) & NEGATIVE_WORDS:
        return "negative"
    if set(words) & POSITIVE_WORDS:
        return "positive"
    return "none"


def is_vague(text: str) -> bool:
    return vague_kind(text) is not None


def validate_request(text) -> Tuple[bool, str]:
    """Input guardrail. Returns (ok, cleaned_text) or (False, error_message)."""
    if not isinstance(text, str):
        return False, "Request must be text."
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return False, "Request is empty. Describe the music you want."
    if len(cleaned) > MAX_LEN:
        return False, f"Request is too long ({len(cleaned)} characters; max {MAX_LEN})."
    if is_vague(cleaned):
        return True, cleaned
    known = MUSIC_WORDS | set(VOCAB["genres"]) | set(VOCAB["moods"]) | set(VOCAB["mood_tags"])
    if not (_words(correct_typos(cleaned)[0]) & known):
        return False, "That doesn't look like a music request. Try describing a genre, mood or activity."
    return True, cleaned


# ---------------------------------------------------------------- parse_offline

GENRE_ALIASES = {
    "hip hop": "hip-hop", "hiphop": "hip-hop", "rap": "hip-hop", "rnb": "r&b", "lo-fi": "lofi",
    "lo fi": "lofi", "electronic": "edm", "dance music": "edm", "classic rock": "rock",
}
MOOD_SYNONYMS = {
    "sad": "melancholic", "rainy": "melancholic", "depressed": "melancholic", "blue": "melancholic",
    "gloomy": "melancholic", "relax": "relaxed", "relaxing": "relaxed", "mellow": "relaxed",
    "chill": "chill", "study": "focused", "studying": "focused", "focus": "focused",
    "concentrate": "focused", "angry": "aggressive", "hype": "energetic", "workout": "energetic",
    "gym": "energetic", "party": "energetic", "joyful": "happy", "upbeat": "happy",
    "love": "romantic", "date": "romantic", "dark": "moody", "night": "moody",
    "calm": "serene", "peaceful": "serene",
}
# Words that hint at a vibe or activity. Mood words alone ("happy", "sad") are deliberately absent:
# with no hint the profile gets no energy at all and scoring skips it.
LOW_ENERGY = {"chill": 0.35, "study": 0.35, "studying": 0.35, "focus": 0.4, "relax": 0.3,
              "relaxing": 0.3, "sleep": 0.15, "calm": 0.25, "peaceful": 0.25,
              "rainy": 0.3, "mellow": 0.3, "soft": 0.25, "slow": 0.25, "cozy": 0.3,
              "low vibes": 0.25, "laid-back": 0.45, "laid back": 0.45, "easygoing": 0.45}
HIGH_ENERGY = {"workout": 0.9, "gym": 0.9, "running": 0.85, "run": 0.85, "party": 0.85,
               "hype": 0.9, "intense": 0.9, "pump": 0.9, "energetic": 0.85, "upbeat": 0.8,
               "loud": 0.9, "fast": 0.85, "heavy": 0.9, "dance": 0.8,
               "angry": 0.85, "blow off steam": 0.9, "pump up": 0.9, "road trip": 0.75, "sunny": 0.75,
               "high energy": 0.9}


TYPO_CUTOFF = 0.75
MIN_TYPO_LEN = 4
MAX_TYPO_LEN_DIFF = 2


def correct_typos(text: str) -> Tuple[str, List[str]]:
    """Fix single-word typos against the catalog's genre and mood words (difflib, cutoff 0.75).

    Only words the parser doesn't already know are touched. Returns (corrected_text, notes).
    """
    targets = sorted({w for w in VOCAB["genres"] + VOCAB["moods"] if re.fullmatch(r"[a-z]+", w)})
    known = (MUSIC_WORDS | GENERIC_WORDS | set(VOCAB["genres"]) | set(VOCAB["moods"]) | set(VOCAB["mood_tags"])
             | set(MOOD_SYNONYMS) | set(LOW_ENERGY) | set(HIGH_ENERGY) | set(GENRE_ALIASES))
    notes: List[str] = []

    def fix(match):
        word = match.group(0)
        if len(word) < MIN_TYPO_LEN or word.lower() in known:
            return word
        near = difflib.get_close_matches(word.lower(), targets, n=1, cutoff=TYPO_CUTOFF)
        # A typo is about the same length as the word it garbles; 'roman' is not a typo of 'romantic'.
        if not near or abs(len(near[0]) - len(word)) > MAX_TYPO_LEN_DIFF:
            return word
        notes.append(f"typo corrected: '{word}' -> '{near[0]}'")
        return near[0]

    return re.sub(r"[A-Za-z]+", fix, text), notes


def _cues(table: Dict[str, float], low: str, words: set) -> List[float]:
    """Energy values for every cue in `table` present in the text (phrases match as substrings)."""
    return [v for k, v in table.items() if (k in low if " " in k else k in words)]


def has_conflicting_cues(text: str) -> bool:
    """True if the request has both a low-energy cue and a high-energy cue (e.g. 'calm' and 'high energy')."""
    low = correct_typos(text)[0].lower()
    words = _words(low)
    return bool(_cues(HIGH_ENERGY, low, words) and _cues(LOW_ENERGY, low, words))


def parse_offline(text: str) -> Dict:
    """Rule-based keyword parser. The fallback and the baseline."""
    return parse_offline_with_notes(text)[0]


def parse_offline_with_notes(text: str) -> Tuple[Dict, List[str]]:
    """Like parse_offline, but also returns notes about typos it corrected."""
    text, notes = correct_typos(text)
    low = text.lower()
    words = _words(low)
    profile: Dict = {}

    for alias, genre in GENRE_ALIASES.items():
        if alias in low:
            profile["genre"] = genre
            break
    else:
        for genre in sorted(VOCAB["genres"], key=len, reverse=True):  # "indie pop" before "pop"
            if re.search(rf"(?<![\w-]){re.escape(genre)}(?![\w-])", low):
                profile["genre"] = genre
                break

    if "genre" not in profile and words & {"chill", "study", "studying", "lofi"}:
        profile["genre"] = "lofi"

    for word in sorted(words):
        if word in VOCAB["moods"]:
            profile["mood"] = word
            break
    else:
        for word in re.findall(r"[a-z-]+", low):
            if word in MOOD_SYNONYMS:
                profile["mood"] = MOOD_SYNONYMS[word]
                break

    highs, lows = _cues(HIGH_ENERGY, low, words), _cues(LOW_ENERGY, low, words)
    if highs and lows:
        energies = highs + lows  # opposing cues pull toward the middle (the note is added by parse_request)
    else:
        energies = highs or lows
    if energies:  # no hint in the words -> no energy key at all
        profile["energy"] = round(sum(energies) / len(energies), 2)

    if re.search(r"\b(no|without)\s+(vocals|lyrics|singing|words)\b|\binstrumental\b", low):
        profile["instrumental"] = True
    elif re.search(r"\b(vocals|singing|sing along|lyrics)\b", low):
        profile["instrumental"] = False

    if words & {"acoustic", "rainy", "cozy", "unplugged"}:
        profile["likes_acoustic"] = True
    elif words & {"electronic", "synth"}:
        profile["likes_acoustic"] = False

    tags = [t for t in VOCAB["mood_tags"] if t in words]
    if tags:
        profile["mood_tags"] = tags
    return profile, notes


# ---------------------------------------------------------------- parse_with_llm

FEW_SHOT = """Examples:
Request: "upbeat pop for a road trip"
{"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": false}

Request: "mellow acoustic evening, nothing with vocals"
{"genre": "folk", "mood": "relaxed", "energy": 0.25, "likes_acoustic": true, "instrumental": true}

Request: "aggressive loud music to lift weights to"
{"genre": "metal", "mood": "aggressive", "energy": 0.95, "tempo_bpm": 160, "mood_tags": ["driving"]}

Request: "romantic songs for date night"
{"mood": "romantic", "mood_tags": ["romantic"]}

Request: "happy jazz"
{"genre": "jazz", "mood": "happy"}
"""


def build_prompt(text: str, few_shot: bool = True) -> str:
    prompt = (
        "Convert the music request into a JSON taste profile. Reply with ONLY a JSON object, "
        "no prose and no code fences.\n"
        'Keys: "genre" (string), "mood" (string), and optionally "energy" (number 0-1), '
        '"likes_acoustic" (bool), "tempo_bpm" (number), "instrumental" (bool), "mood_tags" (list of strings).\n'
        'Include "energy" ONLY if the request mentions pace, intensity, or an activity '
        '(for example "chill", "workout", "road trip", "to fall asleep"). A mood alone, such as '
        '"happy" or "romantic", is not a hint: leave "energy" out.\n'
        f"Allowed genres: {', '.join(VOCAB['genres'])}\n"
        f"Allowed moods: {', '.join(VOCAB['moods'])}\n"
        f"Allowed mood_tags: {', '.join(VOCAB['mood_tags'])}\n"
        "Use only allowed values; use null for genre or mood if nothing fits.\n"
    )
    if few_shot:
        prompt += "\n" + FEW_SHOT
    return prompt + f'\nRequest: "{text}"\n'


def _extract_json(raw: str) -> Dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in LLM response")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM JSON is not an object")
    return data


def parse_with_llm(text: str, few_shot: bool = True) -> Dict:
    """Ask Gemini for a profile. Raises LLMError or ValueError on failure."""
    return _extract_json(ask_llm(build_prompt(text, few_shot)))


# ---------------------------------------------------------------- validate_profile

def _closest(value, allowed: List[str]) -> Optional[str]:
    match = difflib.get_close_matches(value, allowed, n=1, cutoff=0.8)
    return match[0] if match else None


def validate_profile(profile: Dict) -> Tuple[Dict, List[str]]:
    """Normalize a profile. Returns (clean_profile, list_of_fixes_made)."""
    fixes: List[str] = []
    clean: Dict = {}
    if not isinstance(profile, dict):
        return {}, ["profile was not a dict; discarded"]

    for key in profile:
        if key not in ALLOWED_KEYS:
            fixes.append(f"dropped unknown key '{key}'")

    for key, vocab in (("genre", VOCAB["genres"]), ("mood", VOCAB["moods"])):
        if key not in profile:
            continue
        raw = profile[key]
        val = raw.strip().lower() if isinstance(raw, str) else None
        if isinstance(raw, str) and val != raw:
            fixes.append(f"normalized {key} '{raw}' -> '{val}'")
        if val in vocab:
            clean[key] = val
        else:
            near = _closest(val, vocab) if val else None
            clean[key] = near
            if raw is not None:
                fixes.append(f"unknown {key} {raw!r} -> {near!r}")

    if "energy" in profile:
        try:
            e = float(profile["energy"])
            c = min(1.0, max(0.0, e))
            if c != e:
                fixes.append(f"clamped energy {e} -> {c}")
            clean["energy"] = c
        except (TypeError, ValueError):
            fixes.append(f"invalid energy {profile['energy']!r}; dropped")

    for key in ("likes_acoustic", "instrumental"):
        if key in profile:
            if isinstance(profile[key], bool):
                clean[key] = profile[key]
            else:
                fixes.append(f"invalid {key} {profile[key]!r}; dropped")

    if "tempo_bpm" in profile:
        try:
            clean["tempo_bpm"] = float(profile["tempo_bpm"])
        except (TypeError, ValueError):
            fixes.append(f"invalid tempo_bpm {profile['tempo_bpm']!r}; dropped")

    if "mood_tags" in profile:
        raw = profile["mood_tags"]
        raw = raw.split("|") if isinstance(raw, str) else raw
        if isinstance(raw, list):
            kept = []
            for t in raw:
                t_norm = str(t).strip().lower()
                if t_norm in VOCAB["mood_tags"]:
                    mapped = t_norm
                else:
                    mapped = _closest(t_norm, VOCAB["mood_tags"])
                    if mapped:
                        fixes.append(f"mapped mood_tag {t!r} -> {mapped!r}")
                    else:
                        fixes.append(f"dropped unknown mood_tag {t!r}")
                if mapped and mapped not in kept:
                    kept.append(mapped)
            if kept:
                clean["mood_tags"] = kept
        else:
            fixes.append("invalid mood_tags; dropped")
    return clean, fixes


# ---------------------------------------------------------------- parse_request

NOTE_POSITIVE = "Your request was general, so I went with something positive and easygoing."
NOTE_NEGATIVE = "Your request was general, so I went with something calm and reflective."
POPULAR_NOTE = "Here are some of the popular songs in our catalog."
VAGUE_NOTES = {NOTE_POSITIVE, NOTE_NEGATIVE, POPULAR_NOTE}  # any of these caps confidence at 50%
VAGUE_PROFILES = {
    "positive": ({"mood": "happy", "energy": 0.45}, NOTE_POSITIVE),
    "negative": ({"mood": "melancholic", "energy": 0.25}, NOTE_NEGATIVE),
    "none": ({"popularity": 100}, POPULAR_NOTE),  # no clue at all: rank by the catalog's popularity score
}
CONFLICT_NOTE = "conflicting cues detected"

def _has_no_preferences(profile: Dict) -> bool:
    """True if the profile has nothing to score on (every value missing or empty)."""
    return not any(v not in (None, [], "") for v in profile.values())


def parse_request(text: str, few_shot: bool = True, offline: bool = False) -> Tuple[Optional[Dict], str, List[str]]:
    """Validate, try the LLM, fall back to offline. Returns (profile, source, fixes).

    A rejected request returns (None, "rejected", [error message]).
    """
    ok, result = validate_request(text)
    if not ok:
        return None, "rejected", [result]

    kind = vague_kind(result)
    if kind:  # nothing to parse: a broad default, no LLM call needed
        profile, note = VAGUE_PROFILES[kind]
        return dict(profile), "default", [note]

    # Checked on the request text itself, so the LLM and offline paths both get it.
    conflict = [CONFLICT_NOTE] if has_conflicting_cues(result) else []

    if not offline and is_llm_available():
        try:
            profile, fixes = validate_profile(parse_with_llm(result, few_shot))
            if _has_no_preferences(profile):
                return dict(VAGUE_PROFILES["none"][0]), "llm", [POPULAR_NOTE]
            return profile, "llm", conflict + fixes
        except (LLMError, ValueError):
            pass  # fall through to the offline parser
    raw, notes = parse_offline_with_notes(result)
    profile, fixes = validate_profile(raw)
    if _has_no_preferences(profile):  # nothing usable was understood: fall back to popular songs
        return dict(VAGUE_PROFILES["none"][0]), "offline", notes + [POPULAR_NOTE]
    return profile, "offline", conflict + notes + fixes


if __name__ == "__main__":
    import sys

    force_offline = "--offline" in sys.argv[1:]
    for request in (
        "something chill to study to, no vocals",
        "high energy workout music",
        "sad songs for a rainy day",
    ):
        if force_offline:
            profile, fixes = validate_profile(parse_offline(request))
            source = "offline"
        else:
            profile, source, fixes = parse_request(request)
        print(f"Request: {request}")
        print(f"  profile: {profile}")
        print(f"  source:  {source}")
        print(f"  fixes:   {fixes}\n")
