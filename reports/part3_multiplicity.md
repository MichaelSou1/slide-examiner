# Multiplicity correction (E2)

## Primary cross-model tests (pooled / stratified McNemar)

The "recovers across models" claims are tested as ONE stratified McNemar over the per-model matched pairs — the analysis that matches the claim and is immune to the per-cell multiplicity penalty. `c=0` means not a single reversal in any model.

| Claim | b (gain) | c (loss) | χ² | p | strata | fully consistent |
|---|---|---|---|---|---|---|
| G7 C3-vs-C0 (capable models) | 149 | 0 | 149.0 | 0.0000 | 4 | yes (no reversal) |
| G1 C2-vs-C0 (strong Qwens) | 93 | 36 | 25.2 | 5.21e-07 | 2 | no (max c=27) |

Family of **59** reported significance tests across elicitation (paired McNemar), examiner (two-proportion z), and reward (G7 preference vs chance). Holm (FWER) survivors: **20**; Benjamini-Hochberg (FDR) survivors: **31** at α=0.05.

| Source | Contrast | raw p | Holm p | Holm✓ | BH p | BH✓ | headline |
|---|---|---|---|---|---|---|---|
| examiner | examiner:S4-density-synth(ft8b>zs30b) | 4.53e-07 | 1.90e-05 | ✓ | 2.00e-06 | ✓ | ★ |
| examiner | examiner:S4-density-real(zs30b>ft8b) | 1.13e-05 | 4.73e-04 | ✓ | 3.70e-05 | ✓ | ★ |
| elicitation | gemma4-31b/G7/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | gemma4-31b/G7/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | gemma4-31b/S6/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | ovis-9b/S6/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | ovis-9b/S6/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/G7/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/G1/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/G1/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | qwen35-27b/S6/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-27b/S6/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-9b/G7/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | qwen35-9b/S6/C1-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen35-9b/S6/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen36-27b/G7/C2-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ |  |
| elicitation | qwen36-27b/G7/C3-vs-C0 McNemar | 0.0000 | 0.0000 | ✓ | 0.0000 | ✓ | ★ |
| elicitation | internvl-8b/G1/C3-vs-C0 McNemar | 1.00e-04 | 0.0041 | ✓ | 2.95e-04 | ✓ |  |
| elicitation | ovis-9b/S6/C1-vs-C0 McNemar | 1.00e-04 | 0.0041 | ✓ | 2.95e-04 | ✓ |  |
| elicitation | qwen36-27b/G1/C2-vs-C0 McNemar | 0.0019 | 0.0741 | · | 0.0053 | ✓ | ★ |
| elicitation | gemma4-31b/S6/C2-vs-C0 McNemar | 0.0026 | 0.0988 | · | 0.0067 | ✓ |  |
| elicitation | gemma4-31b/S6/C3-vs-C0 McNemar | 0.0026 | 0.0988 | · | 0.0067 | ✓ |  |
| elicitation | gemma4-31b/G1/C1-vs-C0 McNemar | 0.0033 | 0.1188 | · | 0.0081 | ✓ |  |
| elicitation | qwen35-27b/G7/C3-vs-C0 McNemar | 0.0039 | 0.1365 | · | 0.0092 | ✓ | ★ |
| elicitation | qwen35-9b/S6/C3-vs-C0 McNemar | 0.0118 | 0.4012 | · | 0.0268 | ✓ |  |
| elicitation | gemma4-31b/G7/C2-vs-C0 McNemar | 0.0152 | 0.5016 | · | 0.0332 | ✓ |  |
| elicitation | internvl-8b/G7/C2-vs-C0 McNemar | 0.0192 | 0.6144 | · | 0.0391 | ✓ |  |
| elicitation | qwen35-27b/G1/C3-vs-C0 McNemar | 0.0192 | 0.6144 | · | 0.0391 | ✓ |  |
| elicitation | internvl-8b/G1/C1-vs-C0 McNemar | 0.0230 | 0.6900 | · | 0.0438 | ✓ |  |
| elicitation | internvl-8b/G1/C2-vs-C0 McNemar | 0.0230 | 0.6900 | · | 0.0438 | ✓ |  |
| elicitation | qwen35-9b/G1/C1-vs-C0 McNemar | 0.0400 | 1.0000 | · | 0.0737 | · |  |
| elicitation | qwen35-9b/G1/C3-vs-C0 McNemar | 0.0681 | 1.0000 | · | 0.1218 | · |  |
| elicitation | gemma4-31b/G1/C3-vs-C0 McNemar | 0.0893 | 1.0000 | · | 0.1550 | · |  |
| elicitation | gemma4-31b/G1/C2-vs-C0 McNemar | 0.1175 | 1.0000 | · | 0.1981 | · |  |
| elicitation | qwen36-27b/G1/C1-vs-C0 McNemar | 0.1250 | 1.0000 | · | 0.2049 | · |  |
| elicitation | ovis-9b/G7/C2-vs-C0 McNemar | 0.1496 | 1.0000 | · | 0.2386 | · |  |
| elicitation | qwen35-27b/S6/C2-vs-C0 McNemar | 0.3877 | 1.0000 | · | 0.5865 | · |  |
| elicitation | ovis-9b/G1/C2-vs-C0 McNemar | 0.4244 | 1.0000 | · | 0.6260 | · |  |
| elicitation | ovis-9b/G1/C1-vs-C0 McNemar | 0.4614 | 1.0000 | · | 0.6640 | · |  |
| elicitation | qwen36-27b/G7/C1-vs-C0 McNemar | 0.5000 | 1.0000 | · | 0.7024 | · |  |
| elicitation | qwen36-27b/S6/C2-vs-C0 McNemar | 0.5386 | 1.0000 | · | 0.7231 | · |  |
| elicitation | ovis-9b/G1/C3-vs-C0 McNemar | 0.5413 | 1.0000 | · | 0.7231 | · |  |
| elicitation | ovis-9b/G7/C1-vs-C0 McNemar | 0.5515 | 1.0000 | · | 0.7231 | · |  |
| elicitation | internvl-8b/S6/C1-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7622 | · |  |
| elicitation | internvl-8b/S6/C2-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7622 | · |  |
| elicitation | internvl-8b/S6/C3-vs-C0 McNemar | 0.6201 | 1.0000 | · | 0.7622 | · |  |
| elicitation | internvl-8b/G7/C1-vs-C0 McNemar | 0.6655 | 1.0000 | · | 0.7789 | · |  |
| elicitation | internvl-8b/G7/C3-vs-C0 McNemar | 0.6655 | 1.0000 | · | 0.7789 | · |  |
| elicitation | qwen36-27b/G1/C3-vs-C0 McNemar | 0.7807 | 1.0000 | · | 0.8858 | · |  |
| elicitation | ovis-9b/G7/C3-vs-C0 McNemar | 0.8145 | 1.0000 | · | 0.9067 | · |  |
| elicitation | qwen35-27b/G7/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G7/C1-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G7/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen35-9b/G1/C2-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen36-27b/S6/C1-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| elicitation | qwen36-27b/S6/C3-vs-C0 McNemar | 1.0000 | 1.0000 | · | 1.0000 | · |  |
| reward | reward:Skywork-VL-Reward-7B/G7-pref-vs-chance | 4.22e-08 | 2.00e-06 | ✓ | 0.0000 | ✓ | ★ |
| reward | reward:LAION-Aesthetic (CLIP-L/14)/G7-pref-vs-chance | 0.2059 | 1.0000 | · | 0.3197 | · |  |
| reward | reward:DocReward-3B/G7-pref-vs-chance | 0.6733 | 1.0000 | · | 0.7789 | · |  |

## Headline-claim survival

- gemma4-31b/G7/C3-vs-C0 McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen35-27b/G7/C3-vs-C0 McNemar: raw p=0.0039 → Holm p=0.1365 → survives BH only.
- qwen35-27b/G1/C2-vs-C0 McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen35-9b/G7/C3-vs-C0 McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen36-27b/G7/C3-vs-C0 McNemar: raw p=0.0000 → Holm p=0.0000 → **survives**.
- qwen36-27b/G1/C2-vs-C0 McNemar: raw p=0.0019 → Holm p=0.0741 → survives BH only.
- examiner:S4-density-synth(ft8b>zs30b): raw p=4.53e-07 → Holm p=1.90e-05 → **survives**.
- examiner:S4-density-real(zs30b>ft8b): raw p=1.13e-05 → Holm p=4.73e-04 → **survives**.
- reward:Skywork-VL-Reward-7B/G7-pref-vs-chance: raw p=4.22e-08 → Holm p=2.00e-06 → **survives**.
