# G6 page-offset margin corpus — READY (audited; body-model GPU run in flight)

`data/part3/manifest_g6_internal.jsonl` (208 rec: 160 G6 = 80 freeform + 80 template across
8 margin strata, 48 NO_DEFECT). Generator `scripts/part3_e8_make_g6_internal.py`. CPU/Playwright.

## Design — PAGE OFFSET (decoupled from G3 by construction)
The WHOLE content block translates toward the left edge so the shifted-side (left) margin
shrinks, leaving asymmetric whitespace on the right. Content starts **balanced (96px both
sides)**; the defect moves every element together → **internal alignment is preserved**, only
the block-vs-page position is wrong. (A *single* shifted element would instead read as G3
misalignment — that is the clean conceptual split: single→misalign, all-together→margin.)
Decidable from the slide alone (asymmetric margins + edge-crowding), no invisible reference.
- **Strata = resulting left margin (px):** 80, 64, 48, 32, 16, 8, 0, −16 (mild asymmetry →
  flush with the edge → content overruns/clipped). Full range generated; report per-stratum
  (let the data speak, like G3).
- Injector: `inject_margin_violation(..., page_margin_px=)` (mode `internal_page_offset`);
  legacy single-element absolute path kept as fallback. 19 injection/geometry tests pass.

## Audit — ALL CLEAN
| check | result |
|---|---|
| matched per-deck twins | 160 distinct def + **160 distinct clean, 160/160 same-deck** |
| render fidelity | freeform 80/80 render (def≠clean); template 80/80 **snap-absorbed** (def==clean) |
| **internal alignment preserved** | **80/80** (relative element offsets identical to the clean) — the G3 decoupling |
| magnitude faithful | **80/80** rendered leftmost-x == labelled left_margin (1920 frame) |
| linter | fires margin<32 (16/8/0/−16 = 10/10 each), abstains 80/64/48/32; **0 FP clean + 0 FP NO_DEFECT** |
| hygiene | 1920×1080; metadata.template_condition on all 208; 0 missing IR; freeform_only→104 |
| visual | confirmed: whole block shoved left (title flush at edge), big empty right margin, elements still mutually aligned |

## Linter coverage (CPU, freeform, per-stratum)
overall **0.75** (recall 0.50, spec 1.00, 0 FP). Per-stratum recall: margin {80,64,48,32}=0/10
(mild asymmetry, ≥32px = not a hard violation, abstain); margin {16,8,0,−16}=10/10 (within the
32px safe margin = genuine violation). Clean threshold at the conventional 32px line.

## GPU re-run (in flight)
qwen35-27b (body model, NOTHINK via the elicit path) on G6 freeform C0/C3/AFC + the fixed S6
valid-figure corpus C0/C3/AFC → `data/part3/p1e8_qwen35-27b_{g6,s6}_{C0,C3,AFC}.json`. Expect:
like G3, the page-offset口径 should lift G6 off the old image-only 0.50 once the margin crosses
into violation; S6 should recover now that the slides actually contain the contradicting image.
(Full 6-model roster saturation is the optional next step for a G6 Fig-10-style curve.)
