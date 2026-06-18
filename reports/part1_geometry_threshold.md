# Part 1 — geometry-detection threshold vs model size

Real VLM probe (vLLM) over the expanded Part 1 geometry subset (288 page samples: G1–G6 across full severity grids + 80 clean negatives), modalities A/B/C, task T1. 0% parse failure on all three models.

## Detection recall — best of image channels (A or C)

| Defect | 4B | 8B | 30B-A3B |
|---|---|---|---|
| G1_TEXT_OVERFLOW | 0/40 | 0/40 | 20/40 |
| G2_ELEMENT_OVERLAP | 0/32 | 0/32 | 2/32 |
| G3_ALIGNMENT_OFFSET | 0/40 | 0/40 | 0/40 |
| G4_FONT_SIZE_INCONSISTENCY | 0/32 | 0/32 | 2/32 |
| G5_BRAND_COLOR_VIOLATION | 0/32 | 0/32 | 0/32 |
| G6_MARGIN_VIOLATION | 0/32 | 0/32 | 1/32 |

Clean-negative false positives (modality C): 4B 0/80, 8B 0/80, 30B-A3B 0/80.

## Findings

- **4B and 8B are geometrically blind**: 0 detections across all six geometry defect types, in both the image-only (A) and image+structure (C) channels, even though every defect is clearly rendered (visible cards, overflow spilling past borders, boxes blending on overlap).
- **The threshold first breaks at 30B-A3B, and only for the grossest defect — text overflow (G1)**: 50% recall from the image. The finer geometric defects stay at the floor even at 30B: alignment offset (G3) and brand-color delta (G5) = 0; overlap (G2), font delta (G4), margin bleed (G6) are within noise of 0 (1–2 / 32).
- **The structured oracle hurts geometry perception**: on 30B, G1 overflow recall is 20/40 from the image alone (A) but only 4/40 when the structure is added (C). The bbox/text fields distract rather than help.
- **Even the detected overflow is barely severity-graded**: 30B G1 recall by overflow magnitude (A) is 4.0px=2/8, 8.0px=5/8, 16.0px=3/8, 32.0px=6/8, 64.0px=4/8 — roughly flat, i.e. it spots *that* text spills, not *how much*.
- **All three models are highly conservative**: 0 false positives across 80 clean negatives at every size — recall, not precision, is the binding constraint.

## Implication for the matrix

This is strong, multi-scale evidence for the contract's design: **G1–G6 belong to the symbolic linter**. A VLM cannot be the primary geometry detector up to 30B; only gross text-overflow is within reach, and only at 30B, and only from the image. The examiner's value is the semantic (S) group and cross-checks — not geometry. For the full matrix, score G-group against the linter and reserve VLM geometry calls for overflow cross-checks on the largest models.

