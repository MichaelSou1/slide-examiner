## E2 — compute-matched C0 ablation (paired-clean detection, modality A)

Same model, image, and rendered corpus across conditions. **C0_rep** gives C0 the SAME K-call budget C3 spends in deployment (K=10), aggregated as **union** (any draw) and **maj** (majority of draws); **C0_full** matches C3's definitions + forced evidence in a single call. Δ = C3 balanced accuracy − the control's; McNemar p is the exact paired test, **Holm** = family-wise corrected over the 24 E2 tests (α=0.05, 14 rejected).

| Model | Defect | C0 | C0_full | C0_rep union | C0_rep maj | C3 | Δ(C3−C0_rep·un) | Δ(C3−C0_full) |
|---|---|---|---|---|---|---|---|---|
| gemini-2.5-flash | G1 | 0.51 | 0.61 | 0.55 | 0.54 | 0.64 | +0.09 (p=0.427→1.0) | +0.02 (p=0.845→1.0) |
| gemini-2.5-flash | G7 | 0.61 | 0.73 | 0.61 | 0.59 | 0.88 | +0.27 (p=0.0→0.0 ✅) | +0.15 (p=0.0015→0.0186 ✅) |
| gpt-5.1-nothinking | G1 | 0.51 | 0.50 | 0.56 | 0.51 | 0.50 | -0.06 (p=0.0625→0.625) | +0.00 (p=1.0→1.0) |
| gpt-5.1-nothinking | G7 | 0.70 | 0.79 | 0.78 | 0.63 | 0.83 | +0.05 (p=0.2912→1.0) | +0.04 (p=0.6358→1.0) |
| qwen3-vl-plus | G1 | 0.86 | 0.80 | 0.84 | 0.75 | 0.50 | -0.34 (p=0.0→0.0 ✅) | -0.30 (p=0.0→0.0002 ✅) |
| qwen3-vl-plus | G7 | 0.64 | 0.67 | 0.66 | 0.61 | 0.92 | +0.26 (p=0.0→0.0 ✅) | +0.24 (p=0.0→0.0 ✅) |

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

- **gemini-2.5-flash / G1**: MIXED: C0_full ≈ C3 — definitions+evidence in one call suffice; decomposition is not the key ingredient. (C0=0.51, C3=0.64; Δ C3−C0_rep,union = +0.09; Δ C3−C0_full = +0.02)
- **gemini-2.5-flash / G7**: WIN: C3 still beats the compute-matched C0_rep — recovery is NOT test-time compute. (C0=0.61, C3=0.88; Δ C3−C0_rep,union = +0.27; Δ C3−C0_full = +0.15)
- **gpt-5.1-nothinking / G1**: N/A: C3 does not recover over C0 here (C3≤C0) — this is a reference-assisted / non-format-suppressed class, not a target of the compute-match; report as a negative control. (C0=0.51, C3=0.50; Δ C3−C0_rep,union = -0.06; Δ C3−C0_full = +0.00)
- **gpt-5.1-nothinking / G7**: MIXED: C0_full ≈ C3 — definitions+evidence in one call suffice; decomposition is not the key ingredient. (C0=0.70, C3=0.83; Δ C3−C0_rep,union = +0.05; Δ C3−C0_full = +0.04)
- **qwen3-vl-plus / G1**: N/A: C3 does not recover over C0 here (C3≤C0) — this is a reference-assisted / non-format-suppressed class, not a target of the compute-match; report as a negative control. (C0=0.86, C3=0.50; Δ C3−C0_rep,union = -0.34; Δ C3−C0_full = -0.30)
- **qwen3-vl-plus / G7**: WIN: C3 still beats the compute-matched C0_rep — recovery is NOT test-time compute. (C0=0.64, C3=0.92; Δ C3−C0_rep,union = +0.26; Δ C3−C0_full = +0.24)

**Test-family growth**: this report adds **24** paired McNemar tests — add these to the paper's Holm family and update the "N-test family" count.

