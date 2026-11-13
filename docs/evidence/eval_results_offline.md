# Evaluation results (offline, deterministic)

- Command: `python eval/run_eval.py`
- Date: 2026-11-13
- Cases: `eval/cases.json` (20 cases)

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
| H1 | holdout | PASS | 0.63 |  |
| H2 | holdout | PASS | 0.75 |  |
| H3 | holdout | PASS | 0.73 |  |
| H4 | holdout | PASS | 0.72 |  |
| H5 | holdout | PASS | 0.63 |  |

## Summary

- **20/20 passed** (100%)
- normal: 6/6 (100%)
- edge: 5/5 (100%)
- guardrail: 4/4 (100%)
- holdout: 5/5 (100%)
- Average confidence (answered cases, n=17): 0.68
- Answers from the LLM: 0; from the template: 17; rejected (no answer): 3
- Cases that needed a retry: 0
