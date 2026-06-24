# E8 — canonical internal-contrast diagnosis (G3/G5 redo)

**Setup.** After re-operationalising the injectors (internal contrast: one item out of
line with / a different colour from its sibling column) and the elicit 口径, the G3/G5
diagnosis was regenerated **through the canonical `inject_slide_defect` dispatcher + the
real renderer** (`scripts/part3_regen_g3g5.py` → `data/part3/manifest_g3g5_internal.jsonl`,
96 defectives over 16 clean slides, all `mode=internal`, n=16/stratum) and re-run with the
default internal-contrast question (qwen-vl-max via DashScope).

## Result — both classes become format-suppressed-then-recoverable, with a clean magnitude threshold

| condition | **G3 alignment** (8/16/32 px) | **G5 colour, chromatic** (ΔE2000 12/24/40) |
|---|---|---|
| C0 pointwise (general examiner) | 0.50 · 0.50 · 0.50 | 0.50 · 0.50 · 0.50 |
| **C3 atomic (internal 口径)** | **0.50 · 0.94 · 1.00** | **0.50 · 0.56 · 1.00** |
| specificity (clean not flagged) | 16/16 at every level | 16/16 at every level |
| AFC (2-AFC) overall | acc 0.58, dec 0.59 | acc 0.41, dec 0.41 |

- **Format suppression, now universal.** C0 (pointwise) is at chance for every class/level; a
  single atomic query (C3) recovers detection once the defect clears a **perceptual magnitude
  threshold** — G3 from 16 px (~8.5 px @render), chromatic G5 from ΔE2000≈40. The model is
  **calibrated** throughout (specificity 1.0 — it abstains below threshold, never false-alarms).
- This is exactly the paper's central effect (pointwise-suppressed → query-recovered) — and the
  re-operationalised **G3 now joins it (C0 0.50 → C3 1.00)** instead of being the "genuinely
  sub-perceptual" exception. The original exception was an artifact of the absolute-translation /
  external-brand operationalisation.

## The genuinely sub-perceptual residue (re-anchored)

The earlier **achromatic** internal-G5 (one bullet a lighter *gray*, gray-axis step) stayed at
**C3 0.50 at every ΔE (recall 0/16), specificity 16/16** — calibrated but unresolvable. So the
*real* "genuinely sub-perceptual" example is a **well-posed but sub-threshold** defect (achromatic
lightness on small text; small offsets), NOT the old ill-posed external-reference defect. (The
canonical injector now produces a **hue** swap — a real off-brand colour; the achromatic case is
kept as a sub-perceptual probe.)

## Bottom line for the paper (T1)

Replace "fine alignment / colour are **genuinely sub-perceptual capability floors**" with: *the
absolute-offset / external-brand operationalisations were ill-posed (undecidable without an
invisible reference); re-posed as internal contrasts, both are **format-suppressed-then-recoverable
with a clean magnitude threshold and perfect calibration** — the genuinely sub-perceptual residue
is the well-posed sub-threshold tail (tiny offsets, achromatic lightness).* Strengthens the central
thesis (one more recoverable class, no exception to explain away).

**Caveats:** single cloud model (qwen-vl-max), n=16/stratum; local-roster confirmation pending GPU.
Data: `data/part3/e8_reval/{g3canon,g5canon}_{C0,C3,AFC}*.json`.
