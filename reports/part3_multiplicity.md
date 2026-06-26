# Multiplicity correction (E2)

## Primary cross-model tests (pooled / stratified McNemar)

The "recovers across models" claims are tested as ONE stratified McNemar over the per-model matched pairs — the analysis that matches the claim and is immune to the per-cell multiplicity penalty. `c=0` means not a single reversal in any model.

| Claim | b (gain) | c (loss) | χ² | p | strata | fully consistent |
|---|---|---|---|---|---|---|
| G7 C3-vs-C0 (capable models) | 233 | 2 | 227.1 | 0.0000 | 4 | no (max c=2) |
| G1 C2-vs-C0 (strong Qwens) | 93 | 36 | 25.2 | 5.21e-07 | 2 | no (max c=27) |

Family of **61** reported significance tests across elicitation (paired McNemar), examiner (two-proportion z), and reward (G7 preference vs chance). Holm (FWER) survivors: **23**; Benjamini-Hochberg (FDR) survivors: **33** at α=0.05.

| Source | Contrast | raw p | Holm p | Holm✓ | BH p | BH✓ | headline |
|---|---|---|---|---|---|---|---|
| examiner | examiner:S4-density-synth(ft8b>zs30b) | 4.53e-07 | 1.90e-05 | ✓ | 1.00e-06 | ✓ | ★ |
| examiner | examiner:S4-density-real(zs30b>ft8b) | 1.13e-05 | 4.73e-04 | ✓ | 3.40e-05 | ✓ | ★ |
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
| elicitation | internvl-8b/G1/C3-vs-C0 McNemar | 1.00e-04 | 0.0040 | ✓ | 2.65e-04 | ✓ |  |
| elicitation | ovis-9b/S6/C1-vs-C0 McNemar | 1.00e-04 | 0.0040 | ✓ | 2.65e-04 | ✓ |  |
| elicitation | qwen36-27b/G1/C2-vs-C0 McNemar | 0.0019 | 0.0722 | · | 0.0048 | ✓ | ★ |
| elicitation | gemma4-31b/S6/C2-vs-C0 McNemar | 0.0026 | 0.0962 | · | 0.0061 | ✓ |  |
| elicitation | gemma4-31b/S6/C3-vs-C0 McNemar | 0.0026 | 0.0962 | · | 0.0061 | ✓ |  |
| elicitation | gemma4-31b/G1/C1-vs-C0 McNemar | 0.0033 | 0.1155 | · | 0.0075 | ✓ |  |
| elicitation | qwen35-9b/S6/C3-vs-C0 McNemar | 0.0118 | 0.4012 | · | 0.0257 | ✓ |  |
| elicitation | gemma4-31b/G7/C2-vs-C0 McNemar | 0.0152 | 0.5016 | · | 0.0320 | ✓ |  |
| elicitation | internvl-8b/G7/C2-vs-C0 McNemar | 0.0192 | 0.6144 | · | 0.0378 | ✓ |  |
| elicitation | qwen35-27b/G1/C3-vs-C0 McNemar | 0.0192 | 0.6144 | · | 0.0378 | ✓ |  |
| elicitation | internvl-8b/G1/C1-vs-C0 McNemar | 0.0230 | 0.6900 | · | 0.0425 | ✓ |  |
| elicitation | internvl-8b/G1/C2-vs-C0 McNemar | 0.0230 | 0.6900 | · | 0.0425 | ✓ |  |
| elicitation | qwen35-9b/G1/C1-vs-C0 McNemar | 0.0400 | 1.0000 | · | 0.0718 | · |  |
| elicitation | qwen35-9b/G1/C3-vs-C0 McNemar | 0.0681 | 1.0000 | · | 0.1187 | · |  |
| elicitation | gemma4-31b/G1/C3-vs-C0 McNemar | 0.0893 | 1.0000 | · | 0.1513 | · |  |
| elicitation | gemma4-31b/G1/C2-vs-C0 McNemar | 0.1175 | 1.0000 | · | 0.1937 | · |  |
| elicitation | qwen36-27b/G1/C1-vs-C0 McNemar | 0.1250 | 1.0000 | · | 0.2007 | · |  |
| elicitation | ovis-9b/G7/C2-vs-C0 McNemar | 0.1496 | 1.0000 | · | 0.2340 | · |  |
| elicitation | qwen35-27b/S6/C2-vs-C0 McNemar | 0.3877 | 1.0000 | · | 0.5768 | · |  |
| elicitation | ovis-9b/G1/C2-vs-C0 McNemar | 0.4244 | 1.0000 | · | 0.6164 | · |  |
| elicitation | ovis-9b/G1/C1-vs-C0 McNemar | 0.4614 | 1.0000 | · | 0.6545 | · |  |
| elicitation | qwen36-27b/G7/C1-vs-C0 McNemar | 0.5000 | 1.0000 | · | 0.6932 | · |  |
| elicitation | qwen36-27b/S6/C2-vs-C0 McNemar | 0.5386 | 1.0000 | · | 0.7158 | · |  |
| elicitation | ovis-9b/G1/C3-vs-C0 McNemar | 0.5413 | 1.0000 | · | 0.7158 | · |  |
| elicitation | ovis-9b/G7/C1-vs-C0 McNemar | 0.5515 | 1.0000 | · | 0.7158 | · |  |
| elicitation | internvl-8b/S6/C1-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7565 | · |  |
| elicitation | internvl-8b/S6/C2-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7565 | · |  |
| elicitation | internvl-8b/S6/C3-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7565 | · |  |
| elicitation | internvl-8b/G7/C1-vs-C0 McNemar | 0.6655 | 1.0000 | · | 0.7749 | · |  |
| elicitation | internvl-8b/G7/C3-vs-C0 McNemar | 0.6655 | 1.0000 | · | 0.7749 | · |  |
| elicitation | qwen36-27b/G1/C3-vs-C0 McNemar | 0.7807 | 1.0000 | · | 0.8819 | · |  |
| elicitation | ovis-9b/G7/C3-vs-C0 McNemar | 0.8145 | 1.0000 | · | 0.9034 | · |  |
| elicitation | qwen35-27b/G7/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G7/C1-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G7/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G1/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen36-27b/S6/C1-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen36-27b/S6/C3-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| reward | reward:CLIP-IQA (ViT-L/14)/G7-pref-vs-chance | 2.54e-10 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| reward | reward:Skywork-VL-Reward-7B/G7-pref-vs-chance | 4.22e-08 | 2.00e-06 | ✓ | 0.0000 | ✓ | ★ |
| reward | reward:PickScore-v1/G7-pref-vs-chance | 6.19e-05 | 0.0025 | ✓ | 1.80e-04 | ✓ | ★ |
| reward | reward:LAION-Aesthetic (CLIP-L/14)/G7-pref-vs-chance | 0.2059 | 1.0000 | · | 0.3140 | · |  |
| reward | reward:DocReward-3B/G7-pref-vs-chance | 0.6733 | 1.0000 | · | 0.7749 | · |  |

## Headline-claim survival

- gemma4-31b/G7/C3-vs-C0 McNemar: raw p=1.19e-14 → Holm p=0.0000 → **survives**.
- qwen35-27b/G7/C3-vs-C0 McNemar: raw p=1.46e-11 → Holm p=0.0000 → **survives**.
- qwen35-27b/G1/C2-vs-C0 McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen35-9b/G7/C3-vs-C0 McNemar: raw p=4.44e-16 → Holm p=0.0000 → **survives**.
- qwen36-27b/G7/C3-vs-C0 McNemar: raw p=6.46e-27 → Holm p=0.0000 → **survives**.
- qwen36-27b/G1/C2-vs-C0 McNemar: raw p=0.0019 → Holm p=0.0722 → survives BH only.
- examiner:S4-density-synth(ft8b>zs30b): raw p=4.53e-07 → Holm p=1.90e-05 → **survives**.
- examiner:S4-density-real(zs30b>ft8b): raw p=1.13e-05 → Holm p=4.73e-04 → **survives**.
- reward:PickScore-v1/G7-pref-vs-chance: raw p=6.19e-05 → Holm p=0.0025 → **survives**.
- reward:Skywork-VL-Reward-7B/G7-pref-vs-chance: raw p=4.22e-08 → Holm p=2.00e-06 → **survives**.
