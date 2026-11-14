# AI Interactions: AIMA

## Purpose

This file shows how the agent works step by step. It has real traces from runs, the key prompts, and the design decisions I made while building it with AI help. For my overall reflection on working with AI, see the [AI collaboration section of the model card](model_card.md#ai-collaboration).

## Agent workflow

This is what `run()` in [src/assistant.py](src/assistant.py) does for each request. The diagram is in [diagrams/architecture.mmd](diagrams/architecture.mmd). Steps marked **Decision** are where the agent picks a path.

1. **Input guardrail.** `validate_request` rejects empty text, text over 500 characters, and text with no music words. Decision: a rejected request stops here with an error message and no further steps except logging.
2. **Vague-request check.** `parse_request` calls `vague_kind` first. Decision: a general request such as "something good" gets a broad default profile and a plain-English note, with no Gemini call. A positive request defaults to mood happy, a negative one to melancholic, and no clue at all ranks by popularity.
3. **Parse.** Decision: if offline mode is off and a Gemini key is available, `parse_with_llm` runs the few-shot prompt. If Gemini fails or returns bad JSON, the offline rule-based parser takes over. The trace records the source as `llm`, `offline`, or `default`.
4. **Validate the profile.** `validate_profile` snaps values to the allowed vocabulary and drops unknown keys. It records every change in `fixes`. The parse step also adds the bittersweet and conflicting-cues notes.
5. **Retrieve.** `add_mood_valence` adds a valence target for the mood. `retrieve_songs` scores the 60-song catalog and returns the top 5. `retrieve_guide_notes` pulls the matching genre and mood notes from the guide.
6. **Generate.** Decision: with offline mode off and a key available, `_generate_verified` builds the answer prompt and calls Gemini. `_call_llm` retries once if the error is transient (a timeout, 429, or 5xx). Otherwise the agent skips to step 9.
7. **Verify.** `verify_answer` runs 4 checks: `titles_match_retrieved`, `no_duplicate_picks`, `text_names_only_retrieved`, and `correct_pick_count`.
8. **Retry with feedback.** Decision: if any check fails on the first attempt, the agent sends the problems back to Gemini and generates once more. If the second answer also fails, the answer is dropped.
9. **Template fallback.** Decision: if there is no answer by now (offline mode, no key, an API failure, or two failed verifications), `template_answer` builds one from the top 3 songs. The same 4 checks run on it.
10. **Confidence.** `compute_confidence` combines match strength (50%), parse source (20%), and verification (30%). A vague request caps it at 0.5, and conflicting cues subtract 0.2.
11. **Trace logging.** `Trace.write` appends one JSON line to `logs/traces.jsonl`. This also happens for a rejected request.

## Agent traces

### Trace 1: a wrong title format, caught and fixed by a retry

This is a live Gemini run from Nov 11 for "sad songs for a rainy day". The full capture is in [phase3_live_runs.md](docs/evidence/phase3_live_runs.md). The first block is the end of what the user saw after the retry.

```
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

This is the trace line for the same run. The `...` marks where I trimmed the `validate`, `parse`, `retrieve`, and first `generate` steps.

```json
{
  "timestamp": "2026-11-11T21:43:49.166582+00:00",
  "request": "sad songs for a rainy day",
    ...
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

This shows the whole safety loop. Gemini first wrote its picks as `"Crossroads Lament" by Delta Jack`. That is a natural way to write it, but it is not an exact catalog title. `titles_match_retrieved` failed, the `retry` step recorded the exact problem, and the second answer passed. Confidence came out at 0.73 because verification only passed after a retry. I captured this on the 22-song version when the guardrail had 3 checks. It has 4 now. The `"attempt": 1` on the second `generate` step is the old name for what is now `api_try`.

### Trace 2: a rejected request

This one takes a different path. It comes from [sample_traces.md](docs/evidence/sample_traces.md), a live evaluation run from 2026-11-13. The empty request never reaches retrieval or Gemini.

```json
{
  "request": "",
  "answer_source": null,
  "confidence": null,
  "steps": [
    {
      "step": "validate",
      "ok": false,
      "ms": 0.1,
      "error": "Request is empty. Describe the music you want."
    },
    {
      "step": "parse",
      "ok": false,
      "ms": 0.0,
      "source": "rejected",
      "fixes": [
        "Request is empty. Describe the music you want."
      ],
      "profile": null
    }
  ],
  "errors": []
}
```

The input guardrail fails in `validate`, `parse` records the source as `rejected` with no profile, and the run ends. There is no `retrieve`, `generate`, or `verify` step. For a path with a transient API error and a retry, see the N2 trace in the same file.

### How to see a trace yourself

- Every run appends one JSON line to `logs/traces.jsonl`. The log files are not committed.
- `run()` returns the same steps as `result["trace_steps"]`. Each step has `step`, `ok`, and `ms`, plus extra fields such as `source`, `profile`, `titles`, `checks`, and `problems`.
- The Behind the scenes panel in the app shows the same steps in plain English.
- More traces: [sample_traces.md](docs/evidence/sample_traces.md) and [phase3_live_runs.md](docs/evidence/phase3_live_runs.md).

## Key prompts

### Parser prompt

[src/profile_parser.py](src/profile_parser.py), function `build_prompt`, which `parse_with_llm` calls. The instructions:

```python
"Convert the music request into a JSON taste profile. Reply with ONLY a JSON object, "
"no prose and no code fences.\n"
...
'Include "energy" ONLY if the request mentions pace, intensity, or an activity '
'(for example "chill", "workout", "road trip", "to fall asleep"). A mood alone, such as '
'"happy" or "romantic", is not a hint: leave "energy" out.\n'
f"Allowed genres: {', '.join(VOCAB['genres'])}\n"
f"Allowed moods: {', '.join(VOCAB['moods'])}\n"
f"Allowed mood_tags: {', '.join(VOCAB['mood_tags'])}\n"
"Use only allowed values; use null for genre or mood if nothing fits.\n"
```

Two of the five few-shot examples (`FEW_SHOT`):

```
Request: "romantic songs for date night"
{"mood": "romantic", "mood_tags": ["romantic"]}

Request: "happy jazz"
{"genre": "jazz", "mood": "happy"}
```

The "energy only if there is a hint" rule is how I stopped Gemini from inventing preferences. The allowed lists come from the catalog, so Gemini can only name genres and moods that exist. Both examples I picked leave energy out.

### Answer-generation prompt

[src/assistant.py](src/assistant.py), function `build_answer_prompt`:

```python
"You are a friendly music assistant. Recommend songs ONLY from the candidate list below.",
...
"Background notes:"
...
f"Pick {N_PICKS} different candidate songs and explain why each fits in 2-3 friendly sentences "
"total across the answer. Use exact titles from the list, and do not mention any other song. "
"Reply with ONLY JSON in this shape:",
'{"picks": [{"title": "...", "why": "..."}], "summary": "..."}',
```

This is the grounding part. Gemini only sees the retrieved songs and the guide notes, and it is told to use exact titles and name no other song. The output checks then test that rule, because a prompt alone does not guarantee it.

### Retry-with-feedback prompt

[src/assistant.py](src/assistant.py), function `_generate_verified`:

```python
prompt = (base + "\n\nYour previous reply was rejected for these problems:\n- "
          + "\n- ".join(problems)
          + "\nFix them. Use only exact titles from the candidate list, no duplicates, "
            "and reply with ONLY the JSON.")
```

It reuses the original prompt and adds the exact problems from the failed checks. Naming the problem (for example, which titles did not match) is what let the second answer in Trace 1 pass.

## Design decision log

| Decision | Who suggested it | What I chose | Why |
|---|---|---|---|
| Offline fallback for every step | Claude (planning chat) | Kept | The free tier allowed about 20 calls a day and I hit 429 and 503 errors. Tests and the main eval run free. |
| No invented energy | Found by me while testing | Set energy only when the request hints at a vibe | I removed the 0.5 default and the eval dropped to 18/20. The default had been hiding how thin the catalog was. |
| Thin catalog | Claude suggested a "weak pick" note | Rejected it and expanded the catalog from 22 to 60 songs | The point is 3 good picks, so I fixed the cause and did not warn about it. |
| Mood families | Claude, for thin-catalog requests | Agreed and kept them | A different mood in the same family earns half the mood weight, so related moods get partial credit. |
| Valence hint | Claude, after "sad rock" returned upbeat songs | Agreed and kept it | The hint pulls results toward the right feel. |
| Vibe words instead of "energy" ("hype" for the highest level) | Me | Plain words in the UI | The user never sees the word energy. |
| Vague requests | Me (the popular-songs idea) | A positive request defaults to happy, a negative one to melancholic with a calm, reflective note, and no clue ranks by popularity with a note | A vague request still deserves a useful answer. Confidence is capped at 0.5. |
| Happy plus sad | Me | Becomes bittersweet with no penalty. Conflicting vibe cues get a 0.2 confidence penalty | Mixed feelings are real. Contradictory cues are a sign the request is unclear. |
| Typo length guard | A UI test written by Claude in VS Code | Typo fixes only apply to words of similar length | The test caught "roman" becoming "romantic". |
| Simpler UI | Me | Removed the RAG toggle, example buttons, the How it works sidebar, and the why text on cards | Cards show cover and title. Details go in Behind the scenes. |
| Few-shot stays the default parser | Result of my comparison | Kept few-shot | It followed my design rules more closely, although 3 cases is too small to call a winner ([parser_comparison_subset.md](docs/evidence/parser_comparison_subset.md)). |

## When the AI was wrong

- **The confidence drop.** Claude in the planning chat said a drop in confidence from 0.97 to 0.73 was caused by the retry. Claude in VS Code corrected it. They were different requests. The retry explains 0.15 of the gap and the weaker top match explains the rest.
- **Gemini's title format.** Gemini wrote `"Crossroads Lament" by Delta Jack` instead of the exact title. The `titles_match_retrieved` check caught it (Trace 1).
- **The typo matcher.** My typo fix turned "roman" into "romantic", so a sentence about the Roman Empire passed as a music request. A UI test caught it, and I added the length guard.
