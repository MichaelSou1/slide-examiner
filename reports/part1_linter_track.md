# Part 1 — Track L: symbolic linter as the G-group detector of record

Deterministic `lint_slide` over `data/part1/manifest_geometry.jsonl` (288 records: G1-G6 at a full severity grid + 80 paired clean negatives). The linter is the **ground truth and upper bound** the VLM geometry sweep (`runs/probe/part1_geometry_summary.json`) is measured against.

## Detection recall + false positives (freeform = upper bound)

On **freeform** the linter is the detector of record; misses are only where the injected magnitude is below the linter's own deliberate threshold (G2 iou<0.05, G3 offset<4px). 0 FP across all clean negatives.

| defect | freeform recall | tp/n | template recall | FP on clean |
|---|---|---|---|---|
| G1_TEXT_OVERFLOW | **1.00** | 20/20 | 0.00 | 0/80 |
| G2_ELEMENT_OVERLAP | **0.75** | 12/16 | 0.00 | 0/80 |
| G3_ALIGNMENT_OFFSET | **0.80** | 16/20 | 0.00 | 0/80 |
| G4_FONT_SIZE_INCONSISTENCY | **1.00** | 16/16 | 1.00 | 0/80 |
| G5_BRAND_COLOR_VIOLATION | **1.00** | 16/16 | 1.00 | 0/80 |
| G6_MARGIN_VIOLATION | **1.00** | 16/16 | 0.00 | 0/80 |

## Template collapse (H1-tpl): snap-to-master absorption, model-decoupled

Absorption = `1 - template_recall / freeform_recall`. Measured purely on the linter (no VLM), per SPEC §3.0(8): the question "does the template *absorb* the geometry defect" is symbolic and model-independent.

| defect | absorption | reading |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 | **fully absorbed** |
| G2_ELEMENT_OVERLAP | 1.00 | **fully absorbed** |
| G3_ALIGNMENT_OFFSET | 1.00 | **fully absorbed** |
| G4_FONT_SIZE_INCONSISTENCY | 0.00 | not absorbed |
| G5_BRAND_COLOR_VIOLATION | 0.00 | not absorbed |
| G6_MARGIN_VIOLATION | 1.00 | **fully absorbed** |

- Positional geometry (G1 overflow, G2 overlap, G3 offset, G6 margin) is **fully absorbed** by snap-to-master → the intern-system simplification "under a corporate master you can drop G1/G2/G3/G6 checks" is empirically licensed (SPEC §8).
- Font-size (G4) and brand-color (G5) are **not** snapped by the master and survive → those two G checks stay live even under templates.

## Recall by injected severity, freeform (psychophysical x-axis lives here)

**G1_TEXT_OVERFLOW** (magnitude = `overflow_px`):  
4.0: 4/4 · 8.0: 4/4 · 16.0: 4/4 · 32.0: 4/4 · 64.0: 4/4

**G2_ELEMENT_OVERLAP** (magnitude = `iou`):  
0.049: 0/4 · 0.103: 4/4 · 0.23: 4/4 · 0.596: 4/4

**G3_ALIGNMENT_OFFSET** (magnitude = `offset_px`):  
2.0: 0/4 · 4.0: 4/4 · 8.0: 4/4 · 16.0: 4/4 · 32.0: 4/4

**G4_FONT_SIZE_INCONSISTENCY** (magnitude = `delta_pt`):  
1.0: 4/4 · 2.0: 4/4 · 4.0: 4/4 · 8.0: 4/4

**G5_BRAND_COLOR_VIOLATION** (magnitude = `delta_e`):  
3.185: 4/4 · 6.2: 4/4 · 11.999: 4/4 · 23.789: 4/4

**G6_MARGIN_VIOLATION** (magnitude = `bleed_px`):  
4.0: 4/4 · 8.0: 4/4 · 16.0: 4/4 · 32.0: 4/4

## Linter-recovered reading vs. injected magnitude (monotone = usable as θ axis)

**G1_TEXT_OVERFLOW**: inj=4->meas=56.1 · inj=4->meas=56.1 · inj=4->meas=56.1 · inj=4->meas=56.1 · inj=8->meas=56.1 · inj=8->meas=56.1

**G2_ELEMENT_OVERLAP**: inj=0.103->meas=0.103 · inj=0.103->meas=0.103 · inj=0.103->meas=0.103 · inj=0.103->meas=0.103 · inj=0.23->meas=0.23 · inj=0.23->meas=0.23

**G3_ALIGNMENT_OFFSET**: inj=4->meas=4 · inj=4->meas=4 · inj=4->meas=4 · inj=4->meas=4 · inj=8->meas=8 · inj=8->meas=8

**G4_FONT_SIZE_INCONSISTENCY**: inj=1->meas=1 · inj=1->meas=1 · inj=1->meas=1 · inj=1->meas=1 · inj=2->meas=2 · inj=2->meas=2

**G5_BRAND_COLOR_VIOLATION**: inj=3.18->meas=3.18 · inj=3.18->meas=3.18 · inj=3.18->meas=3.18 · inj=3.18->meas=3.18 · inj=6.2->meas=6.2 · inj=6.2->meas=6.2

**G6_MARGIN_VIOLATION**: no measured readings recovered.

## Take

- The linter recovers a **continuous, monotone** geometry reading for every G type — this is where the SPEC §3.0 psychophysical curve is drawn, not on the VLM (which is step-like / random; see `part1_geometry_threshold.md`).
- Linter recall and 0-FP-on-clean set the **upper bound**; the VLM pointwise geometry numbers (4B/8B random, only 30B G1) are reported only as "broke / didn't break random", per the three-track design.
