import csv
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool

def _profile_to_prefs(user: UserProfile) -> Dict:
    """Converts a UserProfile into the dict format score_song expects."""
    return {
        "genre": user.favorite_genre,
        "mood": user.favorite_mood,
        "energy": user.target_energy,
        "likes_acoustic": user.likes_acoustic,
    }

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Returns the k songs that best match the user, highest score first."""
        user_prefs = _profile_to_prefs(user)
        ranked = sorted(
            self.songs,
            key=lambda song: score_song(user_prefs, asdict(song))[0],
            reverse=True,
        )
        return ranked[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Returns the scoring reasons for a song as one semicolon-separated string."""
        _, reasons = score_song(_profile_to_prefs(user), asdict(song))
        return "; ".join(reasons)

_SONG_CACHE: Dict[str, List[Dict]] = {}


def load_songs(csv_path: str, verbose: bool = False) -> List[Dict]:
    """Loads songs from a CSV file into a list of dicts with numeric fields converted.

    The catalog is read once per path and reused. `verbose` prints the count on the first read.
    """
    cache_key = str(Path(csv_path).resolve())
    if cache_key in _SONG_CACHE:
        return list(_SONG_CACHE[cache_key])
    int_fields = ("id", "popularity", "release_decade")
    float_fields = (
        "energy",
        "tempo_bpm",
        "valence",
        "danceability",
        "acousticness",
        "instrumentalness",
        "speechiness",
        "liveness",
    )

    songs: List[Dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            song = dict(row)
            for field in int_fields:
                song[field] = int(row[field])
            for field in float_fields:
                song[field] = float(row[field])
            song["mood_tags"] = row["mood_tags"].split("|")
            songs.append(song)

    _SONG_CACHE[cache_key] = songs
    if verbose:
        print(f"Loaded songs: {len(songs)}")
    return list(songs)

class ScoringStrategy:
    """A ranking mode: a name, a one-line description, and a table of weights."""
    name = "balanced"
    description = "Default weights: genre +2.0, mood +1.0, energy up to 1.5."
    weights = {
        "genre": 2.0,
        "mood": 1.0,
        "energy": 1.5,
        "acoustic": 0.5,
        "tempo": 0.5,
        "valence": 0.5,
        "popularity": 0.5,
        "decade": 0.5,
        "mood_tag": 0.25,  # per shared tag, max 3 tags
        "instrumental": 0.5,
    }


class GenreBoostStrategy(ScoringStrategy):
    name = "genre-boost"
    description = "Genre counts double (4.0); mood and energy count less."
    weights = {**ScoringStrategy.weights, "genre": 4.0, "mood": 0.5, "energy": 1.0}


class MoodFirstStrategy(ScoringStrategy):
    name = "mood-first"
    description = "Mood counts triple (3.0); genre drops to 1.0."
    weights = {**ScoringStrategy.weights, "mood": 3.0, "genre": 1.0}


class EnergyFocusedStrategy(ScoringStrategy):
    name = "energy-focused"
    description = "Energy closeness counts most (4.0); genre and mood count 0.5."
    weights = {**ScoringStrategy.weights, "energy": 4.0, "genre": 0.5, "mood": 0.5}


STRATEGIES: Dict[str, ScoringStrategy] = {
    s.name: s
    for s in (ScoringStrategy(), GenreBoostStrategy(), MoodFirstStrategy(), EnergyFocusedStrategy())
}


def get_strategy(name: str) -> ScoringStrategy:
    """Returns the ranking mode with this name, or raises ValueError if it does not exist."""
    if name not in STRATEGIES:
        raise ValueError(f"Unknown mode '{name}'. Choose from: {', '.join(STRATEGIES)}")
    return STRATEGIES[name]


def score_song(user_prefs: Dict, song: Dict, mode: str = "balanced") -> Tuple[float, List[str]]:
    """Scores one song against user preferences using a ranking mode; returns (score, reasons)."""
    w = get_strategy(mode).weights
    score = 0.0
    reasons: List[str] = []

    if "genre" in user_prefs and song["genre"] == user_prefs["genre"]:
        score += w["genre"]
        reasons.append(f"genre match (+{w['genre']:.2f})")

    if "mood" in user_prefs and song["mood"] == user_prefs["mood"]:
        score += w["mood"]
        reasons.append(f"mood match (+{w['mood']:.2f})")

    if "energy" in user_prefs:
        target = user_prefs["energy"]
        points = w["energy"] * max(0.0, 1 - abs(song["energy"] - target))
        score += points
        reasons.append(f"energy {song['energy']:.2f} vs target {target:.2f} (+{points:.2f})")

    if "likes_acoustic" in user_prefs:
        if user_prefs["likes_acoustic"]:
            points = w["acoustic"] * song["acousticness"]
            reasons.append(f"acousticness {song['acousticness']:.2f}, likes acoustic (+{points:.2f})")
        else:
            points = w["acoustic"] * (1 - song["acousticness"])
            reasons.append(f"acousticness {song['acousticness']:.2f}, prefers non-acoustic (+{points:.2f})")
        score += points

    if "tempo_bpm" in user_prefs:
        target = user_prefs["tempo_bpm"]
        points = w["tempo"] * max(0.0, 1 - abs(song["tempo_bpm"] - target) / 60)
        score += points
        reasons.append(f"tempo {song['tempo_bpm']:.0f} BPM vs target {target:.0f} (+{points:.2f})")

    if "valence" in user_prefs:
        target = user_prefs["valence"]
        points = w["valence"] * max(0.0, 1 - abs(song["valence"] - target))
        score += points
        reasons.append(f"valence {song['valence']:.2f} vs target {target:.2f} (+{points:.2f})")

    if "popularity" in user_prefs:
        target = user_prefs["popularity"]
        points = w["popularity"] * max(0.0, 1 - abs(song["popularity"] - target) / 100)
        score += points
        reasons.append(f"popularity {song['popularity']} vs target {target:.0f} (+{points:.2f})")

    if "decade" in user_prefs and song["release_decade"] == user_prefs["decade"]:
        score += w["decade"]
        reasons.append(f"decade match, {song['release_decade']}s (+{w['decade']:.2f})")

    if "mood_tags" in user_prefs:
        wanted = user_prefs["mood_tags"]
        if isinstance(wanted, str):
            wanted = wanted.split("|")
        shared = [tag for tag in wanted if tag in song["mood_tags"]][:3]
        points = w["mood_tag"] * len(shared)
        score += points
        if shared:
            reasons.append(f"shared mood tags {', '.join(shared)} (+{points:.2f})")

    if "instrumental" in user_prefs:
        if user_prefs["instrumental"]:
            points = w["instrumental"] * song["instrumentalness"]
            reasons.append(f"instrumentalness {song['instrumentalness']:.2f}, wants instrumental (+{points:.2f})")
        else:
            points = w["instrumental"] * (1 - song["instrumentalness"])
            reasons.append(f"instrumentalness {song['instrumentalness']:.2f}, wants vocals (+{points:.2f})")
        score += points

    return score, reasons

def recommend_songs(
    user_prefs: Dict,
    songs: List[Dict],
    k: int = 5,
    mode: str = "balanced",
    diversity: bool = False,
) -> List[Tuple[Dict, float, str]]:
    """Scores every song in a ranking mode and returns the top k as (song, score, explanation); diversity=True re-ranks to avoid repeat artists and genres."""
    get_strategy(mode)  # fail early on an unknown mode
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song, mode)
        scored.append((song, score, reasons))

    scored.sort(key=lambda item: item[1], reverse=True)

    if not diversity:
        return [(song, score, "; ".join(reasons)) for song, score, reasons in scored[:k]]

    # Fill the list one slot at a time, charging each candidate for repeats already picked.
    picked: List[Tuple[Dict, float, str]] = []
    remaining = scored[:]
    while remaining and len(picked) < k:
        best = None
        for index, (song, score, reasons) in enumerate(remaining):
            artist_penalty = 1.0 * sum(1 for p, _, _ in picked if p["artist"] == song["artist"])
            genre_penalty = 0.5 * sum(1 for p, _, _ in picked if p["genre"] == song["genre"])
            adjusted = score - artist_penalty - genre_penalty
            if best is None or adjusted > best[0]:
                best = (adjusted, index, artist_penalty, genre_penalty)

        adjusted, index, artist_penalty, genre_penalty = best
        song, _, reasons = remaining.pop(index)
        reasons = list(reasons)
        if artist_penalty:
            reasons.append(f"artist repeat penalty (-{artist_penalty:.2f})")
        if genre_penalty:
            reasons.append(f"genre repeat penalty (-{genre_penalty:.2f})")
        picked.append((song, adjusted, "; ".join(reasons)))

    return picked
