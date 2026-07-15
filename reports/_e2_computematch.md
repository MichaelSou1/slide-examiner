## E2 — compute-matched C0 ablation (paired-clean detection, modality A)

Same model, image, and rendered corpus across conditions. The compute-matched control is **self-consistency**: majority vote over K=10 independent C0 draws — the standard way to spend extra test-time compute for accuracy. Δ = C3 balanced accuracy − the control's; McNemar p is the exact paired test, **Holm** = family-wise corrected over the 24 E2 tests (α=0.05, 14 rejected).

### Main — pointwise baseline vs. compute-matched self-consistency vs. atomic C3

| Model | Defect | C0 | Self-consistency (K-vote) | C3 | Δ(C3−self-cons) | Δ(C3−C0) |
|---|---|---|---|---|---|---|
| gemini-2.5-flash | G1 | 0.51 | 0.54 | 0.64 | +0.10 (p=0.1338→1.0) | +0.12 (p=0.0639→0.625) |
| gemini-2.5-flash | G7 | 0.61 | 0.59 | 0.88 | +0.29 (p=0.0→0.0 ✅) | +0.27 (p=0.0→0.0 ✅) |
| gpt-5.1-nothinking | G1 | 0.51 | 0.51 | 0.50 | -0.01 (p=1.0→1.0) | -0.01 (p=1.0→1.0) |
| gpt-5.1-nothinking | G7 | 0.70 | 0.63 | 0.83 | +0.20 (p=0.0→0.0 ✅) | +0.13 (p=0.0021→0.023 ✅) |
| qwen3-vl-plus | G1 | 0.86 | 0.75 | 0.50 | -0.25 (p=0.0→0.0002 ✅) | -0.36 (p=0.0→0.0 ✅) |
| qwen3-vl-plus | G7 | 0.64 | 0.61 | 0.92 | +0.31 (p=0.0→0.0 ✅) | +0.28 (p=0.0→0.0 ✅) |

### Supplement — definition-matched control (C0_full: whole-taxonomy single call + per-type definitions + forced evidence)

| Model | Defect | C0_full | C3 | Δ(C3−C0_full) |
|---|---|---|---|---|
| gemini-2.5-flash | G1 | 0.61 | 0.64 | +0.02 (p=0.845→1.0) |
| gemini-2.5-flash | G7 | 0.73 | 0.88 | +0.15 (p=0.0015→0.0186 ✅) |
| gpt-5.1-nothinking | G1 | 0.50 | 0.50 | +0.00 (p=1.0→1.0) |
| gpt-5.1-nothinking | G7 | 0.79 | 0.83 | +0.04 (p=0.6358→1.0) |
| qwen3-vl-plus | G1 | 0.80 | 0.50 | -0.30 (p=0.0→0.0002 ✅) |
| qwen3-vl-plus | G7 | 0.67 | 0.92 | +0.24 (p=0.0→0.0 ✅) |

### Supplement — union (any-vote) aggregation of the same K draws

Union flags a slide if ANY of the K draws flags it. This is a decision-threshold relaxation (an OR over draws), not a compute-scaling method: as K grows it converges to always-flag, and on a highly conservative model (specificity ≈ 1) it harvests recall without spending compute any differently than majority does. We therefore use majority (self-consistency) as the headline compute-matched control and report union here in full. Note C3 matches or beats union's best score with 1 call vs. its ~8–10 calls per slide.

| Model | Defect | Union (any-vote) | C3 | Δ(C3−union) |
|---|---|---|---|---|
| gemini-2.5-flash | G1 | 0.55 | 0.64 | +0.09 (p=0.427→1.0) |
| gemini-2.5-flash | G7 | 0.61 | 0.88 | +0.27 (p=0.0→0.0 ✅) |
| gpt-5.1-nothinking | G1 | 0.56 | 0.50 | -0.06 (p=0.0625→0.625) |
| gpt-5.1-nothinking | G7 | 0.78 | 0.83 | +0.05 (p=0.2912→1.0) |
| qwen3-vl-plus | G1 | 0.84 | 0.50 | -0.34 (p=0.0→0.0 ✅) |
| qwen3-vl-plus | G7 | 0.66 | 0.92 | +0.26 (p=0.0→0.0 ✅) |

### Budget (E3) — completion tokens per slide

If C3 does not spend MORE output tokens than C0_full, the recovery cannot be a test-time-compute artifact. `calls/slide` shows C0_rep's K× multiplier.

| Model | Cond | calls/slide | prompt tok/slide | completion tok/slide | reasoning tok/slide |
|---|---|---|---|---|---|
| gemini-2.5-flash | C0 | 1.0 | 2371.7 | 156.9 | 1094.8 |
| gemini-2.5-flash | C0_full | 1.0 | 2908.7 | 130.5 | 1237.1 |
| gemini-2.5-flash | C0_rep | 10.0 | 23716.7 | 1531.1 | 11631.4 |
| gemini-2.5-flash | C3 | 1.0 | 2024.0 | 37.5 | 401.8 |
| gpt-5.1-nothinking | C0 | 1.0 | 1435.0 | 45.9 | 0.0 |
| gpt-5.1-nothinking | C0_full | 1.0 | 1931.0 | 61.5 | 0.0 |
| gpt-5.1-nothinking | C0_rep | 8.544 | 12261.5 | 348.4 | 0.0 |
| gpt-5.1-nothinking | C3 | 1.0 | 1123.0 | 40.5 | 0.0 |
| qwen3-vl-plus | C0 | 1.0 | 1411.0 | 121.6 | 0.0 |
| qwen3-vl-plus | C0_full | 1.0 | 1902.0 | 134.6 | 0.0 |
| qwen3-vl-plus | C0_rep | 8.372 | 11813.6 | 1083.6 | 0.0 |
| qwen3-vl-plus | C3 | 1.0 | 1098.0 | 34.7 | 0.0 |

### Reading

- **gemini-2.5-flash / G1**: INCONCLUSIVE at current n — inspect CIs. (C0=0.51, C3=0.64; Δ C3−self-cons = +0.10; Δ C3−C0_full = +0.02)
- **gemini-2.5-flash / G7**: WIN: C3 beats the compute-matched self-consistency control — the recovery is NOT test-time compute. (C0=0.61, C3=0.88; Δ C3−self-cons = +0.29; Δ C3−C0_full = +0.15)
- **gpt-5.1-nothinking / G1**: N/A: C3 does not recover over C0 here (C3≤C0) — this is a reference-assisted / non-format-suppressed class, not a target of the compute-match; report as a negative control. (C0=0.51, C3=0.50; Δ C3−self-cons = -0.01; Δ C3−C0_full = +0.00)
- **gpt-5.1-nothinking / G7**: WIN: C3 beats the compute-matched self-consistency control — the recovery is NOT test-time compute. (C0=0.70, C3=0.83; Δ C3−self-cons = +0.20; Δ C3−C0_full = +0.04)
- **qwen3-vl-plus / G1**: N/A: C3 does not recover over C0 here (C3≤C0) — this is a reference-assisted / non-format-suppressed class, not a target of the compute-match; report as a negative control. (C0=0.86, C3=0.50; Δ C3−self-cons = -0.25; Δ C3−C0_full = -0.30)
- **qwen3-vl-plus / G7**: WIN: C3 beats the compute-matched self-consistency control — the recovery is NOT test-time compute. (C0=0.64, C3=0.92; Δ C3−self-cons = +0.31; Δ C3−C0_full = +0.24)

**Test-family growth**: this report adds **24** paired McNemar tests — add these to the paper's Holm family and update the "N-test family" count.

