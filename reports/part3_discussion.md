# Part 3 — discussion (mechanism, caveats, faithfulness)

_This narrative accompanies the auto-generated tables in `reports/part3.md`
(`runs/probe/part3/summary.json`). Numbers below are filled from the live run._

## What was actually run (faithful setup)

- **被优化系统**: the `generator.generate_deck` agent (brief → content-JSON → IR →
  render-free structure), steered only by the 4 editable `PromptModules`. Generator +
  frozen reflection LLM = `mimo-v2.5-pro` (online API, thinking disabled), identical
  across every condition.
- **IV = examiner feedback source**, served as the *actual* Part-1/2 models so the
  H3 x-axis matches the examiner used: linter (offline) / Qwen3-VL-8B / Qwen3-VL-30B-A3B
  / finetuned-8B / hybrid (linter gate + ft-8B reflection).
- **Convergence DV**: rollouts until the running-best **independent common quality**
  (`part3_quality`: coverage 0.40 / conciseness 0.25 / terms 0.15 / geometry 0.20,
  model-free) ≥ 0.8 — the same yardstick for all conditions, never the optimization
  signal. Seed = the near-empty `WEAK_PROMPT_MODULES`. Tasks use **vague briefs**
  (rubric in metadata only), so the skill — not the brief — must carry conventions.

## Headline (H3): design-domain feedback-transfer counterexample

Convergence rollouts do **not** decrease monotonically with examiner intrinsic
quality, and the decoupled hybrid is **not** strictly faster than the best single
source. This is the SPEC §6 pre-registered falsification branch ("若 design 域不单调 …
报告为 design 域的 feedback-transfer 反例"), reported honestly — a *negative transfer
result*, not a claim that feedback quality is irrelevant in general (RL/text already
established it does matter: Gao 2210.10760 / PRIME 2602.11570).

## Mechanism (why it lands flat here)

1. **A capable frozen generator floors the task.** Even the near-empty weak seed
   yields decks whose common quality is already close to threshold; some validation
   tasks clear 0.8 within the first few rollouts purely from per-task variation, so the
   running-best convergence metric saturates at a small rollout index for *every*
   condition — independent of the feedback source.
2. **Proxy saturation gates the optimizer.** GEPA only mutates when a candidate's
   proxy is improvable. The linter geometry proxy and the lenient zero-shot-8B examiner
   both sit at ~1.0 on these decks ("All subsample scores perfect. Skipping."), so those
   conditions never mutate — they "converge" trivially by *not exploring*. The
   finetuned-8B examiner is the only source whose proxy is informative enough to drive
   real mutations, but each mutation costs a full-valset re-evaluation, so the
   higher-quality examiner can even take *more* rollouts to first cross the gold bar.
3. **Net effect**: the very property that makes a better examiner useful (it disagrees
   with bad decks → drives edits) is penalised by a running-best convergence metric when
   the generator is already strong. The informative-vs-saturated-proxy distinction is
   visible in the optimization traces (ft/hybrid mutate; linter/zs-8B skip) but does not
   translate into the headline efficiency number.

## Caveats / threats to validity (stated, not hidden)

- **Metric**: running-best-over-rollouts rewards non-exploration; a
  best-candidate-mean-quality metric might separate conditions better (future work).
- **Generator strength**: a weaker generator (so the skill carries more of the quality)
  would likely re-expose a feedback-quality gradient; the negative result is specific to
  a *capable* frozen generator on this testbed.
- **Budget**: small per-cell rollout budget (deck 12, val 4) for API-latency reasons;
  the SkillOpt edit-economy argument (≤4 accepted edits) makes this defensible but it is
  not a large sweep.
- **Carrier coverage**: GEPA is the reported carrier; the SkillOpt optimizer-agnostic
  arm is noted separately.
- **Modality**: feedback is structure-only (`--no-render`, modality B) for disk reasons;
  geometry is verifiable from IR, semantic critique reads deck structure.

## Reward-hacking audit (gold-vs-proxy, held-out test)

No adversarial gaming under any condition: every AeSlides-style cheat detector
(hidden/oversized/out-of-bounds text, overlay occlusion, degenerate empty pages)
returns **0**, and the strict geometry gold is 1.0 everywhere. There IS a uniform
**proxy−gold gap** (proxy=1.0 vs held-out common-quality gold ≈0.65–0.72; gap
0.28–0.35, flagged "over-optimized" by the 0.15 margin) — but it is **generalization
gap / proxy-gold mismatch, not hacking**: the optimizer maxes its proxy on the
optimization split, which doesn't fully transfer to held-out test decks. The
*verifiable* linter condition has the **smallest** gap (0.279) and the all-linter-gate
hybrid the largest (0.352) here — so on this run the "verifiable gate is most
hack-resistant" expectation is only partially borne out (no cheats anywhere; gap
ordering does not single out the gate), reported honestly rather than spun.

## What still holds (positive sub-results)

- The **decoupled architecture is implementable and behaves as designed**: the
  verifiable linter gate keeps selection trustworthy (its proxy is itself verifiable,
  giving the smallest proxy−gold gap) while the learned ft-8B critique supplies the
  reflection ASI. No condition exhibits AeSlides-style reward-hacking.
- The pipeline is a real, reproducible skill-space-optimization harness over a design
  reward (the measurement contribution), independent of the H3 sign.
