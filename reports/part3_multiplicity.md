# Multiplicity correction (E2)

## Primary cross-model tests (pooled / stratified McNemar)

The "recovers across models" claims are tested as ONE stratified McNemar over the per-model matched pairs — the analysis that matches the claim and is immune to the per-cell multiplicity penalty. `c=0` means not a single reversal in any model.

| Claim | b (gain) | c (loss) | χ² | p | strata | fully consistent |
|---|---|---|---|---|---|---|
| G7 C3-vs-C0 (capable models) | 233 | 2 | 227.1 | 0.0000 | 4 | no (max c=2) |
| G1 C2-vs-C0 (strong Qwens) | 93 | 36 | 25.2 | 5.21e-07 | 2 | no (max c=27) |

Family of **85** reported significance tests across elicitation (paired McNemar), compute-matched ablations (paired McNemar), examiner (two-proportion z), and reward (G7 preference vs chance). Holm (FWER) survivors: **35**; Benjamini-Hochberg (FDR) survivors: **47** at α=0.05.

| Source | Contrast | raw p | Holm p | Holm✓ | BH p | BH✓ | headline |
|---|---|---|---|---|---|---|---|
| compute_match | gemini-2.5-flash/G7/C3_vs_C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | gemini-2.5-flash/G7/C3_vs_C0_rep McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | gemini-2.5-flash/G7/C3_vs_C0_rep_maj McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| compute_match | gpt-5.1-nothinking/G7/C3_vs_C0_rep_maj McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| compute_match | qwen3-vl-plus/G1/C3_vs_C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G1/C3_vs_C0_full McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G1/C3_vs_C0_rep McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G1/C3_vs_C0_rep_maj McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G7/C3_vs_C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G7/C3_vs_C0_full McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G7/C3_vs_C0_rep McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| compute_match | qwen3-vl-plus/G7/C3_vs_C0_rep_maj McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| compute_match | gemini-2.5-flash/G7/C3_vs_C0_full McNemar | 0.0015 | 0.0750 | · | 0.0035 | ✓ |  |
| compute_match | gpt-5.1-nothinking/G7/C3_vs_C0 McNemar | 0.0021 | 0.1008 | · | 0.0047 | ✓ |  |
| compute_match | gpt-5.1-nothinking/G1/C3_vs_C0_rep McNemar | 0.0625 | 1.0000 | · | 0.1084 | · |  |
| compute_match | gemini-2.5-flash/G1/C3_vs_C0 McNemar | 0.0639 | 1.0000 | · | 0.1086 | · |  |
| compute_match | gemini-2.5-flash/G1/C3_vs_C0_rep_maj McNemar | 0.1338 | 1.0000 | · | 0.2068 | · |  |
| compute_match | gpt-5.1-nothinking/G7/C3_vs_C0_rep McNemar | 0.2912 | 1.0000 | · | 0.4268 | · |  |
| compute_match | gemini-2.5-flash/G1/C3_vs_C0_rep McNemar | 0.4270 | 1.0000 | · | 0.5950 | · |  |
| compute_match | gpt-5.1-nothinking/G7/C3_vs_C0_full McNemar | 0.6358 | 1.0000 | · | 0.7720 | · |  |
| compute_match | gemini-2.5-flash/G1/C3_vs_C0_full McNemar | 0.8450 | 1.0000 | · | 0.9451 | · |  |
| compute_match | gpt-5.1-nothinking/G1/C3_vs_C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| compute_match | gpt-5.1-nothinking/G1/C3_vs_C0_full McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| compute_match | gpt-5.1-nothinking/G1/C3_vs_C0_rep_maj McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| examiner | examiner:S4-density-synth(ft8b>zs30b) | 4.53e-07 | 2.50e-05 | ✓ | 1.00e-06 | ✓ | ★ |
| examiner | examiner:S4-density-real(zs30b>ft8b) | 1.13e-05 | 6.08e-04 | ✓ | 3.00e-05 | ✓ | ★ |
| elicitation | gemma4-31b/G7/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | gemma4-31b/S6/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | ovis-9b/S6/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | ovis-9b/S6/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/G7/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/G1/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/G1/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | qwen35-27b/S6/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/S6/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-9b/S6/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-9b/S6/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen36-27b/G7/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen36-27b/G7/C3-vs-C0 McNemar | 6.46e-27 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | qwen35-9b/G7/C3-vs-C0 McNemar | 4.44e-16 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | gemma4-31b/G7/C3-vs-C0 McNemar | 1.19e-14 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | qwen35-27b/G7/C3-vs-C0 McNemar | 1.46e-11 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | internvl-8b/G1/C3-vs-C0 McNemar | 1.00e-04 | 0.0052 | ✓ | 2.43e-04 | ✓ |  |
| elicitation | ovis-9b/S6/C1-vs-C0 McNemar | 1.00e-04 | 0.0052 | ✓ | 2.43e-04 | ✓ |  |
| elicitation | qwen36-27b/G1/C2-vs-C0 McNemar | 0.0019 | 0.0931 | · | 0.0044 | ✓ | ★ |
| elicitation | gemma4-31b/S6/C2-vs-C0 McNemar | 0.0026 | 0.1222 | · | 0.0055 | ✓ |  |
| elicitation | gemma4-31b/S6/C3-vs-C0 McNemar | 0.0026 | 0.1222 | · | 0.0055 | ✓ |  |
| elicitation | gemma4-31b/G1/C1-vs-C0 McNemar | 0.0033 | 0.1485 | · | 0.0068 | ✓ |  |
| elicitation | qwen35-9b/S6/C3-vs-C0 McNemar | 0.0118 | 0.5192 | · | 0.0239 | ✓ |  |
| elicitation | gemma4-31b/G7/C2-vs-C0 McNemar | 0.0152 | 0.6536 | · | 0.0300 | ✓ |  |
| elicitation | internvl-8b/G7/C2-vs-C0 McNemar | 0.0192 | 0.8064 | · | 0.0363 | ✓ |  |
| elicitation | qwen35-27b/G1/C3-vs-C0 McNemar | 0.0192 | 0.8064 | · | 0.0363 | ✓ |  |
| elicitation | internvl-8b/G1/C1-vs-C0 McNemar | 0.0230 | 0.9200 | · | 0.0416 | ✓ |  |
| elicitation | internvl-8b/G1/C2-vs-C0 McNemar | 0.0230 | 0.9200 | · | 0.0416 | ✓ |  |
| elicitation | qwen35-9b/G1/C1-vs-C0 McNemar | 0.0400 | 1.0000 | · | 0.0708 | · |  |
| elicitation | qwen35-9b/G1/C3-vs-C0 McNemar | 0.0681 | 1.0000 | · | 0.1135 | · |  |
| elicitation | gemma4-31b/G1/C3-vs-C0 McNemar | 0.0893 | 1.0000 | · | 0.1460 | · |  |
| elicitation | gemma4-31b/G1/C2-vs-C0 McNemar | 0.1175 | 1.0000 | · | 0.1884 | · |  |
| elicitation | qwen36-27b/G1/C1-vs-C0 McNemar | 0.1250 | 1.0000 | · | 0.1968 | · |  |
| elicitation | ovis-9b/G7/C2-vs-C0 McNemar | 0.1496 | 1.0000 | · | 0.2271 | · |  |
| elicitation | qwen35-27b/S6/C2-vs-C0 McNemar | 0.3877 | 1.0000 | · | 0.5586 | · |  |
| elicitation | ovis-9b/G1/C2-vs-C0 McNemar | 0.4244 | 1.0000 | · | 0.5950 | · |  |
| elicitation | ovis-9b/G1/C1-vs-C0 McNemar | 0.4614 | 1.0000 | · | 0.6326 | · |  |
| elicitation | qwen36-27b/G7/C1-vs-C0 McNemar | 0.5000 | 1.0000 | · | 0.6746 | · |  |
| elicitation | qwen36-27b/S6/C2-vs-C0 McNemar | 0.5386 | 1.0000 | · | 0.7079 | · |  |
| elicitation | ovis-9b/G1/C3-vs-C0 McNemar | 0.5413 | 1.0000 | · | 0.7079 | · |  |
| elicitation | ovis-9b/G7/C1-vs-C0 McNemar | 0.5515 | 1.0000 | · | 0.7103 | · |  |
| elicitation | internvl-8b/S6/C1-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7639 | · |  |
| elicitation | internvl-8b/S6/C2-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7639 | · |  |
| elicitation | internvl-8b/S6/C3-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7639 | · |  |
| elicitation | internvl-8b/G7/C1-vs-C0 McNemar | 0.6655 | 1.0000 | · | 0.7840 | · |  |
| elicitation | internvl-8b/G7/C3-vs-C0 McNemar | 0.6655 | 1.0000 | · | 0.7840 | · |  |
| elicitation | qwen36-27b/G1/C3-vs-C0 McNemar | 0.7807 | 1.0000 | · | 0.8968 | · |  |
| elicitation | ovis-9b/G7/C3-vs-C0 McNemar | 0.8145 | 1.0000 | · | 0.9231 | · |  |
| elicitation | qwen35-27b/G7/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G7/C1-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G7/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G1/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen36-27b/S6/C1-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen36-27b/S6/C3-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| reward | reward:CLIP-IQA (ViT-L/14)/G7-pref-vs-chance | 2.54e-10 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| reward | reward:Skywork-VL-Reward-7B/G7-pref-vs-chance | 4.22e-08 | 2.00e-06 | ✓ | 0.0000 | ✓ | ★ |
| reward | reward:PickScore-v1/G7-pref-vs-chance | 6.19e-05 | 0.0033 | ✓ | 1.59e-04 | ✓ | ★ |
| reward | reward:LAION-Aesthetic (CLIP-L/14)/G7-pref-vs-chance | 0.2059 | 1.0000 | · | 0.3070 | · |  |
| reward | reward:DocReward-3B/G7-pref-vs-chance | 0.6733 | 1.0000 | · | 0.7840 | · |  |

## Headline-claim survival

- gemma4-31b/G7/C3-vs-C0 McNemar: raw p=1.19e-14 → Holm p=0.0000 → **survives**.
- qwen35-27b/G7/C3-vs-C0 McNemar: raw p=1.46e-11 → Holm p=0.0000 → **survives**.
- qwen35-27b/G1/C2-vs-C0 McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen35-9b/G7/C3-vs-C0 McNemar: raw p=4.44e-16 → Holm p=0.0000 → **survives**.
- qwen36-27b/G7/C3-vs-C0 McNemar: raw p=6.46e-27 → Holm p=0.0000 → **survives**.
- qwen36-27b/G1/C2-vs-C0 McNemar: raw p=0.0019 → Holm p=0.0931 → survives BH only.
- examiner:S4-density-synth(ft8b>zs30b): raw p=4.53e-07 → Holm p=2.50e-05 → **survives**.
- examiner:S4-density-real(zs30b>ft8b): raw p=1.13e-05 → Holm p=6.08e-04 → **survives**.
- reward:PickScore-v1/G7-pref-vs-chance: raw p=6.19e-05 → Holm p=0.0033 → **survives**.
- reward:Skywork-VL-Reward-7B/G7-pref-vs-chance: raw p=4.22e-08 → Holm p=2.00e-06 → **survives**.
- gemini-2.5-flash/G7/C3_vs_C0_rep_maj McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- gpt-5.1-nothinking/G7/C3_vs_C0_rep_maj McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen3-vl-plus/G7/C3_vs_C0_rep_maj McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
