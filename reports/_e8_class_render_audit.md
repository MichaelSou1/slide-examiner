# Render-degeneracy / missing-element audit — all coverage classes (the "S6-type bug" sweep)

**Trigger:** S6 image/text-contradiction showed VLM recall 0/18 in Table 2 — traced to a DATA bug:
the rendered slides have **no image element** (`['title','text','text','text']`), so the cross-modal
contradiction is unjudgeable. Swept every other class for the same failure modes.

**Manifest:** `data/part2/manifest_eval_test_rendered.jsonl` (freeform), the Table-2/coverage source.
**Checks per class:** (a) defective render == clean render (didn't render / snap-absorbed); (b) the
visual element the defect NEEDS to be decidable from the slide is present.

| class | n | def==clean | needs-elem | verdict |
|---|---|---|---|---|
| G1 overflow | 54 | 0/54 | — | OK (renders) |
| G2 overlap | 54 | 0/54 | — | OK |
| G3 alignment | 36 | 0/36 | — | OK (also re-done in E8) |
| G5 color | 54 | 0/54 | — | OK (also re-done in E8) |
| G6 margin | 36 | 0/36 | — | OK render; see 口径 note |
| S1 title/body | 18 | 0/18 | — | OK (renders; the C3 FP effect is real, not a bug) |
| S4 density | 36 | 0/36 | — | OK |
| **S6 image/text** | 18 | 0/18 | **18/18 MISSING image** | **DATA BUG — re-run on valid-figure corpus** |
| S2 narrative-order | 18 | (no clean twin) | deck-level | not an image class (examiner-scope) |
| S3 terminology | 18 | (no clean twin) | deck-level | not an image class (linter/examiner-scope) |

(G7 lives in `manifest_g7_rendered.jsonl`, separately validated — declared box legal, rendered
content overflows; the flagship, not degenerate.)

## Conclusion
- **Only S6 needs re-running for a data bug.** Every other image-level class renders a visibly
  different defective and carries the element its defect needs. No second S6.
- **S6 fix:** re-run C0/C3 (and confirm 2-AFC) on `data/part1_img/manifest_s6_rendered.jsonl`
  (element types `['title','image','text','text']`, 24 S6 records) and splice the real number into
  Table 2. Current 0.0 is invalid.
- **S2/S3 are deck-scope** (no per-slide clean twin) — correctly handled outside the 9-class image
  table; not a bug.

## Separate category (NOT a data bug): well-posedness / 口径
**G6 margin** renders fine, but "how close to the slide edge is *too* close?" is an absolute-reference
judgement — the same ill-posedness family as the old external-reference G3 (E8). Its image-only
VLM-C0/C3 = 0.50 may be a 口径 artifact, not blindness; it recovers via the structure channel (B>A in
real-CC) and routes to the linter (1.00) regardless. **Optional:** an E8-style internal-contrast /
magnitude re-operationalisation of G6 would let Fig 10's "magnitude-gated" claim generalise beyond
G3 — but it is NOT a data bug and is not required (linter covers G6).
