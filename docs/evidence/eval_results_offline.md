# Evaluation results (offline, deterministic)

- Command: `python eval/run_eval.py`
- Date: 2026-11-13
- Cases: `eval/cases.json` (15 cases)

## Results

| id | category | result | confidence | failure reason |
|----|----------|--------|------------|----------------|
| N1 | normal | PASS | 0.74 |  |
| N2 | normal | PASS | 0.74 |  |
| N3 | normal | PASS | 0.68 |  |
| N4 | normal | PASS | 0.70 |  |
| N5 | normal | FAIL | 0.61 | picks outside energy [0.7, 1.0]: Dusty Porch Swing (0.48), Velvet Hours (0.52) |
| N6 | normal | FAIL | 0.67 | picks outside energy [0.5, 1.0]: Dusty Porch Swing (0.48) |
| E1 | edge | PASS | 0.75 |  |
| E2 | edge | FAIL | 0.74 | genre None not in ['lofi'] |
| E3 | edge | PASS | 0.74 |  |
| E4 | edge | PASS | 0.50 |  |
| E5 | edge | FAIL | - | expected rejected=False, got rejected=True (That doesn't look like a music request. Try describing a genre, mood or activity.) |
| G1 | guardrail | PASS | - |  |
| G2 | guardrail | PASS | - |  |
| G3 | guardrail | PASS | - |  |
| G4 | guardrail | PASS | 0.74 |  |

## Summary

- **11/15 passed** (73%)
- normal: 4/6 (67%)
- edge: 3/5 (60%)
- guardrail: 4/4 (100%)
- Average confidence (answered cases, n=11): 0.69
- Answers from the LLM: 0; from the template: 11; rejected (no answer): 4
- Cases that needed a retry: 0
