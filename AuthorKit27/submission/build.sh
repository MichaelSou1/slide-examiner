#!/bin/bash
# Build the AAAI-27 anonymous submission (two-column, BibTeX).
# Usage:  bash build.sh
# Requires a full TeX Live (2025+) with: pdflatex, bibtex, pdfinfo.
# (newtx, booktabs, overpic, natbib, aaai2027 — all in TeX Live.)
set -u
cd "$(dirname "$0")"

PDFLATEX="${PDFLATEX:-pdflatex}"
BIBTEX="${BIBTEX:-bibtex}"
PDFINFO="${PDFINFO:-pdfinfo}"

run() {
  "$@" -interaction=nonstopmode -halt-on-error -file-line-error main.tex > /dev/null 2>&1
}

echo "[build] pass 1 (pdflatex) ..."; run "$PDFLATEX"; rc1=$?
echo "[build] bibtex ...";          "$BIBTEX" main > /dev/null 2>&1; rcb=$?
echo "[build] pass 2 (pdflatex) ..."; run "$PDFLATEX"; rc2=$?
echo "[build] pass 3 (pdflatex) ..."; run "$PDFLATEX"; rc3=$?

if [ -f main.pdf ] && [ "$rc3" -eq 0 ]; then
  echo "[build] SUCCESS  rc1=$rc1 bibtex=$rcb rc2=$rc2 rc3=$rc3"
  ls -la main.pdf
  if command -v "$PDFINFO" >/dev/null 2>&1; then
    echo "[build] pages:"; "$PDFINFO" main.pdf 2>/dev/null | grep -iE "^Pages"
  fi
  echo "[build] NOTE: AAAI-27 allows 7 pages technical content + unlimited references + 1 checklist page."
  echo "       References and the reproducibility checklist do not count toward the 7-page limit."
else
  echo "[build] FAILED rc1=$rc1 bibtex=$rcb rc2=$rc2 rc3=$rc3 — last errors:"
  "$PDFLATEX" -interaction=nonstopmode -file-line-error main.tex 2>&1 \
    | grep -nE ":[0-9]+:|! |Undefined|Missing|not found|Error|Runaway" | head -40
  echo "[build] bibtex log tail:"; tail -20 main.blg 2>/dev/null
  exit 1
fi
