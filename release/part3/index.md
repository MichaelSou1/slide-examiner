# Part 3 reproducibility release

This bundle exposes derived paired-image manifests and per-item rollout CSVs.
Weights, raw source corpora, and other upstream licensed items stay outside the bundle.

## Manifests
- `data/part2/manifest_eval_test_rendered.jsonl` -> `release/part3/manifests/manifest_eval_test_rendered.jsonl`
  - regen: `python scripts/part2_build_dataset.py`
  - note: paired-clean synthetic evaluation manifest used by the main Part 2/Part 3 tables.
- `data/part3/manifest_g7_rendered.jsonl` -> `release/part3/manifests/manifest_g7_rendered.jsonl`
  - seed: `20260620`
  - regen: `python scripts/part3_build_g7.py --per-variant 30 --seed 20260620`
  - note: synthetic G7 paired images with clean twins and render-containment overflow labels.
- `data/part3/manifest_real_rendered.jsonl` -> `release/part3/manifests/manifest_real_rendered.jsonl`
  - seed: `20260622`
  - regen: `python scripts/part3_real_inject.py --seed 20260622`
  - note: real-layout paired images from licensed decks; only derived artifacts are released here.
- `data/part3/manifest_g6_internal.jsonl` -> `release/part3/manifests/manifest_g6_internal.jsonl`
  - regen: `python scripts/part3_e8_make_g6_internal.py`
  - note: internal-contrast G6 corpus; deterministic through the fixed build pipeline.
- `data/part3/manifest_coverage_internal.jsonl` -> `release/part3/manifests/manifest_coverage_internal.jsonl`
  - regen: `python scripts/part3_e8_regen_corpus.py --target coverage`
  - note: paired clean-twin coverage corpus; deterministic through the fixed build pipeline.

## Row CSVs
- `data/part3/p1*_rows.jsonl` -> 188 CSVs, 28664 rows
  - note: row-level outputs behind the paired-clean Protocol-1 / McNemar tables.
- `data/part3/pc_real*_rows.jsonl` -> 4 CSVs, 4008 rows
  - note: row-level outputs behind the real-layout A/B/C paired-clean tables.

## License note
The withheld upstream items are licensing-constrained, not convenience-constrained.
Only derived artifacts are released here.
