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


def validate_request(text) -> Tuple[bool, str]:
    """Input guardrail. Returns (ok, cleaned_text) or (False, error_message)."""
    if not isinstance(text, str):
        return False, "Request must be text."
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return False, "Request is empty. Describe the music you want."
    if len(cleaned) > MAX_LEN:
        return False, f"Request is too long ({len(cleaned)} characters; max {MAX_LEN})."
    known = MUSIC_WORDS | set(VOCAB["genres"]) | set(VOCAB["moods"]) | set(VOCAB["mood_tags"])
    if not (_words(cleaned) & known):
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
LOW_ENERGY = {"chill": 0.35, "study": 0.35, "studying": 0.35, "focus": 0.4, "relax": 0.3,
              "relaxing": 0.3, "sleep": 0.15, "calm": 0.25, "peaceful": 0.25, "sad": 0.3,
              "rainy": 0.3, "mellow": 0.3, "soft": 0.25, "slow": 0.25, "cozy": 0.3}
HIGH_ENERGY = {"workout": 0.9, "gym": 0.9, "running": 0.85, "run": 0.85, "party": 0.85,
               "hype": 0.9, "intense": 0.9, "pump": 0.9, "energetic": 0.85, "upbeat": 0.8,
               "loud": 0.9, "fast": 0.85, "heavy": 0.9, "dance": 0.8}


def parse_offline(text: str) -> Dict:
    """Rule-based keyword parser. The fallback and the baseline."""
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

    energies = [v for k, v in HIGH_ENERGY.items() if k in words] or [
        v for k, v in LOW_ENERGY.items() if k in words
    ]
    profile["energy"] = round(sum(energies) / len(energies), 2) if energies else 0.5

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
    return profile


# ---------------------------------------------------------------- parse_with_llm

FEW_SHOT = """Examples:
Request: "upbeat pop for a road trip"
{"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": false}

Request: "mellow acoustic evening, nothing with vocals"
{"genre": "folk", "mood": "relaxed", "energy": 0.25, "likes_acoustic": true, "instrumental": true}

Request: "aggressive loud music to lift weights to"
{"genre": "metal", "mood": "aggressive", "energy": 0.95, "tempo_bpm": 160, "mood_tags": ["driving"]}
"""


def build_prompt(text: str, few_shot: bool = True) -> str:
    prompt = (
        "Convert the music request into a JSON taste profile. Reply with ONLY a JSON object, "
        "no prose and no code fences.\n"
        'Keys: "genre" (string), "mood" (string), "energy" (number 0-1), and optionally '
        '"likes_acoustic" (bool), "tempo_bpm" (number), "instrumental" (bool), "mood_tags" (list of strings).\n'
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

def parse_request(text: str, few_shot: bool = True, offline: bool = False) -> Tuple[Optional[Dict], str, List[str]]:
    """Validate, try the LLM, fall back to offline. Returns (profile, source, fixes).

    A rejected request returns (None, "rejected", [error message]).
    """
    ok, result = validate_request(text)
    if not ok:
        return None, "rejected", [result]

    if not offline and is_llm_available():
        try:
            profile, fixes = validate_profile(parse_with_llm(result, few_shot))
            return profile, "llm", fixes
        except (LLMError, ValueError):
            pass  # fall through to the offline parser
    profile, fixes = validate_profile(parse_offline(result))
    return profile, "offline", fixes


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
