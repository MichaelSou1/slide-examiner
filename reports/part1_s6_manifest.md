# Part 1 — S6 image-text contradiction, now manifest

Image-bearing decks (`scripts/part1_image_corpus.py`): each figure element draws an up/down trend glyph + a caption of what it depicts; that depicted claim is **stripped from the structure oracle** (`diagram_claim`/`diagram_false_claim`/`diagram_trend` are hidden), so a contradiction is perceivable only from the image. The body agrees with the figure in the clean control and is flipped to the authored contradiction for S6. 30B-A3B, A/B/B'/C, T1, 24 S6 + 24 agreeing-clean, 0% parse failure.

## Discrimination (contradiction vs agreement) — paired controls

| Modality | recall (TP/P) | false-pos (FP/N) | precision | balanced accuracy |
|---|---|---|---|---|
| A | 24/24 | 24/24 | 0.5 | 0.5 |
| B | 3/24 | 0/24 | 1.0 | 0.562 |
| B_prime | 19/24 | 15/24 | 0.559 | 0.583 |
| C | 24/24 | 24/24 | 0.5 | 0.5 |

## Finding — a negative result, and a methodology warning

- **The defect is now genuinely manifest** (verified by eye and in the VLM caption: "a green upward-pointing triangle ... 'revenue rose' ... text reads 'revenue fell'"). So S6's earlier 0/8 was a non-manifest-data artifact — that part is fixed.
- **But the 30B model cannot actually do S6**: on the image channels (A and C) it asserts a contradiction on essentially *every* figure slide — 24/24 on true S6 **and** 24/24 on the agreeing-clean controls — i.e. precision 0.50 and **balanced accuracy 0.50, exactly chance**. The 100% 'recall' is blanket over-firing, not detection.
- **Structure-only B is precise but blind**: 0 false positives, but only 3/24 recall, because the figure's depicted claim is intentionally absent from the oracle. B cannot be the S6 detector.
- **The caption channel B' is only just above chance** (balanced accuracy 0.58): even though the caption transcribes both the figure trend and the contradicting text, the model still over-asserts (15/24 false positives).
- **Methodology warning for the matrix**: S6 (and any agreement-checking defect) MUST be scored with paired clean controls and balanced accuracy / precision, never recall alone — a recall-only view here would have reported '100% S6 detection' when the true discrimination is chance.

## Forced-choice (2-AFC) re-eval — VLMs compare better than they judge

Same images, different question: show the contradiction slide **and** its matching agreeing-clean slide (same figure, only the body differs) side by side, and ask *which* slide has the image-text contradiction. Each of the 12 figure pairs runs in both orderings to cancel position bias.

- **2-AFC accuracy: 100% (24/24)**, robust across both orderings **100% (12/12)**, pick distribution {'A': 12, 'B': 12} (perfectly balanced → no position bias).
- **So the model HAS the capability**: at chance (0.50) pointwise, perfect (1.00) in forced choice. The failure was calibrating an absolute yes/no judgement in isolation — not perception. Given the contrast it discriminates flawlessly.
- **Protocol recommendation**: evaluate agreement-checking defects (S6, likely S3) with the pairwise / forced-choice arm the contract already defines (`PairwiseResult`), not pointwise detection — the strongest evidence so far that relative judgement is the right framing for the hard semantic checks.

