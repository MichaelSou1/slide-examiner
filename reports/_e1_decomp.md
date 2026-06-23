### E1 — elicitation-recovery decomposition (freeform items, modality A)

All scores are balanced accuracy on a chance-0.5 task, so the components add: **naming** = C0_named − C0 (format suppression proper); **pairing** = AFC_bal − C0_named (availability of a clean reference). AFC_bal is the balanced accuracy of the true 2-AFC (defective vs clean twin) with the AFC_clean *consistent-invention* rate as its specificity side (so a forced-pick artifact is penalised). McNemar p is the exact paired test; **Holm** = family-wise corrected over the 36 E1 tests (α=0.05).

| Model | Defect | C0 | C0_named | AFC_bal [CI] | naming | pairing | gate | McNemar named·vs·C0 (Holm) |
|---|---|---|---|---|---|---|---|---|
| gemma4-31b | G1 | 0.75 | 0.50 | 0.67 [0.58-0.73] | -0.25 | +0.17 | ⚠pairing | 0.0036→0.0647 |
| gemma4-31b | S6 | 0.81 | 0.50 | 0.64 [0.47-0.75] | -0.31 | +0.14 | ⚠pairing | 0.0433→0.6554 |
| gemma4-31b | G7 | 0.69 | 0.88 | 0.97 [0.91-0.98] | +0.19 | +0.08 | ✅naming | 0.0001→0.002 ✅ |
| internvl-8b | G1 | 0.15 | 0.50 | 0.51 [0.47-0.55] | +0.35 | +0.01 | ✅naming | 0.0→0.0 ✅ |
| internvl-8b | S6 | 0.44 | 0.50 | 0.56 [0.43-0.66] | +0.06 | +0.06 | ⚠pairing | 0.8601→1.0 |
| internvl-8b | G7 | 0.46 | 0.50 | 0.50 [0.47-0.53] | +0.04 | +0.00 | ✅naming | 0.5682→1.0 |
| ovis-9b | G1 | 0.54 | 0.50 | 0.71 [0.62-0.78] | -0.04 | +0.21 | ⚠pairing | 0.4545→1.0 |
| ovis-9b | S6 | 0.92 | 0.50 | 0.58 [0.44-0.70] | -0.42 | +0.08 | ⚠pairing | 0.0007→0.0168 ✅ |
| ovis-9b | G7 | 0.60 | 0.53 | 0.88 [0.81-0.92] | -0.07 | +0.35 | ⚠pairing | 0.041→0.6554 |
| qwen35-27b | G1 | 0.78 | 0.50 | 0.97 [0.89-0.99] | -0.28 | +0.47 | ⚠pairing | 0.0009→0.0198 ✅ |
| qwen35-27b | S6 | 0.92 | 0.50 | 1.00 [0.82-1.00] | -0.42 | +0.50 | ⚠pairing | 0.0015→0.0298 ✅ |
| qwen35-27b | G7 | 0.79 | 1.00 | 0.99 [0.95-1.00] | +0.21 | -0.01 | ✅naming | 0.0→0.0 ✅ |
| qwen35-9b | G1 | 0.75 | 0.50 | 0.97 [0.89-0.99] | -0.25 | +0.47 | ⚠pairing | 0.0009→0.0198 ✅ |
| qwen35-9b | S6 | 0.92 | 0.53 | 0.58 [0.44-0.70] | -0.39 | +0.06 | ⚠pairing | 0.0026→0.049 ✅ |
| qwen35-9b | G7 | 0.50 | 0.93 | 0.89 [0.79-0.95] | +0.43 | -0.04 | ✅naming | 0.0→0.0 ✅ |
| qwen36-27b | G1 | 0.50 | 0.50 | 1.00 [0.93-1.00] | +0.00 | +0.50 | ⚠pairing | 1.0→1.0 |
| qwen36-27b | S6 | 0.50 | 0.50 | 1.00 [0.82-1.00] | +0.00 | +0.50 | ⚠pairing | 1.0→1.0 |
| qwen36-27b | G7 | 0.51 | 1.00 | 0.99 [0.94-1.00] | +0.49 | -0.01 | ✅naming | 0.0→0.0 ✅ |

#### Guess-floor control (AFC_clean — two clean slides)

invention = fabricated consistent winner over ALL clean pairs (the artifact that would inflate a forced choice — low is good); tie-rate = how often the model correctly calls two clean slides a tie (high = it abstains rather than guessing); pick-first = position bias.

| Model | Defect | AFC strict acc | invention (all pairs) | tie-rate | pick-first |
|---|---|---|---|---|---|
| gemma4-31b | G1 | 1.00 | 0.00 | 1.00 | — |
| gemma4-31b | S6 | 1.00 | 0.00 | 1.00 | — |
| gemma4-31b | G7 | 0.98 | 0.00 | 0.99 | 0.50 |
| internvl-8b | G1 | 0.03 | 0.00 | 1.00 | — |
| internvl-8b | S6 | 0.11 | 0.00 | 1.00 | — |
| ovis-9b | G1 | 0.96 | 0.00 | 1.00 | — |
| ovis-9b | S6 | 1.00 | 0.00 | 1.00 | — |
| ovis-9b | G7 | 0.97 | 0.00 | 1.00 | — |
| qwen35-27b | G1 | 1.00 | 0.00 | 1.00 | — |
| qwen35-27b | S6 | 1.00 | 0.00 | 1.00 | — |
| qwen35-27b | G7 | 1.00 | 0.01 | 0.96 | 0.86 |
| qwen35-9b | G1 | 0.98 | 0.04 | 0.48 | 0.96 |
| qwen35-9b | S6 | 0.17 | 0.00 | 0.92 | 1.00 |
| qwen35-9b | G7 | 0.93 | 0.15 | 0.54 | 0.82 |
| qwen36-27b | G1 | 1.00 | 0.00 | 0.98 | 1.00 |
| qwen36-27b | S6 | 1.00 | 0.00 | 1.00 | — |
| qwen36-27b | G7 | 1.00 | 0.02 | 0.92 | 0.87 |
