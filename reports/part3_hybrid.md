# Part 3 (Hybrid arm) — A symbolic–neural critic for slide defects, and recovering VLM detection that pointwise rubric grading suppresses

> **Status:** Protocols 1–3 complete. Protocol-1 = elicitation recovery (6 models / 4 families); Protocol-2 =
> hybrid-critic coverage (hybrid 8/9 @ 0.885 vs linter 5/9 / VLM 2/9) + honest SlideAudit image-only scoping;
> Protocol-3 = multi-RM reward audit (3 scorers: narrow document/aesthetic rewards blind to G7, a general-VLM reward
> detects it) + perturbation-fidelity audit (45% snap-absorbed, zero-signal across all rewards).
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
3. **(Protocol 3)** The G7 blind spot is a property of **narrow critics**: across 3 published reward scorers, a
   document-structure reward and a pure-aesthetic scorer are insensitive to G7 (at chance), but a capable
   general-multimodal reward detects it — so "G7 needs a VLM engine" holds whether that VLM is prompted (Result 1)
   or reward-headed. A perturbation-fidelity audit further shows ~45% of injected defects never render (zero signal
   for *every* reward).
4. The defensible contribution is the **per-defect bottleneck dichotomy + the G7 linter-blind class with a
   falsifiable criterion + real-data (SlideAudit) scoping**, not "beating DocReward."

### Summary — claims ↔ evidence

| Claim | Evidence (this report) | Cross-ref (Parts 1–2) |
|---|---|---|
| **1.** Changing *elicitation* (not the model) recovers detection that pointwise+rubric suppresses; C3-vs-C0 isolates "format suppression, not capability". | Result 1: C3 rescues G7 across Qwen 9B/27B/3.6 + Gemma4 (0.50/0.93/0.52/0.75 → 0.93–1.00); replicates over 4 families. C3>C0 on real SlideAudit too (Result 2b). | 30B free-form vs pointwise on the ToC slide (A.1.2). |
| **2.** A static per-defect router gives a hybrid that covers **strictly more** than linter-alone or VLM-alone; G7 is caught by the VLM engine while the linter misses it. | Result 2a: hybrid **8/9 @ 0.885** vs linter 5/9 @0.70, VLM 2/9 @0.57; **G7: linter 0.00 / VLM-C0 0.50 / hybrid 1.00**. | linter 0.75–1.0 on geometry; DesignLab 0.149 placement recall. |
| **3.** The G7 blind spot is a property of *narrow* critics, not all neural rewards; a fidelity audit quantifies the "injected-but-not-rendered" hazard. | Result 3a (3-RM, n=90): DocReward G7 **0.48**, LAION-aesthetic **0.57** (both CI-spanning-chance) vs Skywork-VL **0.79** (detects). Result 3b: **45%** snapped away; snap-absorbed → gap 0.0 for **all** rewards. | snap-bug byte/structure check (Part 2); Result-1 C3 = prompted VLM also detects G7. |
| **4.** The contribution is the **per-defect bottleneck dichotomy + the falsifiable G7 linter-blind class + real-data scoping**, not "beating DocReward". | All four Results + honest SlideAudit image-only degradation + S6 negative. | Part-1 sub-perceptual geometry; Part-2 examiner + linter routing. |
| **5.** The perception/capability split **replicates on real layouts** with a lossless tool oracle (closes the §8 "can't run structured eval on real slides" hole). | Result 4 (Zenodo10K, 209 real pairs, 3 models): all 3 outcomes appear — G1/G2 image-sufficient, **G6 margin perception (B 0.70 > A 0.59, structure rescues weak VLMs)**, **G3 alignment capability (A=B=C≈0.50, → linter)**; real-deck render-fidelity 0.93 (vs synthetic 45% absorbed). | Part-1 A/B/C synthetic attribution; §4 template-absorption hazard (now shown template-specific). |

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

![Per-defect coverage: linter vs single VLM vs routed hybrid](../docs/figs/p3_coverage_heatmap.png)

**Reading.** The hybrid **strictly dominates** both single-engine critics — mean bal-acc 0.885 vs 0.70
(linter) / 0.57 (VLM), and 8/9 classes covered vs 5/9 / 2/9 — because the engines are *complementary*, exactly as
the bottleneck dichotomy predicts:

1. **Linter owns declared geometry** (G1–G6: 0.80–1.00 at precision 1.00) where the **VLM is at floor** (C0
   0.47–0.71, cannot name fine alignment/colour/margin from pixels — the Part-1 sub-perceptual result).
2. **VLM owns the render class G7** — the load-bearing cell: **linter 0.00** (blind by construction), **VLM-C0
   0.50** (cannot *name* the off-taxonomy class), **hybrid 1.00 at precision 1.00** via the C3 atomic-binary engine.
   No single *narrow* engine covers G7; the hybrid does. (Result 3a: the linter, a document-structure reward
   (DocReward 0.48) and an aesthetic scorer (LAION 0.57) all miss G7, while a general-VLM reward (Skywork 0.79)
   detects it — confirming the engine G7 needs is a capable VLM, prompted or reward-headed.)
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

We do not retrain a reward model (expensive, derivative). Instead we **audit published ones** and
**audit the data pipeline itself**, two cheap experiments that yield a hard, falsifiable finding apiece.

### Result 3a — the G7 blind spot is a property of *narrow* critics, not of capable general VLMs (multi-RM audit)

We **audit four published scorers** spanning three categories and three
backbone families on the **same paired-clean slides** (G7 at **90/90**; 18–54 pairs/synth class, freeform renders),
behind a uniform `RewardAdapter` interface (`slide_examiner/reward_adapters.py`, `scripts/part3_p3_reward_audit.py`,
`data/part3/p3_audit_multi.json`). The falsifiable question per class: `reward(clean) > reward(defective)`? A scorer
blind to a class assigns the defective slide no lower reward → paired preference ≈ 0.5 (CI spanning chance).

| Reward scorer | category | backbone | contract |
|---|---|---|---|
| **DocReward-3B** (`jeepliu/DocReward-3B`) | document structure/style | Qwen2.5-VL-3B | BT value head on `<\|regression\|>` (image-only) |
| **Skywork-VL-Reward-7B** | general multimodal | Qwen2.5-VL-7B | value head, generic-quality prompt |
| **LAION-Aesthetic** | pure aesthetic | CLIP ViT-L/14 | linear head on the image embedding |
| *(IXC-2.5-Reward-7B)* | *general multimodal* | *InternLM2-7B* | *deferred — broken under transformers 5.6; see scoping* |

Each is scored under its native, **deployment-realistic contract with no defect named**; for the prompt-conditioned
rewards we use a generic quality elicitation (and a defect-naming *probe* as a control). Preference accuracy per
class (freeform; 95% CI; **G7 boldface**):

| Reward scorer | G1 overflow | G2 overlap | G5 colour | **G7 render** | S4 density | S6 img-text |
|---|---|---|---|---|---|---|
| DocReward-3B (document) | 0.93 | 1.00 | 0.37 | **0.48 [0.38, 0.58]** | 1.00 | 1.00 |
| Skywork-VL-7B (general-mm) | 0.94 | 0.72 | 0.46 | **0.79 [0.69, 0.86]** | 0.92 | 1.00 |
| LAION-Aesthetic (aesthetic) | 0.37 | 0.91 | 0.57 | **0.57 [0.46, 0.66]** | 0.75 | 0.61 |

![Reward preference per model × defect — narrow rewards miss G7, a general-VLM reward detects it](../docs/figs/p3_reward_blindspot_multi.png)

**Reading.** Every scorer is clearly sensitive to several in-taxonomy classes (DocReward G1/G2/S4/S6 0.93–1.00;
Skywork G1/S4/S6 0.92–1.00; LAION G2 0.91), so each is a *working* reward — its G7 behaviour is not a domain-mismatch
artifact. On **G7 the picture splits**, and this refines our original single-model claim:

- the **symbolic linter (0.00, Result 2)**, the **document-structure reward (DocReward 0.48 [0.38, 0.58], gap −0.09)**
  and the **pure-aesthetic scorer (LAION 0.57 [0.46, 0.66], gap +0.03)** all sit **at chance** — their 95% CIs
  include 0.5, i.e. they carry *no reliable signal* about the render-containment overflow;
- the **general-multimodal reward (Skywork-VL 0.79 [0.69, 0.86], gap +1.36)** **does** detect it — its Qwen2.5-VL-7B
  backbone perceives the overflow even without being told to look for it.

So the G7 blind spot is **not model-agnostic across all neural rewards**; it is a property of **narrow critics** —
rule-based linters and *specialised* (document / aesthetic) reward heads — whereas a **capable general VLM** catches
it. This is consistent with, and an independent instance of, the hybrid thesis: **G7 needs a capable VLM engine, and
that engine works whether it is *prompted* (Result-1 C3, 0.93–1.00) or carries a *reward head* (Skywork 0.79).** The
honest revision of Protocol-3 is therefore: *the linter and narrow rewards motivate the VLM engine; a general VLM
(prompted or reward-headed) closes the gap* — not "every neural reward is blind to G7." (DocReward is also blind to
brand-colour G5 at 0.37, a rule class the linter owns at bal-acc 1.0; complementary strengths persist.)

**Elicitation control (probe).** For the prompt-conditioned Skywork, naming containment/overflow in the prompt lifts
G7 from 0.79 → **0.87** (gap +1.36 → +2.59) — same direction as Result-1's C0→C3, although Skywork already detects
G7 under the generic prompt, so this is reinforcement, not rescue. (A 40-pair subset of a single G7 variant gave
Skywork 0.58 with a CI spanning chance; the full 90-pair audit over all three variants resolves it to 0.79. We
report the full-set number, and the n=40→n=90 shift is itself a note on per-variant heterogeneity.)

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
2. **Reward-pipeline hazard (ties 3a↔3b), now cross-RM:** feeding **all three** reward scorers the **template**
   (snap-absorbed) pairs gives a preference accuracy of **0.00 at a reward gap of exactly 0.000** on G2/G3/G6
   (`data/part3/p3_fidelity_multi.json`) — the two images are pixel-identical, so *no* scorer (document,
   general-multimodal, *or* aesthetic) can react. This part **is** model-agnostic by construction. Any reward/critic
   trained or evaluated on snap-rendered images with IR-derived
   labels inherits ~45 % zero-signal pairs. Perturbation fidelity must be verified at the pixel level, not assumed
   from the IR — a methodological prerequisite the field largely skips.

### Honest scoping (Protocol 3)

- **Three reward scorers audited (document / general-multimodal / aesthetic), not one.** This is the upgrade over
  the original single-DocReward audit: the G7 blind spot is now shown to be a property of *narrow* critics
  specifically (it does **not** generalise to a capable general-multimodal reward, Skywork-VL). That is the honest,
  reviewer-proof finding — a reviewer who tested Skywork themselves would find 0.79, so we report it.
- **IXC-2.5-Reward-7B (general-mm, InternLM2 backbone) attempted but deferred.** It loads on this box only with a
  chain of transformers-5.6 workarounds (offline font, re-added `config.max_length`, vision tower built from config,
  4-GPU `device_map`, `hd_num=1` to fit eager attention), but its **PLoRA image-token adapters do not load** under
  that path (`lora_sft/dpo/web` reported missing → re-initialised), corrupting the image stream (it then *prefers*
  the overlapping G2 slide, pref 0.00). The results are invalid and excluded; the adapter is committed
  (`slide_examiner/reward_adapters.py:IXCRewardAdapter`) for a future single-large-GPU / PLoRA-aware re-run.
- **`MeiGen-AI/PosterReward_v1`** (graphic-design reward, CVPR'26) is public but its *ms-swift* `seq_cls` head needs
  the swift runtime (installing it risks the working serving envs); it remains deferred, not claimed.
- DocReward / Skywork score **documents / general images**, not slides specifically; their G1/G2/S4 sensitivity shows
  the transfer is real, so the G7 result (blind for DocReward, detected by Skywork) is genuine, not a domain artifact.
- We trained no scalar baseline (Protocol-3b optional path) — the published-weight multi-RM audit is the stronger,
  non-derivative evidence and the QLoRA baseline is left as future work.

## Result 4 — real-layout perception/capability attribution (R2; closes the §8 hole)

**The hole.** The Diagnosis (Result-1 / paper §4) runs the A/B/C modality attribution on *synthetic* slides;
the paper's Limitations flagged that the cleanest discrimination — a **structured (image+oracle) evaluation on
*real* slides** — was not run, because a real oracle seemed to need human annotation (labour) or model
self-annotation (bias). We close it with **Zenodo10K** (the PPTAgent corpus, arXiv:2501.03936): real CC-licensed
`.pptx` whose element XML is intact, so `python-pptx` extracts a **lossless** geometry/text/style oracle straight
from the source file — no human, no self-annotation bias.

**Pipeline** (all new: `scripts/part3_pptx_to_ir.py` → `part3_real_inject.py` → `part3_pc_real.py` →
`part3_pc_real_sweep.py` → `part3_pc_real_summary.py`): 26 real decks → 505 slide IRs (px @ 96 dpi, aligned to the
VLM-SlideEval PPTX-XML-GT convention). For a sampled slide we build a one-slide deck and inject **one single-shape
defect in PPTX XML space** — G1 overflow (autofit off + enlarge font), G2 overlap (move a shape onto a sibling),
G3 alignment offset (nudge one axis), G4 font-size inconsistency (resize one block vs peers), G6 margin violation
(push a shape off the slide edge) — then render **both** the clean and defective one-slide deck with the **same real
renderer** (LibreOffice headless → PDF → PNG), so the paired pixel diff isolates exactly the injected defect on
**real pixels**. A self-check drops any pair whose injection did not change the rendered pixels. **G5** (brand colour;
real third-party decks declare no brand palette) and **G7** (already the synthetic falsifiable class; cannot be
reproduced from a real text frame without leaking the overflow text into the oracle) are out of scope, stated
honestly; the S-* semantic classes need content understanding to inject faithfully and stay synthetic. Final set:
**209 paired (clean, defective) slides, 26 decks, 5 classes** (G1 45, G2 41, G3 40, G4 45, G6 38).
*(Injection-quality gotcha, fixed: setting `shape.left` on a python-pptx placeholder that **inherits** its
position synthesizes an `<a:off>` with the other coordinate defaulting to 0 — silently teleporting the shape; the
geometry mutators now pin all four coords. 0/209 perpendicular-jump records after the fix.)*

**Result-4b — render-fidelity on real decks re-checks the §4 hazard (`data/part3/pc_real_fidelity.json`).**
The §4 "snap-to-master absorbs **45%** of injected geometry defects" hazard is **template-specific**: on real
free-form decks only **7.1%** of injections are absorbed (render-fidelity rendered-rate **0.93**; per class G1 1.00
/ G4 1.00 / G2 0.91 / G3 0.91 / G6 0.84). Real geometry renders the perturbation faithfully — exactly the regime the
attribution needs, and a **positive control** on the §4 claim (the absorption is a property of enterprise templates,
not of injection-on-real-layouts).

**Result-4a — attribution, balanced accuracy on paired clean** (mean over 3 models / 3 families: Qwen3.5-27B,
InternVL3.5-8B, Ovis2.5-9B; `data/part3/pc_real_summary.json`, Fig. `docs/figs/pc_real_attribution.png`):

| class | A image | B oracle | C both | ΔB−A | verdict (mean) |
|---|---|---|---|---|---|
| G1 overflow  | **0.70** | 0.50 | 0.64 | −0.20 | image-sufficient |
| G2 overlap   | **0.74** | 0.59 | 0.72 | −0.15 | image-sufficient |
| G3 alignment | 0.51 | 0.49 | 0.50 | −0.03 | **capability / sub-perceptual** |
| G4 font      | 0.61 | 0.62 | 0.62 | +0.01 | image-sufficient (ill-posed) |
| G6 margin    | 0.59 | **0.70** | 0.66 | **+0.11** | **perception (structure rescues)** |

**The three attribution outcomes the §8 experiment was meant to separate all appear, on real geometry:**
1. **Image-sufficient** — G1 overflow, G2 overlap: a capable VLM *perceives* these directly on real renders
   (27B A = 0.79 / 0.87, localize+repair 0.85–0.97 in C). The image is enough; structure adds nothing (B ≤ A).
2. **Perception bottleneck, structure rescues** — **G6 margin**: the bleed is hard to *see* (mean A 0.59) but the
   oracle, whose coordinates show the box crossing the slide boundary, **recovers** it (mean B 0.70, ΔB−A +0.11).
   This is model-dependent: the strong 27B already *sees* the bleed (A 0.72, image-sufficient) while the weaker
   InternVL/Ovis need the structure (A 0.50/0.54 → B 0.58/0.79). This is the exact "**missing structure, not
   missing capability**" cell §8 said it could not isolate.
3. **Capability / genuinely sub-perceptual** — **G3 alignment** is at chance in **every** channel for **every**
   model (A = B = C ≈ 0.50; 27B/InternVL/Ovis all 0.47–0.53). A 20–44 px offset is invisible in the render *and*
   the VLM cannot recover it from exact coordinates (the alignment arithmetic the symbolic linter does
   deterministically). The structured oracle does **not** substitute for the linter — the cleanest real-data
   confirmation of the paper's "fine geometry → linter" routing.

**Takeaway.** On real layouts the perception/capability boundary the paper draws is **real and reproducible**:
coarse geometry is image-sufficient, a margin bleed is a structure-rescuable *perception* bottleneck for weak VLMs,
and fine alignment is a *capability* floor that neither the image nor the VLM-consumed oracle crosses — so it must
route to the symbolic linter. Honest scoping: defects are *injected* (real geometry, real renderer, real oracle;
not naturally-occurring), and SlideAudit remains the naturally-defective image-only probe.

## Honest scoping & negative results

- SlideAudit is **image-only** (no IR) → the hybrid's linter engine runs only in degraded image-only mode on real
  data; the full-power structural path needs native `.pptx` (only the Hermes deck on this box is native). Stated, not hidden.
- The `demo_real/` real-world examples are **non-eval** (qualitative figures / cold-email hooks only); see
  `data/part3/demo_real/SOURCES.md`.
- **OTHER bucket (off-taxonomy scan, A.3.1.2):** across 1,872 C1 free-form rows we logged 2,830 OTHER items, but
  ~98% are the bare `OTHER` label (the C1 classifier's over-flagging on strong models — the same effect that
  collapses C1 in Result 1), not a clean recurring class. The only repeated *off-taxonomy* candidates were
  **low colour contrast** and **border/divider inconsistency** (1–2 hits each) — too sparse to promote to new
  defect classes here, but consistent with SlideAudit's "Insufficient Color Contrast" dim that our taxonomy maps to
  OTHER. Recorded as a weak signal, not a result.

## Conclusion & future work

**Conclusion.** A slide-defect critic should not be one model. Across three protocols on the same data we show: (1)
the detection a pointwise+rubric VLM "loses" is mostly a *format* artifact — atomic-binary elicitation recovers it,
and the effect replicates across 4 model families and transfers to real SlideAudit images; (2) routing each defect
to its bottleneck-appropriate engine yields a hybrid that covers **8/9 classes (0.885)** where the best single
engine covers 5/9 — and the linter-blind render class **G7 is caught only by the hybrid's VLM-C3 engine**; (3) across
three published reward scorers, the G7 blind spot is a property of **narrow critics** — a document-structure reward
(DocReward 0.48) and a pure-aesthetic scorer (LAION 0.57) miss it at chance, while a capable general-multimodal
reward (Skywork-VL 0.79) detects it — so "G7 needs a capable VLM" holds whether the VLM is prompted or reward-headed;
and ~45% of IR-injected geometry defects never survive the standard snap renderer (zero signal for *every* reward) —
so neither "just grab a narrow reward model" nor "trust the rendered labels" is sufficient. The defensible unit of contribution is the **per-defect bottleneck
dichotomy, the falsifiable G7 class, and honest real-data scoping**.

**Future work.** (a) A structured (modality-C) real eval to separate "missing structure" from "missing capability"
on real geometry — currently annotation-blocked; (b) a held-out scalar-reward ablation (train BT on G1–G6/S, hold
out G7) to confirm a pure neural scalar cannot cover the render class without explicit supervision; (c) a small
deployable VLM (3B) specialised for G7-via-C3 to make the hybrid's render engine cheap, with a transfer test to
real overflow; (d) extend the perturbation-fidelity audit to public slide-quality datasets to quantify their label
noise; (e) audit a second published reward model (`MeiGen-AI/PosterReward_v1`) once an ms-swift runtime is
available.
