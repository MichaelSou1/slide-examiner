#!/usr/bin/env bash
# Render a .pptx to per-slide PNGs via LibreOffice(AppImage) -> PDF -> pdftoppm.
# Args: <input.pptx> <out_dir> [dpi]
set -u
IN="$1"; OUT="$2"; DPI="${3:-150}"
SOFFICE=/home/gpus/.local/bin/soffice
mkdir -p "$OUT"
cp -f "$IN" "$OUT/deck.pptx"
pkill -9 -f soffice 2>/dev/null; sleep 2

try_convert() { # $1 = label, rest = extra env/args description
  local prof="/tmp/lo_$1_$$"
  rm -rf "$prof"; mkdir -p "$prof"
  echo "[render] attempt=$1 profile=$prof"
  HOME="$prof" "$SOFFICE" --headless --norestore --nolockcheck --nodefault \
    -env:UserInstallation="file://$prof" \
    --convert-to pdf:impress_pdf_Export --outdir "$OUT" "$OUT/deck.pptx" \
    </dev/null >"$OUT/soffice_$1.log" 2>&1
  echo "[render]   rc=$?  pdf?=$([ -f "$OUT/deck.pdf" ] && echo yes || echo no)"
}

# attempt 1: plain
try_convert plain
if [ ! -f "$OUT/deck.pdf" ]; then
  # attempt 2: extract-and-run (FUSE-less)
  export APPIMAGE_EXTRACT_AND_RUN=1
  try_convert extract
fi

if [ ! -f "$OUT/deck.pdf" ]; then echo "[render] FAILED — last log:"; tail -15 "$OUT"/soffice_*.log; exit 2; fi
pdfinfo "$OUT/deck.pdf" | grep -E "Pages|Page size"
pdftoppm -png -r "$DPI" "$OUT/deck.pdf" "$OUT/slide" </dev/null
echo "[render] DONE pngs=$(ls "$OUT"/slide-*.png 2>/dev/null | wc -l)"
