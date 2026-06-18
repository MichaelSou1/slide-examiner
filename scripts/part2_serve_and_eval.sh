#!/usr/bin/env bash
# Serve one model with vLLM (vllm-qwen env) and run the Part 2 eval suite against it.
# Usage: part2_serve_and_eval.sh NAME MODEL_PATH PORT GPUS TP STYLE [EXTRA_VLLM_ARGS...]
#   NAME       served + output name (e.g. ft-8b, zs-8b, zs-30b)
#   STYLE      trained | scoped
set -u
NAME="$1"; MODEL="$2"; PORT="$3"; GPUS="$4"; TP="$5"; STYLE="$6"; shift 6
EXTRA="$*"
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/envs/slide-examiner/bin/python
OUT="$REPO/runs/probe/part2_eval/$NAME"; mkdir -p "$OUT"
LOG="$REPO/runs/part2/serve_${NAME}.log"
BASE="http://localhost:${PORT}/v1"

echo "[serve] $NAME on GPUS=$GPUS TP=$TP port=$PORT style=$STYLE"
cd /tmp   # avoid torch-inductor reading ./specs
CUDA_VISIBLE_DEVICES="$GPUS" HF_HUB_OFFLINE=1 nohup "$VLLM" serve "$MODEL" \
  --served-model-name "$NAME" --port "$PORT" --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.92 --max-model-len 8192 --limit-mm-per-prompt '{"image":6}' \
  --enforce-eager --trust-remote-code $EXTRA > "$LOG" 2>&1 &
SERVE_PID=$!

# wait for readiness (<=420s)
ready=0
for i in $(seq 1 140); do
  if curl -s "http://localhost:${PORT}/v1/models" 2>/dev/null | grep -q "$NAME"; then ready=1; break; fi
  if ! kill -0 "$SERVE_PID" 2>/dev/null; then echo "[serve] DIED early; tail:"; tail -15 "$LOG"; exit 2; fi
  sleep 3
done
if [ "$ready" -ne 1 ]; then echo "[serve] NOT READY; tail:"; tail -20 "$LOG"; kill -9 "$SERVE_PID" 2>/dev/null; exit 2; fi
echo "[serve] $NAME READY"

run() { echo "  -> $1"; cd "$REPO"; "$PY" scripts/part2_eval.py "$@"; }

# pointwise: in-domain held-out (A/B/C), OOD severity (C), OOD defect (C)
run pointwise --manifest "$REPO/data/part2/manifest_eval_test_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --modalities A B C \
  --max-per-defect 60 --out "$OUT/pointwise_test.json"
run pointwise --manifest "$REPO/data/part2/manifest_eval_ood_severity_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --modalities A C \
  --max-per-defect 40 --out "$OUT/pointwise_ood_severity.json"
run pointwise --manifest "$REPO/data/part2/manifest_eval_ood_defect_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --modalities A C \
  --max-per-defect 40 --out "$OUT/pointwise_ood_defect.json"
# pairwise 2-AFC: G1 overflow (in-domain test) + S6 (held-out figure corpus)
run pairwise --manifest "$REPO/data/part2/manifest_eval_test_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --max-per-defect 60 \
  --out "$OUT/pairwise_g1.json"
run pairwise --manifest "$REPO/data/part2/manifest_s6_eval_rendered.jsonl" \
  --base-url "$BASE" --model "$NAME" --prompt-style "$STYLE" --max-per-defect 24 \
  --out "$OUT/pairwise_s6.json"
# real-data transfer (SlideAudit, real slides, modality A)
if [ -f "$REPO/data/part2/manifest_slideaudit.jsonl" ]; then
  echo "  -> slideaudit (real transfer)"; cd "$REPO"
  "$PY" scripts/part2_slideaudit_eval.py --base-url "$BASE" --model "$NAME" \
    --prompt-style "$STYLE" --max-pos-per-defect 60 --max-slides 500 \
    --out "$OUT/slideaudit.json"
fi

echo "[teardown] killing $NAME"
kill -9 "$SERVE_PID" 2>/dev/null
pkill -9 -f "served-model-name $NAME" 2>/dev/null
# kill leftover EngineCore on these GPUs
pkill -9 -f "VLLM::EngineCore" 2>/dev/null
sleep 5
echo "[done] $NAME"
