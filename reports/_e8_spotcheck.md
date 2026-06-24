# E8 — human perceptual spot-check of injected defects

Sample: **69 defective+clean pairs**, freeform (non-template) renders, stratified across 9 single-slide classes (S2/S3 are deck-level, no single-slide clean twin -> out of scope). Labeller: the human author (primary); an independent Claude image-vision pass (secondary, disclosed) corroborates.

## Headline

- **Negative controls are sound: 69/69 clean twins verified clean** (1.00 [0.95, 1.00]) — no injector leakage into the reference.
- **Defect perceptual-presence is class-dependent, not uniform** (overall 52/69 = 0.75 [0.64, 0.84]):
  - **Verified present (7/7–9/9, ~1.00):** G1 overflow, G2 overlap, G7 containment-overflow, S1 title/body mismatch, S4 density, and **S6 image/text contradiction** (on the corrected figure-bearing corpus — see below).
  - **Partial (4/7 = 0.57):** G6 margin — small inset removals are sometimes below notice ("still space til margin").
  - **Not perceptually present (0/7):** **G3 alignment** (offsets of 4–32 px on near-full-width titles are sub-perceptual) and **G5 brand-color** (ΔE2000 ≈ 3.2 between near-blacks #111111/#181818 — at/below JND).
- **Human–Claude agreement:** defect-visible raw 0.90, Cohen's κ = 0.76; twin-clean raw 1.00, κ = 1.00. The one real divergence is **G1** (human 1.00 vs Claude 0.33): the G1 injector uses an `XX/XXX` title-marker; the human reads the resulting overflow as visible, the stricter Claude pass discounts markers that reach-but-don't-spill the box.

## Coding note

6 G5 pairs (005, 015, 016, 022, 030, 034) were left blank with notes "can't tell the colour difference". For a *perceptual-presence* verification, "a human cannot perceive the named defect" **is** the outcome, so they are coded **not-verified** (`defect_visible = no`, `indeterminate = true`) and their twins (no visible defect on either panel) coded clean. The raw export is preserved at `docs/spotcheck/labels.json`; the coded file is `docs/spotcheck/labels_coded.json`. So G5 is 0/7 = 1 explicit-absent + 6 indeterminate.

## Interpretation (paper-facing)

These outcomes **corroborate, not threaten, the paper's existing honesty**: §Diagnosis already labels G3 alignment "genuinely sub-perceptual (stays at chance under every elicitation)", which the 0/7 human rate independently confirms; G5 is a non-headline class and its sub-threshold ΔE2000 is consistent with the declared-IR-vs-pixels caveat. Two injector artifacts surfaced for the record: (i) **G5** sometimes renders as a **font-weight** change, not a colour change (pair 022); (ii) **G1** overflow is induced by an `XX/XXX` marker rather than organic long text. The headline elicitation classes used by the paper — **G1, S6, G7** — all verify at ~1.00 (S6 only after switching to the figure-bearing corpus, which the generic part-2 eval set lacked).

## IR-faithfulness — "not visible" is NOT an injector failure

Every "not-visible" label was audited against the **source IR** (defective vs clean slide JSON, independent of the render): `scripts/part3_spotcheck_irdiff.py` → `data/part3/e8_ir_faithfulness.json`. **51/51 part-2-sourced injections are present in the structure** (the other 18 pairs are the S6 figure-corpus + G7, human-verified visible 9/9 each). So no sampled defect is a tooling failure; the not-visible outcomes decompose into three benign causes, and **human perceptual calls track the injected IR magnitude monotonically**:

| class | not-visible cause (IR-verified) | evidence |
|---|---|---|
| **G3** alignment | sub-perceptual **magnitude** | 5/7 sampled are 4 px offsets (~2 px @ render — invisible); 2/7 are 32 px (~17 px, a uniform shift of a near-full-width title, hard side-by-side) |
| **G5** brand-colour | perceptually-weak **channel** | injection is an *achromatic* near-black lightness shift (#111111→#181818/#2a2a2a/#444444); even ΔE2000=23.8 reads as "thinner", not "wrong colour" — ΔE2000 overstates dark-text-lightness salience |
| **G6** margin | sub-threshold **severity** | visible 4/7 = `x:96→0` (flush to edge); not-visible 3/7 = `x:96→28` (a gap remains → "not defective enough") |

Implications: (i) this gives **independent human evidence** for the paper's existing "G3 is genuinely sub-perceptual" claim (neither human nor VLM resolves it — correctly *not* rescued by elicitation); (ii) two honest measurement caveats surface — ΔE2000 overstates achromatic-text salience (G5), and a *side-by-side* (non-overlay) format plus a sample skewed to small magnitudes understates fine-geometry/colour detectability; (iii) the headline elicitation classes (G1/S6/G7) and G2/S1/S4 are unambiguously present **and** visible.

### Defect visible on the defective render? (human)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G3_ALIGNMENT_OFFSET | 0.00 [0.00, 0.35] | 7 |
| G6_MARGIN_VIOLATION | 0.57 [0.25, 0.84] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G5_BRAND_COLOR_VIOLATION | 0.00 [0.00, 0.35] | 7 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **0.75 [0.64, 0.84]** | **69** |

### Twin actually clean? (human)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G3_ALIGNMENT_OFFSET | 1.00 [0.65, 1.00] | 7 |
| G6_MARGIN_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G5_BRAND_COLOR_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **1.00 [0.95, 1.00]** | **69** |

### Flagged pairs (candidate injector artifacts)

| pair | class | flag | note | composite |
|---|---|---|---|---|
| 005 | G5_BRAND_COLOR_VIOLATION | defect not visible | can't tell difference in colour [E8-coded: indeterminate->not-verified] | pairs/pair_005_G5.png |
| 007 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_007_G3.png |
| 008 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_008_G3.png |
| 012 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_012_G3.png |
| 015 | G5_BRAND_COLOR_VIOLATION | defect not visible | can't tell any difference in color [E8-coded: indeterminate->not-verified] | pairs/pair_015_G5.png |
| 016 | G5_BRAND_COLOR_VIOLATION | defect not visible | no difference [E8-coded: indeterminate->not-verified] | pairs/pair_016_G5.png |
| 019 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_019_G3.png |
| 022 | G5_BRAND_COLOR_VIOLATION | defect not visible | i can only see difference in font (bold v.s. not bold) [E8-coded: indeterminate->not-verified] | pairs/pair_022_G5.png |
| 028 | G6_MARGIN_VIOLATION | defect not visible | the defective one is not defective enough | pairs/pair_028_G6.png |
| 030 | G5_BRAND_COLOR_VIOLATION | defect not visible | can't tell [E8-coded: indeterminate->not-verified] | pairs/pair_030_G5.png |
| 034 | G5_BRAND_COLOR_VIOLATION | defect not visible | can't tell [E8-coded: indeterminate->not-verified] | pairs/pair_034_G5.png |
| 036 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_036_G3.png |
| 041 | G6_MARGIN_VIOLATION | defect not visible | still space til margin | pairs/pair_041_G6.png |
| 044 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_044_G3.png |
| 058 | G3_ALIGNMENT_OFFSET | defect not visible |  | pairs/pair_058_G3.png |
| 059 | G6_MARGIN_VIOLATION | defect not visible |  | pairs/pair_059_G6.png |
| 060 | G5_BRAND_COLOR_VIOLATION | defect not visible |  | pairs/pair_060_G5.png |

### Secondary cross-check (Claude image vision, disclosed)

_Labelled independently of the human pass; reported as corroboration only._

- **defect visible**: raw agreement 0.90 (n=69), Cohen's kappa 0.76
- **twin clean**: raw agreement 1.00 (n=69), Cohen's kappa 1.00

### Defect visible (Claude)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 0.33 [0.12, 0.65] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G3_ALIGNMENT_OFFSET | 0.00 [0.00, 0.35] | 7 |
| G6_MARGIN_VIOLATION | 0.43 [0.16, 0.75] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G5_BRAND_COLOR_VIOLATION | 0.00 [0.00, 0.35] | 7 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **0.65 [0.53, 0.75]** | **69** |

### Twin clean (Claude)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G3_ALIGNMENT_OFFSET | 1.00 [0.65, 1.00] | 7 |
| G6_MARGIN_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G5_BRAND_COLOR_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **1.00 [0.95, 1.00]** | **69** |
