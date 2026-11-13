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
| N5 | normal | PASS | 0.72 |  |
| N6 | normal | PASS | 0.75 |  |
| E1 | edge | PASS | 0.75 |  |
| E2 | edge | PASS | 0.75 |  |
| E3 | edge | PASS | 0.74 |  |
| E4 | edge | PASS | 0.36 |  |
| E5 | edge | PASS | 0.50 |  |
| G1 | guardrail | PASS | - |  |
| G2 | guardrail | PASS | - |  |
| G3 | guardrail | PASS | - |  |
| G4 | guardrail | PASS | 0.74 |  |

## Summary

- **15/15 passed** (100%)
- normal: 6/6 (100%)
- edge: 5/5 (100%)
- guardrail: 4/4 (100%)
- Average confidence (answered cases, n=12): 0.68
- Answers from the LLM: 0; from the template: 12; rejected (no answer): 3
- Cases that needed a retry: 0
