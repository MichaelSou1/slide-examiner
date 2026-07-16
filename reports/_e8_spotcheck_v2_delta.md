# E8 spot-check v2 delta summary

Generated from `docs/spotcheck/{manifest,labels}.json` and `docs/spotcheck/{manifest_v2,labels_v2}.json`.

## What changed

- The **55 non-replaced pairs are unchanged** between v1 and v2 (`55/55` identical labels).
- The only change is the corrected replacement block for **G3/G5**:
  - `G3_ALIGNMENT_OFFSET`: `0/7 -> 8/8` defect-visible
  - `G5_BRAND_COLOR_VIOLATION`: `0/7 -> 10/10` defect-visible
- All other classes remain at the v1 rates:
  - `G1`: `9/9`
  - `G2`: `7/7`
  - `G6`: `7/7`
  - `G7`: `9/9`
  - `S1`: `7/7`
  - `S4`: `7/7`
  - `S6`: `9/9`

## Human spot-check v2

- `reports/_e8_spotcheck_v2.md`
- `data/part3/e8_spotcheck_v2.json`

Headline result: **73/73 defect-visible, 73/73 twin-clean, flagged pairs = 0**.

## IR-faithfulness v2

- `data/part3/e8_ir_faithfulness_v2.json`

Audited pairs = the 55 classes with source-structure evidence available in the generic part-2 pool or the corrected replacement G3/G5 HTML artifacts.

Headline result: **55/55 injections present in the source structure**.

Per-class audit coverage:

- `G1`: `9/9`
- `G2`: `7/7`
- `G3`: `8/8`
- `G5`: `10/10`
- `G6`: `7/7`
- `S1`: `7/7`
- `S4`: `7/7`

S6/G7 remain outside this script's structure audit scope because they come from dedicated corpora rather than the generic part-2 manifest, but both are human-verified visible in v2.
