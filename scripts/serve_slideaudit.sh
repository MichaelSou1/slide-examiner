#!/usr/bin/env bash
# Serve one model and run ONLY the SlideAudit real-transfer eval (synthetic already done).
# Usage: serve_slideaudit.sh NAME MODEL_PATH PORT GPUS TP STYLE [EXTRA...]
set -u
NAME="$1"; MODEL="$2"; PORT="$3"; GPUS="$4"; TP="$5"; STYLE="$6"; shift 6; EXTRA="$*"
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/envs/slide-examiner/bin/python
OUT="$REPO/runs/probe/part2_eval/$NAME"; mkdir -p "$OUT"
LOG="$REPO/runs/part2/serve_sa_${NAME}.log"
cd /tmp
CUDA_VISIBLE_DEVICES="$GPUS" HF_HUB_OFFLINE=1 nohup "$VLLM" serve "$MODEL" \
  --served-model-name "$NAME" --port "$PORT" --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.92 --max-model-len 8192 --limit-mm-per-prompt '{"image":6}' \
  --enforce-eager --trust-remote-code $EXTRA > "$LOG" 2>&1 &
SERVE_PID=$!
for i in $(seq 1 160); do
  curl -s "http://localhost:${PORT}/v1/models" 2>/dev/null | grep -q "$NAME" && { echo "[serve] $NAME READY"; break; }
  kill -0 "$SERVE_PID" 2>/dev/null || { echo "[serve] DIED"; tail -15 "$LOG"; exit 2; }
  sleep 3
done
cd "$REPO"
"$PY" scripts/part2_slideaudit_eval.py --base-url "http://localhost:${PORT}/v1" --model "$NAME" \
  --prompt-style "$STYLE" --max-pos-per-defect 60 --max-slides 500 --out "$OUT/slideaudit.json"
kill -9 "$SERVE_PID" 2>/dev/null; pkill -9 -f "VLLM::EngineCore" 2>/dev/null; sleep 4
echo "[done] $NAME slideaudit"
