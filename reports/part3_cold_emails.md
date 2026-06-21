# Part 3 — cold-email templates (PhD / RA outreach)

Four templates, one per target group. Each leads with **one concrete, falsifiable finding** from this project
(not a generic compliment), states what was built, and makes a specific ask. Replace `[...]` placeholders; attach or
link `reports/part3_hybrid.md`. Keep to ~150 words when sending.

> Personalise the first sentence with a specific result/figure from their paper so it does not read as a blast.

---

## 1 — MSR (DocReward / document & slide reward modeling)

**Subject:** DocReward-3B is blind to render-containment overflow — a small audit + a hybrid fix

Dear Dr. [Name],

I read DocReward closely and ran a small audit of the released `jeepliu/DocReward-3B` weights. On 40 paired
clean/defective slides where text **visibly overflows its container** (a class I call G7: declared bbox legal, but
the rendered content spills out), DocReward's preference accuracy is **0.28 — its 95% CI sits entirely below
chance**; it slightly *prefers* the overflowing slide, while scoring 0.95–1.00 on overlap/overflow/density it can
see. I also found that ~45% of IR-injected geometry defects never survive a standard snap-to-master renderer, so
reward pairs built that way carry silent label noise (identical pixels → zero reward signal).

I built a symbolic–neural **hybrid critic** that routes this render class to a VLM under atomic-binary elicitation
(0.50→1.00) while a linter handles declared geometry. Full write-up + code: [link]. I'm applying for
[PhD/RA] positions and would value 15 minutes of your time — would you be open to a short call?

Best, [Name] · [affiliation] · [github/site]

---

## 2 — KAIST (Choo group / DesignLab, layout & design critique)

**Subject:** A falsifiable "linter-blind" layout-defect class + where the symbolic/neural split should fall

Dear Prof. Choo,

DesignLab's finding that even a coordinate-fed neural model reaches only ~0.149 placement recall motivated a
question I chased: *which* defects belong to a symbolic linter and which to a VLM. I get a clean dichotomy — a
declared-bbox linter hits 0.8–1.0 at ~0 FP on alignment/overlap/margin/colour where a VLM is at floor, but it is
**blind by construction** to a render-containment class (G7: legal bbox, content overflows after rendering). A
routed **hybrid** covers 8/9 defect classes (0.885) vs 5/9 for the linter alone, and **G7 is caught only by the
hybrid's VLM engine** (linter 0.00 → 1.00).

Code + 6-model evidence: [link]. I'm seeking a [PhD/RA] position in design-quality modeling and would love to
discuss whether this routing view is useful for DesignLab. Could we talk briefly?

Best, [Name] · [affiliation]

---

## 3 — Tsinghua (PresentBench / presentation evaluation)

**Subject:** Your atomic-checklist insight, quantified as a "format suppression" effect (and where it transfers)

Dear [Name],

PresentBench's move from holistic judging to **atomic binary checklist items with forced localization** matches
what I see mechanistically: putting a whole defect taxonomy in one pointwise+rubric call makes VLMs abstain, but the
*same model* recovers detection under atomic-binary elicitation — e.g. a render-overflow class goes 0.50→1.00, and
the effect **replicates across 4 model families** and **transfers to real SlideAudit images** (C3>C0 on every
class, G5 0.52→0.81). I read this as format suppression, not a capability gap — direct support for your checklist
design. I also keep an OTHER bucket for off-taxonomy items as a complement to a fixed checklist.

Write-up + code: [link]. I'm applying for [PhD/RA] roles in presentation/document evaluation and would value your
perspective on combining fixed checklists with open scans. Open to a short call?

Best, [Name] · [affiliation]

---

## 4 — VLM spatial-reasoning / perception group

**Subject:** Fine slide geometry is sub-perceptual for VLMs — but the failure is partly elicitation, not perception

Dear Prof. [Name],

A clean case study for VLM spatial limits: on synthetic slides, fine geometry (2–32 px alignment offsets, small
overlaps) stays at chance for VLMs across resolution/encoder/scale — genuinely sub-perceptual, best left to a
symbolic checker. **But** a render-level containment overflow that *is* perceivable is suppressed by pointwise+rubric
formatting and recovers fully (0.50→1.00) under atomic-binary elicitation with forced localization; I verify the
models name the *specific* overflowing element (≥98% region+element correct), ruling out a yes-bias. So part of the
apparent "blindness" is an elicitation/calibration artifact, separable from true perceptual limits.

6-model, 4-family evidence + code: [link]. I'm looking for a [PhD/RA] position on VLM perception/spatial reasoning
and would welcome 15 minutes to discuss the perception-vs-calibration split. Would that be possible?

Best, [Name] · [affiliation]
