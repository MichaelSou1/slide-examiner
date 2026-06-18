# Part 1 — does resolution or forced-choice rescue geometry?

Pointwise detection puts every ≤30B VLM at chance on geometry. Two remaining levers, tested on the two highest-signal defects: **higher render resolution (1536 / 2048)** and a **2-AFC forced-choice** framing (show the defective slide and its matching clean slide — same base, only the defect differs — and ask *which* one has the defect; both orderings to cancel position bias). 24 pairs/defect, image-only.

## Forced-choice accuracy (chance = 50%)

| Model | Defect | pointwise bal-acc | 2-AFC @1536 | 2-AFC @2048 |
|---|---|---|---|---|
| Qwen3-VL-8B | G1 text overflow | 0.50 | 100% | 100% |
| Qwen3-VL-8B | G3 alignment offset | 0.50 | 50% (all-one-side) | 50% (all-one-side) |
| Qwen3-VL-30B-A3B | G1 text overflow | 0.65 | 100% | 100% |
| Qwen3-VL-30B-A3B | G3 alignment offset | 0.50 | 50% (all-one-side) | 50% (all-one-side) |

## Findings — two different failure modes

- **G1 text overflow was a *calibration* failure, fully rescued by forced choice.** Qwen3-VL-8B is at chance pointwise (0.50) but scores **100%** in 2-AFC (48/48, balanced picks, robust across both orderings); the 30B is also 100%. The overflow was always perceivable — the model just couldn't set an absolute "is this overflow?" threshold in isolation. Given the contrast it is perfect, even at 8B.
- **G3 alignment offset is a genuine *perception* threshold, rescued by nothing.** Forced choice leaves it at **50% with an all-one-side bias** (the model cannot tell the slides apart, so it always answers A). This holds at both 1536 and 2048 and at both 8B and 30B. A 2–32px element shift is simply below the VLM's perceptual resolution for this task.
- **Render resolution made no difference** (1536 ≡ 2048 everywhere). The geometry gap is not a pixel-budget problem.

## Implication

The geometry "blindness" is two distinct things, and they imply different tools:

1. **Gross-but-miscalibrated defects (text overflow):** a VLM *can* do them — but only relatively. A **pairwise / forced-choice examiner** is the right framing (overflow 8B: chance → 100%). This matches the S6 result: relative judgement beats absolute scoring for the checks the model perceives but can't calibrate.
2. **Sub-threshold fine defects (alignment, and by extension font-size/colour/small-margin):** genuinely below VLM perception up to 30B, unrescued by framing, resolution, or scale → the **symbolic linter is irreplaceable** here.

So the refined Part 1 division of labour: linter owns the fine geometry (G2–G6 fine end); the VLM, used *pairwise*, can contribute on text overflow; pointwise VLM geometry detection should not be scored at all. Caveat: synthetic slides, one defect family each for the two mechanisms, 24 pairs — the overflow rescue is striking and clean, but the fine-geometry floor should be confirmed on real decks.

