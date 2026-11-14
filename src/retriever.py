"""Retrieval step of the RAG pipeline: pick candidate songs and matching guide notes."""

import re
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Tuple

from src.recommender import recommend_songs

GUIDE_PATH = Path(__file__).resolve().parent.parent / "data" / "genre_guide.md"


def mood_valence_target(mood: str, songs: List[Dict]) -> Optional[Dict]:
    """Average valence of the catalog songs with this mood, computed from the data (None if no song has it)."""
    values = [s["valence"] for s in songs if s["mood"] == mood]
    if not values:
        return None
    return {"mood": mood, "valence": round(mean(values), 3), "songs": len(values)}


def add_mood_valence(profile: Dict, songs: List[Dict]) -> Tuple[Dict, Optional[Dict]]:
    """If the profile has a mood and no valence, add a target valence derived from that mood's catalog songs.

    Returns (profile, hint) where hint describes what was added, or None if nothing was added.
    """
    if not profile.get("mood") or "valence" in profile:
        return profile, None
    hint = mood_valence_target(profile["mood"], songs)
    if hint is None:
        return profile, None
    return dict(profile, valence=hint["valence"]), hint


def load_guide(path: Path = GUIDE_PATH) -> Dict[str, str]:
    """Split the guide into {heading: text} using the '## ' headings."""
    text = Path(path).read_text(encoding="utf-8")
    sections: Dict[str, str] = {}
    for block in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        sections[heading.strip().lower()] = " ".join(body.split())
    return sections


def retrieve_songs(
    profile: Dict, songs: List[Dict], k: int = 5, mode: str = "balanced", diversity: bool = False
) -> List[Tuple[Dict, float, str]]:
    """Top-k songs as (song, score, reasons) via recommend_songs."""
    return recommend_songs(profile, songs, k=k, mode=mode, diversity=diversity)


def retrieve_guide_notes(profile: Dict, retrieved_songs: List[Tuple[Dict, float, str]]) -> Dict[str, str]:
    """Guide sections for the requested genre/mood and the genres of the retrieved songs."""
    guide = load_guide()
    wanted = [profile.get("genre"), profile.get("mood")]
    wanted += [song["genre"] for song, _, _ in retrieved_songs]
    notes: Dict[str, str] = {}
    for key in wanted:
        if key and key.lower() in guide and key.lower() not in notes:
            notes[key.lower()] = guide[key.lower()]
    return notes
