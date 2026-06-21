#!/usr/bin/env bash
# Render <pptx> -> per-slide PNGs using the UNSQUASHFS-EXTRACTED LibreOffice binary
# (the AppImage launcher hangs under the harness; the extracted ELF does not).
# Args: <input.pptx> <out_dir> [dpi]
set -u
IN="$1"; OUT="$2"; DPI="${3:-150}"
LO_ROOT=/tmp/lo_root
SOF="$LO_ROOT/opt/libreoffice26.2/program/soffice"
APP=/home/gpus/.local/opt/LibreOffice.AppImage
mkdir -p "$OUT"

# (re)extract the AppImage filesystem if missing (FUSE-free)
if [ ! -x "$SOF" ]; then
  echo "[render] extracting LibreOffice fs ..."
  rm -rf "$LO_ROOT"
  unsquashfs -o 193728 -d "$LO_ROOT" "$APP" >/tmp/unsq.log 2>&1
  SOF=$(find "$LO_ROOT" -path "*/program/soffice" -type f | head -1)
fi
[ -x "$SOF" ] || { echo "[render] no soffice binary"; exit 2; }

cp -f "$IN" "$OUT/deck.pptx"
pkill -9 -f soffice.bin 2>/dev/null; sleep 1
rm -rf /tmp/lo_prof; mkdir -p /tmp/lo_prof
rm -f "$OUT/deck.pdf" "$OUT"/slide-*.png
HOME=/tmp/lo_prof "$SOF" --headless --norestore --nologo --nolockcheck \
  -env:UserInstallation=file:///tmp/lo_prof \
  --convert-to pdf --outdir "$OUT" "$OUT/deck.pptx" </dev/null >"$OUT/soffice.log" 2>&1
echo "[render] soffice rc=$?"
[ -f "$OUT/deck.pdf" ] || { echo "[render] NO PDF"; tail -5 "$OUT/soffice.log"; exit 2; }
pdftoppm -png -r "$DPI" "$OUT/deck.pdf" "$OUT/slide" </dev/null
echo "[render] DONE pngs=$(ls "$OUT"/slide-*.png 2>/dev/null | wc -l)"
