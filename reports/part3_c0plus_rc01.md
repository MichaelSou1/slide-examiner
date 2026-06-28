# RC-01 / C0+ control — does naming G7 in the rubric recover it, or is the atomic format load-bearing?

**Design.** C0+ = the C0 whole-taxonomy single pointwise call, with G7 *added to the candidate
catalog and CHECK_SCOPE* (otherwise byte-identical overloaded format). Separates the two readings of
the C0->C3 G7 recovery: prompt-coverage (C0 never asked) vs format-suppression (overloaded format buries
it even when named). Four capable models, manifest_g7_rendered (freeform), modality A, paired-clean.

## Per-model G7 balanced accuracy (detection) + named + specificity

| Model | C0 det | **C0+ det** | C3 det | C0 named | **C0+ named** | C3 named | C0+ spec | C3 spec |
|-------|--------|-------------|--------|----------|---------------|----------|----------|---------|
| Qwen3.5-9B | 0.50 | **0.58** | 0.93 | 0.50 | **0.72** | 0.93 | 0.17 | 0.87 |
| Qwen3.6-27B | 0.51 | **0.72** | 1.00 | 0.50 | **0.74** | 1.00 | 0.43 | 1.00 |
| Qwen3.5-27B | 0.79 | **0.82** | 1.00 | 0.50 | **0.82** | 1.00 | 0.64 | 1.00 |
| Gemma4-31B | 0.69 | **0.72** | 0.99 | 0.50 | **0.82** | 0.99 | 0.44 | 1.00 |

## Decomposition (paired McNemar, pooled over 4 models)

- **COVERAGE** (C0->C0+, named-target on defectives): **234 gained / 0 lost**, exact McNemar p=7.2e-71.
  Adding G7 to the rubric recovers naming on essentially every defective, unanimously across models.
- **FORMAT/recall** (C0+->C3, detection on defectives): 0 gained / 2 lost — recall is already saturated;
  the atomic format does NOT add recall.
- **FORMAT/specificity** (clean-twin false positives, C0+ vs C3): pooled **183/330 (55%) -> 8/330 (2.4%)**.
  The overloaded whole-taxonomy format, even when it names G7 correctly on defectives, over-flags clean
  slides; the atomic per-type binary + forced-evidence gate is what restores specificity.

## Conclusion

The C0->C3 G7 recovery is **not** a single effect. It decomposes into (i) a **coverage** component — the
off-taxonomy class must be named in the rubric before the model will emit it (C0 named-recall 0.00 -> C0+
0.64-0.97) — and (ii) a **format** component whose locus is **specificity**: only the atomic elicitation
converts naming into high-specificity detection (clean-twin FP 55% -> 2.4%). The DA's prompt-coverage concern
is therefore PARTIALLY CORRECT (naming carries the recall recovery) but the format-suppression claim SURVIVES
in sharpened form: the whole-taxonomy format suppresses **precision/specificity**, not the model's ability to
perceive the defect. Naming alone, inside the overloaded format, is necessary but not sufficient.
