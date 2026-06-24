# E8 — affected-experiments inventory (ill-posed G3/G5 operationalisation)

**Scope of the problem.** Only **G3 (alignment)** and **G5 (brand-colour)** are ill-posed: their injected defect is defined against an **invisible external reference** (an absolute expected position / a brand palette), so "is it wrong?" is undecidable from the slide alone — at chance for model *and* human. Every other class is an **internal/visible** inconsistency and is fine: G1 text-vs-its-box, G2 element-vs-element, G6 element-vs-slide-edge, G7 content-vs-container, S6 figure-vs-text (after the figure-corpus fix). The re-exam (qwen-vl-max, internal-contrast 口径) shows: G3 → C3 **1.00**, human 8/8; G5 → clean magnitude curve (ΔE40 **1.00**, calibrated), vs original both ~chance/abstain.

**Root cause (the injectors).** `slide_examiner/injection.py`: `inject_alignment_offset` (absolute translation vs `expected_bbox`) and `inject_brand_color_violation` (ΔE2000 vs declared brand colour). These feed data generation across **Part 1 / Part 2 / Part 3** (`part1_synthesis`, `part2_synthesis`, `part2_build_sft`, `part3_real_inject`, `part3_p2_eval`, `part1_build_corpus`, …). NB the linter (`geometry.py:detect_alignment_offsets`) already has BOTH an external `expected_bbox` path **and** an internal `alignment_group` path — the injection used the external one; the linter's internal rule is *vindicated*, not broken.

---

## Tier 1 — conclusion OVERTURNED (must rewrite; re-run done/needed)

| where | claim | status |
|---|---|---|
| §Diagnosis (main.tex 56, 96, 108, 286, 300, 313–314) | "**G3 alignment genuinely sub-perceptual** — forced choice does *not* rescue it (stays at chance)" | **FALSE as stated.** Re-exam: internal relative-misalignment → C3 1.00, AFC 0.75, human 8/8. It was the absolute-translation injection that was ill-posed. **Rewrite** to "the absolute-offset operationalisation is ill-posed; a relative misalignment is format-suppressed-then-recoverable like the others." |
| §Diagnosis dichotomy (main.tex 96, 201, 305, 804) | "two kinds: **recoverable (G1/S6/G7) vs genuinely-sub-perceptual (G3)**" | **Revised.** G3 moves to the recoverable side. A *genuine* sub-perceptual example now = a **well-posed but sub-threshold** defect (e.g. internal-G5 at ΔE≈12: 0/4 recall but specificity 1.0 — calibrated, not confused). |
| §Modality A/B/C ablation (main.tex 673, 685–686, 700; `part1_geometry_report`, `part1_encoder_report`) | "**G3 alignment is a capability floor at chance in EVERY channel** (A=B=C≈0.5)" | **Affected** — used absolute-G3. Under internal 口径 the pixel channel (A) recovers (C3 1.00). **Re-run on internal-G3 or rewrite/scope.** |

## Tier 2 — FRAMING / caveat (valid at IR-rule level; perceptual reframe)

| where | claim | reframe |
|---|---|---|
| §Coverage table (main.tex 464–465) | "**linter owns G3/G5 at 1.00**, VLM at chance (0.47/0.50)" | The linter detects an **IR-conformance** violation (position-vs-declared, colour-vs-brand) — valid for IR-owning deployment. But "VLM at chance" was the ill-posed 口径; under internal-contrast the VLM recovers (G3 C3 1.00; G5 ΔE40 1.00). Reframe the column as "IR-rule coverage" + note VLM handles the internal forms. |
| §Reward audit (main.tex 527, 541) | "reward models **blind to brand-colour G5** (≤0.04), linter owns at 1.00" | About external-colour G5. Holds as "narrow rewards miss declared-brand violations"; OPTIONAL re-test on internal-colour-contrast. Reward main line is **G7**, so low priority. |
| §Taxonomy routing (main.tex 250, 252, 129) | "G3/G5 → symbolic **linter**" | Still defensible (linter owns IR-rules at ~0 FP), but it's not because the VLM *can't* — it's because the linter is cheaper/exact on IR. Soften "the VLM is blind." |
| line 432 | "pointwise recovers per class — brand-colour 0.52→0.81, alignment 0.56→0.72" | Already a *partial-recovery* signal that contradicts "stays at chance" — **harmonise** with the new internal-口径 numbers (it was always pointing this way). |

## Tier 3 — DATASET-level (trained/measured on ill-posed labels)

| where | impact |
|---|---|
| Part 2 examiner SFT + eval (`part2_build_sft`, `part2_synthesis`, examiner per-defect G3/G5) | Trained & scored on absolute-G3 / external-G5. **Per-G3/G5 examiner columns measure ill-posed defects** (interpret with care / re-label). Headline **8B>30B** aggregates over all classes — G3/G5 a minority, so headline is *mostly* robust but should be re-checked with G3/G5 excluded or re-operationalised. |
| Part 1 corpus / freeze (`part1_build_corpus`, `part1_freeze_dataset`) | The injected G3/G5 items in the frozen corpus are ill-posed; any per-class G3/G5 number inherits it. |

## Tier 4 — NOT affected (safe / vindicated)

- **G1 / G2 / G6 / G7** — internal/visible by construction; their elicitation + coverage + 8B>30B stand. (Human spot-check: ~100% perceptible.)
- **S6** — separately fixed (valid figure corpus; 2-AFC 1.00 reproduced).
- **Downstream / self-refine (E6)** — coverage-axis, not G3/G5-perception.
- **The linter's `alignment_group` rule** — already internal-contrast; **vindicated** as the correct operationalisation.
- **IR-faithfulness** — 51/51 injections present (no tooling failure); the issue is *operationalisation*, not a bug.

---

## Recommended redo scope (minimal-sufficient)

1. **Re-operationalise the injectors** (`inject_alignment_offset` → relative/group-misalignment; add `inject_color_inconsistency` = one element off its siblings). Root fix; everything downstream then regenerates correctly. *(generators already prototyped: `part3_g3_relmisalign.py`, `part3_g5_internal.py`.)*
2. **Re-run the Part-3 diagnosis** (C0/C3/2-AFC) on internal-G3/G5 — **done directionally** (cloud qwen-vl-max); firm up n + local-roster confirm.
3. **Re-run / rewrite the Part-1 Modality A/B/C** G3 cell (Tier 1) — the "floor in every channel" claim.
4. **Rewrite** Tier-1 prose; **reframe** Tier-2 (coverage/taxonomy/reward) as IR-rule + internal-recoverable; **caveat** Tier-3 (examiner per-G3/G5).
5. **Keep** the "genuinely sub-perceptual" concept but re-anchor it to a *well-posed sub-threshold* example (internal-G5 ΔE12) — which the data already supports.

**Not required:** re-running G1/G2/G6/G7/S6, downstream, or the reward G7 line.
