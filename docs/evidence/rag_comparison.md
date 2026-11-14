# RAG comparison: answers with vs without the genre guide

- Mode: live (Gemini)
- Command: `python eval/compare_rag.py`
- Date: 2026-11-14
- Requests parsed with the offline parser (0 LLM calls); each answer generated once with guide notes and once without.
- "Guide words used" = distinct content words (5+ letters, minus a small stopword list) from the retrieved guide notes that appear in the picks' explanations. It is a crude measure.

## Summary

| metric | with guide | without guide |
|---|---|---|
| Avg confidence | 0.81 | 0.81 |
| Avg guide words used | 4.0 | 2.0 |
| Avg explanation length (words) | 13.8 | 12.1 |
| Total retries | 1 | 1 |
| Answers from the LLM | 2 | 2 |
| Verification checks passed (4 per request) | 12 | 12 |

## Side by side

| request | guide sections retrieved | with guide | without guide |
|---|---|---|---|
| sad songs for a rainy day | melancholic, classical, blues, folk, lofi | **Elegy for Winter Strings**: Its slow classical strings offer a sorrowful, delicate backdrop perfect for watching the rain.<br>**Crossroads Lament**: This soulful blues track delivers a bittersweet, emotional tone that feels cozy and reflective.<br>**Letters from the Orchard**: Gentle acoustic folk melodies give this song a wistful feel ideal for quiet indoor moments.<br><br>source: llm; checks 4/4; retries 0; confidence 0.87; guide words used 7 (acoustic, bittersweet, emotional, quiet, reflective, sorrowful, soulful); avg explanation 14.3 words | **Elegy for Winter Strings**: A calm classical track with a melancholic feel, a good fit for what you asked.<br>**Crossroads Lament**: An easygoing blues track with a melancholic feel, a good fit for what you asked.<br>**Letters from the Orchard**: A calm folk track with a wistful feel, a close match for what you asked.<br><br>source: template; checks 4/4; retries 1; confidence 0.72; guide words used 0; avg explanation 15.0 words<br>API ERROR: LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, quota, and model name.; LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, quota, and model name. |
| romantic dinner music | romantic, latin, pop, rock, r&b, hip-hop | **Corazón de Fuego**: Corazón de Fuego brings warm Latin rhythms that add a passionate touch to your dinner.<br>**Afterglow Avenue**: Afterglow Avenue features tender pop melodies that create a sweet, cozy background.<br>**Velvet Hours**: Velvet Hours provides smooth R&B grooves perfect for an intimate evening together.<br><br>source: llm; checks 4/4; retries 0; confidence 0.90; guide words used 5 (brings, grooves, intimate, smooth, tender); avg explanation 13.0 words | **Corazón de Fuego**: Warm Latin rhythms set an intimate tone for your meal.<br>**Afterglow Avenue**: Smooth pop melodies bring a cozy and modern romantic feel.<br>**Velvet Hours**: Soft R&B vibes create a charming backdrop for your special evening.<br><br>source: llm; checks 4/4; retries 0; confidence 0.90; guide words used 3 (intimate, smooth, special); avg explanation 10.3 words |
| lofi for late night coding | lofi, moody | **Rainy Bus Window**: A lofi track with a wistful feel, a close match for what you asked.<br>**Midnight Coding**: A lofi track with a chill feel, a close match for what you asked.<br>**Focus Flow**: A lofi track with a focused feel, a close match for what you asked.<br><br>source: template; checks 4/4; retries 1; confidence 0.67; guide words used 0; avg explanation 14.0 words<br>API ERROR: LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, quota, and model name.; LLMError: Gemini API call failed (ServerError, code=503) using model 'gemini-3.5-flash'. Check your API key, network, quota, and model name. | **Midnight Coding**: This track sets a cozy vibe perfect for late-night programming.<br>**Focus Flow**: Its steady rhythm helps keep you locked into deep concentration.<br>**Quiet Hours**: It provides a peaceful backdrop to keep your mind calm during late hours.<br><br>source: llm; checks 4/4; retries 0; confidence 0.82; guide words used 3 (hours, night, steady); avg explanation 11.0 words |

## Verdict

INCONCLUSIVE: 2 of 6 LLM calls failed with API errors, so the two columns are not a fair comparison. Re-run when the quota has reset.
