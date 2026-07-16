# E8 — human perceptual spot-check of injected defects

Sample: **73 defective+clean pairs**, freeform (non-template) renders, stratified across 9 single-slide classes (S2/S3 are deck-level, no single-slide clean twin -> out of scope).

### Defect visible on the defective render? (human)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G3_ALIGNMENT_OFFSET | 1.00 [0.68, 1.00] | 8 |
| G6_MARGIN_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G5_BRAND_COLOR_VIOLATION | 1.00 [0.72, 1.00] | 10 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **1.00 [0.95, 1.00]** | **73** |

### Twin actually clean? (human)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G3_ALIGNMENT_OFFSET | 1.00 [0.68, 1.00] | 8 |
| G6_MARGIN_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G5_BRAND_COLOR_VIOLATION | 1.00 [0.72, 1.00] | 10 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **1.00 [0.95, 1.00]** | **73** |

### Flagged pairs (candidate injector artifacts)

_None — every sampled defect was judged visible and every twin clean._

### Secondary cross-check (Claude image vision, disclosed)

_Labelled independently of the human pass; reported as corroboration only._

- **defect visible**: raw agreement 0.82 (n=55), Cohen's kappa 0.00
- **twin clean**: raw agreement 1.00 (n=55), Cohen's kappa 1.00

### Defect visible (Claude)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 0.33 [0.12, 0.65] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G6_MARGIN_VIOLATION | 0.43 [0.16, 0.75] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **0.82 [0.70, 0.90]** | **55** |

### Twin clean (Claude)

| class | rate [95% Wilson CI] | n |
|---|---|---|
| G1_TEXT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| G2_ELEMENT_OVERLAP | 1.00 [0.65, 1.00] | 7 |
| G6_MARGIN_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| G7_RENDER_CONTAINMENT_OVERFLOW | 1.00 [0.70, 1.00] | 9 |
| S1_TITLE_BODY_MISMATCH | 1.00 [0.65, 1.00] | 7 |
| S4_DENSITY_RULE_VIOLATION | 1.00 [0.65, 1.00] | 7 |
| S6_IMAGE_TEXT_CONTRADICTION | 1.00 [0.70, 1.00] | 9 |
| **overall** | **1.00 [0.93, 1.00]** | **55** |
