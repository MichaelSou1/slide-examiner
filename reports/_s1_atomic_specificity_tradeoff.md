# Finding: atomic (C3) elicitation trades specificity for recall — it is NOT a free lunch

**Status:** verified real effect (not a bug), 2026-06-25. Source: `data/part3/p2_synth.json`
`config_per_class` (coverage eval, body model qwen35-27b, n=18+18 per class).

## The S1 "reversal" is FP-driven, recall is saturated either way
For **S1 title/body mismatch**, open pointwise (C0) BEATS atomic targeted (C3):

| elicitation | recall | specificity | bal-acc | tp/fn/fp/tn |
|---|---|---|---|---|
| C0 (open rubric) | 1.00 | 0.889 | **0.944** | 18/0/**2**/16 |
| C3 (atomic yes/no) | 1.00 | 0.667 | 0.833 | 18/0/**6**/12 |

Both catch **all 18** defectives (recall 1.0). The whole gap is **false positives on CLEAN
slides**: C3 over-asserts (fp 2→6, spec .89→.67). The atomic forced yes/no — "*is there a
title/body mismatch?*" — induces a **yes-bias on a fuzzy/subjective class** (title↔body relevance
has a soft boundary), so the model invents the defect on clean slides. C0's open rubric lets it stay
silent when clean. (Prompt is fine: a broken prompt would tank recall, which is saturated at 1.0.)

## Why this is a selling point, not something to fix
C3 helps **only where recall is the bottleneck**, and hurts where recall is already saturated:

| class | C0→C3 bal-acc | bottleneck | C3 effect |
|---|---|---|---|
| G7 render-overflow | 0.50→**1.00** | recall (0.50) | +0.50 recovers |
| S4 density | 0.51→**0.93** | recall | +0.42 recovers |
| **S1 title/body** | 0.94→**0.83** | specificity (recall already 1.0) | **−0.11 inflates FP** |

**Two paper uses:**
1. **Sharpens "route the elicitation per class" (no universal-best prompt).** The minimal hybrid
   isn't just linter-vs-VLM; even within the VLM, the *elicitation* must be class-matched. S1 is the
   clean counterexample that justifies not forcing C3 everywhere.
2. **The nuance the "pointwise-rubric under-reports" warning needs.** Atomic per-type elicitation
   recovers recall the conventional rubric suppresses, **but inflates false positives on subjective
   classes** — so the methodological recommendation is "decompose recall-limited classes," not
   "always go atomic." Pre-empts the reviewer who says "so just always ask per-type?"

**Where to put it:** §5 (elicitation) as the honest counter-direction to the C0→C3 recovery; one row
in Table 2 already shows it (S1 routed to VLM-C0, not C3). Tie to the `vlm_c3_everywhere` baseline
column (S1 0.833) vs the routed (0.944).
