# Phase 3: Live Gemini Runs

These are real runs of `python -m src.assistant` against the live Gemini API, captured on Nov 11, 2026. They were made before the trace field `attempt` on `generate` steps was renamed to `api_try`, so the trace lines below still use the old name. Nothing here was re-run or edited. The only thing left out of the CLI output is the `Loaded songs: 22` line printed by the song loader, which was filtered out when the runs were captured.

## Run 1: "something chill to study to, no vocals"

```
Request: something chill to study to, no vocals

Profile (llm): {'genre': 'lofi', 'mood': 'chill', 'energy': 0.3, 'instrumental': True, 'mood_tags': ['focused', 'calm']}

Retrieved songs:
  1. Library Rain - Paper Lanterns [lofi] score 5.12
       genre match (+2.00); mood match (+1.00); energy 0.35 vs target 0.30 (+1.42); shared mood tags calm (+0.25); instrumentalness 0.88, wants instrumental (+0.44)
  2. Midnight Coding - LoRoom [lofi] score 5.00
       genre match (+2.00); mood match (+1.00); energy 0.42 vs target 0.30 (+1.32); shared mood tags calm (+0.25); instrumentalness 0.85, wants instrumental (+0.42)
  3. Focus Flow - LoRoom [lofi] score 4.30
       genre match (+2.00); energy 0.40 vs target 0.30 (+1.35); shared mood tags focused, calm (+0.50); instrumentalness 0.90, wants instrumental (+0.45)
  4. Spacewalk Thoughts - Orbit Bloom [ambient] score 2.94
       mood match (+1.00); energy 0.28 vs target 0.30 (+1.47); instrumentalness 0.94, wants instrumental (+0.47)
  5. Nocturne in Blue Hour - Elena Vasquez [classical] score 1.75
       energy 0.15 vs target 0.30 (+1.27); instrumentalness 0.96, wants instrumental (+0.48)

Guide notes used: lofi, chill, ambient, classical

Answer (llm):
  * Library Rain: Library Rain features mellow lo-fi beats perfect for creating a cozy, vocal-free study environment.
  * Midnight Coding: Midnight Coding provides a calm, steady rhythm to help you stay effortlessly relaxed while working.
  * Focus Flow: Focus Flow offers a smooth, purely instrumental groove designed for deep concentration.

  Here are three chill, vocal-free tracks perfectly tailored to help you focus while studying!

Verification:
  [PASS] titles_match_retrieved: all picks were retrieved
  [PASS] no_duplicate_picks: no duplicates
  [PASS] summary_names_only_retrieved: summary is clean

Confidence: 0.97 (top score 5.12 of a possible 5.50; request parsed by llm; verification passed on the first try.)
```

## Run 2: "sad songs for a rainy day"

```
Request: sad songs for a rainy day

Profile (llm): {'genre': None, 'mood': 'melancholic', 'energy': 0.2, 'likes_acoustic': True, 'mood_tags': ['melancholic', 'sorrowful']}

Retrieved songs:
  1. Crossroads Lament - Delta Jack [blues] score 2.69
       mood match (+1.00); energy 0.46 vs target 0.20 (+1.11); acousticness 0.66, likes acoustic (+0.33); shared mood tags sorrowful (+0.25)
  2. Nocturne in Blue Hour - Elena Vasquez [classical] score 2.16
       energy 0.15 vs target 0.20 (+1.42); acousticness 0.97, likes acoustic (+0.48); shared mood tags melancholic (+0.25)
  3. Spacewalk Thoughts - Orbit Bloom [ambient] score 1.84
       energy 0.28 vs target 0.20 (+1.38); acousticness 0.92, likes acoustic (+0.46)
  4. Willow Road - Maple & Pine [folk] score 1.76
       energy 0.33 vs target 0.20 (+1.30); acousticness 0.91, likes acoustic (+0.46)
  5. Library Rain - Paper Lanterns [lofi] score 1.71
       energy 0.35 vs target 0.20 (+1.28); acousticness 0.86, likes acoustic (+0.43)

Guide notes used: melancholic, blues, classical, ambient, folk, lofi

Answer (llm):
  * Crossroads Lament: This sorrowful blues track features soulful guitar work perfect for quiet reflection.
  * Nocturne in Blue Hour: Its gentle classical piano creates a deeply melancholic atmosphere.
  * Library Rain: Mellow lofi keys add a cozy, relaxing backdrop for watching the rain.

  Here are three cozy, melancholic tracks to keep you company on a rainy day.

Verification:
  [PASS] titles_match_retrieved: all picks were retrieved
  [PASS] no_duplicate_picks: no duplicates
  [PASS] summary_names_only_retrieved: summary is clean

Confidence: 0.73 (top score 2.69 of a possible 3.50; request parsed by llm; verification passed only after a retry.)
```

## Guardrail catch

In Run 2, Gemini's first answer wrote its picks as `"Crossroads Lament" by Delta Jack` instead of the exact title `Crossroads Lament`. The `titles_match_retrieved` check failed, and the retry prompt told Gemini exactly which titles were not an exact match. The second answer passed all three checks, so the final verification above shows PASS, and confidence came out at 0.73 for this run versus 0.97 for Run 1. Part of that gap is the retry, which lowers the verification term from 1.0 to 0.5 (a 0.15 drop); the rest comes from Run 2's weaker top retrieval score (2.69 of 3.50 versus 5.12 of 5.50). The two runs also used different requests.

## Trace lines

The last two lines of `logs/traces.jsonl`, one per run, pretty-printed with no values changed. The second `generate` step in Run 2 shows `"attempt": 1` because that field counted API tries, not overall attempts; this is why it was renamed to `api_try`.

```json
{
  "timestamp": "2026-11-11T21:43:01.621127+00:00",
  "request": "something chill to study to, no vocals",
  "steps": [
    {
      "step": "validate",
      "ok": true,
      "ms": 0.1
    },
    {
      "step": "parse",
      "ok": true,
      "ms": 5007.2,
      "source": "llm",
      "fixes": [],
      "profile": {
        "genre": "lofi",
        "mood": "chill",
        "energy": 0.3,
        "instrumental": true,
        "mood_tags": [
          "focused",
          "calm"
        ]
      }
    },
    {
      "step": "retrieve",
      "ok": true,
      "ms": 4.0,
      "titles": [
        "Library Rain",
        "Midnight Coding",
        "Focus Flow",
        "Spacewalk Thoughts",
        "Nocturne in Blue Hour"
      ],
      "guide_notes": [
        "lofi",
        "chill",
        "ambient",
        "classical"
      ]
    },
    {
      "step": "generate",
      "ok": true,
      "ms": 14416.3,
      "attempt": 1
    },
    {
      "step": "verify",
      "ok": true,
      "ms": 5.0,
      "attempt": 1,
      "checks": {
        "titles_match_retrieved": true,
        "no_duplicate_picks": true,
        "summary_names_only_retrieved": true
      },
      "problems": []
    }
  ],
  "errors": [],
  "answer_source": "llm",
  "confidence": 0.97
}

{
  "timestamp": "2026-11-11T21:43:49.166582+00:00",
  "request": "sad songs for a rainy day",
  "steps": [
    {
      "step": "validate",
      "ok": true,
      "ms": 0.3
    },
    {
      "step": "parse",
      "ok": true,
      "ms": 7191.9,
      "source": "llm",
      "fixes": [],
      "profile": {
        "genre": null,
        "mood": "melancholic",
        "energy": 0.2,
        "likes_acoustic": true,
        "mood_tags": [
          "melancholic",
          "sorrowful"
        ]
      }
    },
    {
      "step": "retrieve",
      "ok": true,
      "ms": 3.9,
      "titles": [
        "Crossroads Lament",
        "Nocturne in Blue Hour",
        "Spacewalk Thoughts",
        "Willow Road",
        "Library Rain"
      ],
      "guide_notes": [
        "melancholic",
        "blues",
        "classical",
        "ambient",
        "folk",
        "lofi"
      ]
    },
    {
      "step": "generate",
      "ok": true,
      "ms": 13741.7,
      "attempt": 1
    },
    {
      "step": "verify",
      "ok": false,
      "ms": 2.9,
      "attempt": 1,
      "checks": {
        "titles_match_retrieved": false,
        "no_duplicate_picks": true,
        "summary_names_only_retrieved": true
      },
      "problems": [
        "titles_match_retrieved: not retrieved: ['\"Crossroads Lament\" by Delta Jack', '\"Nocturne in Blue Hour\" by Elena Vasquez', '\"Library Rain\" by Paper Lanterns']"
      ]
    },
    {
      "step": "retry",
      "ok": true,
      "ms": 0.0,
      "reason": "titles_match_retrieved: not retrieved: ['\"Crossroads Lament\" by Delta Jack', '\"Nocturne in Blue Hour\" by Elena Vasquez', '\"Library Rain\" by Paper Lanterns']"
    },
    {
      "step": "generate",
      "ok": true,
      "ms": 25020.3,
      "attempt": 1
    },
    {
      "step": "verify",
      "ok": true,
      "ms": 0.5,
      "attempt": 2,
      "checks": {
        "titles_match_retrieved": true,
        "no_duplicate_picks": true,
        "summary_names_only_retrieved": true
      },
      "problems": []
    }
  ],
  "errors": [],
  "answer_source": "llm",
  "confidence": 0.73
}
```
