# Part 3 prep — reuse inventory, GPU map, serving recipe

Part 3 validates: examiner **feedback-source quality** (IV, measured in Parts 1/2)
→ skill-space optimizer **convergence efficiency + final quality**, across
optimizer families (SkillOpt primary / GEPA secondary), with the optimizer kernel
+ reflection LLM **frozen** (only the feedback source varies). Architecture under
test = **decoupled feedback**: verifiable linter = selection gate, learned ft-8B
examiner = reflection ASI.

> Novelty scope (do not overclaim): intersection transfer of "verifier-quality →
> efficiency" into **skill-space × design** + decoupled verifiable/learned feedback
> + gold-vs-proxy audit. We do **not** claim to discover that feedback quality
> matters (Gao 2210.10760 / PRIME 2602.11570 did, in RL). Slide gen is a testbed;
> self-refine is a baseline only.

## Reusable assets (do NOT reimplement)

| Need | Reuse | Notes |
|------|-------|-------|
| Slide/Deck IR | `slide_examiner/schemas.py` (`Slide/Deck/Element/BBox/DefectLabel`) | frozen dataclasses, `.to_dict/.from_mapping` |
| Dual render | `slide_examiner/render.py` (`render_slide_multi_resolution`, `render_slides_to_png`, `build_render_spec`, `check_render_artifact`, `render_pptx_to_pngs`) | HTML default; PPTX fidelity path |
| Geometry linter | `slide_examiner/geometry.py` (`lint_slide`, `linter_score`) | verifiable G1–G6 |
| Term linter (S3) | `slide_examiner/term_consistency.py` (`lint_deck`) | deck-level |
| Examiner contract | `slide_examiner/examiner_contract.py` (`build_messages_from_sample`, `normalize_contract_output`) | trained format = ft-8B |
| ft-8B examiner | `runs/part2/examiner_merged` | served via vLLM OpenAI endpoint |
| Stats | `slide_examiner/statistics.py` (`wilson_interval`, `balanced_accuracy_ci`, `two_proportion_z_test`, `variance_gated_effect`) | CIs + gating for reports |
| Panel | `slide_examiner/panel.py` (`summarize_panel_ratings`, `inter_annotator_agreement`) | P8 final eval |
| Hybrid ASI synth | `slide_examiner/gepa_eval.py` (`evaluate_hybrid_feedback`) | linter gate + examiner ASI |

## New Part 3 modules

- `slide_examiner/skill_doc.py` — `PromptModules` (4 editable modules) + markdown ↔ component-dict round trip (shared by both carriers).
- `slide_examiner/generator.py` — `generate_deck` agent loop (brief → content JSON → IR → render); `deck_from_content_json` extended additively (figures + key_terms).
- `slide_examiner/feedback_sources.py` — 5 `FeedbackSource`s (linter / zs-8B / zs-30B / ft-8B / hybrid) → `(selection_score, reflection_text)`.
- `slide_examiner/skillopt_adapter.py` (P4) — `EnvAdapter` subclass + `ReflACTTrainer` driver.
- `slide_examiner/gepa_runner.py` (P4) — non-dry-run wired to `gepa.api.optimize`.

## Optimizer carriers (installed from PyPI; GitHub unreachable)

- **SkillOpt** = pip `skillopt` 0.1.0 (internally **ReflACT**). Subclass `skillopt.envs.base.EnvAdapter`:
  `rollout(env, skill_content, out_dir) -> [{"id","hard","soft","fail_reason"}]`
  (`soft` = our `selection_score`), `reflect(results, skill_content, out_dir) -> [RawPatch]`.
  Run: `skillopt.engine.trainer.ReflACTTrainer(cfg, adapter).train()`. Gate via `gate_metric="soft"`.
  Optimizer/target LLM via `qwen_chat` backend → local vLLM (`QWEN_CHAT_BASE_URL`, `QWEN_CHAT_MODEL`).
- **GEPA** = pip `gepa` 0.1.1. `gepa.api.optimize(seed_candidate=<4-module dict>, trainset, valset, adapter, reflection_lm=<local callable>, max_metric_calls, seed, run_dir)`. Adapter implements `evaluate` (scores=selection_score) + `make_reflective_dataset` (Feedback=reflection_text).

## Generator / reflection LLM

`Qwen3.6-27B-AWQ-INT4` at `/home/gpus/models/Qwen3.6-27B-AWQ-INT4` (compressed-tensors,
multimodal dense used text-only). ONE served vLLM instance backs both the generator
and the frozen reflection role (different prompts). No API key needed.

## Serving recipe (see memory `vllm-serving-gotchas`)

```bash
# generator + frozen reflection (Qwen3.6-27B), GPU 0,1
CUDA_VISIBLE_DEVICES=0,1 vllm serve /home/gpus/models/Qwen3.6-27B-AWQ-INT4 \
  --served-model-name qwen3.6-27b --port 8200 --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.92 --max-model-len 8192 --enforce-eager \
  --disable-custom-all-reduce --trust-remote-code
# examiner feedback source (ft-8B / zs-8B), GPU 2,3
CUDA_VISIBLE_DEVICES=2,3 vllm serve runs/part2/examiner_merged \
  --served-model-name ft-8b --port 8101 --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.92 --max-model-len 8192 --limit-mm-per-prompt '{"image":6}' \
  --enforce-eager --trust-remote-code
```

GPU map: 27B on GPU0,1; examiner on GPU2,3. Conditions run one at a time → only
two served models coexist. `linter` condition needs only the 27B instance.

## Disk

Box is ~full after the model download. Render rollouts at low `long_edge` and clean
intermediate PNGs between rollouts (`runs/probe/part3/` keeps only summaries).

## Actual run configuration (2026-06-19) — deviations from the original plan

The live sweep that produced the reported artifacts differs from the recipe above
in three deliberate ways; all are documented here for reproducibility.

1. **Generator + frozen reflection LLM = online API (`mimo-v2.5-pro`), not the local
   27B.** Putting the generator on the API frees all 4 GPUs for the examiner gradient
   (one ~8B model per TP=2 pair), and keeps the generator/reflection **identical
   across every condition** (the control). `mimo-v2.5-pro` is a *reasoning* model: under
   a tight `max_tokens` it spends the whole budget on `reasoning_content` and returns
   empty `content` → degenerate decks. Fix = `PART3_DISABLE_THINKING=1` in `.env`
   (sends `chat_template_kwargs={"enable_thinking":false}`; harmlessly ignored by the
   local Qwen3-VL examiners, whose templates have no such var). Always pass
   `--gen-max-tokens 2048` even at page level — the generator emits a *full* deck JSON
   and `max_slides` only truncates afterward, so 700 tokens truncates the JSON.
2. **Faithful examiner gradient via local serving** (`scripts/part3_faithful_sweep.sh`):
   the IV uses the *actual* models measured in Parts 1/2 — Qwen3-VL-8B (`zero_shot_8b`),
   Qwen3-VL-30B-A3B-AWQ (`zero_shot_30b`), and the ft-8B (`finetuned_8b`/`hybrid` reflection
   arm) — so the H3 x-axis (intrinsic quality) matches the examiner actually used. Two
   serve phases (a 4×20 GB box holds two ~8B TP=2 models, not three): Phase A = 8B + ft-8B
   together; Phase B = 30B-A3B alone. `linter` needs no examiner.
3. **Testbed made non-trivial (else skill-space optimization saturates).** Measured: a
   capable generator scores ~1.0 common-quality even with a near-empty skill when the
   brief leaks the rubric. So tasks now use **vague briefs** (`scripts/part3_build_tasks.py`)
   that omit the section list / slide count / consistency hints — the rubric lives in
   task metadata only, for scoring. Optimization starts from `WEAK_PROMPT_MODULES`
   (the genuine no-skill seed; ~0.73 common-quality, real headroom). Convergence is
   measured against an **independent, model-free common quality** (`slide_examiner/part3_quality.py`:
   coverage 0.40 / conciseness 0.25 / terms 0.15 / geometry 0.20) — the SPEC §5.2 "fixed
   quality threshold" DV and the Gao gold-vs-proxy gold. The linter proxy (geometry) is
   blind to 65 % of that gold (coverage+conciseness), which a semantic examiner can reveal:
   that asymmetry is the H3 mechanism.

**Run commands.**
```bash
# 1) faithful sweep (serves examiners, runs GEPA over the 5-condition IV; ~90 min)
PAGE_BUDGET=6 DECK_BUDGET=12 PAGE_SEEDS="0 1" DECK_SEEDS="0 1 2" \
  bash scripts/part3_faithful_sweep.sh            # -> runs/probe/part3/{pilot_main,main}.jsonl
# 2) API-only analysis (no GPU): pilot variance, hacking audit, final judge, synthesis + H3
bash scripts/part3_analyze.sh
```
DV/threshold: deck convergence threshold = 0.8 common-quality; page pilot uses 0.55
(2 slides cannot cover a 4-6 section rubric, so the page bar is lowered purely for
variance estimation — the deck-level run is the reported H3 result).
