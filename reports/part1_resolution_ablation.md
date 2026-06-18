# Part 1 — Resolution ablation (narrowed)

Per SPEC §3.0 / todo §7 the resolution sweep is **collapsed to a spot-check on the
non-floor cells only** (no more 768/1024/1536/2048 × every defect — the geometry
sweep already showed 1536 ≡ 2048). The question is narrowed to: *does resolution
move any cell that is not already pinned at the floor or the ceiling?* Answer: **no.**

## Non-floor cells tested

| cell | metric | low res | high res | Δ |
|---|---|---|---|---|
| G1 overflow — pairwise 2-AFC (8B) | robust acc | 1.00 @1536 | 1.00 @2048 | 0 |
| G1 overflow — pairwise 2-AFC (30B) | robust acc | 1.00 @1536 | 1.00 @2048 | 0 |
| G1 overflow — pointwise (8B/30B) | bal-acc | 0.50 / 0.65 | (same) | 0 |
| G3 offset — pairwise 2-AFC (8B/30B) | acc | 0.50 @1536 | 0.50 @2048 | 0 |
| S1 title/body — pointwise A (30B) | bal-acc | 0.963 @1024 | 0.975 @1536 | +0.012 |
| S1 title/body — pointwise C (30B) | bal-acc | 0.938 @1024 | 0.925 @1536 | −0.013 |

(S1 @1536 raw: `runs/probe/part1_s1_res_1536_30b.jsonl`, 8 S1 positives + 40 paired
clean negatives re-rendered at 1536 long-edge; G1/G3 from `runs/probe/part1_fc_summary.json`.)

## Reading

- **Floor stays floor**: G3 alignment offset (2–32px) is at chance (0.50) regardless
  of resolution — the displacement is below the VLM's perceptual threshold, and more
  pixels do not surface it. Same for pointwise geometry generally.
- **Ceiling stays ceiling**: G1 overflow forced-choice and S1 are already saturated at
  the lower resolution; the extra pixels add nothing (±0.01 = noise on n=48).
- **Resolution is not the lever.** The lever for geometry is *model scale / reasoning*
  (only 30B breaks G1 pointwise) and *relative-vs-absolute framing* (forced-choice
  revives G1 at every size/resolution). This closes the resolution dimension for Part 1:
  it neither rescues a floor cell nor is required by a ceiling cell.
