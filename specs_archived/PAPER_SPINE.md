# Paper Spine — slide-examiner (single integrated paper)

> **Purpose:** portfolio piece for cold-emailing VLM/multimodal PIs (套磁) + PhD apps — NOT a top venue.
> Optimize for *demonstrated research ability* (good question → clean experiment → diagnosis-drives-method
> → honest negatives), not SOTA. Form = arXiv technical report, ~8–12pp. Framing entry = **perception
> bottleneck / format suppression** (the VLM-PI-resonant door).
>
> This doc is the LOCKED main line. Rule for every fork: *if it doesn't serve "two failure types →
> hybrid architecture," demote or cut.* See memory `paper-mainline-and-goal`.

---

## 0. Elevator pitch (what a VLM PI should take away in 60s)

A VLM "fails to see" slide defects for two *different* reasons, and telling them apart changes the fix.
Some failures are a genuine **perception bottleneck** (fine geometry is sub-perceptual — scale, encoder
family, and resolution don't move it). But much of the apparent perception failure is **elicitation-format
suppression**: the capability is there, and a *changed elicitation* (atomic-binary / pairwise) recovers it
**without touching the model**, replicating across 6 VLMs / 4 families and transferring to real data. The
diagnosis dictates the architecture: a per-defect **routed symbolic–neural critic**, with a *falsifiable*
linter-blind render class (**G7**) that a symbolic linter and a published neural reward model **both** miss
— only the VLM-under-changed-elicitation catches it.

---

## 1. Title candidates (VLM口径)

1. **It's the Elicitation, Not the Eyes: Diagnosing the VLM Perception Bottleneck in Slide-Quality
   Inspection and Routing a Symbolic–Neural Critic** ← recommended  
   > Choose this one (#1)
2. Format Suppression, Not Capability: A Perception/Reasoning Diagnosis of Rendered-Document QC
3. Seeing but Not Saying: When VLM Slide Critics Fail at Elicitation, Not Perception

---

## 2. One-sentence thesis (spine)

> In rendered-document (slide) QC, VLM "blindness" splits via an attribution protocol into **(1) genuine
> sub-perceptual failure** (fine geometry; invariant to scale/encoder/resolution → symbolic linter) and
> **(2) elicitation-format suppression** (capability present, suppressed by pointwise+rubric → recovered by
> changed elicitation, no model change). This diagnosis earns a **per-defect bottleneck-routed symbolic–
> neural hybrid critic**, with a falsifiable **linter-blind render class G7** proving neither pure-symbolic
> nor pure-neural-reward suffices.
>
> Connective thread across all parts = **"relative >> absolute / format suppression, not capability"**
> (Part-1 forced-choice ↔ Part-3 C0–C3 — unify these, they are the same phenomenon).

---

## 3. Contributions (4 — goes in intro)

- **C1 — Attribution protocol for generation-QC with a lossless geometric oracle.** Modality A/B/B′/C ×
  T1/T2/T3 separates *perception* vs *reasoning* bottlenecks per defect × model; the oracle is structured
  geometry (bbox+text+style), not a lossy caption → cleaner attribution boundary. Splits failure into
  sub-perceptual vs format-suppressed.
- **C2 — "Format suppression, not capability."** Relative/atomic-binary elicitation recovers detection that
  pointwise+rubric suppresses; the **C3-vs-C0** contrast (same model/taxonomy/image) isolates format from
  capability. Replicates across **6 VLMs / 4 families / 3 scales** and **transfers to real SlideAudit data**;
  localization ≥98% rules out an "always-yes" bluff. Unifies Part-1 forced-choice with Part-3 C0–C3.
- **C3 — A routed symbolic–neural hybrid critic + the falsifiable G7 class.** Static defect→engine router
  covers **8/9** classes (bal-acc 0.885) vs linter-only 5/9 / single-VLM 2/9. **G7** (declared bbox legal,
  rendered content overflows) is *linter-blind by construction* and is missed by a published neural reward
  model (**DocReward pref 0.28**, CI below chance) — **two-sided blindness**; only VLM-under-C3 catches it.
- **C4 — Supporting: an injected-defect specialist examiner (semantic engine) + a perturbation-fidelity
  audit.** 8B examiner > zero-shot 30B on semantic pointwise; and **45% of injected geometry defects never
  render** under the standard snap renderer → a methodology prerequisite the field skips (IR labels ≠ pixel
  truth).

---

## 4. Section map (headline / supporting / demoted / cut)

| § | Section | Source | Role | Must show |
|---|---|---|---|---|
| 1 | Intro | — | — | perception-bottleneck framing; two-failure-type thesis; C1–C4 |
| 2 | Related work | NOVELTY doc | — | VLM perception bottleneck; LLM-as-judge/critic; slide gen+eval; injection-for-eval. Cut 2512.21329 (concurrent, domain+oracle差异化) / use 2604.25235 (ranking-scoring) as **support** / cite LED for injection |
| 3 | Setup | Part 1/2 | — | IR, taxonomy G1–G6/S1–S6, dual linter, modality A/B/B′/C, oracle de-leak |
| 4 | **Diagnosis** | Part 1 | spine | attribution → 2 failure types; geometry sub-perceptual (encoder×5 / res — **1 line each**); **relative>>absolute revives G1/S6**; template-collapse as framing + **45% snap datum**; S3→linter (1 line) |
| 5 | **Hybrid critic** | Part 3 hybrid | **HEADLINE** | elicitation C0–C3; **C3-vs-C0 format-suppression across families**; **G7 falsifiable class**; routing + coverage 8/9 vs 5/9/2/9; **DocReward audit**; perturbation-fidelity |
| 6 | Semantic engine | Part 2 | supporting | specialist 8B > zs-30B on semantic; routing; **honest negatives** (S2/S5 degenerate, sim2real gap) |
| 7 | External validity | Part 2/3 | short | SlideAudit transfer; Hermes real-agent case (**ft-weakest negative supports thesis**); **downstream utility = 1 honest paragraph** |
| 8 | Limitations & negatives | all | — | consolidated; annotation-blocked modality-C real eval; sim2real; downstream small |
| 9 | Conclusion | — | — | the unit of contribution = the diagnosis→routing + G7, not "beating DocReward" |

**Cut / appendix:** downstream utility (self-refine/GEPA) → 1 paragraph in §7 + appendix; **SkillOpt fully
cut**; GEPA detail → appendix; encoder×5 / resolution / S3 linter → 1 line each + appendix.

---

## 5. Claims ↔ evidence (each section's job)

| Claim | Evidence | Where |
|---|---|---|
| Fine geometry is sub-perceptual, not elicitation-fixable | G3–G6 floor across scale + 5 encoders + 2 resolutions + forced-choice | §4 |
| G1 overflow & S6 are *format-suppressed*, not sub-perceptual | pointwise 0.50 → forced-choice 1.0 (Part 1); C2/C3 recovery (Part 3) | §4, §5 |
| Format suppression is model-agnostic + transfers to real data | C3 rescues G7 across Qwen 9B/27B/3.6 + Gemma4 + InternVL/Ovis; C3>C0 on SlideAudit | §5 |
| G7 rescue is real perception, not a "yes" bluff | localization region/element correct ≥98% on 4 capable models | §5 |
| Hybrid strictly dominates single engines | 8/9 @0.885 vs linter 5/9 @0.70 / VLM 2/9 @0.57 | §5 |
| Neither symbolic nor neural-reward covers G7 | linter 0.00 + DocReward pref 0.28 (CI below chance) | §5 |
| IR labels ≠ pixel truth (methodology) | 45% of injected geometry snapped away; snap-absorbed → reward gap 0.000 | §5/§4 |
| Specialist examiner is a strong semantic engine | ft-8B S-group bal-acc ≈0.99–1.0 > zs-30B 0.785; S4 recall 0→0.97 (p=4.5e-7) | §6 |
| Examiner learned a *distribution*, not universal quality (honest) | Hermes OOD placeholder defect: ft-8B weakest, zs-30B best | §6/§7 |

---

## 6. Figures

- **Fig 1 (NEW, make):** conceptual — two failure types → defect→engine routing diagram. The paper's anchor.
- **Fig 2:** attribution / relative>>absolute (Part 1) — pointwise vs forced-choice for G1/S6 (+ G3 floor as contrast).
- **Fig 3 (exists):** `docs/figs/p3_coverage_heatmap.png` — per-defect bal-acc × linter/VLM/hybrid, G7 boxed.
- **Fig 4 (exists):** `docs/figs/p3_reward_blindspot.png` — DocReward pref-acc, G7 below chance.
- **Tables:** C3-vs-C0 across families; hybrid coverage 8/9; examiner S-group table (with Wilson CIs).

---

## 7. Tone & honesty rules (for套磁)

- Never inflate. Downstream +0.659 is "positive direction, tiny magnitude, floored by a strong generator" —
  NOT "feedback quality matters."
- Make the negatives load-bearing: localization anti-bluff check, DocReward audit, 45% snap-absorption,
  position-bias bug found+fixed, ft-weakest-on-Hermes — each followed by "which shows…". These signal rigor.
- One-page cold-email research-story summary to be produced separately (hook figs = Fig 3 + Fig 4).

## 8. Gaps to acknowledge (state, don't fix)

- No human-annotated modality-C real eval (annotation-blocked) → "missing structure, not missing method."
- N1 has a concurrent neighbor (2512.21329, ARC domain) → differentiate by domain + lossless geometric oracle
  + closing the loop to architecture.
- Single reward model audited (DocReward); PosterReward deferred (ms-swift runtime).
