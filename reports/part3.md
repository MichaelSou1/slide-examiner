# Part 3 — Examiner quality → downstream utility (lightweight evidence)

_Mode: live. Vehicles: **self-refine (primary)** + **GEPA skill-space (secondary)** + a **real-world Hermes-agent case-study (§6)**._

> **Framing.** This is a VLM paper (Part 1 attribution + Part 2 injected-defect examiner). Part 3
> is **lightweight downstream-utility evidence**, not a skill-optimization headline. We ask one
> narrow question — _does a better examiner buy a generator more when its critique is fed back?_ —
> with two independent vehicles and report the answer honestly, including where it is weak.
>
> Novelty scope: intersection transfer (verifier-quality→utility) into design + decoupled
> verifiable/learned feedback + gold-vs-proxy audit; NOT a claim that "feedback quality matters"
> in general (RL already established that).

Generator + revision = a mainstream API model (`qwen3.6-flash`, DashScope), so no cherry-picked
weak generator. The examiner (the **IV**) is varied across five intrinsic-quality levels; the
**DV** is an independent, model-free common quality (coverage 0.40 / conciseness 0.25 / terms 0.15
/ geometry 0.20) — never the examiner's own score.

| examiner (IV) | intrinsic quality | what it sees |
|---|---|---|
| `linter` | 0.50 | geometry/structure only (no semantics) |
| `zero_shot_8b` | 0.639 | Qwen3-VL-8B, zero-shot |
| `zero_shot_30b` | 0.785 | Qwen3-VL-30B-A3B, zero-shot |
| `finetuned_8b` | 1.00 | Part-2 injected-defect ft-8B |
| `hybrid` | 1.00 | ft-8B semantics + verifiable linter gate |

---

## 1. Self-refine vehicle (PRIMARY)

Cleanest test of feedback transfer: the model edits **this** deck, so there is no proxy
saturation and no running-best-over-rollouts artifact.

```
deck_0 = generate(brief, weak_seed_skill)
for it in 1..N:  critique = examiner.score(deck_{it-1});  deck_it = generate(brief, skill, revise=critique)
```

5 conditions × 3 seeds × 3 tasks × 3 iters = **45 trajectories**. `gain` = final − initial common
quality; `best_gain` = best-over-iters − initial (robust to a strong generator's iter-2 regressing
below the peak); `frac_improved` = fraction of trajectories where the examiner ever lifted quality.

| examiner (IV) | intrinsic q | mean gain | mean best_gain | frac improved | mean final q | reached thr (q≥0.85) |
|---|---|---|---|---|---|---|
| linter | 0.50 | −0.0042 | 0.0083 | 0.22 | 0.754 | 0% |
| zero_shot_8b | 0.639 | +0.0042 | 0.0083 | 0.11 | 0.786 | 0% |
| zero_shot_30b | 0.785 | +0.0125 | 0.0125 | 0.22 | 0.782 | 11% |
| finetuned_8b | 1.00 | +0.0042 | 0.0083 | 0.22 | 0.754 | 0% |
| hybrid | 1.00 | +0.0111 | **0.0194** | 0.22 | 0.767 | 11% |

- examiner-quality ↔ **gain** correlation: **+0.659**
- examiner-quality ↔ **best_gain** correlation: **+0.558**
- examiner-quality ↔ **final-quality** correlation: −0.147

**Direction holds, magnitude is tiny.** Both gain metrics rank `linter` last and the strong
*semantic* examiners (`zero_shot_30b`, `hybrid`) first, giving a positive examiner-quality→gain
slope (+0.56 to +0.66) — the hypothesised sign. But the effects are sub-1% on a 0–1 scale, only
the two strongest semantic examiners ever push a sub-threshold deck over 0.85 (11% of trajectories;
linter/zs8b/ft never do), and final-quality is essentially flat (−0.147). **Mechanism:** a
mainstream generator floors most briefs at iter 0, so the examiner rarely has actionable headroom —
the same flooring that drives the GEPA result in §2.

**One honest non-monotonicity:** `finetuned_8b` (intrinsic q=1.0) gains no more than `zero_shot_8b`
and less than `zero_shot_30b`. The Part-2 ft examiner is strongest on geometry/defects (modality B),
but this DV is coverage-weighted, so the 30B's semantic critique is more *actionable here* than the
ft examiner's structural critique — consistent with Part 1's perception/semantics dissociation. The
verifiable-gated `hybrid` recovers the top `best_gain` (0.0194).

### 1b. Unfloored regime (E6) — weak generator does not make the effect material

R3-W2/S1 (top-venue panel): the +0.66 cashes out to sub-1 % because a strong generator
floors briefs at iter 0; we must show ≥1 regime *with headroom*. We re-ran the **identical**
gradient (same tasks/seeds/iters/weak-seed/model-free DV) swapping only the generator for a
**weak local `Qwen3-VL-4B-Instruct`** (vLLM, CUDA-graphs; examiner gradient served TP=2). The
weak generator is genuinely unfloored — but the effect does not become material; it **vanishes**:

| regime | mean first-draft q | headroom (1−init) | corr q↔gain | corr q↔best_gain | max best_gain | any condition ≥ thr |
|---|---|---|---|---|---|---|
| strong gen (`qwen3.6-flash`, §1) | 0.763 | 0.237 | **+0.659** | +0.558 | 0.0194 | 11 % |
| **weak gen (`Qwen3-VL-4B`, E6)** | **0.662** | **0.338** (1.43×) | **−0.001** | **0.000** | **0.000** | 0 % |

The weak generator leaves **43 % more headroom**, yet **no** examiner — linter → zs-8B → zs-30B →
ft-8B → hybrid — buys *any* refinement gain (every `best_gain` = 0.0000; every per-dimension Δ ≈ 0).
The cause is **where** the headroom sits: it is **coverage-dominated** (mean coverage component 0.19;
geometry/terms/conciseness already ≈ 1.0), and *coverage* (deck completeness — are the required
sections present?) is critiqued by **neither** the geometry linter **nor** the injected-defect examiner.
The perception/defect critic has nothing to say on the axis where a weak generator actually has room.

**Actionability A/B (the null is an axis mismatch, not revision incapacity).** Holding
generator + task + seed fixed and varying **only the critique** (`data/part3/e6_actionability.json`,
n = 3 first drafts):

| critique fed to the (weak) generator | Δ quality | Δ coverage | deck size |
|---|---|---|---|
| **A. real geometry/structure critique** (linter on the clean draft → 0 violations) | **+0.00** | **+0.00** | 5→5, 8→8 |
| **B. explicit coverage critique** (names the missing required sections) | **+0.32** | **+0.81** | 5→8, 5→9, 8→8 |

The same weak 4B that ignores the geometry-clean critique (A) *adds the named missing sections*
when told (B: e.g. a launch deck 5→8 slides, gaining `problem`/`solution`/`call_to_action`). So the
downstream null is **not** that the weak generator can't revise — it is that the examiner critiques
**perception/layout** while a weak generator's headroom is **content completeness**.

**Takeaway (bounded, honest).** The examiner-quality→utility signal is squeezed from **both** sides:
a *strong* generator leaves no headroom (§1), and a *weak* generator leaves headroom on an axis the
perception critic cannot see (E6). The effect would be material only where the generator's deficit
lies **in the examiner's competence** (perceptual/structural), which the A/B direction confirms in
miniature. This sharpens — not threatens — the diagnostic thesis: the examiner's verifiable value is
its **intrinsic** (Parts 1–2) and **case-study** (§6) performance, not this self-refine loop. See Fig.
`docs/figs/p3_e6_unfloored.png`. _Artifacts: `data/part3/e6_unfloored_synth.json`,
`e6_actionability.json`; runner `scripts/part3_e6_parallel.py`; probe `scripts/part3_e6_actionability.py`._

---

## 2. GEPA skill-space vehicle (SECONDARY)

Same IV, but utility is measured as **optimization efficiency**: rollouts until the running-best
independent common quality crosses threshold (censored cells = budget). 4 conditions × 3 seeds
(GEPA carrier; `zero_shot_30b` 5th point + SkillOpt 2nd carrier deferred — see §5).

| condition | intrinsic quality | rollouts→thr (↓ better) | best gold | best proxy | final quality | audit gold | over-opt |
|---|---|---|---|---|---|---|---|
| linter | 0.5 | 3 | 0.9 | 1.0 | 0.75 | 0.6914 | YES |
| zero_shot_8b | 0.639 | 3 | 0.8917 | 1.0 | 0.8167 | 0.7091 | YES |
| finetuned_8b | 1.0 | 4.67 | 0.8596 | 1.0 | 0.7167 | 0.7003 | YES |
| hybrid | 1.0 | 3 | 0.8813 | 1.0 | 0.8 | 0.6896 | YES |

**H3 gate (secondary):**

- quality↔rollouts correlation: **+0.563** (expected < 0 → higher quality, fewer rollouts)
- monotonic decrease: **False** · optimizer-agnostic (per-carrier {'gepa': 0.563}): **False** · hybrid ≥ single sources: **True**
- **Verdict: COUNTEREXAMPLE** (design-domain feedback-transfer; reported honestly)

---

## 3. Reconciling the two vehicles

The vehicles use **different DVs and disagree by construction**, and the reconciliation is the point:

- **GEPA (efficiency DV)** gives a counterexample (+0.563 = better examiner → *more* rollouts). Its
  proxy (the examiner's own selection score) **saturates at 1.0 for every condition**, so
  "rollouts-to-threshold" mostly measures how fast each proxy maxes out, not real utility — inflated
  further by the running-best-over-rollouts artifact and by the strong generator flooring the task.
- **Self-refine (direct-edit DV)** removes both confounds (no proxy, no running-best) and recovers
  the **expected positive direction** (+0.56 to +0.66), just at tiny magnitude.

So the GEPA "counterexample" is **substantially an artifact of the efficiency DV**, not evidence
the examiner is useless: the cleaner measurement shows the examiner-quality→utility signal is real
but **small in this floored, mainstream-generator design domain**. Both vehicles agree on the
mechanism (limited headroom), which is the honest, VLM-centric takeaway — not a "feedback quality
matters" claim.

---

## 4. Reward-hacking audit (held-out test, gold-vs-proxy)

| condition | proxy | held-out gold | gap | over-opt? | AeSlides cheats |
|---|---|---|---|---|---|
| linter | 1.0 | 0.691 | 0.309 | gen-gap | 0 |
| zero_shot_8b | 1.0 | 0.709 | 0.291 | gen-gap | 0 |
| finetuned_8b | 1.0 | 0.700 | 0.300 | gen-gap | 0 |
| hybrid | 1.0 | 0.690 | 0.310 | gen-gap | 0 |

**No adversarial gaming** (every AeSlides cheat detector = 0; strict geometry gold = 1.0 everywhere).
The proxy−gold gap is a **generalization gap** (proxy maxed on the optimization split does not fully
transfer to held-out test decks), **not reward-hacking**. The verifiable linter proxy has the
smallest gap; the all-linter-gate hybrid is comparable — so "verifiable gate is most hack-resistant"
is only weakly borne out here (no cheats anywhere). Full detail + mechanism + caveats:
`reports/part3_discussion.md`.

---

## 5. Scope & honest deferrals (compute/time)

- **Self-refine (§1)** is the full 5-point gradient incl. `zero_shot_30b`, 3 seeds × 3 tasks, 3 iters.
- **GEPA (§2)** is 4 conditions × 3 seeds; its `zero_shot_30b` 5th point and the **SkillOpt**
  optimizer-agnostic second carrier are **deferred** (30B + per-slide ft examiner over 12-slide
  decks runs in hours on this box; SkillOpt's analyst never emits trajectory files in our adapter —
  root-caused, code retained, off mainline). Per-cell budget ≤12 (not 200) for API latency;
  examiner runs structure-only (modality B).
- The human 3-rater panel arm of P8 stays in todo §12; the held-out verifiable gold (audit) + a
  different-source API judge (`final quality`) are the standing arms.

---

## 6. Real-world confirmation — Hermes pre-sales agent (case-study)

The toy testbed (§1–§2) is *soft*: a strong generator floors synthetic briefs, so
effects are tiny. To test transfer on genuine difficulty, we ran the **same examiner
gradient** on a **real deck produced by the Hermes agent** (its `powerpoint` skill):
a 16-slide 智能制造 pre-sales proposal (`SYC盛原成_智能制造售前方案.pptx`), rendered to images.

**Verifiable defect (model-free DV).** The real deck ships with **20 unfilled template
placeholders** (添加标题 / 添加内文 …) across **7 of 16 slides** — even the title slide reads
"添加一级标题文本". This is a *semantic-completeness* defect a geometry linter is **blind to by
construction** (the boxes are geometrically fine; only reading the text reveals they are
placeholders). Ground truth = per-slide placeholder presence (string match).

**Detection by examiner-quality level** (recall over the 7 placeholder slides; "names it" =
critique text literally cites the placeholder; score = examiner's own quality, lower = more mess):

| examiner | intrinsic q | recall (PH slides) | names the placeholder | score PH | score clean | false-flag (clean) |
|---|---|---|---|---|---|---|
| linter | 0.50 | 0.86* | **0 / 7** | 0.14 | 0.56 | 0.44 |
| zero_shot_8b | 0.639 | 0.71 | 2 / 7 | 0.74 | 0.93 | 0.33 |
| zero_shot_30b | 0.785 | **1.00** | **4 / 7** | 0.03 | 0.64 | 0.67 |
| finetuned_8b | 1.00 | 0.71 | **0 / 7** | 0.71 | 0.82 | 0.33 |
| hybrid | 1.00 | 0.71 | 0 / 7 | 0.74 | 0.82 | 0.33 |

Two findings, both honest:

1. **The examiner transfers to real decks.** `zero_shot_30b` flags **all 7** placeholder slides,
   *names* the placeholder in 4, and scores them near-zero (0.03 vs 0.64 clean) — it clearly
   perceives the real mess.
2. **The ranking is by general-VLM ability, NOT Part-2 intrinsic quality.** By the §1–§2 x-axis,
   `finetuned_8b` is top (q=1.0) — but on this **out-of-distribution** defect (placeholders are not
   in the injected-defect taxonomy it was trained on) it **never names the defect (0/7)** and
   discriminates weakest (gap 0.11). The general zero-shot 30B wins. The linter's 0.86 "recall" is
   **spurious** — geometry noise on a crudely-ingested real template, with 0 placeholder mentions and
   a 0.44 false-flag rate; it cannot see the defect. **This reinforces the paper's VLM thesis**: the
   ft examiner learned a defect *distribution*, not a universal notion of slide quality.
   *Caveat:* the 30B is aggressive (0.67 false-flag on "clean" slides) — though some of those slides
   may carry real non-placeholder defects our placeholder-only ground truth ignores.

**Examiner-critique → revision (one pass).** Feeding the flagged placeholders to **mimo-v2.5-pro**
(Hermes's *own* configured generator, not our toy generator) to fill them, then re-rendering, drives
the verifiable mess from **20 → 0 placeholders** (25 placeholder shapes filled with coherent on-topic
content — e.g. s05's three blanks became "行业覆盖广度 / 项目交付实力 / 服务客户规模" with real body copy).
The critique is **actionable on a real deck**.

**Scope (honest).** One real deck, one defect family (placeholders), one revision round; detection
recall is vs a placeholder-only ground truth (clean-slide false-flags may include genuine
non-placeholder issues). It is a *case-study* (external-validity confirmation), not a controlled
gradient — that is §1. Artifacts: `runs/probe/part3/hermes_case.json`, `hermes_revise.json`,
rendered slides under `data/part3/hermes_case/{slides,revised}/`.

---

_Artifacts: `runs/probe/part3/self_refine_summary.json` (+ `self_refine.jsonl`, 45 records),
`runs/probe/part3/summary.json` (GEPA), `runs/probe/part3/hacking.json`,
`runs/probe/part3/hermes_case.json` + `hermes_revise.json` (real-world arm)._
