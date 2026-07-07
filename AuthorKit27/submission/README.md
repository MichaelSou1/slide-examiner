# AAAI-27 Anonymous Submission

Two-column AAAI camera-ready build of the Slide-Examiner paper. The original
single-column technical report is preserved untouched at `paper/main.tex`;
this is a **separate copy** per the author's instruction not to overwrite the
original.

## Build

```bash
bash build.sh
```
Requires TeX Live 2025+ (`pdflatex`, `bibtex`, `pdfinfo`). Produces `main.pdf`.

```
pdflatex main  &&  bibtex main  &&  pdflatex main  &&  pdflatex main
```

## Layout

- `main.tex` — two-column AAAI source (anonymous via `[submission]`).
- `refs.bib` — BibTeX (titles/arXiv ids verified 2026-06-22/24). `aaai2027.bst`
  is used automatically by `aaai2027.sty`.
- `aaai2027.sty`, `aaai2027.bst` — copied from `AuthorKit27/`.
- `figs/` — reused publication-quality figures from `paper/figs/` (PNG data
  figures + PDF vector concept art with `overpic` text overlays).
- `ReproducibilityChecklist.tex` — filled in (uploaded separately at submission).
- `build.sh` — compile script; reports the page count.

## Changes from the single-column technical report (`paper/main.tex`)

1. **Template**: `article` + `\usepackage[submission]{aaai2027}` (two-column,
   US Letter, anonymous). Removed `geometry`, `hyperref`, `enumitem`,
   `newtxtext`/`newtxmath` (auto-loaded by `aaai2027`), manual `\setlist`.
   `\PassOptionsToPackage{table}{xcolor}` enables `\columncolor` in the reward
   table.
2. **Anonymized**: real author/affiliation/email removed; `[submission]` shows
   "Anonymous submission".
3. **Bibliography**: manual `thebibliography` → `\bibliography{refs}` +
   `aaai2027.bst`; `\cite` → `\citep` (natbib).
4. **Figures**: widths adapted to two-column (`\columnwidth` for single-column
   floats, `\textwidth`/`figure*` for the teaser, saturation, and open-world
   panels). Dropped two redundant concept figures (`fig_rel_vs_abs`,
   `fig_openworld`) whose data figures already convey the point — this is the
   "recombine" step. All data figures and the remaining concept figures
   (teaser, modality–task, G7-overflow) are retained.
5. **Tables**: per-class coverage and multi-reward audit tables promoted to
   `table*` (full width) for readability; taxonomy and examiner tables stay
   single-column.
6. **Appendix**: the SlideAudit crosswalk table is relocated to the supplement
   (one-line pointer in §3); the standalone Reproducibility section is folded
   into a `\paragraph{Reproducibility.}` before the references, with the full
   checklist in `ReproducibilityChecklist.tex`.
7. **Prose**: conservatively trimmed (the user's chosen strategy); all
   scientific claims, numbers, and figures are intact.

## Page limit

AAAI-27: **7 pages** of technical content + unlimited references + the
reproducibility checklist page. If the first build exceeds 7 pages, the
conservative strategy allows a second trimming pass (the most compressible
items are the wide `figure*` floats and the reward/coverage tables).
