#!/usr/bin/env bash
# One-shot Part 3 LIVE run: serve generator (Qwen3.6-27B) + examiner (ft-8B) with
# the vllm-qwen env (base vllm has a broken triton_kernels), wait for readiness,
# run the optimizer matrix with base python (has gepa+skillopt), then tear down.
# Everything in ONE process so the servers live exactly as long as this script
# (the harness reaps background processes between separate tool calls).
set -u
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/bin/python          # base: has gepa + skillopt + openai

CONDITIONS="${CONDITIONS:-linter finetuned_8b hybrid}"
CARRIERS="${CARRIERS:-gepa}"
BUDGET="${BUDGET:-6}"
GENTOK="${GENTOK:-600}"
SEEDS="${SEEDS:-0}"
LEVEL="${LEVEL:-page}"
TASKS="${TASKS:-$REPO/data/part3/tasks_pilot}"
SERVE_EXAMINER="${SERVE_EXAMINER:-1}"
OUT="${OUT:-$REPO/runs/probe/part3/live_main.jsonl}"

GEN_PID=""; EX_PID=""
cleanup(){ [ -n "$GEN_PID" ] && kill -9 "$GEN_PID" 2>/dev/null; [ -n "$EX_PID" ] && kill -9 "$EX_PID" 2>/dev/null; pkill -9 -f "VLLM::EngineCore" 2>/dev/null; }
trap cleanup EXIT

cd /tmp   # avoid torch-inductor reading ./specs (memory: vllm-serving-gotchas)

echo "[live] starting generator (Qwen3.6-27B) on GPU0,1 ..."
CUDA_VISIBLE_DEVICES=0,1 HF_HUB_OFFLINE=1 "$VLLM" serve /home/gpus/models/Qwen3.6-27B-AWQ-INT4 \
  --served-model-name qwen3.6-27b --port 8200 --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.92 --max-model-len 8192 --limit-mm-per-prompt '{"image":2}' \
  --enforce-eager --trust-remote-code > "$REPO/runs/serve_gen2.log" 2>&1 &
GEN_PID=$!

if [ "$SERVE_EXAMINER" = "1" ]; then
  echo "[live] starting examiner (ft-8B) on GPU2,3 ..."
  CUDA_VISIBLE_DEVICES=2,3 HF_HUB_OFFLINE=1 "$VLLM" serve "$REPO/runs/part2/examiner_merged" \
    --served-model-name ft-8b --port 8101 --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.92 --max-model-len 8192 --limit-mm-per-prompt '{"image":4}' \
    --enforce-eager --trust-remote-code > "$REPO/runs/serve_ex.log" 2>&1 &
  EX_PID=$!
fi

wait_ready(){ # port name
  for _ in $(seq 1 160); do
    curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "$2" && return 0
    sleep 4
  done; return 1; }

if wait_ready 8200 qwen3.6-27b; then echo "[live] generator READY"; else echo "[live] GEN NOT READY"; tail -25 "$REPO/runs/serve_gen2.log"; exit 1; fi
if [ "$SERVE_EXAMINER" = "1" ]; then
  if wait_ready 8101 ft-8b; then echo "[live] examiner READY"; else echo "[live] examiner NOT READY (examiner conditions will be recorded as failures; linter still runs)"; tail -20 "$REPO/runs/serve_ex.log"; fi
fi

echo "[live] running matrix: conditions=[$CONDITIONS] carriers=[$CARRIERS] budget=$BUDGET seeds=[$SEEDS] level=$LEVEL"
"$PY" "$REPO/scripts/part3_run.py" --carriers $CARRIERS --conditions $CONDITIONS --seeds $SEEDS \
  --budget "$BUDGET" --level "$LEVEL" --gen-max-tokens "$GENTOK" --no-render --tasks-dir "$TASKS" \
  --out "$OUT" --best-dir "$REPO/runs/part3/best_skill_live" \
  --out-root "$REPO/runs/part3/live_runs" \
  --gen-base-url http://127.0.0.1:8200/v1 --optimizer-base-url http://127.0.0.1:8200/v1 \
  --examiner-base-url http://127.0.0.1:8101/v1 --examiner-model ft-8b
echo "[live] DONE -> $OUT"
