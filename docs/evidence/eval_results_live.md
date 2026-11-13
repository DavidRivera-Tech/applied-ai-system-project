# Evaluation results (live, Gemini)

- Command: `python eval/run_eval.py --live`
- Date: 2026-11-13
- Cases: `eval/cases.json` (15 cases)

## Results

| id | category | result | confidence | failure reason |
|----|----------|--------|------------|----------------|
| N1 | normal | PASS | 0.97 |  |
| N2 | normal | PASS | 0.91 |  |
| N3 | normal | PASS | 0.87 |  |
| N4 | normal | PASS | 0.83 |  |
| N5 | normal | PASS | 0.96 |  |
| N6 | normal | PASS | 0.82 |  |
| E1 | edge | PASS | 0.99 |  |
| E2 | edge | PASS | 0.94 |  |
| E3 | edge | PASS | 0.88 |  |
| E4 | edge | PASS | 0.84 |  |
| E5 | edge | FAIL | - | expected rejected=False, got rejected=True (That doesn't look like a music request. Try describing a genre, mood or activity.) |
| G1 | guardrail | PASS | - |  |
| G2 | guardrail | PASS | - |  |
| G3 | guardrail | PASS | - |  |
| G4 | guardrail | PASS | 0.99 |  |

## Summary

- **14/15 passed** (93%)
- normal: 6/6 (100%)
- edge: 4/5 (80%)
- guardrail: 4/4 (100%)
- Average confidence (answered cases, n=11): 0.91
- Answers from the LLM: 10; from the template: 1; rejected (no answer): 4
- Cases that needed a retry: 3
