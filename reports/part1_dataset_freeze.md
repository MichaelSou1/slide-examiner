# Part 1 dataset — FROZEN

`352` samples, frozen by sha256 (see `part1_dataset_freeze.json`). Pairing-first per SPEC §3.0: every positive carries a same-base clean counterpart for balanced-accuracy / pairwise control.

## Coverage

| defect | n |
|---|---|
| G1_TEXT_OVERFLOW | 40 |
| G2_ELEMENT_OVERLAP | 32 |
| G3_ALIGNMENT_OFFSET | 40 |
| G4_FONT_SIZE_INCONSISTENCY | 32 |
| G5_BRAND_COLOR_VIOLATION | 32 |
| G6_MARGIN_VIOLATION | 32 |
| NO_DEFECT | 80 |
| S1_TITLE_BODY_MISMATCH | 8 |
| S2_NARRATIVE_ORDER_BREAK | 8 |
| S3_TERMINOLOGY_INCONSISTENCY | 8 |
| S4_DENSITY_RULE_VIOLATION | 24 |
| S5_MISSING_LOGIC_SECTION | 8 |
| S6_IMAGE_TEXT_CONTRADICTION | 8 |

- **splits**: {'train': 200, 'ood_severity': 80, 'test': 16, 'val': 16, 'ood_defect': 40}
- **template conditions**: {'freeform': 176, 'template': 176} (template = real snap-to-master, linter-verified absorption)
- **held-out severity** (`ood_severity`): {'G5_BRAND_COLOR_VIOLATION': 8, 'S4_DENSITY_RULE_VIOLATION': 8, 'G2_ELEMENT_OVERLAP': 8, 'G1_TEXT_OVERFLOW': 16, 'G3_ALIGNMENT_OFFSET': 24, 'G6_MARGIN_VIOLATION': 16}
- **held-out defect** (`ood_defect`): {'S5_MISSING_LOGIC_SECTION': 8, 'G4_FONT_SIZE_INCONSISTENCY': 32}
- **negative ratio**: 0.227 (80/352)
- **paired-clean image coverage**: 328/352 page-level (deck-level S2/S3/S5 paired at deck granularity)

## Recorded degradations

- negative ratio 0.227 < 0.30 target (80 paired clean negatives; pairing prioritized over absolute count)
- page-level paired-clean image coverage 328/352; the 24 unpaired are deck-level S2/S3/S5 (paired at deck granularity, not single-image)
- S3 terminology + S6 image-text pairs are deck-level / image-corpus (data/part1_img); single-image clean pairing not applicable

## Measurability gates (SPEC §3.0)

- **S6_image_text**: data/part1_img/manifest_s6_rendered.jsonl — figures drawn with ▲/▼ + claim, contradiction only in pixels (measurable)
- **S3_terminology**: deck-level canonical-vs-variant term swap present in sgroup manifest (measurable; Track P forced-choice built separately)
- **template_is_real_snap_to_master**: verified by linter absorption (runs/probe/part1_linter_summary.json: G1/G2/G3/G6 absorb=1.0)

## Frozen manifest hashes

- `data/part1/manifest.jsonl` — `d8fb24270af74e0a…`
- `data/part1/manifest_rendered.jsonl` — `723815ac812a0178…`
- `data/part1/manifest_geometry.jsonl` — `9bcfc2b8a4562b54…`
- `data/part1/manifest_sgroup.jsonl` — `4a7b782340b00290…`
- `data/part1/manifest_freeform.jsonl` — `87238c135e2966d6…`
- `data/part1/manifest_template.jsonl` — `c12feb9ea3ec7740…`
- `data/part1_img/manifest_s6_rendered.jsonl` — `3f6b5acd51443ea1…`
- `data/part1_fc/manifest_1536.jsonl` — `af08fc87e2729d8a…`
- `data/part1_fc/manifest_2048.jsonl` — `9981470e9e73fd52…`
