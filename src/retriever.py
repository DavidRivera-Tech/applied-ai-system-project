"""Retrieval step of the RAG pipeline: pick candidate songs and matching guide notes."""

import re
from pathlib import Path
from typing import Dict, List, Tuple

from src.recommender import recommend_songs

GUIDE_PATH = Path(__file__).resolve().parent.parent / "data" / "genre_guide.md"


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
