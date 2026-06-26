# E8 CPU recompute — Table-2 LINTER column (page-offset G6)

Linter (`detect_margin_violations`) over declared-bbox IR (CPU only). Specificity on the paired CLEAN IR. G6 re-posed as page offset (whole block shifted to one edge).

| Class | linter bal-acc | recall [95% CI] | specificity | n=pos+neg | tp/fp |
|---|---|---|---|---|---|
| G6 | 0.750 | 0.50 [0.39-0.61] | 1.00 | 80+80 | 40/0 |

## Per-stratum linter recall (caught once content nears/clips the edge)

| stratum (shift_px) | linter recall | n |
|---|---|---|
| 16px | 0.00 | 10 |
| 32px | 0.00 | 10 |
| 48px | 0.00 | 10 |
| 64px | 0.00 | 10 |
| 80px | 1.00 | 10 |
| 88px | 1.00 | 10 |
| 96px | 1.00 | 10 |
| 112px | 1.00 | 10 |

**False-fire on paired clean IR:** 0 (0 = calibrated).
