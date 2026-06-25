# E8 Table-2 corrected G3/G5 cells (coverage-freeform, matched twins)

Linter = CPU recompute (declared IR); VLM = body model qwen35-27b, named attribution, paired-clean.

| Class | linter bal-acc (n, FP) | VLM-C0 named | VLM-C3 named |
|---|---|---|---|
| G3 | 0.929 (n=70+70, FP=0) | 0.621 (r=0.24,s=1.00) | 0.707 (r=0.41,s=1.00) |
| G5 | 1.000 (n=40+40, FP=0) | 0.500 (r=0.00,s=1.00) | 0.675 (r=0.35,s=1.00) |

**Routing:** G3/G5 -> LINTER (cheaper, exact on declared geometry, 0 FP). VLM-C3 is the open-world fallback (no IR): recovers supra-threshold but plateaus (~0.85-0.90 by 48px for G3) and needs the magnitude floor; VLM-C0 (open pointwise) suppresses both. See fig10 saturation curve.
