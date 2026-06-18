# Part 2 — Examiner training (Qwen3-VL-8B QLoRA) results

## Training data

- SFT records: **2142** (pointwise 1872, pairwise 270); modality {'A': 747, 'B': 705, 'C': 325, 'B_prime': 95}; A-only fraction of pointwise = 0.399.
- Routing: S-group semantic pointwise; G2–G6 restate-from-structure (B) + abstain-under-image (A); G1/S6 pairwise; **S3 excluded → term-consistency linter**.
- parse failures on export: 0.

## Training health

- last train loss = 0.01801, eval_loss trajectory = [].
- QLoRA 4-bit, rank 16, 2 epochs, cosine LR 1e-4, GPU0, wandb project `slide-examiner-part2`.

## Table 1 — S-group pointwise balanced accuracy (in-domain held-out `test`)

Best modality per cell; main metric = balanced accuracy (paired clean).

| defect | ft-8b | zs-8b | zs-30b |
|---|---|---|---|
| S1_TITLE_BODY_MISMATCH | 1.000 | 0.778 | 0.933 |
| S4_DENSITY_RULE_VIOLATION | 0.983 | 0.529 | 0.774 |
| S2_NARRATIVE_ORDER_BREAK | — | — | — |
| S5_MISSING_LOGIC_SECTION | — | — | — |

## Table 2 — Geometry: symbolic linter vs finetuned examiner

Linter is the detector of record (Part 1). Finetuned examiner is measured for **restate-from-structure (modality B)** and **abstain-under-image (modality A, low FPR = does not hallucinate geometry from pixels)**.

| defect | linter bal_acc | linter FPR | ft B recall | ft A FPR |
|---|---|---|---|---|
| G2_ELEMENT_OVERLAP | 0.711 | 0.000 | 0.300 | 0.000 |
| G3_ALIGNMENT_OFFSET | 0.681 | 0.000 | 0.000 | 0.000 |
| G4_FONT_SIZE_INCONSISTENCY | 1.000 | 0.000 | — | — |
| G5_BRAND_COLOR_VIOLATION | 1.000 | 0.000 | 0.000 | 0.000 |
| G6_MARGIN_VIOLATION | 0.750 | 0.000 | 0.000 | 0.000 |

## Table 3 — Pairwise 2-AFC accuracy (relative judgement)

| track | ft-8b | zs-8b | zs-30b |
|---|---|---|---|
| G1 overflow | 0.650 | 0.975 | 0.700 |
| S6 image-text | 0.500 | 1.000 | 0.500 |

## Table 4 — OOD generalization (group mean balanced accuracy, modality C)

| split | model | semantic | geometry |
|---|---|---|---|
| test | ft-8b | 0.944 | 0.499 |
| test | zs-8b | 0.615 | 0.500 |
| test | zs-30b | 0.750 | 0.511 |
| ood_severity | ft-8b | 0.917 | 0.500 |
| ood_severity | zs-8b | 0.500 | 0.500 |
| ood_severity | zs-30b | 0.594 | 0.522 |
| ood_defect | ft-8b | — | 0.500 |
| ood_defect | zs-8b | — | 0.500 |
| ood_defect | zs-30b | — | 0.500 |

## Notes

- finetuned (`ft-8b`) evaluated at its **trained** prompt format; zero-shot baselines at the **scoped** (schema-spelled-out) format — each at its intended inference setup.
- Real-deck human-panel transfer eval is **blocked** (needs human annotation); tracked in todo §8.
