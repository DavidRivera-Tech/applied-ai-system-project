# Parser comparison: offline vs zero-shot vs few-shot

- Command: `python eval/compare_parsers.py --limit 5`
- Date: 2026-11-14
- Requests: 5 (the first 5 cases from `eval/cases.json`, N1 to N5)
- Profiles are shown after `validate_profile`. Genre/mood/energy rows only count cases that have that expectation (denominators shown).

## Summary

| metric | offline | zero-shot | few-shot |
|---|---|---|---|
| API errors (429/5xx, excluded below) | 0/5 | 2/5 | 1/5 |
| Valid JSON profile | 5/5 | 3/3 | 4/4 |
| Needed fixes from validate_profile | 0/5 | 0/3 | 0/4 |
| Genre matched genre_in | 1/1 | 0/1 | 0/1 |
| Mood matched mood_in | 5/5 | 3/3 | 4/4 |
| Energy in target range | 4/5 | 3/3 | 3/4 |
| Avg time per successful parse | 0.001 s | 19.786 s | 21.210 s |

## Per-request profiles

| id | request | offline | zero-shot | few-shot |
|---|---|---|---|---|
| N1 | something chill to study to, no vocals | `{"genre":"lofi","mood":"chill","energy":0.35,"instrumental":true}` | `{"genre":null,"mood":"chill","energy":0.2,"instrumental":true,"mood_tags":["calm","focused","laid-back"]}` | `{"genre":null,"mood":"chill","energy":0.3,"instrumental":true,"mood_tags":["focused"]}` |
| N2 | high energy workout music | `{"mood":"energetic","energy":0.9}` | FAILED (LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, qu) | `{"genre":null,"mood":"energetic","energy":0.9,"mood_tags":["energetic","motivated"]}` |
| N3 | sad songs for a rainy day | `{"mood":"melancholic","energy":0.3,"likes_acoustic":true}` | FAILED (LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, qu) | FAILED (LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, qu) |
| N4 | romantic dinner music | `{"mood":"romantic","mood_tags":["romantic"]}` | `{"genre":null,"mood":"romantic","energy":0.3,"mood_tags":["romantic","smooth","tender"]}` | `{"genre":null,"mood":"romantic","mood_tags":["romantic"]}` |
| N5 | angry music to blow off steam | `{"mood":"aggressive","energy":0.88}` | `{"genre":null,"mood":"aggressive","energy":0.9,"mood_tags":["aggressive","furious"]}` | `{"genre":null,"mood":"aggressive","energy":0.9,"mood_tags":["aggressive","furious"]}` |

## Fixes applied by validate_profile

None.

## Conclusions

I ran 5 requests through both Gemini prompts, which is 10 calls. Three calls failed with 503 server errors, not quota errors: zero-shot on N2 and N3, and few-shot on N3. That left 3 head-to-head cases (N1, N4 and N5).

- **Valid output.** Both versions returned valid JSON with the expected mood every time they worked. `validate_profile` needed no fixes.
- **The difference was discipline.** On N4 ("romantic dinner music"), zero-shot invented an energy value of 0.3 and added 3 mood tags. Few-shot left energy out and used 1 tag. That matches my "no invented preferences" rule and it matches the offline parser. On N1, zero-shot added 3 tags and few-shot added 1.
- **The energy miss.** Few-shot scored 3/4 on "energy in target range". The miss was N4, where the target is 0.0 to 0.7 and few-shot left energy out on purpose. The metric counts a missing energy as a miss, but my design rule says to leave it out for a mood-only request. Here the metric and my design rule disagree. Offline also scores 4/5 for the same reason.
- **Genre on N1.** Both Gemini versions missed it. The offline parser guesses lofi from the word "study". Gemini left genre null.
- **Offline.** It matched or beat both Gemini versions. These are normal cases it was tuned on, so that is not a fair win.
- **Verdict.** Three cases is too small to call a winner. Few-shot followed my design rules more closely, so it stays the default.
