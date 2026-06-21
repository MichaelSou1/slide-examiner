# Real-deck semantic annotation protocol (deferred / nice-to-have)

> **Status: protocol only — execution is deferred.** This machine cannot produce
> multi-annotator human labels. The protocol is written so the work is *runnable*
> the moment annotators are available, but it is explicitly **not required** for
> Part 2's conclusions: the credible real-world transfer signal is the
> **third-party** SlideAudit set (`reports/part2.md` Table 5), which we did **not**
> annotate ourselves. Hand-rolling our own real test set would invite a
> self-annotation / unfairness critique, so it is parked under the spec's
> "Deferred human-annotation work" section, not on the critical path.

## Why this exists

P0-1's structured real-transfer eval and P0-2's panel both need real decks with
human semantic labels. Geometry (G1–G6) on real decks can be auto-labelled by the
symbolic linter once a deck has element structure (PPTX → IR via `ingest.py`), but
the **semantic** group (S1/S2/S4/S5/S6) has no programmatic ground truth on real
decks — it needs people. This document fixes the labelling rules so that, if/when
annotators exist, the labels are comparable to the synthetic eval (same taxonomy,
same strong-agreement present/absent convention as Table 5).

## Unit of annotation

One judgement per **(target, defect_type)**:

- page-scope defects (S1 title/body, S4 density, S6 image–text): target = a page.
- deck-scope defects (S2 narrative order, S5 missing section): target = a deck.

Use the **same 12-class taxonomy** (`slide_examiner/taxonomy.py`). S3 terminology
is **not** annotated for the VLM examiner — it is routed to the symbolic
term-consistency linter (Part 1 Go/No-Go), so it never enters the panel.

## Label set (three-way)

For each (target, defect_type) the annotator picks exactly one:

| label | meaning |
|---|---|
| `present` | the defect is clearly there |
| `absent` | the defect is clearly not there |
| `uncertain` | genuinely ambiguous / can't tell |

Severity, when `present`, is recorded on the existing `minor / moderate / severe`
scale (optional; not used for the primary balanced-accuracy metric).

## Aggregation (matches Table 5 convention)

- **≥ 2 annotators per target** (3 preferred for the panel arm).
- **strong agreement = ground truth**: a target is a **positive** only if *all*
  annotators said `present`, a **negative** only if *all* said `absent`.
- any `uncertain`, or any disagreement, → **grey zone**, excluded from the primary
  metric (reported separately as a coverage/ambiguity number).
- This is the same "strong-agreement present/absent" rule already used for
  SlideAudit, so synthetic, SlideAudit, and real-panel numbers stay comparable.

## Scale targets (minimum, just enough for a CI)

- page-scope S1, S4: **≥ 30 positive + ≥ 30 negative** each (strong-agreement).
- deck-scope S2, S5: **≥ 20 positive + ≥ 20 negative** each.
- These are sized to produce a Wilson 95% CI, not a large benchmark.

## Output schema (`eval/panel_ratings.jsonl`)

One JSON object per (annotator, target, defect_type), matching the schema
`slide_examiner/panel.py::PanelRating` consumes:

```json
{"sample_id": "<deck-or-page-id>::<DEFECT_TYPE>", "judge_id": "h1",
 "score": 1.0, "source": "human", "passed": true, "notes": "free text"}
```

- `score`: 1.0 for `present`, 0.0 for `absent`. Leave the row **out** for
  `uncertain` (grey zone), or set `passed=null` and exclude in aggregation.
- `passed`: `true` = present, `false` = absent (drives the binary agreement vote).
- `source`: `"human"` for annotators, `"api"` for the frozen API judge arm.

## How to run (once data exists)

```bash
slide-examiner panel eval/panel_ratings.jsonl -o reports/panel_summary.json
```

`reports/panel_summary.json` now reports `agreement.percent_agreement` and
`agreement.cohen_kappa` (2-rater case) in addition to per-sample pass rates, so the
inter-annotator agreement (κ / percent) required to trust the labels is emitted
automatically (`slide_examiner/panel.py::inter_annotator_agreement`).

## What blocks execution

No annotators on this machine. Until then the panel arm of P0-1/P0-2 stays empty
by design; Part 2 stands on synthetic in-domain (Tables 1–4) + third-party
SlideAudit (Table 5). See the spec's "Deferred human-annotation work" section.
