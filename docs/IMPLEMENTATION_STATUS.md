# Slide-Examiner Implementation Status

This document maps the research spec to the current codebase.

## Implemented Code Paths

- Slide/Deck IR: `slide_examiner.schemas`
- Defect taxonomy G1-G6 and S1-S6: `slide_examiner.taxonomy`
- Geometry linting:
  - G1 text overflow
  - G2 element overlap
  - G3 alignment offset
  - G4 font size inconsistency
  - G5 brand color violation
  - G6 margin violation
- Synthetic injection:
  - G1-G6 slide-level injections
  - S1/S4/S6 slide-level semantic-label injections
  - S2/S3/S5 deck-level semantic-label injections
- Ingest/render scaffolds:
  - JSON Slide/Deck IR
  - annotated HTML to Slide IR
  - PPTX geometry extraction with text-outline fallback
  - Slide IR to HTML scaffold
  - optional Playwright HTML raster render
  - optional LibreOffice PPTX to PDF render
- Experiment execution:
  - dataset source registry and explicit URL download helper
  - pre-registered model/modality/task/template/resolution/seed matrix
  - matrix runner for mock/replay/local/API adapters
  - mock SlideProbe runner for A/B/B_prime/C and T1/T2/T3
  - runtime request helper that always sends modality C (image + structure); A/B/B_prime are attribution/training-only paths
  - replay/local Qwen-VL adapter scaffolds
  - probe result JSONL
- Analysis:
  - detection metrics
  - manifest/linter defect distribution summaries
  - A vs B perception/reasoning attribution
  - B vs B_prime caption-oracle gap
  - template-collapse summary
  - severity psychometric thresholds
  - variance gating
  - power/sample-size helper for two-proportion comparisons
  - pre-registered hypothesis gate evaluation
  - repair pass-rate aggregation
  - Markdown report generation
- Repair and auditing:
  - deterministic G1-G6 repair application
  - reward-hacking audit for overflow hidden, hidden/tiny text, off-canvas elements, texture backgrounds, and covering overlays
  - human/API panel rating aggregation
- Examiner training and downstream optimization:
  - QwenVL-style pointwise/pairwise SFT JSONL export
  - Qwen-VL LoRA training command/config dry-run
  - hybrid GEPA-style evaluator
  - GEPA dry-run rollout plan
- Generator scaffold:
  - structured content JSON to Deck IR
  - Deck IR to HTML slide scaffold
  - optional python-pptx export

## Commands

```bash
slide-examiner matrix configs/slideprobe_matrix.json
slide-examiner run-matrix data/manifest.jsonl configs/slideprobe_matrix.json runs/probe/matrix.jsonl --limit 10
slide-examiner data-sources
slide-examiner power 0.50 0.70
slide-examiner generate content.json runs/generated_html
slide-examiner ingest deck.pptx data/deck_ir.json
slide-examiner render data/slide_ir.json runs/rendered/slide.html
slide-examiner repair data/slide_ir.json runs/repaired_slide.json
slide-examiner hacking-audit data/slide_ir.json -o reports/hacking.json
slide-examiner inject data/slide_ir.json G1_TEXT_OVERFLOW runs/injected data/manifest.jsonl
slide-examiner probe data/manifest.jsonl runs/probe/mock.jsonl
slide-examiner eval-examiner data/manifest.jsonl runs/probe/eval.jsonl runs/probe/eval_summary.json
slide-examiner analyze runs/probe/mock.jsonl -o runs/probe/summary.json
slide-examiner distribution data/manifest.jsonl -o reports/distribution.json
slide-examiner hypotheses runs/probe/summary.json -o reports/hypotheses.json
slide-examiner report runs/probe/summary.json reports/slideprobe.md
slide-examiner panel eval/panel_ratings.jsonl -o reports/panel_summary.json
slide-examiner build-sft data/manifest.jsonl data/sft_pointwise.jsonl
slide-examiner train-examiner data/sft_pointwise.jsonl models/examiner --config configs/train_examiner.json
slide-examiner run-gepa tasks/train.jsonl tasks/val.jsonl tasks/test.jsonl runs/gepa/plan.json
slide-examiner gepa-conditions tasks/train.jsonl tasks/val.jsonl tasks/test.jsonl runs/gepa/conditions.json
```

## External Execution Still Required

The code paths exist, but these spec items require external resources to produce real research results:

- Real deck corpora: Zenodo10K/PPTAgent, SlidesBench/PPTBench, and脱敏实习 decks.
- Real raster rendering: install Playwright browsers and/or LibreOffice, then render all generated samples.
- Real VLM inference: install model dependencies and provide Qwen3-VL/API model access.
- Real 8B QLoRA training: run the generated training command on the target GPU setup.
- Real GEPA optimization: install GEPA and run non-dry-run rollouts with a generator, linter, and examiner.
- Human/panel evaluation: collect the external panel labels required by Part 3.

The current test suite verifies the local contracts and smoke pipeline, not the empirical claims.
