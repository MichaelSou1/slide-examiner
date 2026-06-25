# E8 G6 (page-offset) + S6 (valid-figure) re-run — verdicts

## 6-MODEL ROSTER (2026-06-25, the апples-to-apples confirmation, like G3/G5)
Re-ran on the full roster after the口径/data fix (not just the body model). Numbers
`data/part3/p1e8g6s6_<model>_{g6,s6}_{C0,C3,AFC}.json`.

**G6 page-offset — UNIVERSAL blind spot (6/6):** roster-mean C3 bal-acc **0.504** (every model
0.47–0.53 = chance), mean AFC **tie 0.70**. Two failure modes — never-assert (internvl/ovis/qwen36:
recall~0, spec~1) vs leading-Q over-assert (qwen35-27b/gemma: recall~1, spec~0) — both = 0.50.
AFC ties 0.58–1.00; the few non-tie cases are position-random (qwen35-9b strict 0.01). **No model
discriminates a page-offset slide from a balanced one.**

**S6 valid figures — PERCEIVABLE (6/6):** roster-mean AFC **tie 0.07**, strict 0.75–1.00 every model
(internvl even C3 bal 1.00). Data-bug confirmed: on valid figures all models see the contradiction;
single-image C3 over-asserts (needs reference), AFC nails it.

**The split (both were "0.50" in Table 2):** S6 AFC tie **0.07** (sees it → was a data bug) vs G6
AFC tie **0.70** (can't see it → genuine). The re-op is falsifiable and earns its credibility here.

---

## Single-model first look (qwen35-27b body model) — superseded by the roster above

The E8 re-op is a **falsifiable test**: it tells genuine VLM blind spots from prompt/data
artifacts. The three classes split cleanly.

## S6 image/text — was a DATA artifact, now confirmed PERCEIVABLE
On the fixed valid-figure corpus (`manifest_s6_rendered.jsonl`, slides actually contain the
contradicting image; old Table-2 used no-image slides → recall 0/18):
- **2-AFC = 1.00, 0 ties** (n=12 pairs) → the model clearly *perceives* the image/text contradiction.
- C0/C3 single-image: recall 1.0 but **specificity 0.0** (says "contradiction" on the clean too)
  → over-asserts, can't calibrate pointwise.
- Verdict: the old **S6=0.0 was a data bug**, not blindness. S6 is *perceivable* (AFC 1.0) but the
  deployable single-image elicitation doesn't recover it (like G1). Table-2 deployable cell ≈ 0.50,
  but reframe from "blind to image/text contradiction" to "needs a reference / over-asserts pointwise".

## G6 margin (page-offset口径) — GENUINE VLM BLIND SPOT (not an artifact)
Whole content block shifted toward one edge (internal alignment preserved; asymmetric margins),
8 strata from margin 80px (2.5%) to −16px (clipped off the edge). Tested BOTH question framings:
| elicitation | recall | spec | bal-acc | note |
|---|---|---|---|---|
| C3 absolute "safe margin" Q | 0.00 | 1.00 | 0.50 | never flags (reads edge-content as left-alignment) |
| C3 asymmetry "shifted to one side" Q | 0.99 | 0.00 | 0.49 | leading-Q yes-bias: says "yes" on clean too — can't discriminate |
| 2-AFC (either phrase) | — | — | — | **100% ties at margin 80→16; only at −16 (clipped) does it stop tying, then a=10/b=9 (position-random)** |

- It is **not a prompt artifact** (both absolute and asymmetry framings fail; one floors recall, the
  other floors specificity) and **not a data artifact** (corpus fully audited: matched twins,
  magnitude-faithful, 0-FP linter, visually dramatic shift). Even side-by-side the model cannot tell
  a left-shoved slide from a balanced one until the content is **clipped by the page boundary**.
- **Verdict: VLMs are genuinely blind to page-offset / global content positioning.** Distinct from
  G3 (口径 artifact → recovers, magnitude-gated) and S6 (data artifact → AFC 1.0). G6 stays floored
  even after a clean, decidable, well-posed re-op.
- Linter owns it exactly: `detect_margin_violations` 0.75 overall (1.00 once content is <32px from
  the edge), **0 FP**. So G6 → linter because the **VLM genuinely cannot**, not because the linter is
  merely cheaper.

## Why this matters (paper)
The re-op методology earns credibility precisely because it does NOT rescue everything:
- **Artifact, recovers:** G3 (ill-posed external ref), G5 (ditto), S6 (no image rendered).
- **Genuine blind spot, stays floored:** **G6 page-offset** — the clean, falsified-then-confirmed
  case of "the VLM really can't see it."
This replaces the OLD (wrong) "G3 genuinely sub-perceptual" flagship with a CORRECT one: G6 is the
honest "genuinely the eyes can't" class; G3 was format-suppression. Table-2 G6 VLM stays ~0.50
(now *justified* as a real blind spot), linter 1.00 owns it.
