#!/usr/bin/env bash
# Part 3 post-sweep analysis (API-only; no GPU/serving needed): pilot variance,
# gold-vs-proxy reward-hacking audit, frozen-judge final eval, synthesis + H3 gate.
# The generator + judge run on the online API; gold/cheat detectors are offline.
set -u
REPO=/home/gpus/slide-examiner
PY=/home/gpus/anaconda3/bin/python
cd "$REPO"

echo "[analyze] feedback IV (H3 x-axis) ..."
"$PY" scripts/part3_feedback_iv.py >/dev/null

echo "[analyze] page-level pilot variance summary ..."
"$PY" scripts/part3_pilot.py --from-jsonl runs/probe/part3/pilot_main.jsonl \
  --out runs/probe/part3/pilot_summary.json --report reports/part3_pilot.md >/dev/null || echo "  (pilot summary skipped)"

echo "[analyze] gold-vs-proxy reward-hacking audit ..."
"$PY" scripts/part3_hacking_audit.py --main-jsonl runs/probe/part3/main.jsonl \
  --tasks data/part3/tasks/test.jsonl --max-tasks 3 --gen-max-tokens 2048 || echo "  (hacking audit skipped)"

echo "[analyze] frozen-judge final eval (held-out test) ..."
"$PY" scripts/part3_final_eval.py --main-jsonl runs/probe/part3/main.jsonl \
  --tasks data/part3/tasks/test.jsonl --max-tasks 3 --gen-max-tokens 2048 || echo "  (final eval skipped)"

echo "[analyze] synthesis + H3 gate ..."
"$PY" scripts/part3_synthesis.py --main-jsonl runs/probe/part3/main.jsonl
echo "[analyze] DONE"
