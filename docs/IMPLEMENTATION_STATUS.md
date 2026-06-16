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
- Real rendering pipeline (`slide_examiner.render`, validated against real Zenodo10K pilot data):
  - Playwright (bundled chromium or system Chrome fallback) HTML raster render
  - multi-resolution render at 768/1024/1536/2048 long edge via coordinate-scaled HTML (true re-render, not bitmap resampling)
  - `RenderSpec` (image px + `scale_x`/`scale_y`) computed from the bytes actually written, so bbox->pixel conversion stays exact
  - per-image quality checks: exists/openable, byte size, bbox not zero-area/out-of-bounds, text element has ink at its bbox
  - manifest writeback of `image_path` + `metadata.render` (modality A/C find the image, B/C find structure, B' finds caption)
  - LibreOffice PPTX -> PDF -> ordered page PNGs (poppler `pdftoppm`) with page-count/order verification for multi-page decks
- Experiment execution:
  - dataset source registry and explicit URL download helper
  - real-data directory initializer
  - clean-corpus preparation helper for `.pptx`, project JSON IR, and annotated HTML
  - SlidesBench/PPTBench subset-plan and task-adapter helpers
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
slide-examiner init-data-layout
slide-examiner power 0.50 0.70
slide-examiner prepare-clean-corpus pptagent_zenodo10k data/raw/zenodo10k data/ir/zenodo10k_clean data/manifests/zenodo10k_clean_candidates.jsonl --summary reports/data_prep/zenodo10k_cleaning_summary.json
slide-examiner benchmark-plan pptbench reports/data_prep/pptbench_plan.json
slide-examiner prepare-benchmark pptbench data/raw/pptbench/tasks.jsonl data/manifests/pptbench_tasks.jsonl --ir-dir data/ir/pptbench --summary reports/data_prep/pptbench_adapter_summary.json
slide-examiner generate content.json runs/generated_html
slide-examiner ingest deck.pptx data/deck_ir.json
slide-examiner render data/slide_ir.json runs/rendered/slide.html
slide-examiner render-manifest data/manifest.jsonl runs/rendered/native [--long-edge 1024]
slide-examiner render-resolutions data/manifest.jsonl runs/rendered/res --quality-report reports/render/quality.json
slide-examiner render-pptx deck.pptx runs/rendered/pptx_pages/deck --summary reports/render/pptx_render_summary.json
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
- Real raster rendering: DONE for the pilot — see `runs/rendered/zenodo10k_pilot_resolutions/` (4 resolutions, quality report `reports/render/zenodo10k_pilot_resolution_quality.json`) and `runs/rendered/pptx_pages/` (PPTX->PDF->PNG, `reports/render/pptx_render_summary.json`). Remaining work is to render at full Part 1 dataset scale once the dataset is frozen.
  - Sandbox caveat: this machine's LibreOffice is an AppImage; under the current Claude Code sandbox `soffice` is silently killed when launched from a Python subprocess (works when run directly in a shell). PDFs were produced via the shell and rasterized via `render_pdf_to_pngs`. No such limit in the real research environment; `SLIDE_EXAMINER_SOFFICE` can point at an extracted `.../program/soffice` launcher.
- Real VLM inference: PILOT DONE — Qwen3-VL-4B (local vLLM, OpenAI-compatible) ran the full 84-sample × A/B/B′/C × T1/T2/T3 = 1008-call Part 1 pilot. Artifacts: `runs/probe/pilot_probe.jsonl`, `runs/probe/pilot_summary.json`, `reports/pilot_slideprobe.md`; drivers `scripts/run_pilot.py` + `scripts/pilot_report.py`. 0% parse failure. Headline: caption oracle B′ is a dead channel, S-group signal lives in the structured channel, G-group is near-undetectable by the VLM (linter's job), and the deck-level C request needs the full page-image sequence. Remaining: rerun on 8B/30B and at full Part 1 matrix scale once G-injections are made perceptually manifest and a real template manipulation is wired.
  - Serving note: the base conda env has a broken numpy/sklearn ABI; serve from the `vllm-qwen` env. Launch `vllm serve` from a cwd WITHOUT a `specs/` dir and pass `--enforce-eager` — otherwise torch-inductor shells out to gcc and dies on `cannot read spec file './specs'`. Kill leftover `EngineCore` workers (not just `vllm serve`) to free GPU0 between runs.
  - Pre-full-matrix blocker fixes + 8B confirmation (2026-06-16): fixed four issues that would have corrupted the full matrix, validated on Qwen3-VL-8B (vLLM TP=2 on GPU1,2). (1) B′ caption is now generated by a VLM captioning the rendered image (`scripts/caption_images.py`); the contract serializer gained a `caption` field + B_CAPTION_ONLY branch in `build_page_messages`/`build_deck_messages`. (2) Deck modality renders every page (`render-manifest` writes `metadata.page_image_paths`) and the deck serializer sends one image per page. (3) Real `template` manipulation via `slide_examiner/template.py` snap-to-master (absorbs G1/G2 geometry; semantic defects survive) wired into `build-synthetic`. (4) The probe now runs the production contract serializer (`build_messages_from_sample`) with the scope+schema prompt; 0% parse failure. Findings: 8B still detects 0 G1/G2 across all modalities (geometry threshold is not 4B-specific → linter owns G1–G6); S1 image perception wakes up at 8B (A 0%→50%); S2 needs the structured channel (B 83%) and is undetectable from page images even with the full sequence. See `reports/pilot_slideprobe.md`.
  - Geometry-visibility fix (2026-06-16): the original synthetic G1/G2 injections did not render as visible defects (G1 appended a few chars into a 1728px-wide box; transparent text boxes hid overlaps). Fixed `inject_text_overflow` (shrinks the box to the text width) and `render.slide_to_html` (content blocks now render as visible cards: `white-space:nowrap` + translucent bordered box) so overflow spills past a drawn border and overlaps blend into a darker intersection. After the fix the defects are unambiguous to a human, yet Qwen3-VL-4B still detects 0 G1/G2 across all modalities and, in a free-form probe, reports "no text runs outside borders / no boxes overlap" — a genuine model geometry-detection-threshold finding (it only catches gross cases), which reinforces "G1–G6 belong to the symbolic linter." See `reports/pilot_slideprobe.md` and `runs/pilot/sanity/geometry_threshold.json`.
- Real 8B QLoRA training: run the generated training command on the target GPU setup.
- Real GEPA optimization: install GEPA and run non-dry-run rollouts with a generator, linter, and examiner.
- Human/panel evaluation: collect the external panel labels required by Part 3.

The current test suite verifies the local contracts and smoke pipeline, not the empirical claims.
