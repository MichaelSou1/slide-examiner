# E8 internal-口径 roster — G3/G5 format-suppression re-run

Headline metric = **NAMED attribution** (did the model surface *this* defect). C0 = open-ended pointwise (suppressed); C3 = atomic targeted; AFC = 2-AFC strict (defective called worse in both orders). Internal contrast 口径 (one element vs its aligned/coloured siblings — decidable from the slide alone).

## Per-model recovery (pooled over strata)

| Model | Defect | C0 named | C3 named | ΔC3−C0 | AFC strict (n) |
|---|---|---|---|---|---|
| qwen35-9b | G3 | 0.66 (r=0.40[0.29-0.52],s=0.91,n=70+70) | 0.74 (r=0.56[0.44-0.67],s=0.93,n=70+70) | +0.09 | 0.88 (n=43) |
| qwen35-9b | G5 | 0.53 (r=0.05[0.01-0.17],s=1.00,n=40+40) | 0.74 (r=0.47[0.33-0.62],s=1.00,n=40+40) | +0.21 | 1.00 (n=21) |
| internvl-8b | G3 | 0.56 (r=0.23[0.15-0.34],s=0.90,n=70+70) | 0.50 (r=0.00[0.00-0.05],s=1.00,n=70+70) | -0.06 | — |
| internvl-8b | G5 | 0.50 (r=0.00[0.00-0.09],s=1.00,n=40+40) | 0.61 (r=0.23[0.12-0.38],s=1.00,n=40+40) | +0.11 | — |
| ovis-9b | G3 | 0.50 (r=0.00[0.00-0.05],s=1.00,n=70+70) | 0.63 (r=0.27[0.17-0.38],s=1.00,n=68+70) | +0.13 | 1.00 (n=16) |
| ovis-9b | G5 | 0.50 (r=0.00[0.00-0.09],s=1.00,n=40+40) | 0.78 (r=0.57[0.42-0.71],s=0.97,n=40+40) | +0.28 | 1.00 (n=22) |
| qwen36-27b | G3 | 0.57 (r=0.14[0.08-0.24],s=1.00,n=70+70) | 0.73 (r=0.46[0.35-0.57],s=1.00,n=70+70) | +0.16 | 1.00 (n=30) |
| qwen36-27b | G5 | 0.50 (r=0.00[0.00-0.09],s=1.00,n=40+40) | 0.66 (r=0.33[0.20-0.48],s=1.00,n=40+40) | +0.16 | 1.00 (n=19) |
| qwen35-27b | G3 | 0.62 (r=0.24[0.16-0.35],s=1.00,n=70+70) | 0.71 (r=0.41[0.31-0.53],s=1.00,n=70+70) | +0.09 | 1.00 (n=30) |
| qwen35-27b | G5 | 0.50 (r=0.00[0.00-0.09],s=1.00,n=40+40) | 0.68 (r=0.35[0.22-0.51],s=1.00,n=40+40) | +0.18 | 1.00 (n=19) |
| gemma4-31b | G3 | 0.66 (r=0.34[0.24-0.46],s=0.97,n=70+70) | 0.77 (r=0.54[0.43-0.65],s=1.00,n=70+70) | +0.11 | 1.00 (n=30) |
| gemma4-31b | G5 | 0.55 (r=0.10[0.04-0.23],s=1.00,n=40+40) | 0.71 (r=0.45[0.31-0.60],s=0.97,n=40+40) | +0.16 | 1.00 (n=17) |

## Roster mean (over models reporting the cell)

| Defect | mean C0 named | mean C3 named | mean AFC strict | n models |
|---|---|---|---|---|
| G3 | 0.59 | 0.68 | 0.98 | 6 |
| G5 | 0.51 | 0.70 | 1.00 | 6 |

## Clean-magnitude threshold — roster-mean C3 named bal-acc by stratum

| Defect | stratum | mean C0 | mean C3 | mean AFC | n models |
|---|---|---|---|---|---|
| G3 | 2px | 0.49 | 0.50 | 0.00 | 6 |
| G3 | 4px | 0.52 | 0.49 | 0.00 | 6 |
| G3 | 8px | 0.51 | 0.52 | 0.00 | 6 |
| G3 | 16px | 0.54 | 0.63 | 1.00 | 6 |
| G3 | 32px | 0.64 | 0.83 | 1.00 | 6 |
| G3 | 48px | 0.73 | 0.90 | 1.00 | 6 |
| G3 | 64px | 0.73 | 0.90 | 1.00 | 6 |
| G5 | 6ΔE | 0.50 | 0.49 | — | 6 |
| G5 | 12ΔE | 0.50 | 0.53 | 1.00 | 6 |
| G5 | 24ΔE | 0.51 | 0.78 | 1.00 | 6 |
| G5 | 40ΔE | 0.54 | 0.99 | 1.00 | 6 |
