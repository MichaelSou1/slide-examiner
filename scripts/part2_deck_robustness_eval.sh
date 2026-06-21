#!/usr/bin/env bash
# P2-1 (deck S2/S5 paired-clean) + P1-2 (prompt-format robustness).
# Serves one model with vLLM (vllm-qwen env) and runs:
#   - deck_test.json        : deck-only S2 pointwise (A/B/C) vs rendered clean decks
#   - deck_ood_defect.json  : deck-only S5 pointwise (A/B/C) vs rendered clean decks
#   - pointwise_test_trained.json : (ROBUST=1 only) page semantic at TRAINED format
# Usage: part2_deck_robustness_eval.sh NAME MODEL PORT GPUS TP STYLE ROBUST [EXTRA_VLLM_ARGS...]
set -u
NAME="$1"; MODEL="$2"; PORT="$3"; GPUS="$4"; TP="$5"; STYLE="$6"; ROBUST="$7"; shift 7
EXTRA="$*"
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/envs/slide-examiner/bin/python
OUT="$REPO/runs/probe/part2_eval/$NAME"; mkdir -p "$OUT"
LOG="$REPO/runs/part2/serve_deck_${NAME}.log"
BASE="http://localhost:${PORT}/v1"

echo "[serve] $NAME on GPUS=$GPUS TP=$TP port=$PORT style=$STYLE robust=$ROBUST"
cd /tmp   # avoid torch-inductor reading ./specs
CUDA_VISIBLE_DEVICES="$GPUS" HF_HUB_OFFLINE=1 nohup "$VLLM" serve "$MODEL" \
  --served-model-name "$NAME" --port "$PORT" --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.92 --max-model-len 8192 --limit-mm-per-prompt '{"image":6}' \
  --enforce-eager --trust-remote-code $EXTRA > "$LOG" 2>&1 &
SERVE_PID=$!

ready=0
for i in $(seq 1 160); do
  if curl -s "http://localhost:${PORT}/v1/models" 2>/dev/null | grep -q "$NAME"; then ready=1; break; fi
  if ! kill -0 "$SERVE_PID" 2>/dev/null; then echo "[serve] DIED early; tail:"; tail -20 "$LOG"; exit 2; fi
  sleep 3
done
if [ "$ready" -ne 1 ]; then echo "[serve] NOT READY; tail:"; tail -25 "$LOG"; kill -9 "$SERVE_PID" 2>/dev/null; exit 2; fi
echo "[serve] $NAME READY"

run() { echo "  -> $1"; cd "$REPO"; "$PY" scripts/part2_eval.py "$@"; }

# P2-1: deck-level S2 (test) — paired clean decks
run pointwise --manifest "$REPO/data/part2/manifest_eval_test_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --modalities A B C \
  --deck-only --deck-clean "$REPO/data/part2/deck_clean_test.jsonl" \
  --max-per-defect 72 --out "$OUT/deck_test.json"
# P2-1: deck-level S5 (ood_defect) — paired clean decks
run pointwise --manifest "$REPO/data/part2/manifest_eval_ood_defect_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --modalities A B C \
  --deck-only --deck-clean "$REPO/data/part2/deck_clean_ood_defect.jsonl" \
  --max-per-defect 60 --out "$OUT/deck_ood_defect.json"

# P1-2: zero-shot baselines re-run at ft's TRAINED format (page semantic robustness)
if [ "$ROBUST" = "1" ]; then
  run pointwise --manifest "$REPO/data/part2/manifest_eval_test_rendered.jsonl" \
    --base-url "$BASE" --model "$NAME" --prompt-style trained --modalities A B C \
    --only-defects S1_TITLE_BODY_MISMATCH S4_DENSITY_RULE_VIOLATION \
    --max-per-defect 60 --out "$OUT/pointwise_test_trained.json"
fi

echo "[teardown] killing $NAME"
kill -9 "$SERVE_PID" 2>/dev/null
pkill -9 -f "served-model-name $NAME" 2>/dev/null
pkill -9 -f "VLLM::EngineCore" 2>/dev/null
sleep 5
echo "[done] $NAME"
