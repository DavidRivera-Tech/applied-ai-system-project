# Sample traces (live run)

Generated 2026-11-13 by `python eval/run_eval.py --live`. Full per-step traces as logged by the assistant; no API key is included.

## Clean pass: N1

```json
{
  "request": "something chill to study to, no vocals",
  "answer_source": "llm",
  "confidence": 0.97,
  "steps": [
    {
      "step": "validate",
      "ok": true,
      "ms": 0.2
    },
    {
      "step": "parse",
      "ok": true,
      "ms": 20132.1,
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
      "ms": 1.0,
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
      "ms": 35446.3,
      "api_try": 1
    },
    {
      "step": "verify",
      "ok": true,
      "ms": 1.5,
      "attempt": 1,
      "checks": {
        "titles_match_retrieved": true,
        "no_duplicate_picks": true,
        "text_names_only_retrieved": true,
        "correct_pick_count": true
      },
      "problems": []
    }
  ],
  "errors": []
}
```

## Retry: N2

```json
{
  "request": "high energy workout music",
  "answer_source": "llm",
  "confidence": 0.91,
  "steps": [
    {
      "step": "validate",
      "ok": true,
      "ms": 0.2
    },
    {
      "step": "parse",
      "ok": true,
      "ms": 44983.7,
      "source": "llm",
      "fixes": [],
      "profile": {
        "genre": null,
        "mood": "energetic",
        "energy": 0.9,
        "mood_tags": [
          "energetic",
          "motivated"
        ]
      }
    },
    {
      "step": "retrieve",
      "ok": true,
      "ms": 4.0,
      "titles": [
        "Fuego en la Calle",
        "Gym Hero",
        "Pulse Theory",
        "Storm Runner",
        "Iron Cathedral"
      ],
      "guide_notes": [
        "energetic",
        "latin",
        "pop",
        "edm",
        "rock",
        "metal"
      ]
    },
    {
      "step": "generate",
      "ok": false,
      "ms": 59465.1,
      "api_try": 1,
      "error": "LLMError"
    },
    {
      "step": "retry",
      "ok": true,
      "ms": 0.0,
      "reason": "transient API error"
    },
    {
      "step": "generate",
      "ok": true,
      "ms": 31838.8,
      "api_try": 2
    },
    {
      "step": "verify",
      "ok": true,
      "ms": 0.5,
      "attempt": 1,
      "checks": {
        "titles_match_retrieved": true,
        "no_duplicate_picks": true,
        "text_names_only_retrieved": true,
        "correct_pick_count": true
      },
      "problems": []
    }
  ],
  "errors": [
    {
      "step": "generate",
      "type": "LLMError",
      "message": "Gemini API call failed (ServerError, code=504) using model 'gemini-3.5-flash'. Check your API key, network, quota, and model name."
    }
  ]
}
```

## Guardrail rejection: G1

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
