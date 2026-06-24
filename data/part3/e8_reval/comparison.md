# E8 re-examination — realistic vs original injection (qwen-vl-max)

Same elicitation protocol (C0 pointwise / C3 atomic / AFC 2-AFC) on the realistic defect variants vs the original (ill-posed) injections. Detection = balanced accuracy [95% Wilson CI]; AFC = rate the defective is called worse (chance 0.5).

## G3 alignment

| condition | realistic | original injection |
|---|---|---|
| C0 | 0.50 [0.34,0.66] (n=8) | 0.50 [0.47,0.53] (n=60) |
| C3 | 0.75 [0.45,0.89] (n=8) | 0.50 [0.47,0.53] (n=60) |
| AFC | 0.75 (n=8 — dec 75%, tie 25%) | 0.00 (n=60 — dec 0%, tie 100%) |

**Verdict:** **INJECTION ARTIFACT** — original ~chance but realistic variant is detected; the 'at chance' claim must be rewritten.

## G5 brand-colour

| condition | realistic | original injection |
|---|---|---|
| C0 | 0.50 [0.38,0.62] (n=12) | 0.50 [0.46,0.54] (n=60) |
| C3 | 0.50 [0.38,0.62] (n=12) | 0.50 [0.47,0.53] (n=60) |
| AFC | 0.08 (n=12 — dec 8%, tie 92%) | 0.00 (n=60 — dec 0%, tie 100%) |

**Verdict:** sub-perceptual claim **survives** — even the realistic variant stays ~chance.

## S6 image/text

| condition | realistic | original injection |
|---|---|---|
| C0 | 0.50 [0.43,0.57] (n=24) | — |
| C3 | 0.50 [0.43,0.57] (n=24) | — |
| AFC | 1.00 (n=24 — dec 100%, tie 0%) | — |

**Verdict:** realistic-only (original degenerate set has no clean twin; compare to paper's reported chance).
