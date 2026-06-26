# R7 — Frontier VLM-as-judge row (Qwen3.7-Max)

Model: `qwen3.7-max-2026-06-08` via DashScope OpenAI-compatible endpoint (`PART3_GEN_*`).

Metric: paired preference accuracy `P(score(clean)>score(defective))`; ties are not counted as clean-preferred, matching the reward-audit convention.

| Defect | pref-acc [95% CI] | mean score gap clean-def | n | ties |
|---|---:|---:|---:|---:|
| G1 overflow | 0.125 [0.043,0.310] | +1.25 | 24 | 20 |
| G2 overlap | 0.917 [0.742,0.977] | +17.50 | 24 | 1 |
| G7 render-overflow | 1.000 [0.862,1.000] | +25.00 | 24 | 0 |
| S4 density | 1.000 [0.862,1.000] | +21.67 | 24 | 0 |

## Same closed model on G7 C0 vs C3

| Condition | detection bal-acc [95% CI] | detection precision | named bal-acc [95% CI] | tp/fp/tn/fn |
|---|---:|---:|---:|---:|
| C0 whole-taxonomy pointwise | 0.800 [0.654,0.894] | 0.773 | 0.500 [0.456,0.544] | 34/10/30/6 |
| C3 atomic + evidence | 1.000 [0.912,1.000] | 1.000 | 1.000 [0.912,1.000] | 40/0/40/0 |

Interpretation: the closed frontier VLM judge strongly penalizes G7 as a pointwise quality scorer (24/24 clean-preferred). Under the examiner protocol, C0 already often says something is wrong at the detection level but cannot name the off-taxonomy G7 class; C3 supplies the named/localized recovery (1.00 bal-acc, 1.00 precision).
