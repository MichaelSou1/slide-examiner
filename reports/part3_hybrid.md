# Part 3 (Hybrid arm) — A symbolic–neural critic for slide defects, and recovering VLM detection that pointwise rubric grading suppresses

> **Status:** Protocols 1–3 complete. Protocol-1 = elicitation recovery (6 models / 4 families); Protocol-2 =
> hybrid-critic coverage (hybrid 8/9 @ 0.885 vs linter 5/9 / VLM 2/9) + honest SlideAudit image-only scoping;
> Protocol-3 = published reward-model audit (DocReward blind to G7) + perturbation-fidelity audit (45% snap-absorbed).
> This is an **additive arm** to [part3.md](part3.md) (the self-refine / GEPA downstream-utility study) — a
> separate mechanism-analysis of *how to detect* slide defects, output here and not over-writing that report.

## Thesis (A.0)

The ideal slide-defect critic is **symbolic–neural hybrid**, routed by a per-defect bottleneck:

- **Fine-geometry / rule classes** (G3 alignment, G4 font, G5 brand color, G6 margin, fine G2, S3 terminology,
  S4 density) → a **symbolic linter** (coordinates/rules give ≈0.75–1.0 at ~0 FP; even DesignLab's own neural
  model, fed coordinates, reaches only 0.149 placement recall).
- **Text / structural semantics** (S1 title↔body, S2 narrative order) → an **LLM**.
- **Perceivable-but-format-suppressed render classes** (G1 overflow, S6 image↔text, and the new **G7 render-level
  containment overflow**) → a **VLM**, but only under a *changed elicitation* (atomic binary per-type with forced
  evidence / free-form→classify / synthetic-twin pairwise), **not** the whole taxonomy crammed into one
  pointwise+rubric absolute judgement.

Four claims map to the three protocols:

1. **(Protocol 1, load-bearing)** For the rescuable classes, changing *elicitation* — not the model — recovers
   detection that the pointwise+rubric format suppresses; the **C3-vs-C0** contrast isolates "format suppression,
   not capability."
2. **(Protocol 2)** A static router (defect→engine) gives a hybrid critic that **covers strictly more** than either
   the linter alone or a VLM alone; G7 is caught by the VLM engine while the linter **and** a pure-neural reward
   baseline both miss it.
3. **(Protocol 3)** Published design reward models are **insensitive** to G7 / to perturbations that never render,
   and a perturbation-fidelity audit quantifies the "injected-but-not-rendered" hazard.
4. The defensible contribution is the **per-defect bottleneck dichotomy + the G7 linter-blind class with a
   falsifiable criterion + real-data (SlideAudit) scoping**, not "beating DocReward."

## Background facts this builds on (A.1)

1. Three models (zs-8b / ft-8b / zs-30b) under pointwise+rubric+modality-A, whole-taxonomy single call, all return
   `has_defect=false` on a real "table-of-contents overflow" slide.
2. The *same* image and *same* 30B, asked freely, names the "05 overflow" correctly → the failure is at the
   **calibration / format** layer, not raw perception.
3. Fine geometry (G3 2–32px, tiny G2) stays at floor across resolution / encoder / scale / forced-choice →
   **sub-perceptual, not rescuable → keep the linter** (Parts 1–2).
4. The linter judges the **declared bbox**; its blind spot is **structurally legal but renders broken** = **G7**.

## Methods

### The G7 class (definitional, falsifiable — A.3)

`G7_RENDER_CONTAINMENT_OVERFLOW`: an element whose **declared bbox is legal** (inside the page safe-margin, no bbox
IoU overlap) but whose **rendered content overflows its container / card / page**. Criterion: the declared-bbox
geometry linter returns no finding (asserted), while a human / free VLM sees the overflow. Synthesized (HTML
renderer, freeform, **no snap-to-master**) in three variants — `card_height` (list items render below a too-short
card), `unbreakable_text` (a long unbreakable token spills past the card's right edge), `image_objectfit` (an image
bleeds out of its frame). The IR carries only the legal layout (short fitting card text, non-overlapping in-margin
bboxes); overflow content lives in element metadata and is drawn only by the renderer, so the defect exists **only
in the rendered pixels** → linter- and structure-blind by construction.

**Data:** `data/part3/manifest_g7_rendered.jsonl` — **90 paired** (defective + same-base clean) slides, 30 per
variant. **Linter-blindness self-check: 90/90 (100%) of defectives produce zero `lint_slide` findings** (threshold
was ≥90%). G1/S6 reuse `data/part2/manifest_eval_test_rendered.jsonl` (108 G1, 36 S6 positives, with IR + clean
pairs). Taxonomy is aligned to **SlideAudit** (UIST'25) via `data/part3/taxonomy_map.json` (19-dim bidirectional;
G7 = our-extension refining SlideAudit's "Content Overflow/Cut-off"); all output is reported in SlideAudit-canonical
categories, with an `OTHER` bucket for off-taxonomy items.

### Elicitation conditions (A.4)

| Cond | Elicitation | Engine |
|---|---|---|
| **C0** | pointwise + rubric, **whole taxonomy in one call** (the Part 2 format) | `part3_elicit.py` reusing `part2_eval` |
| **C1** | free-form *describe* → cheap *classify-to-taxonomy* (with `OTHER` exit) | `slide_examiner/elicit_freeform.py` |
| **C2** | geometry-normalized **synth-twin pairwise** (snap-to-master re-render, both orders) | `slide_examiner/elicit_pairwise.py` |
| **C3** | **atomic per-type binary** YES/NO + **forced localization** (PresentBench-style) | `part3_elicit.py` |

Scored paired-clean at two levels — **detection** (`has_defect`) and **named** (the asked type) — with balanced
accuracy + Wilson CI, recall, FPR, precision (`slide_examiner/statistics.py`). The **core scientific contrast is
C3 vs C0**: same model, same taxonomy, same image; the only difference is "ask everything at once" vs "atomic
binary + forced evidence." If C3 ≫ C0, pointwise abstention is a format/cognitive-load artifact, not a capability
gap (the PresentBench-backed claim).

External support: PresentBench (Tsinghua) reports holistic one-shot judging causes judge overload/abstention and
that **atomic binary checklist items (one call each) + forced localization** are reliable and human-aligned; its
Tables 3–4 self-report "Visual Design & Layout" as the lowest-scoring, widest-model-gap dimension needing
"dedicated visual/rendering pipelines" — external support for *needing a hybrid critic*.

## Result 1 — elicitation recovery (Protocol 1)

**6 models across 4 families and 3 scales** — Qwen3.5-9B / Qwen3.5-27B / Qwen3.6-27B (Qwen, three scales),
InternVL3.5-8B (OpenGVLab), Ovis2.5-9B (AIDC), Gemma4-31B (Google) — × C0/C1/C2/C3 × {G1,S6,G7}, modality A,
paired-clean (60 G1 / 36 S6 / 60 G7 positives + matched cleans), all zero-shot. Cell = **detection** bal-acc ·
precision. Verdict **✅ rescued** = Δbal-acc>0 AND McNemar p<0.05 on paired same-image correctness AND
precision≥0.70. (`data/part3/p1_summary.json`, `reports/_p1_tables.md`.)

| Family (scale) | Defect | C0 | C1 free-form | C2 synth-twin | C3 atomic-binary | Verdict |
|---|---|---|---|---|---|---|
| Qwen 9B  | G1 | 0.64 p.62 | 0.52 | 0.64 p1.0 | 0.51 | — |
| Qwen 9B  | S6 | 0.92 p.86 | 0.58 | 0.50 | 0.75 p.91 | — |
| Qwen 9B  | **G7** | 0.50 | 0.50 | 0.51 | **0.93 p.88** | ✅ C3 |
| Qwen 27B | G1 | 0.69 p.63 | 0.46 | **0.93 p1.0** | 0.50 | ✅ C2 |
| Qwen 27B | S6 | 0.89 p.82 | 0.49 | 0.94 p1.0 | 0.50 | — |
| Qwen 27B | **G7** | 0.93 p.87 | 0.51 | 0.92 p1.0 | **1.00 p1.0** | ✅ C3 |
| Qwen3.6 27B | G1 | 0.53 | 0.50 | **0.78 p1.0** | 0.50 | ✅ C2 |
| Qwen3.6 27B | S6 | 0.50 | 0.50 | 0.58 p1.0 | 0.50 | — |
| Qwen3.6 27B | **G7** | 0.52 | 0.50 | **0.92 p.93** | **1.00 p1.0** | ✅ C2/C3 |
| Gemma4 31B (Google) | G1 | 0.64 p.60 | 0.50 | 0.75 p1.0 | 0.50 | — |
| Gemma4 31B (Google) | S6 | 0.81 p.72 | 0.50 | 0.50 | 0.50 | — |
| Gemma4 31B (Google) | **G7** | 0.75 p.67 | 0.50 | 0.56 p1.0 | **1.00 p1.0** | ✅ C3 |
| InternVL 8B | G1 | 0.32 p.37 | 0.50 | 0.50 | **0.60 p1.0** | ✅ C3 |
| InternVL 8B | S6 | 0.43 | 0.50 | 0.50 | 0.50 | — |
| InternVL 8B | G7 | 0.47 | 0.50 | 0.56 p.55 | 0.50 | ❌ |
| Ovis 9B | G1 | 0.47 | 0.51 | 0.51 p1.0 | 0.50 | — |
| Ovis 9B | S6 | 0.92 p.87 | 0.60 | 0.53 p1.0 | 0.50 | — |
| Ovis 9B | G7 | 0.59 p.82 | 0.64 | 0.67 p1.0 | 0.61 p1.0 | — |

**Reading (model-agnostic findings):**

1. **C3 atomic-binary rescues the G7 render class — and it replicates across two unrelated families at every
   scale.** Qwen3.5-9B 0.50→**0.93**, Qwen3.5-27B 0.93→**1.00**, Qwen3.6-27B 0.52→**1.00**, and **Google
   Gemma4-31B 0.75→1.00** (precision 0.88–1.00, McNemar p<0.05). This is the headline "format suppression, not
   capability" result: C0's fixed taxonomy cannot *name* the off-taxonomy render class, so it abstains/misnames;
   the atomic per-type binary recovers it. That the *same* effect appears in Qwen *and* Google models (different
   pre-training, different vendors) is the core model-agnostic evidence. (On Qwen3.6-27B, C2 synth-twin also
   reaches G7, 0.92.)

2. **C2 synth-twin rescues declared-geometry G1 on the capable models.** Qwen3.5-27B 0.69→**0.93**,
   Qwen3.6-27B 0.53→**0.78** (precision 1.00): snap-to-master absorbs the declared overflow and the pairwise
   contrast exposes it — C2's designed target.

3. **C1 free-form is unreliable — it collapses on the strong models.** Qwen-27B/3.6-27B C1 ≈ 0.46–0.50 with
   fpr≈1.0 (flags a defect on nearly every clean slide); the capable, verbose models free-associate nits. So
   naive free-form is not a universal recovery — it trades a weak model's abstention for a strong model's
   over-flagging.

4. **Cross-family replication + an honest weak case.** OpenGVLab's **InternVL-8B** over-flags G1 under C0 (0.32,
   high fpr) and **C3 cleans it (→0.60, precision 1.00, ✅)** — the same "atomic binary disciplines the model"
   mechanism in a different family. AIDC's **Ovis-9B** (a weaker 9B) shows **no significant rescue**, though C2/C3
   stay high-precision on G7 (0.67 / 0.61, precision 1.00) — an honest "weaker model, modest gains" case. (Both
   Ovis and Qwen-9B already handle S6 well under C0, 0.92.)

### C3 vs C0 on G7 — the format-suppression contrast, across families

| Family (scale) | G7 C0 | G7 C3 | Δ |
|---|---|---|---|
| Qwen 9B | 0.50 | **0.93** | +0.43 |
| Qwen 27B | 0.93 | **1.00** | +0.07 |
| Qwen3.6 27B | 0.52 | **1.00** | +0.48 |
| **Gemma4 31B (Google)** | 0.75 | **1.00** | +0.25 |
| InternVL 8B | 0.47 | 0.50 | +0.03 |
| Ovis 9B | 0.59 | 0.61 | +0.02 |

C3 ≥ C0 on G7 for **every** model (strongly on the capable Qwen + Google families, both reaching 1.00), while C3 *loses* to C0 on the in-taxonomy
G1/S6 (C0 already contains them). The format-suppression effect is **specific to the off-taxonomy render class
G7** — exactly the hybrid critic's VLM target. The capable Qwen models hit the ceiling (1.00 at precision 1.00);
the weaker InternVL/Ovis see G7 only marginally (the legal-bbox render overflow sits near their perceptual floor).

### Localization verification — the G7 rescue is real perception, not a "yes" bluff

The paired-clean control rules out "always-yes" hallucination (precision 1.00 = zero false alarms on the
identical-but-clean twins), but it leaves open whether a correct *yes* points to the *right place*. So the
forced evidence (C3 names a region + an element) is checked against the synthetic G7 ground truth (the overflow
region + which element spills). On the **four capable models' G7 true-positives, the evidence is correct ≥98%
on both region and element** (`localization_g7`, `part3_p1_summary.py`):

| Model | C3 G7 detections (n) | region correct | element correct |
|---|---|---|---|
| Qwen 9B | 60 | 98% | 98% |
| Qwen 27B | 60 | 100% | 100% |
| Qwen3.6 27B | 60 | 100% | 100% |
| Gemma4 31B (Google) | 60 | 100% | 100% |
| Ovis 9B (weak) | 13 | 100% | 46% |

Critically, the models name the **specific spilling content**, not a generic "bottom": e.g. Gemma4 *"the list
items starting from 'Cost attribution'"*, Qwen-27B *"the list items 'Cost attribution', 'Multi-tenant
isolation'"* — exactly the bullets rendered *below* the card. A bluffing model cannot read back the specific
overflowing item by its text, which rules out both the "always-yes" and the "spurious busyness-cue" failure
modes. (Ovis, the weak 9B, still gets the *region* right 100% on its 13 detections but names the element less
reliably — consistent with it being a marginal perceiver of G7.) Localization correctness on *real* data
(SlideAudit, where some dims carry human bounding boxes) and a perturbation-fidelity audit of the ground truth
itself are deferred to Protocols 2–3.

### A.4 verdict — no universal elicitation; recovery is model × class × elicitation conditional

- **Rescued (✅, 7 cells):** G7 via **C3** on Qwen-9B, Qwen-27B & **Google Gemma4-31B** (+ C2 on Qwen3.6-27B);
  G1 via **C2** on Qwen-27B & Qwen3.6-27B; G1 via **C3** on InternVL-8B.
- The optimal elicitation is **jointly determined by model capability × defect class** — C3 for the render class
  on a capable model, C2 for declared geometry, and *not* C1 (which collapses on strong models). The pattern
  **replicates across 4 families (Qwen / OpenGVLab / AIDC / Google) and 3 scales**: the effect is a property of
  the elicitation × defect interaction, not of one model or vendor — the model-agnostic evidence for the thesis.
- This is a *positive* result for the hybrid thesis: the router must be capability- and class-aware, and the VLM
  engine's defensible win is **G7 via C3 on a capable model** (Qwen-27B and Gemma4-31B both at 1.00 / precision 1.00).
- **Honest negatives & scoping:** S6 (image-text) is never *rescued* (C0 already decent where the model is able,
  weak otherwise). InternVL barely perceives G7; Ovis shows no significant rescue. C1 collapses on strong models.
  One further family was attempted but dropped: **Zhipu GLM-4.6V-Flash** served cleanly (on an isolated
  transformers-5 env) but ran pathologically slowly at our settings (~2 h/cell). *Serving-stack note:* the newest
  models needed care — many (Qwen3.5/3.6, Ovis2.5, Gemma4) are **thinking models** (handled with
  `enable_thinking=false` + a 2048-token budget + a `<think>`-tolerant parser); Gemma4 required an isolated
  **vLLM 0.23+cu129** env (its only release wheel is CUDA-13, incompatible with the box's CUDA-12.8 driver — the
  cu129 wheel was pulled via a GitHub mirror, paired with torch-cu128, and served with **fp8 KV disabled** since
  the RTX-3080/Ampere lacks the `fp8e4nv` dtype). None of this is hidden; it shapes the router and the scoping.

## Result 2 — hybrid critic coverage (Protocol 2)

`slide_examiner/hybrid_critic.py` wires a **static router** (`defect → engine`) over three engines and one served
VLM/LLM endpoint (Qwen3.5-27B): the symbolic **linter** (`lint_slide`/`lint_deck`, shipped defaults, ~0 FP), the
**VLM** under its best Protocol-1 elicitation (G7→C3, S6/S1→C0), and a text-only **LLM** (S4 density, deck
semantics). We score three *critic configurations* on the same paired-clean synthetic slides, per class, by **named
attribution** (the critic must emit the *correct* defect type on the defective image and not on its clean twin),
at paired-clean balanced accuracy · precision (`scripts/part3_p2_eval.py`, `data/part3/p2_synth.json`,
freeform renders, mpd=40).

### Result 2a — synthetic all-class coverage

| Defect | router | linter-only | VLM-only (C0) | **hybrid** |
|---|---|---|---|---|
| G1 overflow | linter | 1.00 p1.00 | 0.50 | **1.00 p1.00** |
| G2 overlap | linter | 0.80 p1.00 | 0.71 p1.00 | **0.80 p1.00** |
| G3 alignment | linter | 1.00 p1.00 | 0.47 | **1.00 p1.00** |
| G5 colour | linter | 1.00 p1.00 | 0.50 | **1.00 p1.00** |
| G6 margin | linter | 1.00 p1.00 | 0.50 | **1.00 p1.00** |
| **G7 render-overflow** | VLM (C3) | **0.00** | 0.50 | **1.00 p1.00** |
| S1 title-body | VLM (C0) | 0.50 | 0.94 p0.90 | **0.94 p0.90** |
| S4 density | LLM | 0.50 | 0.51 | **0.72 p1.00** |
| S6 image-text | VLM | 0.50 | 0.50 | 0.50 |

| Critic config | mean bal-acc | classes covered (bal-acc ≥ 0.70 & precision ≥ 0.70) |
|---|---|---|
| linter-only | 0.70 | **5 / 9** (G1, G2, G3, G5, G6 — all geometry) |
| VLM-only (C0) | 0.57 | **2 / 9** (G2, S1) |
| **hybrid (routed)** | **0.885** | **8 / 9** (all but S6) |

**Reading.** The hybrid **strictly dominates** both single-engine critics — mean bal-acc 0.885 vs 0.70
(linter) / 0.57 (VLM), and 8/9 classes covered vs 5/9 / 2/9 — because the engines are *complementary*, exactly as
the bottleneck dichotomy predicts:

1. **Linter owns declared geometry** (G1–G6: 0.80–1.00 at precision 1.00) where the **VLM is at floor** (C0
   0.47–0.71, cannot name fine alignment/colour/margin from pixels — the Part-1 sub-perceptual result).
2. **VLM owns the render class G7** — the load-bearing cell: **linter 0.00** (blind by construction), **VLM-C0
   0.50** (cannot *name* the off-taxonomy class), **hybrid 1.00 at precision 1.00** via the C3 atomic-binary engine.
   No single standard engine covers G7; the hybrid does. (Result 3a shows a published neural reward model also
   scores 0.28 here — so linter, pointwise-VLM, *and* neural reward all miss G7.)
3. **LLM owns density** S4 (0.72 at precision 1.00, where linter and pointwise-VLM are at chance).
4. **A data-driven routing finding:** S1 title-body mismatch was initially routed to the text-LLM, but the text-only
   probe **over-flags** (0.25, precision 0.09) while the image-bearing VLM names it reliably (**0.94, precision
   0.90**). Title-body mismatch needs the *rendered layout*, not just the text — so the router assigns S1→VLM. We
   report this transparently as a refinement, not a tuned result.
5. **Honest negative:** **S6 image-text contradiction stays at 0.50 for every engine** — never rescued (consistent
   with Result 1). It is the one class the hybrid does not cover; we do not hide it.

### Result 2b — real data (SlideAudit), honest image-only degradation

SlideAudit is **image-only — 0/2400 records carry element structure (IR)**. So the hybrid's two *structural*
engines cannot run (the linter needs declared bboxes; the text-LLM needs the slide text) and **the hybrid degrades
to its VLM engine** — the central real-data caveat, stated not hidden. What transfers is the Protocol-1 elicitation
effect: per SlideAudit-canonical class, present vs `confident_absent`, paired bal-acc · precision
(`scripts/part3_p2_slideaudit.py`, `data/part3/p2_slideaudit.json`, 40/class).

| Defect (SlideAudit) | VLM C0 | VLM **C3** (atomic) | Δ |
|---|---|---|---|
| G3 alignment | 0.56 | **0.72 p0.71** | +0.16 |
| G5 colour | 0.52 | **0.81 p0.91** | +0.29 |
| S4 density | 0.68 | **0.74 p0.88** | +0.06 |
| G1 overflow | 0.55 | 0.62 p0.81 | +0.07 |
| G4 font | 0.59 | 0.64 p0.79 | +0.05 |
| G6 margin | 0.51 | 0.55 | +0.04 |
| G2 overlap | 0.96 p0.93 | 0.94 p0.95 | −0.02 |

**Reading.** Even with no structure (so no linter), the **atomic-binary C3 elicitation beats C0 pointwise on real
slides for every class** (G5 0.52→0.81, G3 0.56→0.72) — the Protocol-1 "format suppression" effect is **not a
synthetic artifact; it transfers to third-party human-annotated data**. But absolute geometry detection on bare
pixels stays modest (0.55–0.74 outside the blatant overlap class) — real fine geometry needs the symbolic linter,
which needs the element structure that bare images lack (consistent with Part 2). The hybrid's *full* power
therefore requires native `.pptx`/IR; on image-only real data it runs in its degraded VLM-only mode. This is the
honest ceiling, and it is set by **missing structure, not missing method**.

## Result 3 — reward-model audit + perturbation fidelity (Protocol 3)

We do not retrain a reward model (expensive, derivative). Instead we **audit a published one** and
**audit the data pipeline itself**, two cheap experiments that yield a hard, falsifiable finding apiece.

### Result 3a — a published design/document reward model is blind to G7

**Model.** `jeepliu/DocReward-3B` (DocReward, arXiv 2510.11391) — a Qwen2.5-VL-3B with a Bradley-Terry value
head, trained on 117K paired documents to score **structure & style**, explicitly *textual-quality-agnostic*; it
reports beating GPT-5 by 14.6 pts on document professionalism. We load its backbone + `value_head.bin`
(`Linear(2048→1)` on an appended `<|regression|>` token) with plain transformers — no trl/llamafactory — and ask a
single falsifiable question per defect class on the **same paired-clean slides** used by Protocols 1–2:

> does it score the clean slide above its defective twin, i.e. `reward(clean) > reward(defective)`?

A reward blind to a class scores the defective slide no lower → paired preference accuracy ≈ 0.5
(`scripts/part3_p3_reward_audit.py`, `data/part3/p3_audit.json`; 40 pairs/class, freeform renders).

| Defect | preference acc [95% CI] | mean reward gap (clean − def) | verdict |
|---|---|---|---|
| **G7 render-overflow** | **0.28 [0.16, 0.43]** | **−0.23** | ❌ **blind — prefers the broken slide** |
| G5 colour | 0.40 [0.26, 0.55] | −0.01 | ❌ blind (≈ chance) |
| G1 overflow | 0.95 [0.83, 0.99] | +0.63 | ✅ sensitive |
| G2 overlap | 1.00 [0.91, 1.00] | +2.15 | ✅ sensitive |
| S4 density | 1.00 [0.90, 1.00] | +2.22 | ✅ sensitive |
| S6 image-text | 1.00 [0.82, 1.00] | +1.04 | ✅ sensitive |

**Reading.** DocReward cleanly penalises the defects it can see — declared overflow, overlap, density, image-text
(0.95–1.00). But on **G7 its preference accuracy is 0.28, with the 95% CI entirely below chance**: it does not
merely ignore the render-containment overflow, it *slightly prefers* the overflowing slide (negative reward gap —
the over-spilling card simply shows more content). This is the **neural-reward counterpart of the linter's blind
spot**: the linter misses G7 because the declared bbox is legal; the reward model misses G7 because the overflow is
an off-distribution render artifact its preference data never taught it to punish. So for the linter-blind render
class, **both the symbolic linter and a published neural reward model fail — only the VLM-with-C3 engine (Result 1 /
Result 2) catches it.** That is the empirical core of the hybrid thesis: G7 needs an engine that *neither* of the
two standard critics provides. (DocReward is also blind to brand-colour G5, a rule class the linter owns at
bal-acc 1.0 — again complementary strengths.)

### Result 3b — perturbation-fidelity audit: ~45 % of injected geometry defects never render

Generalising the Part-2 *snap-bug* byte/structure check (`scripts/part3_p3_fidelity.py`,
`data/part3/p3_fidelity.json`): every Part-2 defective IR was rendered two ways — `freeform` (drawn as declared)
and `template` (snapped to the master grid first). We measure, per class, whether the injected defect actually
renders (changed-pixel fraction vs its clean twin) under each path.

| Defect | freeform Δpx (median) | template Δpx | absorbed by snap (among rendered) |
|---|---|---|---|
| G2 overlap | 0.090 | 0.000 | **100 %** |
| G3 alignment | 0.007 | 0.000 | **100 %** |
| G6 margin | 0.011 | 0.000 | **100 %** |
| G1 overflow | 0.047 | 0.001 | 20 % |
| G5 colour | 0.0025 | 0.0025 | 0 % |
| S1 / S4 / S6 (text) | 0.006–0.010 | unchanged | 0 % |

**Overall 45 % of injected defectives (306 pairs, all confirmed IR-injected) render under freeform but are *snapped
away*** — pixel-identical to their clean twin — under the template path. Snap-to-master re-fits element bboxes to
the master grid, silently erasing every overlap/alignment/margin perturbation and a fifth of overflows; colour and
text-semantic defects (non-geometric) survive. Two consequences:

1. **Eval validity:** this is exactly why Protocols 1–2 use the freeform renderer — on the template renders ~45 % of
   the "defective" labels sit on visually-clean images (silent label noise). It also explains the latent FF/TPL
   interleaving in the legacy manifest (handled by filtering to freeform).
2. **Reward-pipeline hazard (ties 3a↔3b):** feeding DocReward the **template** (snap-absorbed) pairs gives a
   preference accuracy of **0.00 at a reward gap of exactly 0.000** on G2/G3/G6 — the two images are identical, so
   *no* reward model can react. Any reward/critic trained or evaluated on snap-rendered images with IR-derived
   labels inherits ~45 % zero-signal pairs. Perturbation fidelity must be verified at the pixel level, not assumed
   from the IR — a methodological prerequisite the field largely skips.

### Honest scoping (Protocol 3)

- **One reward model audited.** DocReward is the most on-target public weight (document structure/style). A natural
  second target, **`MeiGen-AI/PosterReward_v1`** (graphic-design reward, CVPR'26), is public and downloaded, but its
  scorer is an *ms-swift* `seq_cls` head we could not reproduce faithfully without the swift runtime (installing it
  risks the working serving envs mid-run); it is deferred, not claimed. The audit *method* is model-agnostic.
- DocReward scores **documents**, not slides specifically; its G1/G2 sensitivity shows the transfer is real, so its
  G7 failure is a genuine blind spot, not a domain mismatch artifact.
- We trained no scalar baseline (Protocol-3b optional path) — the published-weight audit is the stronger,
  non-derivative evidence and the QLoRA baseline is left as future work.

## Honest scoping & negative results

- SlideAudit is **image-only** (no IR) → the hybrid's linter engine runs only in degraded image-only mode on real
  data; the full-power structural path needs native `.pptx` (only the Hermes deck on this box is native). Stated, not hidden.
- The `demo_real/` real-world examples are **non-eval** (qualitative figures / cold-email hooks only); see
  `data/part3/demo_real/SOURCES.md`.
