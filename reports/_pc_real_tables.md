# Part 3 R2 — real-layout modality A/B/C attribution

Models: internvl-8b, ovis-9b, qwen35-27b

Balanced accuracy on paired clean controls (real LibreOffice renders + lossless python-pptx oracle). A = image-only, B = structured oracle, C = image+oracle.

## Per-class mean balanced accuracy across models

Mean over 3 models; n = paired clean controls per model (shared eval set). Per-model intervals are in the detail table below.

| Class | n/model | A (image) | B (oracle) | C (both) | ΔC−A | ΔB−A | verdict |
|---|---|---|---|---|---|---|---|
| G1 overflow | 90 | 0.70 | 0.50 | 0.64 | -0.06 | -0.20 | **image-sufficient** |
| G2 overlap | 82 | 0.74 | 0.59 | 0.72 | -0.02 | -0.15 | **image-sufficient** |
| G3 align | 80 | 0.51 | 0.49 | 0.50 | -0.01 | -0.03 | **capability** |
| G4 font | 90 | 0.61 | 0.62 | 0.62 | +0.01 | +0.01 | **image-sufficient** |
| G6 margin | 76 | 0.59 | 0.70 | 0.66 | +0.07 | +0.11 | **perception** |

## Per-model detail (bal-acc [CI], McNemar C-vs-A)


### internvl-8b (n_pairs=209, failures=0)

| Class | A [CI] (n) | B [CI] (n) | C [CI] (n) | McNemar C-vs-A (p, +/−) | localize C | repair A |
|---|---|---|---|---|---|---|
| G1 overflow | 0.62 [0.49-0.73] (n=90) | 0.52 [0.39-0.65] (n=90) | 0.56 [0.45-0.66] (n=90) | p=0.4885 (23/29) | 0.525 | 1.0 |
| G2 overlap | 0.69 [0.55-0.81] (n=82) | 0.48 [0.34-0.62] (n=82) | 0.61 [0.46-0.74] (n=82) | p=0.1671 (6/13) | 0.483 | 0.957 |
| G3 align | 0.51 [0.43-0.59] (n=80) | 0.49 [0.36-0.62] (n=80) | 0.50 [0.46-0.54] (n=80) | p=1.0 (2/3) | 0.175 | 1.0 |
| G4 font | 0.53 [0.41-0.65] (n=90) | 0.63 [0.49-0.75] (n=90) | 0.58 [0.47-0.68] (n=90) | p=0.5034 (12/8) | 0.707 | 0.972 |
| G6 margin | 0.50 [0.35-0.65] (n=76) | 0.58 [0.43-0.71] (n=76) | 0.55 [0.41-0.69] (n=76) | p=0.424 (9/5) | 0.414 | 1.0 |

### ovis-9b (n_pairs=209, failures=8)

| Class | A [CI] (n) | B [CI] (n) | C [CI] (n) | McNemar C-vs-A (p, +/−) | localize C | repair A |
|---|---|---|---|---|---|---|
| G1 overflow | 0.69 [0.57-0.78] (n=90) | 0.47 [0.36-0.58] (n=90) | 0.56 [0.42-0.68] (n=90) | p=0.0075 (3/15) | 0.8 | 0.895 |
| G2 overlap | 0.65 [0.52-0.75] (n=81) | 0.66 [0.51-0.79] (n=80) | 0.65 [0.52-0.76] (n=81) | p=1.0 (5/4) | 0.562 | 0.8 |
| G3 align | 0.53 [0.43-0.62] (n=80) | 0.47 [0.33-0.62] (n=80) | 0.51 [0.37-0.65] (n=78) | p=1.0 (10/11) | 0.154 | 1.0 |
| G4 font | 0.62 [0.48-0.75] (n=90) | 0.61 [0.47-0.73] (n=90) | 0.69 [0.55-0.80] (n=88) | p=0.3915 (20/14) | 0.737 | 1.0 |
| G6 margin | 0.54 [0.43-0.64] (n=76) | 0.79 [0.64-0.89] (n=76) | 0.71 [0.57-0.81] (n=76) | p=0.0072 (17/4) | 0.895 | 0.667 |

### qwen35-27b (n_pairs=209, failures=0)

| Class | A [CI] (n) | B [CI] (n) | C [CI] (n) | McNemar C-vs-A (p, +/−) | localize C | repair A |
|---|---|---|---|---|---|---|
| G1 overflow | 0.79 [0.67-0.86] (n=90) | 0.51 [0.37-0.65] (n=90) | 0.81 [0.68-0.90] (n=90) | p=0.7744 (7/5) | 0.848 | 0.963 |
| G2 overlap | 0.87 [0.73-0.94] (n=82) | 0.63 [0.48-0.76] (n=82) | 0.90 [0.78-0.96] (n=82) | p=0.5078 (6/3) | 0.914 | 0.912 |
| G3 align | 0.50 [0.35-0.65] (n=80) | 0.50 [0.35-0.65] (n=80) | 0.50 [0.42-0.58] (n=80) | p=1.0 (18/18) | 0.5 | 0.95 |
| G4 font | 0.67 [0.54-0.77] (n=90) | 0.61 [0.49-0.71] (n=90) | 0.59 [0.50-0.67] (n=90) | p=0.1892 (7/14) | 0.778 | 0.8 |
| G6 margin | 0.72 [0.57-0.84] (n=76) | 0.74 [0.59-0.84] (n=76) | 0.72 [0.58-0.83] (n=76) | p=1.0 (7/7) | 0.905 | 0.792 |

## Render-fidelity audit on REAL decks (vs synthetic 45% absorption)

Overall rendered_rate = **0.929** (absorption_rate 0.071), n_scored=225.

| Class | rendered_rate | absorption_rate | changed_frac median |
|---|---|---|---|
| G1 overflow | 1.0 | 0.0 | 0.02908 |
| G2 overlap | 0.911 | 0.089 | 0.00979 |
| G3 align | 0.889 | 0.111 | 0.02009 |
| G4 font | 1.0 | 0.0 | 0.02069 |
| G6 margin | 0.844 | 0.156 | 0.01049 |
