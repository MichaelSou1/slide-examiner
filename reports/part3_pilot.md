# Part 3 — Page-level pilot

- mode: live; budget=24; q=0.8
- cells ok: 8/8

| carrier/condition | seeds reached | rollouts→thr (mean±std) | best score |
|---|---|---|---|
| gepa/linter | 2/2 | 1±0.0 | 1.0 |
| gepa/zero_shot_8b | 2/2 | 1±0.0 | 1.0 |
| gepa/finetuned_8b | 2/2 | 1±0.0 | 1.0 |
| gepa/hybrid | 2/2 | 1±0.0 | 1.0 |

> Proceed to deck-level only where cross-seed std of rollouts-to-threshold is small relative to cross-condition spread.
