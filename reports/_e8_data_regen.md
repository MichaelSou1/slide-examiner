# E8 Data-regen — internal-contrast G3/G5 datasets (no-GPU / Playwright + LibreOffice)

**Date:** 2026-06-24. **Status:** DONE — verifier `scripts/part3_e8_verify_regen.py` = **ALL PASS**.

## Why
The E8 re-operationalisation makes G3 (alignment) and G5 (brand-colour) an **INTERNAL contrast** — one
member shifted/recoloured out of an aligned sibling column, decidable from the slide alone, no invisible
external reference. The old absolute-offset / external-brand injectors (`mode=absolute_fallback`) had
seeded the G3/G5 cells of three datasets with the ill-posed defect. This regenerates those datasets
through the **same production pipeline** the rest of the corpus uses, restricted to {G3,G5} so every other
class's frozen numbers are untouched.

## Datasets produced

| # | dataset | file | composition | renderer |
|---|---|---|---|---|
| 1 | **Part-1 corpus** (Modality A/B/C attribution, paper §4) | `data/part1/manifest_geometry_internal.jsonl` | 186 rec — G3 80 / G5 64 / NO_DEFECT 42; freeform+template | Playwright |
| 2 | **Part-3 coverage** (Table 2 / Result 2a) | `data/part3/manifest_coverage_internal.jsonl` | 234 rec — G3 100 / G5 80 / NO_DEFECT 54; freeform+template | Playwright |
| 3 | **real-CC internal-G3** (Modality-C real, Result 4) | `data/part3/manifest_real_internal_g3.jsonl` | 41 pairs, all `mode=internal` | LibreOffice |

Severity grids span **floor → recovery** (the diagnosis anchors): G3 offset `{2,4,8,16,32}` px, G5 ΔE2000
`{6,12,24,40}` (the taxonomy ceiling is ΔE 24; extended to 40 here so the corpus can exhibit the very
recovery the attribution/coverage measure). Each synthetic record carries the full schema (defective `slide`
IR + `oracle` + `pair` with clean/defective IR JSONs + `metadata.render` + `labels`) plus matched NO_DEFECT
negatives, so Modality B/C and the symbolic linter both work and the VLM clean control finds the paired clean
image.

## How
- **Synthetic (1,2):** `scripts/part3_e8_regen_corpus.py` — restricts `build_synthetic_manifest` to {G3,G5}
  (driving the internal injectors via the canonical `inject_slide_defect` dispatcher), renders every clean +
  defective slide with `render_manifest` (real Playwright), merges freeform+template with `__cond`-qualified
  sample_ids. Part-1 draws on the 12-deck Part-1 pool, coverage on the 28-deck Part-2 pool.
- **Real-CC (3):** `scripts/part3_real_inject.py::mut_g3` rewritten from an absolute nudge to an **internal
  contrast** — `_aligned_column` finds a ≥3-deep column of shapes sharing (within 12 px) a left edge, and the
  middle member is shifted out of line (18–44 px). Two self-checks gate each pair: the existing
  **pixel-change** check (drops snap/absorbed pairs) and a new **IR-faithfulness** check (drops pairs whose
  injected offset does not survive into the lossless `python-pptx` oracle — a few placeholder-inherited shapes
  reflow in pixels but barely move in the IR, which would make the structure channel ill-posed).

## Validation (`scripts/part3_e8_verify_regen.py`)
- **Operationalisation:** every G3/G5 label across all three datasets is `mode=internal`; 0 `absolute_fallback`.
- **Renders:** 100% of records have an on-disk image (186/186, 234/234, defective 41/41 + clean 41/41).
- **Linter calibration (freeform, the "defect present" set)** — vindicates the *fine-geometry → symbolic
  linter* routing (cheaper + exact, near-0 FP, **not** "VLM is blind"):
  - Part-1: G3 ≥8 px detect **24/24**, G5 detect **32/32**, **0/40 & 0/32 false-fire** on the paired clean IR.
  - Coverage: G3 ≥8 px detect **30/30**, G5 detect **40/40**, **0/50 & 0/40 false-fire**.
  - Sub-threshold G3 (2–4 px) correctly **abstains** (linter operating point 4 px) = the re-anchored
    *well-posed sub-threshold residue*, not a false negative.
- **Template snap-absorption (the §4 hazard, internal 口径):** under `template`, the within-column G3 nudge is
  **fully absorbed** (defective IR == clean IR, linter 0/40) while G5 colour **survives** — exactly the
  "template absorbs geometry, semantics/colour survive" finding, now reproduced on the internal defect.
- **Real-deck render-fidelity (positive control):** `pc_real_internal_g3_fidelity.json` overall rendered-rate
  **0.89** (3/46 pixel-absorbed, 2/46 IR-unfaithful) — far below the synthetic enterprise template's 45%
  absorption, confirming real free-form decks render injected geometry faithfully.

## Scope / hand-off
These manifests are the **inputs** for downstream scoring, which lives in other todo sections:
- **GPU roster re-run** (`part3_p1_roster.py --tags internal --conds C0 C3 AFC`, rows 1–3,5) consumes the
  synthetic + real manifests for the C2/C3/AFC × roster numbers.
- **CPU recompute** (Table-2 linter column; 45%-snap fidelity) — calibration is confirmed in-line above; the
  scorer pass that writes the numeric table cells is still TODO.
- **Paper edits (P4)** land after the roster numbers — replace the buggy G3/G5 cells, drop the false
  "genuinely sub-perceptual capability floor", re-anchor to the well-posed sub-threshold tail.

_Artifacts: drivers `scripts/part3_e8_regen_corpus.py`, `scripts/part3_real_inject.py` (mut_g3); verifier
`scripts/part3_e8_verify_regen.py`; fidelity `data/part3/pc_real_internal_g3_fidelity.json`._
