#!/usr/bin/env bash
# Fully-API Part 3 pipeline (no GPU): feedback-IV -> optimizer matrix -> gold-vs-
# proxy hacking audit -> synthesis. Generator + frozen reflection + zero-shot
# examiner all hit the online API in .env. One process so it survives the harness.
set -u
REPO=/home/gpus/slide-examiner
PY=/home/gpus/anaconda3/bin/python
cd "$REPO"

CONDITIONS="${CONDITIONS:-linter zero_shot_8b}"
SEEDS="${SEEDS:-0 1}"
BUDGET="${BUDGET:-8}"
TASKS="${TASKS:-$REPO/data/part3/tasks_pilot}"
MAIN="$REPO/runs/probe/part3/live_main.jsonl"

echo "[api] feedback IV ..."
"$PY" scripts/part3_feedback_iv.py >/dev/null

echo "[api] optimizer matrix (conditions=[$CONDITIONS] seeds=[$SEEDS] budget=$BUDGET) ..."
"$PY" scripts/part3_run.py --carriers gepa --conditions $CONDITIONS --seeds $SEEDS \
  --budget "$BUDGET" --level page --no-render --tasks-dir "$TASKS" \
  --out "$MAIN" --best-dir "$REPO/runs/part3/best_skill_live" --out-root "$REPO/runs/part3/live_runs"

echo "[api] gold-vs-proxy hacking audit ..."
"$PY" scripts/part3_hacking_audit.py --main-jsonl "$MAIN" --max-tasks 2 || echo "[api] hacking audit skipped"

echo "[api] synthesis + H3 gate ..."
"$PY" scripts/part3_synthesis.py --main-jsonl "$MAIN"
echo "[api] DONE"
