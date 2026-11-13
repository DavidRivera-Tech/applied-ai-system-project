"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs
"""

import argparse

from src.recommender import STRATEGIES, get_strategy, load_songs, recommend_songs


PROFILES = {
    "High-Energy Pop": {
        "genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False,
    },
    "Chill Lofi": {
        "genre": "lofi", "mood": "chill", "energy": 0.35, "likes_acoustic": True,
    },
    "Deep Intense Rock": {
        "genre": "rock", "mood": "intense", "energy": 0.92, "likes_acoustic": False,
    },
    "Edge Case: Classical but High Energy": {
        "genre": "classical", "mood": "melancholic", "energy": 0.9, "likes_acoustic": True,
    },
    "Edge Case: Genre Not in Catalog": {
        "genre": "k-pop", "mood": "happy", "energy": 0.75,
    },
    "Edge Case: Capitalized Input": {
        "genre": "Pop", "mood": "Happy", "energy": 0.8,
    },
    "Extended: Late-Night Focus": {
        "genre": "lofi", "mood": "focused", "energy": 0.4, "likes_acoustic": True,
        "tempo_bpm": 78, "valence": 0.55, "instrumental": True,
        "mood_tags": ["focused", "calm"], "decade": 2020,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Music Recommender Simulation")
    parser.add_argument(
        "--mode",
        choices=list(STRATEGIES),
        default="balanced",
        help="ranking mode (default: balanced)",
    )
    parser.add_argument(
        "--list-modes",
        action="store_true",
        help="print each ranking mode's name and description, then exit",
    )
    parser.add_argument(
        "--diversity",
        action="store_true",
        help="re-rank so the same artist and genre don't fill the top results (off by default)",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="print each profile's results as a table (off by default)",
    )
    args = parser.parse_args()

    if args.table:
        from tabulate import tabulate  # imported here so the default output needs no extra install

    if args.list_modes:
        for strategy in STRATEGIES.values():
            print(f"{strategy.name}: {strategy.description}")
        return

    songs = load_songs("data/songs.csv", verbose=True)
    if args.mode != "balanced":
        print(f"Mode: {args.mode} - {get_strategy(args.mode).description}")
    if args.diversity:
        print("Diversity re-rank: on (artist repeat -1.00, genre repeat -0.50)")

    for name, user_prefs in PROFILES.items():
        recommendations = recommend_songs(
            user_prefs, songs, k=5, mode=args.mode, diversity=args.diversity
        )

        profile = ", ".join(f"{key}={value}" for key, value in user_prefs.items())
        header = f"PROFILE: {name}"
        print()
        print(header)
        print("=" * len(header))
        print(f"Preferences: {profile}")

        if args.table:
            rows = [
                [
                    rank,
                    song["title"],
                    song["artist"],
                    song["genre"],
                    f"{score:.2f}",
                    "\n".join(explanation.split("; ")),
                ]
                for rank, (song, score, explanation) in enumerate(recommendations, start=1)
            ]
            print()
            print(
                tabulate(
                    rows,
                    headers=["#", "Title", "Artist", "Genre", "Score", "Why"],
                    tablefmt="grid",
                    disable_numparse=True,
                )
            )
        else:
            for rank, (song, score, explanation) in enumerate(recommendations, start=1):
                print(f"\n{rank}. {song['title']} by {song['artist']}  (score: {score:.2f})")
                for reason in explanation.split("; "):
                    print(f"     - {reason}")
        print()


if __name__ == "__main__":
    main()
