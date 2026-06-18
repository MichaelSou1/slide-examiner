# Part 1 — is the geometry blindness a vision-encoder artifact?

**Hypothesis.** VLMs are blind to slide geometry (G1–G6) because of their contrastive (CLIP/SigLIP) vision encoder, which suppresses fine-grained cues. If so, a non-SigLIP or native-resolution encoder should break the blindness. **Test:** five ~8–9B models with different encoders on the same 288 geometry samples (G1–G6 + 80 clean negatives), A/B/C, T1, plus the 30B-A3B for the size axis.

**Metric: balanced accuracy** on paired clean controls (recall alone is misleading — some models over-fire). 0.50 = chance / no real discrimination.

## Geometry discrimination by encoder

| Model | encoder | bias (FP/neg) | G1 overflow bal-acc | mean G1–G6 bal-acc | parse-fail |
|---|---|---|---|---|---|
| Qwen3-VL-8B | SigLIP2 | abstains (0/160) | 0.50 | 0.50 | 0% |
| Penguin-VL-8B | LLM-based (anti-contrastive) | abstains (0/160) | 0.50 | 0.50 | 0% |
| InternVL3.5-8B | InternViT | over-fires (86/160) | 0.49 | 0.50 | 0% |
| Ovis2.5-9B | NaViT (native-res) | mild over-call (27/160) | 0.50 | 0.49 | 12% |
| Kimi-VL-A3B | MoonViT (native-res) | abstains (0/160) | 0.50 | 0.50 | 0% |
| Qwen3-VL-30B-A3B | SigLIP2 (size ref) | abstains (3/160) | 0.65 | 0.53 | 0% |

## Result — the encoder hypothesis is NOT supported

- **Every 8–9B model is at chance-level geometry discrimination** (mean balanced accuracy ≈ 0.50), regardless of encoder family: SigLIP2 (Qwen3-VL), LLM-based/anti-contrastive (Penguin-VL), InternViT (InternVL3.5), and two native-resolution encoders — NaViT (Ovis2.5) and MoonViT (Kimi-VL). Native resolution does not help either.
- **They differ only in BIAS, not perception.** Qwen3-VL, Penguin-VL and Kimi-VL *abstain* (0 false positives, ~0 recall); InternVL3.5 *over-fires* (53% G1 recall but 54% false-positive rate → balanced accuracy 0.49, still chance); Ovis2.5 mildly over-calls. Recall-only would have ranked InternVL 'best', but with paired controls its 'detection' is just trigger-happiness.
- **The only model that genuinely breaks G1 is the 30B-A3B** (G1 balanced accuracy ~0.75: 50% recall with 0 false positives). So the lever is *scale / LLM reasoning*, not the vision encoder — even native-res encoders at 8–9B don't move it.
- **Perception is not the bottleneck; geometric reasoning is.** The document specialist dots.ocr reads the overflowing title verbatim ("…real XXXXX") and lays out every box with coordinates — i.e. the pixels and text are perfectly legible — yet it (and every chat VLM here) cannot turn that into "this text overflows its box / these boxes overlap." The gap is reasoning over geometry, which is exactly what the symbolic linter does deterministically.

## Net

`G1–G6 → symbolic linter` is now the most stress-tested conclusion in Part 1: it survives a model-size sweep (4B/8B/30B) AND a vision-encoder sweep across five families (SigLIP2 / LLM-based / InternViT / NaViT / MoonViT). Swapping the encoder — even to native resolution or an anti-contrastive design — does not give a VLM slide-geometry detection at 8–9B. Document/OCR specialists (dots.ocr, PaddleOCR-VL) are perception front-ends, not examiners (they parse layout, they do not judge defects), and are best used to *feed* the linter/reasoner, not replace it.

## Caveats

- 1024px render, pointwise, single instances per family (e.g. Penguin via SDPA ViT; Ovis had 12% parse failures from less JSON-compliant output). Higher render resolution and a forced-choice (2-AFC) framing remain untested and could still help — but the simple "swap the encoder" intervention clearly does not.

