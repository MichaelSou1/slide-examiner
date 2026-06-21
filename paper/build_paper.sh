#!/bin/bash
# Wait for the scheme-full TeX Live install to finish, then build the paper twice.
set -u
TL=/home/gpus/texlive/2026/bin/x86_64-linux
export PATH="$TL:$PATH"
cd /home/gpus/slide-examiner/paper

echo "[build] waiting for TeX Live to be compile-ready ..."
ready=0
for i in $(seq 1 120); do
  if [ -x "$TL/pdflatex" ]; then
    printf '\\documentclass{article}\\begin{document}ok\\end{document}\n' > /tmp/_tltest.tex
    if "$TL/pdflatex" -interaction=nonstopmode -output-directory=/tmp /tmp/_tltest.tex >/tmp/_tltest.log 2>&1 \
       && [ -f /tmp/_tltest.pdf ]; then
      echo "[build] TeX ready after ~$((i*15))s"; ready=1; break
    fi
  fi
  sleep 15
done
if [ "$ready" -ne 1 ]; then echo "[build] TeX never became ready"; exit 2; fi

echo "[build] pass 1 ..."
"$TL/pdflatex" -interaction=nonstopmode -halt-on-error -file-line-error main.tex > build1.log 2>&1
rc1=$?
echo "[build] pass 2 ..."
"$TL/pdflatex" -interaction=nonstopmode -halt-on-error -file-line-error main.tex > build2.log 2>&1
rc2=$?

if [ -f main.pdf ] && [ "$rc2" -eq 0 ]; then
  echo "[build] SUCCESS  rc1=$rc1 rc2=$rc2"
  ls -la main.pdf
  echo "[build] pages:"; "$TL/pdfinfo" main.pdf 2>/dev/null | grep -iE "^Pages" || true
else
  echo "[build] FAILED rc1=$rc1 rc2=$rc2 — last errors:"
  grep -nE "^.*:[0-9]+:|! |Undefined|Missing|not found|Error" build2.log | head -40
fi
