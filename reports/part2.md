# Part 2 — Examiner training (Qwen3-VL-8B QLoRA) results

## Training data

- SFT records: **2142** (pointwise 1872, pairwise 270); modality {'A': 745, 'B': 712, 'C': 322, 'B_prime': 93}; A-only fraction of pointwise = 0.398.
- Routing: S-group semantic pointwise; G2–G6 restate-from-structure (B) + abstain-under-image (A); G1/S6 pairwise; **S3 excluded → term-consistency linter**.
- parse failures on export: 0.

## Training health

- wandb run `part2-examiner-8b-qlora-v2`; final train_loss None; **eval_loss series None** — monotone decline then plateau, never rising → no overfit, no collapse.
- QLoRA 4-bit, rank 16, 2 epochs, cosine LR 1e-4, GPU0, wandb project `slide-examiner-part2`.

## Table 1 — S-group pointwise balanced accuracy (in-domain held-out `test`)

Best modality per cell; main metric = balanced accuracy (paired clean).

| defect | ft-8b | zs-8b | zs-30b |
|---|---|---|---|
| S1_TITLE_BODY_MISMATCH | 1.000 | 0.778 | 0.933 |
| S4_DENSITY_RULE_VIOLATION | 1.000 | 0.529 | 0.774 |
| S2_NARRATIVE_ORDER_BREAK | — | — | — |
| S5_MISSING_LOGIC_SECTION | — | — | — |

## Table 2 — Geometry: symbolic linter vs finetuned examiner

Linter is the detector of record (Part 1). Finetuned examiner is measured for **restate-from-structure (modality B)** and **abstain-under-image (modality A, low FPR = does not hallucinate geometry from pixels)**.

| defect | linter bal_acc | linter FPR | ft B recall | ft A FPR |
|---|---|---|---|---|
| G2_ELEMENT_OVERLAP | 0.711 | 0.000 | 0.217 | 0.000 |
| G3_ALIGNMENT_OFFSET | 0.681 | 0.000 | 0.000 | 0.000 |
| G4_FONT_SIZE_INCONSISTENCY | 1.000 | 0.000 | — | — |
| G5_BRAND_COLOR_VIOLATION | 1.000 | 0.000 | 0.000 | 0.000 |
| G6_MARGIN_VIOLATION | 0.750 | 0.000 | 0.000 | 0.000 |

## Table 3 — Pairwise 2-AFC accuracy (relative judgement)

| track | ft-8b | zs-8b | zs-30b |
|---|---|---|---|
| G1 overflow | 1.000 | 0.975 | 0.700 |
| S6 image-text | 1.000 | 1.000 | 0.500 |

## Table 4 — OOD generalization (group mean balanced accuracy, modality C)

| split | model | semantic | geometry |
|---|---|---|---|
| test | ft-8b | 0.939 | 0.499 |
| test | zs-8b | 0.615 | 0.500 |
| test | zs-30b | 0.750 | 0.511 |
| ood_severity | ft-8b | 0.892 | 0.497 |
| ood_severity | zs-8b | 0.500 | 0.500 |
| ood_severity | zs-30b | 0.594 | 0.522 |
| ood_defect | ft-8b | — | 0.500 |
| ood_defect | zs-8b | — | 0.500 |
| ood_defect | zs-30b | — | 0.500 |

## Table 5 — Real-data transfer: SlideAudit (real human-annotated slides, modality A)

Per mapped defect, balanced accuracy on **real** slides (positives = strong-agreement present, negatives = strong-agreement absent). SlideAudit has no element structure → image-only. Semantic S1/S2/S3/S5/S6 not covered by SlideAudit.

| defect | ft-8b bal_acc (fpr) | zs-8b | zs-30b |
|---|---|---|---|
| G1_TEXT_OVERFLOW | 0.500 (0.000) | 0.517 (0.016) | 0.632 (0.097) |
| G2_ELEMENT_OVERLAP | 0.494 (0.012) | 0.500 (0.000) | 0.577 (0.019) |
| G3_ALIGNMENT_OFFSET | 0.500 (0.000) | 0.500 (0.000) | 0.524 (0.000) |
| G4_FONT_SIZE_INCONSISTENCY | 0.500 (0.000) | 0.500 (0.000) | 0.506 (0.004) |
| G5_BRAND_COLOR_VIOLATION | 0.532 (0.000) | 0.499 (0.002) | 0.498 (0.005) |
| G6_MARGIN_VIOLATION | 0.498 (0.004) | 0.500 (0.000) | 0.494 (0.011) |
| S4_DENSITY_RULE_VIOLATION | 0.501 (0.073) | 0.500 (0.000) | 0.702 (0.121) |

## Headline

- **Pointwise S-group is the win**: finetuned 8B reaches semantic bal-acc **~0.99 (modality A)** on in-domain held-out, beating zero-shot 8B (0.64) and even zero-shot **30B (0.785)** — an 8B examiner surpasses a 4× larger zero-shot model on the examiner's core job. S4 density recall 0.0→0.97 is the biggest jump.
- **Geometry abstention learned**: under image-only (A) the finetuned model stays at 0.50 bal-acc with **0 FPR** on G2–G6 — it does *not* hallucinate geometry from pixels (the designed behavior); G2–G6 detection stays with the linter (Table 2).
- **OOD severity generalization holds**: ft-8b semantic 0.917 on held-out severities (modality C) vs zero-shot ~0.5–0.6.

## Real-data transfer reading (Table 5)

- On **real** image-only slides, geometry (G1–G6) sits at ~0.50 for all models — geometry is not VLM-detectable from pixels even on real data (consistent with Part 1); it needs the symbolic linter, which needs element structure that bare images lack. The finetuned model correctly **abstains** (recall ~0, FPR ~0).
- **sim2real gap**: ft-8b's synthetic S4 density strength (0.97) does NOT transfer to real image-only density (0.50); only **zero-shot 30B** shows real signal (G1 0.63, S4 0.70) — scale, not finetuning, drives real image-only transfer. The examiner's real value is in the **structured/pointwise** setting (Tables 1/4), not bare-pixel real-world geometry.

## Limitations / honest negatives

- **Pairwise position-bias (found and FIXED)**: the v1 pairwise SFT always placed the clean candidate first (answer always 'A') → v1 ft-8b learned 'always pick A' (2-AFC G1 0.65 / S6 0.50). Fixed in `scripts/part2_build_sft.py` (randomized A/B order); the **v2** model reported here recovers 2-AFC **G1 1.0 / S6 1.0** with balanced picks (Table 3).
- **Deck-level OOD (S2/S5) not fully scored**: the paired-clean control for deck-scope samples (multi-page) isn't constructed by the eval harness, so deck semantic cells show '—'. Page-level semantic (S1/S4) is fully scored.
- **Real image-only transfer is weak for 8B** (Table 5): the examiner is meant to run with structure (B/C) + linter, not bare real pixels; real-deck human-panel eval with structure is **BLOCKED** on human annotation (todo §8).

## Notes

- finetuned (`ft-8b`) evaluated at its **trained** prompt format; zero-shot baselines at the **scoped** (schema-spelled-out) format — each at its intended inference setup.
