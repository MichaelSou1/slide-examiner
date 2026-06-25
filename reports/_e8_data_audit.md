# E8 data-integrity audit (2026-06-25)

Triggered by reviewer scrutiny of the G3 results ("can VLMs really not see bullet
misalignment? is the injection magnitude too small?"). Visual + pixel + pairing audit
of all four E8 internal-口径 manifests. **Three bugs found; two invalidate GPU results.**

## Bug 1 — `manifest_g3g5_internal.jsonl` shares ONE clean twin (CRITICAL)
All 240 defectives point at a single `clean_slide__clean/clean.png` (a *different deck*,
"Decisions for planning this quarter"; the 32px defective is "Churn is quietly compounding").
- `distinct clean imgs = 1` for 240 defectives; no per-deck clean was rendered.
- **Impact:** 2-AFC partner is a fixed unrelated slide (not the defective's own aligned twin)
  → AFC confounded by content, not alignment. Specificity is statistically degenerate (n=1
  distinct clean repeated 120×, reported as n=120). **Recall is still valid** (measured on the
  genuine injected defectives), so the C0→C3 recall recovery survives, but bal-acc/AFC do not.
- **Cause:** this manifest was built by an earlier/separate path, NOT the canonical
  `part3_e8_regen_corpus.py` (whose `coverage`/`part1` targets DO render matched per-deck twins).
- **Fix:** discard `g3g5_internal`; use `coverage_internal` (100/100 distinct same-deck twins).

## Bug 2 — template renders snap-absorb the G3 offset (known hazard, but it leaked in)
`coverage_internal` & `geometry_internal` carry BOTH `/freeform/` and `/template/` renders.
Template = snap-to-master → the within-column nudge is absorbed → `defective.png == clean.png`
(pixel-identical, **defect invisible**). Flat **50% of every G3 stratum** is template (even 32px),
G5 is 0% (colour survives template). This is the documented §4 template-absorption hazard.

## Bug 3 — the `freeform_only` filter was a silent no-op (ROOT CAUSE)
`part3_p2_eval.freeform_only()` and elicit `--freeform-only` tested for a `__template` **suffix**,
but the E8 corpora encode the variant as a `/template/` **directory**. So the filter matched
nothing → template-degenerate G3 records polluted every consumer:
- **Row 3 (p2_eval coverage):** ran on 100 G3 = 50 freeform + 50 invisible-template → G3 diluted.
- **standalone linter recompute:** same dilution.
- **Fixed** at both sites (match `__template` OR `/template/`).

### Effect of the fix — linter coverage on **freeform-only** G3/G5
| metric | template-polluted (wrong) | freeform-only (correct) |
|---|---|---|
| G3 linter bal-acc | 0.70 (recall 0.40) | **0.90 (recall 0.80)** |
| G3 per-stratum 4/8/16/32px | 0.50 each | **1.00 each** |
| G3 2px (sub-threshold) | 0.00 | 0.00 (correct abstain) |
| G5 linter | 1.00 | 1.00 |
| false-fire on clean IR | 0 | 0 |
The "flat 50%" was entirely contamination. Freeform linter = **perfect on supra-threshold G3
(≥4px), 0 FP**; abstains only at 2px (the well-posed sub-perceptual residue).

## Clean-data confirmation (freeform-only)
| manifest | freeform defectives | degenerate@any stratum | clean-twin mismatch |
|---|---|---|---|
| coverage_internal | 90 (G3 50, G5 40) | 0 | 0/90 |
| geometry_internal | 72 (G3 40, G5 32) | 0 | 0/72 |
| real_internal_g3 | 41 (G3) | 0 (no template) | 0/41 |
Every freeform defective differs from its correctly-matched same-deck clean twin at all strata
(2px changes ~15k px from antialiasing but is sub-perceptual → linter rightly abstains).

## Visual confirmation
The **32px** G3 freeform render shows an obvious right-shift of the middle box
(`runs/part3/g3g5_internal/g3i_32_002/defective.png`); VLMs detect it (C3 0.85, AFC 0.84 on the
buggy run). So it is NOT "blind to all bullet misalignment" — the misses are at small offsets
(8/16px ≈ 0.8–1.6% width; cloud qwen-vl-max recovered at 16px, the local AWQ roster only at 32px).

## Status of GPU results
| Row | status | reason |
|---|---|---|
| Row 1 (diagnosis, g3g5_internal) | **INVALID (AFC/spec)** | shared clean; recall valid only |
| Row 3 (coverage p2_eval) | **INVALID** | template-polluted; killed mid-run |
| Row 5 (real-CC) | not done | killed mid body-run (data itself clean) |
| Row 2 (modality) | not run | — |
| Row 4 (reward G5) | valid-ish | G5 renders in template too; n=80 mixed (ff+tmpl) |
| CPU linter recompute | **VALID (fixed)** | freeform-only: G3 0.90, G5 1.00 |

## Re-run plan (PAUSED — awaiting go-ahead, no GPU per user)
1. Corrected Row 1: roster × {C0,C3,AFC} on `coverage_internal` **freeform-only** (matched twins;
   G3 50 = 10/stratum, G5 40). Roster tag `covint` already wired; pass `--freeform-only`.
2. Row 3: p2_eval on coverage_internal (filter now works).
3. Row 5: pc_real on real_internal_g3 (clean).
4. Row 2: roster modality A/B/C on geometry_internal **freeform-only**.
5. (optional) Row 4 re-run freeform-only G5 (n=40) for consistency.

Code fixes already committed to working tree: `part3_p2_eval.freeform_only` (+ `_is_template`),
`part3_elicit.py --freeform-only`, `part3_e8_linter_coverage.py` (freeform filter), roster `covint`
tag. No GPU was launched for the corrected runs.

---

## Second pass — deep audit (2026-06-25, CPU only)
Re-reviewed at user request. **No new bugs beyond the three above.** New positive verifications:

| check | result |
|---|---|
| internal-contrast **well-posedness** | **0 ill-posed** — clean has aligned(G3)/same-colour(G5) siblings; defective changes EXACTLY one element (coverage 90/90, geometry 72/72) |
| **IR-faithfulness** | exactly one element changes per defective; no multi/zero change |
| **G5 chromatic** | 0 gray-axis — true hue-swap (#222222→#2d2721/#50371f…) |
| **magnitude faithful** | `offset_px` = rendered px (IR & render both 1920×1080, scale 1.000); xcorr confirms exact 8/16/32px shifts |
| duplicate sample_ids | 0 (all manifests) |
| NO_DEFECT controls clean | linter fires 0/54 (coverage), 0/42 (geometry) |
| deck leakage coverage↔geometry | 0 (disjoint part2 vs part1 pools; 80 vs 36 decks) |
| dimensions | synthetic 1920×1080 uniform; real varies per-deck (expected for Zenodo) |

**Magnitude, quantified honestly (re the "injection too small" concern):** injections are FAITHFUL
but subtle in-render — largest stratum 32px = **1.67% of width**, others 0.10–0.83%. So "VLM misses
small G3" = "misses sub-2%-width shifts" (a fair sub→supra sweep, not broken). OPTIONAL: add a
48–64px stratum (2.5–3.3%) to map the saturation point and show VLMs nail clearly-visible misalign.

**Extra nail in g3g5_internal:** it renders at 1024×576 (different scale from the good 1920 corpus)
AND its shared clean is a different deck → the defective's true shift is literally unmeasurable
(xcorr across unrelated slides is meaningless). Discard confirmed.

**Verdict:** the GOOD corpora (coverage_internal, geometry_internal, real_internal_g3) are clean,
well-posed, IR-faithful, leakage-free. The only defects were the three above (2 fixed in code, 1 =
discard g3g5_internal).

---

## Third pass — saturation tail added + 4th filter-convention bug (2026-06-25)
User asked to add a larger G3 stratum to map the detection saturation point.
`scripts/part3_e8_add_g3_strata.py` appends **G3 48 px (2.5 %) and 64 px (3.3 %)** to coverage &
geometry via the same production pipeline (G3-only, no re-sample of the audited 2-32 px records).
- coverage: +40 (48/64 ×10 ff + ×10 tmpl) -> G3 freeform strata {2,4,8,16,32,48,64}×10.
- geometry: +32 -> G3 freeform ×8 each.
- **Audit of new strata:** 0 degenerate (freeform), well-posed 100 %, IR-faithful, render shift =
  exactly 48/64 px (xcorr), linter detects 48/64 = 1.00.

**4th bug (filter convention, fixed):** the addendum rendered into `…/template_g3sat/` dirs, which the
`/template/`-substring check still missed. Root-caused the filter to the AUTHORITATIVE
`metadata.template_condition` field (present on all synthetic records) with path heuristics only as a
fallback — fixed in `part3_p2_eval._is_template` AND elicit `--freeform-only`. Verified:
coverage 274 -> 137 freeform; G3 freeform strata all ×10.

**Linter (freeform, full curve):** G3 bal-acc **0.929** (recall 0.86; per-stratum 2px 0.00, 4-64px all
1.00), G5 1.00, 0 FP. Saturation: linter already perfect ≥4px; the VLM saturation point is what the
GPU re-run (Row 1, coverage-freeform, p1e8c) now measures across 2-64px.

GPU re-runs LAUNCHED (user said go): Row 1 = roster C0/C3/AFC on coverage-freeform, 2-server
(strong-pair GPU0,1 + weak-trio GPU2,3), out-prefix p1e8c. Rows 3/5/2/4 to follow.
