# Part 1 — Track E: S-group pointwise attribution across sizes (balanced accuracy)

Real VLM probe (vLLM Qwen3-VL 4B / 8B / 30B-A3B), A/B/B'/C × T1 over the frozen S-group subset (64 defectives + 40 paired clean). **Main metric = balanced accuracy** (recall + specificity on level-matched clean), per SPEC §3.0 轨 E. B' = VLM-image caption (held fixed at the 30B caption across sizes, so the cross-size comparison isolates *reasoning over a fixed caption* from caption quality).

## Group balanced accuracy (mean over level's defects)

| level | model | A | B | B′ | C |
|---|---|---|---|---|---|
| page | 4B | 0.5 | 0.5 | 0.5 | 0.5 |
| page | 8B | 0.583 | 0.5 | 0.5 | 0.583 |
| page | 30B | 0.745 | 0.701 | 0.625 | 0.722 |
| deck | 4B | 0.5 | 0.611 | 0.486 | 0.542 |
| deck | 8B | 0.5 | 0.667 | 0.521 | 0.458 |
| deck | 30B | 0.66 | 0.521 | 0.639 | 0.583 |

## Per-defect balanced accuracy (best channel bolded mentally)

| defect | level | model | A | B | B′ | C |
|---|---|---|---|---|---|---|
| S1_TITLE_BODY_MISMATCH | page | 4B | 0.5 | 0.5 | 0.5 | 0.5 |
| S1_TITLE_BODY_MISMATCH | page | 8B | 0.75 | 0.5 | 0.5 | 0.75 |
| S1_TITLE_BODY_MISMATCH | page | 30B | 0.963 | 0.75 | 0.5 | 0.938 |
| S4_DENSITY_RULE_VIOLATION | page | 4B | 0.5 | 0.5 | 0.5 | 0.5 |
| S4_DENSITY_RULE_VIOLATION | page | 8B | 0.5 | 0.5 | 0.5 | 0.5 |
| S4_DENSITY_RULE_VIOLATION | page | 30B | 0.771 | 0.854 | 0.875 | 0.729 |
| S6_IMAGE_TEXT_CONTRADICTION | page | 4B | 0.5 | 0.5 | 0.5 | 0.5 |
| S6_IMAGE_TEXT_CONTRADICTION | page | 8B | 0.5 | 0.5 | 0.5 | 0.5 |
| S6_IMAGE_TEXT_CONTRADICTION | page | 30B | 0.5 | 0.5 | 0.5 | 0.5 |
| S2_NARRATIVE_ORDER_BREAK | deck | 4B | 0.5 | 0.646 | 0.521 | 0.5 |
| S2_NARRATIVE_ORDER_BREAK | deck | 8B | 0.5 | 1.0 | 0.562 | 0.375 |
| S2_NARRATIVE_ORDER_BREAK | deck | 30B | 0.542 | 0.417 | 0.604 | 0.354 |
| S3_TERMINOLOGY_INCONSISTENCY | deck | 4B | 0.5 | 0.5 | 0.5 | 0.5 |
| S3_TERMINOLOGY_INCONSISTENCY | deck | 8B | 0.5 | 0.5 | 0.5 | 0.5 |
| S3_TERMINOLOGY_INCONSISTENCY | deck | 30B | 0.667 | 0.562 | 0.688 | 0.562 |
| S5_MISSING_LOGIC_SECTION | deck | 4B | 0.5 | 0.688 | 0.438 | 0.625 |
| S5_MISSING_LOGIC_SECTION | deck | 8B | 0.5 | 0.5 | 0.5 | 0.5 |
| S5_MISSING_LOGIC_SECTION | deck | 30B | 0.771 | 0.583 | 0.625 | 0.833 |

## Reading

- Recall-only would inflate (the 30B S6 channel reports 100% recall at 0.50 bal-acc — pure over-report). Balanced accuracy on the paired clean is the honest number; see `part1_s6_manifest.md` for the canonical example.
