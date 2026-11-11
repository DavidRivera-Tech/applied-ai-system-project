# 🎵 Music Recommender Simulation

## Original Project: Music Recommender Simulation (Module 3)

The original project was a content-based music recommender that scored 22 songs against a hand-written taste profile (genre, mood, energy, and acousticness), ranked them, and explained each score. It also offered optional ranking modes and a diversity penalty. It worked, but it had real limits that this project fixes:

- It couldn't understand plain-English requests; the taste profile had to be written by hand.
- It used brittle exact string matching, so "Pop" did not match "pop".
- It had no self-checking of its output.

## Project Summary

My version is called **GenreFirst 1.0**. It is a small content-based music recommender that reads a 22-song catalog and scores every song against one listener's taste: a favorite genre, a favorite mood, a target energy level, and whether they like acoustic sound. Genre match counts the most (+2.00), then how close the song's energy is to the target (up to 1.50), then mood (+1.00), then acoustic preference (up to 0.50). It sorts the songs by score and prints the top 5, with the reasons behind each score. It also supports optional extra rules, four ranking modes (`--mode`), an optional diversity re-rank (`--diversity`), and table output (`--table`). I tested it on six listener profiles, including three edge cases, plus a seventh profile that demonstrates the optional extra rules, to see where it works well and where genre-heavy scoring and a tiny catalog lead it astray.

---

## How The System Works

### How real-world recommenders work

Platforms like Spotify and YouTube predict what you'll enjoy next by combining two approaches. **Collaborative filtering** ignores what a song sounds like and looks at behavior across millions of users: if people who saved the same songs as you also love a track you haven't heard, it becomes a good bet for you. **Content-based filtering** looks at the attributes of the songs themselves (genre, mood, tempo, energy) and recommends songs similar to the ones you already like. Collaborative filtering finds surprising matches but fails on brand-new songs and users (the "cold start" problem), while content-based filtering works from day one and is easy to explain but can trap you in a bubble. Real systems blend both, using signals such as likes, skips, listening time, repeat plays, playlist adds, and song attributes like genre, mood, and tempo. Implicit signals like skips and listening time matter most because there is far more of them than explicit likes.

### Three separate pieces of this system

- **Input data (song features):** the catalog in `data/songs.csv`. Each song is described by its attributes and never changes based on who is listening.
- **User preferences (taste profile):** a small `UserProfile` describing what one listener wants right now: favorite genre, favorite mood, a target energy level, and whether they like acoustic sound.
- **Ranking and selection (scoring rule + ranking rule):**
  - The **scoring rule** judges one song against one user and returns a single number. For numeric features it rewards *closeness* to the user's target (for example `1 - abs(song_energy - target_energy)`), not simply higher or lower values.
  - The **ranking rule** takes every song's score, sorts the whole list, and returns the top results. It works at the list level, which is where later improvements like a diversity penalty (so one artist can't fill the top five) will go.

### What this simplified version prioritizes

This recommender is **content-based only**, since there is a song catalog and a taste profile but no crowd of other users. It prioritizes:

1. **Genre match:** the strongest signal of long-term taste, so it is worth the most points.
2. **Energy closeness:** rewards songs near the user's target energy, not just louder or quieter ones.
3. **Mood match:** what the listener wants to feel right now.

### Features used

**`Song` object** (every column in `data/songs.csv`):

- `id`
- `title`
- `artist`
- `genre`
- `mood`
- `energy` (0-1)
- `tempo_bpm`
- `valence` (0-1)
- `danceability` (0-1)
- `acousticness` (0-1)
- `popularity` (0-100)
- `release_decade`
- `mood_tags` (pipe-separated, e.g. `euphoric|uplifting`)
- `instrumentalness` (0-1)
- `speechiness` (0-1)
- `liveness` (0-1)

**`UserProfile` object:**

- `favorite_genre`
- `favorite_mood`
- `target_energy`
- `likes_acoustic`

### Algorithm Recipe

Each song gets a score by adding up these rules. The numbers are the default `balanced` weights:

| Rule | Points |
|---|---|
| Genre match | **+2.0** if `song.genre == favorite_genre`, otherwise 0 |
| Mood match | **+1.0** if `song.mood == favorite_mood`, otherwise 0 |
| Energy closeness | **1.5 × (1 − \|song energy − target energy\|)**, never below 0 |
| Acoustic preference | If `likes_acoustic`: **+0.5 × acousticness**. Otherwise: **+0.5 × (1 − acousticness)** |
| **Optional extra rules** | *Each one counts only if its key is in the user's preferences* |
| Tempo (`tempo_bpm`) | **0.5 × (1 − \|song BPM − target BPM\| / 60)**, never below 0 |
| Valence (`valence`) | **0.5 × (1 − \|song valence − target\|)**, never below 0 |
| Popularity (`popularity`) | **0.5 × (1 − \|song popularity − target\| / 100)**, never below 0 |
| Decade (`decade`) | **+0.5** if `song.release_decade` matches |
| Mood tags (`mood_tags`) | **+0.25** per shared tag, up to 3 tags |
| Instrumental (`instrumental`) | If true: **+0.5 × instrumentalness**. Otherwise: **+0.5 × (1 − instrumentalness)** |

The most a song can earn is **5.0** with the four core rules. If a listener supplies every optional key, the maximum is **8.25** (5.0 plus five optional rules at 0.5 each, plus 0.75 for three shared mood tags). The other ranking modes change these weights; see "Ranking modes" under Experiments You Tried.

Numeric features reward **closeness, not higher or lower values**. A song with energy 0.80 earns full energy points for a user targeting 0.80, and a song at 0.95 earns fewer, even though it is "more energetic." Likewise, a user who dislikes acoustic music earns points from songs with *low* acousticness, not from songs with high or low values in general.

**Data flow:**

```
INPUT                    PROCESS                               OUTPUT
-----                    -------                               ------
User preferences   -->   Load every song from songs.csv  -->   Sort songs by score
(genre, mood,            For each song:                        (highest first)
 target energy,            apply the scoring rules             Return the top k
 likes acoustic)           to get one score                    recommendations
```

### Expected Biases

- **Genre can dominate.** At +2.0 it is the largest single reward, so a song in the favorite genre can outrank a song that is a near-perfect mood and energy match but in a different genre. Great matches outside the user's genre get pushed down the list.
- **Thin genres give weak results.** Most genres in the catalog have only one song, and only pop, lofi, and jazz have more than one. A user whose favorite genre is, say, metal gets one genre bonus to hand out. After that song, the rest of the list is ranked only by mood, energy, and acousticness.
- **Exact string matching is brittle.** `indie pop` does not match `pop`, and a mood like `focused` does not match `chill`, even though a listener might enjoy both. Close matches get zero credit.
- **Some features are still ignored.** Tempo, valence, popularity, decade, mood tags, and instrumentalness are now optional rules, but they only count when the listener supplies them. Danceability, speechiness, and liveness are still unused, so two songs that feel very different can score the same.

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows
   ```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python -m src.main
```

### Command-line options

- `--mode {balanced,genre-boost,mood-first,energy-focused}`: choose how much each rule counts (default: `balanced`).
- `--list-modes`: print each ranking mode's name and description, then exit.
- `--diversity`: re-rank the results so one artist or genre can't fill the top spots (artist repeat -1.00, genre repeat -0.50). Off by default.
- `--table`: print each profile's results as a table, with one reason per line. Off by default.

The flags work together. For example:

```bash
python -m src.main --table --mode mood-first --diversity
```

### Table output

This is the actual output of `python -m src.main --table --diversity`, shown for the High-Energy Pop profile only:

```
Loaded songs: 22
Diversity re-rank: on (artist repeat -1.00, genre repeat -0.50)

PROFILE: High-Energy Pop
========================
Preferences: genre=pop, mood=happy, energy=0.8, likes_acoustic=False

+-----+-------------------+---------------+-----------+---------+-------------------------------------------------+
| #   | Title             | Artist        | Genre     | Score   | Why                                             |
+=====+===================+===============+===========+=========+=================================================+
| 1   | Sunrise City      | Neon Echo     | pop       | 4.88    | genre match (+2.00)                             |
|     |                   |               |           |         | mood match (+1.00)                              |
|     |                   |               |           |         | energy 0.82 vs target 0.80 (+1.47)              |
|     |                   |               |           |         | acousticness 0.18, prefers non-acoustic (+0.41) |
+-----+-------------------+---------------+-----------+---------+-------------------------------------------------+
| 2   | Gym Hero          | Max Pulse     | pop       | 3.28    | genre match (+2.00)                             |
|     |                   |               |           |         | energy 0.93 vs target 0.80 (+1.30)              |
|     |                   |               |           |         | acousticness 0.05, prefers non-acoustic (+0.47) |
|     |                   |               |           |         | genre repeat penalty (-0.50)                    |
+-----+-------------------+---------------+-----------+---------+-------------------------------------------------+
| 3   | Rooftop Lights    | Indigo Parade | indie pop | 2.77    | mood match (+1.00)                              |
|     |                   |               |           |         | energy 0.76 vs target 0.80 (+1.44)              |
|     |                   |               |           |         | acousticness 0.35, prefers non-acoustic (+0.33) |
+-----+-------------------+---------------+-----------+---------+-------------------------------------------------+
| 4   | Concrete Crown    | Kid Meridian  | hip-hop   | 1.91    | energy 0.78 vs target 0.80 (+1.47)              |
|     |                   |               |           |         | acousticness 0.12, prefers non-acoustic (+0.44) |
+-----+-------------------+---------------+-----------+---------+-------------------------------------------------+
| 5   | Fuego en la Calle | Los Soleros   | latin     | 1.84    | energy 0.86 vs target 0.80 (+1.41)              |
|     |                   |               |           |         | acousticness 0.15, prefers non-acoustic (+0.42) |
+-----+-------------------+---------------+-----------+---------+-------------------------------------------------+
```

With the diversity re-rank on, Afterglow Avenue (a second Neon Echo song, 3.72 without the re-rank) drops out of the top 5.

### Running Tests

Run the tests with:

```bash
pytest
```

The suite has 12 tests in `tests/test_recommender.py`: 2 starter tests for the `Recommender` class and 10 more that cover loading songs, energy scoring, ranking order, the ranking modes, the unknown-mode error, and the diversity re-rank.

---

## Sample Recommendation Output

This is the first of the seven profiles that `python -m src.main` runs (High-Energy Pop: pop / happy / energy 0.8 / not acoustic):

```
PROFILE: High-Energy Pop
========================
Preferences: genre=pop, mood=happy, energy=0.8, likes_acoustic=False

1. Sunrise City by Neon Echo  (score: 4.88)
     - genre match (+2.00)
     - mood match (+1.00)
     - energy 0.82 vs target 0.80 (+1.47)
     - acousticness 0.18, prefers non-acoustic (+0.41)

2. Gym Hero by Max Pulse  (score: 3.78)
     - genre match (+2.00)
     - energy 0.93 vs target 0.80 (+1.30)
     - acousticness 0.05, prefers non-acoustic (+0.47)

3. Afterglow Avenue by Neon Echo  (score: 3.72)
     - genre match (+2.00)
     - energy 0.68 vs target 0.80 (+1.32)
     - acousticness 0.20, prefers non-acoustic (+0.40)

4. Rooftop Lights by Indigo Parade  (score: 2.77)
     - mood match (+1.00)
     - energy 0.76 vs target 0.80 (+1.44)
     - acousticness 0.35, prefers non-acoustic (+0.33)

5. Concrete Crown by Kid Meridian  (score: 1.91)
     - energy 0.78 vs target 0.80 (+1.47)
     - acousticness 0.12, prefers non-acoustic (+0.44)
```

The results match what a pop/happy listener would expect: Sunrise City (4.88) is #1 because it is the only song to earn both the genre and mood bonuses (and its energy is almost on target), and the other two pop songs, Gym Hero (3.78) and Afterglow Avenue (3.72), come next. Rooftop Lights (2.77) got no genre points because "indie pop" does not exactly match "pop", which is the string-matching bias predicted in Expected Biases. With the +2.00 genre bonus it would have scored 4.77 and ranked #2, so a near-perfect match for this listener is pushed down to fourth. See [model_card.md](model_card.md) section 7 for the other five evaluation profiles. The seventh profile, Extended: Late-Night Focus, demonstrates the optional extra rules; run `python -m src.main` to see its output.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or demo video link here -->

---

## Experiments You Tried

### Weight shift: genre 2.0 → 1.0 and energy 1.5 → 3.0

**What I changed.** I halved the genre bonus and doubled the energy closeness weight, which raises the maximum possible score from 5.0 to 5.5 (1.0 + 1.0 + 3.0 + 0.5). I ran all six profiles, then restored the original weights.

**High-Energy Pop (pop, happy, energy 0.8, not acoustic)**

| Rank | Before (genre 2.0, energy 1.5) | Score | After (genre 1.0, energy 3.0) | Score |
|---|---|---|---|---|
| 1 | Sunrise City | 4.88 | Sunrise City | 5.35 |
| 2 | Gym Hero | 3.78 | Rooftop Lights | 4.21 |
| 3 | Afterglow Avenue | 3.72 | Gym Hero | 4.08 |
| 4 | Rooftop Lights | 2.77 | Afterglow Avenue | 4.04 |
| 5 | Concrete Crown | 1.91 | Concrete Crown | 3.38 |

**Edge Case: Classical but High Energy (classical, melancholic, energy 0.9, likes acoustic)**

| Rank | Before (genre 2.0, energy 1.5) | Score | After (genre 1.0, energy 3.0) | Score |
|---|---|---|---|---|
| 1 | Nocturne in Blue Hour | 2.86 | Storm Runner | 3.02 |
| 2 | Crossroads Lament | 2.17 | Crossroads Lament | 3.01 |
| 3 | Storm Runner | 1.53 | Fuego en la Calle | 2.96 |
| 4 | Fuego en la Calle | 1.51 | Gym Hero | 2.94 |
| 5 | Gym Hero | 1.48 | Pulse Theory | 2.90 |

**More accurate, or just different?** Mostly different, with one clear improvement. For the classical profile, the old #1 was Nocturne in Blue Hour, a 0.15-energy song for a listener who asked for 0.9, and it dropped out of the top 5 entirely. For the pop profile, the happy indie pop song Rooftop Lights moved ahead of two actual pop songs, which is defensible but not obviously better.

**Trade-off.** Doubling the energy weight fixed the classical problem, but it made the system behave more like a plain energy sort. In the classical results, the scores are bunched between 2.90 and 3.02, so tiny energy differences decide the order, and the one classical song is gone. A listener who truly wants classical music would now be poorly served.

**Weights reverted.** I restored genre 2.0 and energy 1.5 after the experiment, and `git diff src/recommender.py` showed no changes. All the other results in this README and the model card use the original weights.

### Ranking modes

The weight-shift experiment above was a one-off edit. I later turned it into switchable ranking modes: each mode is a small class that only holds a table of weights. Run `python -m src.main --list-modes` to see them, or `python -m src.main --mode energy-focused` to switch.

| Mode | Weights changed from balanced |
|---|---|
| balanced (default) | none: genre 2.0, mood 1.0, energy 1.5 |
| genre-boost | genre 4.0, mood 0.5, energy 1.0 |
| mood-first | mood 3.0, genre 1.0 |
| energy-focused | energy 4.0, genre 0.5, mood 0.5 |

Top 3 results for the Classical but High Energy listener (classical, melancholic, energy 0.9, likes acoustic):

| Mode | #1 | #2 | #3 |
|---|---|---|---|
| balanced | Nocturne in Blue Hour (2.86) | Crossroads Lament (2.17) | Storm Runner (1.53) |
| genre-boost | Nocturne in Blue Hour (4.74) | Crossroads Lament (1.39) | Storm Runner (1.04) |
| mood-first | Crossroads Lament (4.17) | Nocturne in Blue Hour (1.86) | Storm Runner (1.53) |
| energy-focused | Storm Runner (4.01) | Fuego en la Calle (3.92) | Gym Hero (3.90) |

The same listener gets three different #1 songs across the four modes. Genre-boost keeps Nocturne in Blue Hour first and widens its lead, which makes the genre-dominance problem worse. Mood-first puts the blues song Crossroads Lament first, because it is the only melancholic song. Energy-focused puts Storm Runner first, the song closest to the 0.9 energy the listener asked for. That matches the weight-shift experiment above, where Storm Runner also took #1 once energy counted for more than genre. Scores are not normalized, so they can't be compared between modes.

---

## Limitations and Risks

- **Genre dominates a tiny catalog.** The +2.00 genre bonus is larger than the most energy closeness can add (1.50), and 14 of the 17 genres have only one song. A 0.15-energy classical song ranked #1 (2.86) for a listener who wanted energy 0.9.
- **Exact, case-sensitive matching.** "Pop" does not match "pop". The Capitalized Input profile dropped Sunrise City from 4.88 to 1.47 with no warning.
- **Sparse moods.** There is no "sad" mood, and 9 of the 15 moods appear on just one song.
- **No input validation.** Energy closeness is now clamped at 0, so a target like 2.0 can't give negative points, but out-of-range targets still aren't rejected.
- **Artist repetition.** This happens by default: Neon Echo holds #1 and #3 in the High-Energy Pop results, because nothing limits one artist. `--diversity` fixes it, at a cost to relevance (see model card section 6).

See the [model card](model_card.md) (sections 6 and 7) for more detail and the full numbers.

---

## Reflection

Read and complete `model_card.md`:

[**Model Card**](model_card.md)

A recommender turns data into predictions by describing things as numbers and labels, then measuring how well each one fits. In my version, each song has a genre, a mood, an energy level, and an acousticness value. The listener has four matching preferences. A scoring rule adds up points for each match, with closeness counting for energy, and then the songs are sorted by score. Real systems like Spotify do the same thing in spirit, but they learn from millions of plays and skips instead of rules I wrote by hand. What surprised me is how much a handful of simple rules can feel like a real recommendation.

Bias shows up in the choices, not in some hidden part of the code. I decided genre is worth +2.00, which is more than energy can ever add, so a 0.15-energy classical song ranked #1 for someone who wanted energy 0.9. The catalog matters too: 14 of the 17 genres have one song, so most listeners get a one-song list after the genre match. Even the matching rule is a choice. Typing "Pop" instead of "pop" dropped Sunrise City from 4.88 to 1.47 with no warning. The result is that listeners whose taste fits the catalog get good lists, and everyone else gets weaker ones without being told. Bigger systems have the same shape, just with more data and less visible choices.
