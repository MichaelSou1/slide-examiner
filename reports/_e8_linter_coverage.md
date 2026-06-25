# E8 CPU recompute — Table-2 LINTER column (internal-口径 G3/G5)

Linter over declared-bbox IR (CPU only). Detection = the linter emits the class; specificity measured on the paired CLEAN IR (declared-bbox negative). Internal rules: `alignment_group` (G3), `detect_color_inconsistency` (G5).

| Class | linter bal-acc | recall [95% CI] | specificity | n=pos+neg | tp/fp |
|---|---|---|---|---|---|
| G3 | 0.929 | 0.86 [0.76-0.92] | 1.00 | 70+70 | 60/0 |
| G5 | 1.000 | 1.00 [0.91-1.00] | 1.00 | 40+40 | 40/0 |

## Per-stratum linter recall (supra-threshold detected / sub-threshold abstained)

| Class | stratum | linter recall | n |
|---|---|---|---|
| G3 | 2px | 0.00 | 10 |
| G3 | 4px | 1.00 | 10 |
| G3 | 8px | 1.00 | 10 |
| G3 | 16px | 1.00 | 10 |
| G3 | 32px | 1.00 | 10 |
| G3 | 48px | 1.00 | 10 |
| G3 | 64px | 1.00 | 10 |
| G5 | 6ΔE | 1.00 | 10 |
| G5 | 12ΔE | 1.00 | 10 |
| G5 | 24ΔE | 1.00 | 10 |
| G5 | 40ΔE | 1.00 | 10 |

**False-fire on paired clean IR:** 0 (0 = calibrated; the linter's near-zero-FP edge).
