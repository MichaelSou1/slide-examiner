# Part 1 — SlideProbe diagnostic synthesis (three-track)

Consolidation of the frozen Part 1 matrix under the three-track design (SPEC §3.0): **Track L** symbolic linter for G-group geometry, **Track E** pointwise S-group attribution (balanced accuracy on paired clean), **Track P** pairwise / 2-AFC for the consistency-check defects. Main metric throughout is **balanced accuracy + paired clean** — never recall alone.

## Table 1 — Track E: S-group pointwise channel picture (balanced accuracy)

Mean balanced accuracy over each level's defects, per model × modality. B′ = VLM-image caption held fixed at the 30B caption across sizes.

| level | model | A | B | B′ | C |
|---|---|---|---|---|---|
| page | 4B | 0.5 | 0.5 | 0.5 | 0.5 |
| page | 8B | 0.583 | 0.5 | 0.5 | 0.583 |
| page | 30B | 0.745 | 0.701 | 0.625 | 0.722 |
| deck | 4B | 0.5 | 0.611 | 0.486 | 0.542 |
| deck | 8B | 0.5 | 0.667 | 0.521 | 0.458 |
| deck | 30B | 0.66 | 0.521 | 0.639 | 0.583 |

Per-defect highlights (best channel):
- **S1_TITLE_BODY_MISMATCH** (page): best = 30B / A @ bal-acc 0.963
- **S4_DENSITY_RULE_VIOLATION** (page): best = 30B / B_prime @ bal-acc 0.875
- **S6_IMAGE_TEXT_CONTRADICTION** (page): best = 4B / A @ bal-acc 0.5
- **S2_NARRATIVE_ORDER_BREAK** (deck): best = 8B / B @ bal-acc 1.0
- **S3_TERMINOLOGY_INCONSISTENCY** (deck): best = 30B / B_prime @ bal-acc 0.688
- **S5_MISSING_LOGIC_SECTION** (deck): best = 30B / C @ bal-acc 0.833

## Table 2 — Track P: forced-choice vs pointwise (H-rel)

| defect | pointwise bal-acc | 2-AFC robust acc | verdict |
|---|---|---|---|
| G1_TEXT_OVERFLOW (8B) | 0.5 | 1.0 (robust 1.0) | **revived** — relative>>absolute |
| G3_ALIGNMENT_OFFSET (8B) | 0.5 | 0.5 (robust 0.0) | floor — true perceptual threshold |
| S6_IMAGE_TEXT_CONTRADICTION (30B) | 0.5 | 1.0 | **revived** — relative>>absolute |
| S3_TERMINOLOGY_INCONSISTENCY (30B) | (deck, ~random) | 0.625 (robust 0.25) | **NOT revived** — biased, sub-threshold reading |

- G1 overflow and S6 image-text contradiction: pointwise random → forced-choice ~100% robust. Two independent pieces of **H-rel** (relative judgement >> absolute scoring).
- **S3 is the honest counterexample**: terminology inconsistency is *not* rescued by forced-choice (62%, heavy position bias, 2/8 robust) — reading the same term across deck pages and spotting a subtle variant is below threshold even side-by-side. H-rel is a real effect, not universal.
- **S3 is not a VLM task at all** — it leaves the examiner. The B (structure) channel already feeds the full deck text (both variants present) yet scores 0.56; the bottleneck is OCR-from-pixels + pointwise yes/no framing, not the reasoning. So S3 is routed to a **symbolic term-consistency linter** (`slide_examiner/term_consistency.py`: extract terms → occurrence table → near-duplicate cluster, image-free) — on the frozen S3 subset it is **recall 1.00 / 0 FP on 40 deck controls / bal-acc 1.000** vs the VLM's 0.69 (`reports/part1_term_consistency.md`). Synthetic '…X'-suffix variants are fully symbolic; for fuzzy real-world drift (K8s/Kubernetes) the same occurrence table feeds a text-LLM, and `--glossary` supports the corporate term-sheet variant.

## Table 3 — Track L: linter geometry (detector of record) + VLM threshold flag

| defect | linter recall (freeform) | template absorption | FP | VLM pointwise |
|---|---|---|---|---|
| G1_TEXT_OVERFLOW | 1.0 | 1.0 | 0/80 | broke (30B only, A recall 0.5 / bal-acc 0.65) |
| G2_ELEMENT_OVERLAP | 0.75 | 1.0 | 0/80 | random |
| G3_ALIGNMENT_OFFSET | 0.8 | 1.0 | 0/80 | random |
| G4_FONT_SIZE_INCONSISTENCY | 1.0 | 0.0 | 0/80 | random |
| G5_BRAND_COLOR_VIOLATION | 1.0 | 0.0 | 0/80 | random |
| G6_MARGIN_VIOLATION | 1.0 | 1.0 | 0/80 | random |

- Linter is the **detector of record** for G2–G6 (0 FP on all clean; freeform recall floor-limited only by its own deliberate thresholds). Psychophysical θ-curve is drawn on the linter's continuous reading (`part1_linter_track.md`), not the VLM.
- VLM pointwise geometry is reported only as **broke / didn't break random** — 4B/8B random everywhere, 30B breaks only G1 overflow (A=0.5); confirmed invariant across 5 encoder families and 1536/2048 resolution.

## Gates (H1 / H1-tpl / H-rel) and Go/No-Go

- **H1_restated** — SUPPORTED: Pointwise VLM geometry detection is unreachable at <=30B and does not improve with encoder family or resolution; only G1 overflow is reachable in forced-choice (8B already 100%).
- **H1_tpl_restated** — SUPPORTED: Template (snap-to-master) absorption is a symbolic, model-decoupled property; the VLM-detection-drop is unmeasurable below 30B because geometry pointwise is already at the floor.
- **H_rel** — SUPPORTED (with a documented boundary): Relative (forced-choice) judgement >> absolute (pointwise) scoring for consistency-check defects.
- **track_E_examiner_effective** — SUPPORTED: S-group pointwise attribution is a real examiner signal (not random) under balanced accuracy.

### Decision: **GO to Part 2**

H-rel holds (G1+S6) and S-group examiner is effective under balanced accuracy → train an 8B examiner with pointwise (S1/S4/S5) + pairwise (G1-overflow/S6) dual output, G2–G6 labels fed from the linter. G-group→linter is settled and goes straight into the Part 2/3 hybrid architecture. S3 leaves the VLM examiner entirely → slide_examiner.term_consistency linter (symbolic, image-free; bal-acc 1.000 vs VLM 0.69 on the frozen subset; text-LLM + --glossary for fuzzy real-world drift), since the B channel proves the text was present and the VLM still failed.
