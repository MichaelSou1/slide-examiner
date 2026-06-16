# Slide-Examiner Data Layout

This directory is for local research data. Large or private artifacts stay out of
git; only this README and `.gitkeep` placeholders are versioned.

- `raw/`: original downloaded or desensitized files.
- `ir/`: normalized Slide/Deck IR JSON files.
- `manifests/`: manifest JSONL files used by probing, rendering, and SFT export.

Runtime outputs use sibling top-level directories:

- `runs/rendered/`: rasterized slide/page images.
- `runs/probe/`: model output JSONL and summaries.
- `reports/`: analysis, cleaning, and human annotation reports.

Start a fresh workspace with:

```bash
slide-examiner init-data-layout
```
