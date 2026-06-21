# demo_real — qualitative AI-PPT-failure references (NON-EVAL)

**Tag: `non-eval`.** Nothing here enters the quantitative Protocol-1/2 scoring
(A.3.1.3). Quantitative real-data signal comes only from SlideAudit
(`data/part2/manifest_slideaudit.jsonl`, labelled). This folder is for report
figures, qualitative cases, and cold-email hooks.

## Status of automated image capture (2026-06-20)

Per the user's instruction I searched the web for real "AI 做 PPT 翻车" examples.
Outcome, recorded honestly:

- The articles that *document* AI-slide failures (overflow, overlap, wall-of-text,
  HTML→PPTX export breakage) illustrate with **marketing/UI imagery, not actual
  broken-slide screenshots** (verified by downloading & inspecting candidates from
  autoppt / smallppt / slidesai blogs — all template galleries or product shots).
- Real fail *screenshots* live mostly on social hosts (X/Reddit/小红书) that are
  **network-blocked from this box** (e.g. wikimedia upload returns HTTP 000;
  WebFetch refuses these domains), so they cannot be scraped automatically here.
- Therefore: **the value extracted is the corroborating SOURCES below**, not the
  pixels. Actual fail-screenshot capture is deferred to Phase 5 — either a user
  drop into this folder, or capture from a reachable host. Each dropped image
  should get a one-line note here: `<file> — <defect desc> — <SlideAudit class | OTHER>`.

## Corroborating sources (external support for the hybrid-critic motivation)

These back the claim that the *render-level / containment* failure mode (our **G7**)
is a real, named, recurring problem in deployed AI slide generators — i.e. the
gap a VLM-engine in the hybrid critic targets and a declared-bbox linter / neural
reward misses.

1. **2Slides — "Why AI Slide Tools Break on PowerPoint Export (2026)"**
   https://2slides.com/blog/why-ai-slide-tools-break-powerpoint-export
   → *"Most AI presentation tools render slides as HTML/CSS in the browser, then
   approximate a PowerPoint file at export time. Because HTML layout and the OOXML
   (PowerPoint) format do not map 1:1 … text boxes overlap."* **Direct external
   witness for G7**: structurally-valid declared layout, broken rendered containment.

2. **smallppt — "7 Most Common Mistakes Using AI to Create Slides"**
   https://smallppt.com/blog/basics/common-ai-slide-mistakes-tips
   → "If the AI generates too much text, it will simply overflow outside the box."
   (G1 text overflow / S4 density.)

3. **autoppt — "7 Common Mistakes to Avoid When Creating Slides with AI"**
   https://autoppt.com/blog/avoid-ai-slide-mistakes/
   → "wall of words"; "clipped shapes"; "placeholder leftovers". (S4 density;
   G7 clipped/containment; placeholder-completeness — cf. the Hermes case in part3.md §6.)

4. **SlidesAI — "Common Mistakes When Using AI Presentation Makers"**
   https://www.slidesai.io/blog/common-ai-presentation-mistakes
   → "Text overflow, bad alignment, clipped shapes, weak contrast, and placeholder
   leftovers are normal first-pass failures." (G1/G3/G7/G5 + completeness.)

5. **Anthropic / Claude slide generation (reported)** — "Claude struggles with
   layout and design … overflowing text boxes and misplaced elements." (G1/G2/G7.)

## Mapping note

G7 (render-containment overflow) ↔ SlideAudit nearest class **"Content
Overflow/Cut-off"** (our-extension refinement; see `../taxonomy_map.json`). The
synthetic G7 pairs in `../manifest_g7_rendered.jsonl` reproduce exactly the
failure mode sources (1)(3)(4) describe in prose.
