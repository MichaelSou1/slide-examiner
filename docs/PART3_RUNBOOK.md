# Part 3 runbook — real execution vs. dry-run (engineering delivery)

This maps every Part 3 entry point to whether it performs **real** optimization /
serving or is a **dry-run / offline-smoke** helper, and gives the exact commands.
See `docs/PART3_PREP.md` for the asset inventory + serving recipe and the design
rationale (vague briefs, common-quality DV, faithful examiner gradient).

## Real execution (hits models, produces reported artifacts)

| Command | What it really does | Output |
|---|---|---|
| `scripts/part3_build_tasks.py` | builds the deck-level task set (vague briefs; rubric in metadata only) + sha256 freeze | `data/part3/tasks/{train,val,test}.jsonl`, `reports/data_prep/part3_task_acquisition.json` |
| `scripts/part3_feedback_iv.py` | reads frozen Part 1/2 summaries → examiner intrinsic-quality x-axis (the IV); never recomputes | `runs/probe/part3/feedback_iv.json` |
| `scripts/part3_faithful_sweep.sh` | **REAL** sweep: serves Qwen3-VL-8B/30B/ft-8B examiners locally, runs GEPA (or `CARRIER=skillopt`) over the 5-condition IV with the API generator+reflection | `runs/probe/part3/{pilot_main,main}.jsonl`, `runs/part3/best_skill_*/` |
| `scripts/part3_run.py` | one optimizer matrix invocation (used by the sweep; `--smoke` = offline) | `<--out>.jsonl` + best skills |
| `scripts/part3_analyze.sh` | **REAL** API-only post-processing: pilot variance, gold-vs-proxy audit, frozen-judge final eval, synthesis + H3 gate | `reports/part3*.md`, `runs/probe/part3/{pilot_summary,hacking,final_eval,summary}.json` |
| `scripts/part3_hacking_audit.py` | regenerates test decks from each best skill (API), scores verifiable gold + AeSlides cheat flags | `runs/probe/part3/hacking.json`, `reports/part3_hacking.md` |
| `scripts/part3_final_eval.py` | frozen API judge (≠ any feedback source) over held-out test decks; panel κ wired | `runs/probe/part3/final_eval.json` |
| `scripts/part3_synthesis.py` | examiner-quality→efficiency curve + H3 verdict | `reports/part3.md`, `runs/probe/part3/summary.json` |

`run_gepa(..., dry_run=False)` / `run_skillopt(...)` are the **real** optimizer
paths (non-dry-run); GEPA real optimization is also unit-proven offline
(`tests/test_part3_optimizers.py::test_gepa_real_run_offline_optimizes`).

## Dry-run / offline-smoke (no models; CI + pipeline validation)

| Command | Purpose |
|---|---|
| `gepa_runner.build_gepa_condition_plan` / `run_gepa_experiment(dry_run=True)` | the original condition planner (returns a plan dict; **not** optimization) |
| `scripts/part3_*.py --smoke` / `part3_run.py --smoke` | offline fake LLMs (deterministic generator whose cleanliness responds to skill quality) — validates the full P5–P9 pipeline with no server |
| `scripts/part3_generator_smoke.py` | 1-task generator wiring + render round-trip smoke |

## Reproduce end-to-end (real)

```bash
python scripts/part3_build_tasks.py
python scripts/part3_feedback_iv.py
PAGE_BUDGET=6 DECK_BUDGET=12 PAGE_SEEDS="0 1" DECK_SEEDS="0 1 2" \
  bash scripts/part3_faithful_sweep.sh         # GEPA carrier (primary)
# optional second carrier for optimizer-agnostic:
# CARRIER=skillopt RUN_PAGE=0 bash scripts/part3_faithful_sweep.sh
bash scripts/part3_analyze.sh
```
Env: serving uses the `vllm-qwen` conda env; gepa/skillopt/openai live in `base`
(`PART3_DISABLE_THINKING=1` in `.env` for the mimo reasoning generator). The human
3-rater panel arm of P8 is deferred to todo §12 (auto judge is the standing arm).
