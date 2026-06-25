# E8 corrected results (2026-06-25) — supersedes the buggy G3/G5 numbers

After the data audit (3 bugs: shared-clean diagnosis manifest; template-snap; freeform
filter keyed on path not `metadata.template_condition`) + adding G3 **48/64px saturation
strata**, all G3/G5 experiments were re-run on **coverage-freeform, matched-twin** data
(prefix `p1e8c`, tag `covint`, 6 VLMs). `offset_px` = rendered px in a 1920 frame
(32px = 1.67% of width; cross-correlation confirmed).

## Row 1 — diagnosis saturation curve (roster-mean, 6 VLMs, NAMED bal-acc)
| | C0 (open) | C3 (atomic) | 2-AFC |
|---|---|---|---|
| G3 2px (0.10%) | 0.49 | 0.50 | 0.00 |
| G3 4px (0.21%) | 0.52 | 0.49 | 0.00 |
| G3 8px (0.42%) | 0.51 | 0.52 | 0.00 |
| G3 16px (0.83%) | 0.54 | 0.63 | **1.00** |
| G3 32px (1.67%) | 0.64 | 0.83 | 1.00 |
| **G3 48px (2.50%)** | 0.73 | **0.90** | 1.00 |
| **G3 64px (3.33%)** | 0.73 | **0.90** | 1.00 |
| G5 6ΔE | 0.50 | 0.49 | — |
| G5 12ΔE | 0.50 | 0.53 | 1.00 |
| G5 24ΔE | 0.51 | 0.78 | 1.00 |
| G5 40ΔE | 0.54 | **0.99** | 1.00 |

**The corrected story (replaces "G3 genuinely sub-perceptual / capability floor"):**
- G3 is **format-suppressed-then-recoverable with a magnitude threshold**: 2-AFC saturates to
  **1.00 by 16px** (0.83% width); single-image atomic C3 climbs to a **~0.90 plateau by 48–64px**.
- The **genuinely sub-perceptual residue is only the sub-threshold tail** (G3 ≤8px / G5 ≤6ΔE),
  where 2-AFC itself stays at chance — well-posed but below acuity.
- Single-image C3 plateaus below 1.0 (~0.90): a real residual ceiling on *absolute* spatial
  judgement; paired/contrastive (2-AFC) has no such ceiling.
- Honest heterogeneity: internvl-8b under-asserts under C3 (recall≈0) and ties on 2-AFC; the Qwen
  family carries the recovery.
- Figure: `paper/figs/fig10_g3_saturation.png`.

## Row 3 — Table-2 cells (coverage-freeform, body model qwen35-27b)
| Class | linter (0 FP) | VLM-C0 | VLM-C3 |
|---|---|---|---|
| G3 | **0.929** (n=70+70) | 0.621 | 0.707 |
| G5 | **1.000** (n=40+40) | 0.500 | 0.675 |
Linter per-stratum: 2px abstain (0.00), 4–64px all 1.00, 0 false-fire. Routing reframe: G3/G5 →
linter because it is **cheaper + exact on declared geometry, near-0 FP** — NOT because the VLM is
blind (the VLM recovers supra-threshold under C3/2-AFC, just lower and needing the magnitude floor).

## Row 2 — modality A/B/C on internal-G3 (geometry-freeform, 3 VLMs)
G3 named bal-acc, C0: **mod-A (image) 0.62 > mod-C (hybrid) 0.59 > mod-B (IR-text) 0.49**.
So G3 is **NOT a floor in every channel** — it is above chance in the image/hybrid channels;
IR-text *alone* does not help (the model cannot judge alignment from coordinates-as-text better
than the linter does). (qwen35-9b C3 cell lost to a mid-run server kill; C3 cells from internvl
+ qwen36 ≈ 0.63 across modalities.)

## Row 4 — reward audit on internal-chromatic G5 (freeform, n=40, 5 scorers)
G5 pref-acc 0.575–0.775 (mean 0.685), all weakly > chance — chromatic inconsistency is a low-level
signal every CLIP-based reward partly sees; **no clean narrow-vs-general split**. G3-offset column
< 0.5 (rewards mildly *prefer* the offset) → blind to fine alignment, supporting linter-routes-G3.

## Row 5 — real-CC reproduction (41 real Zenodo decks, internal-G3 @44px, qwen35-27b)
A 0.537 / B 0.512 / C 0.524 (all near chance, high FPR; McNemar n.s.). **The synthetic saturation
does NOT fully transfer to real cluttered decks** — on real layouts the misaligned element is hard
to isolate among many real elements, and specificity collapses (apparent misalignments everywhere).
Honest external-validity bound: the clean-slide saturation is an upper bound; real-deck G3 is harder.
