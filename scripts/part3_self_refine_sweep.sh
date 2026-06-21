#!/usr/bin/env bash
# Part 3 SELF-REFINE full gradient (downgraded PRIMARY vehicle). Same faithful 2-phase
# examiner serving as part3_faithful_sweep.sh, but runs the generate->critique->revise
# loop (no GEPA/SkillOpt). Generator + revision = the API model (PART3_GEN_*); examiner
# (the IV) = local Qwen3-VL-8B / 30B-A3B / ft-8B served here. One process (harness reaping).
set -u
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/bin/python
LOG=$REPO/runs/part3/sweep
mkdir -p "$LOG" "$REPO/runs/probe/part3"

M_8B=/home/gpus/models/Qwen3-VL-8B-Instruct
M_30B=/home/gpus/models/Qwen3-VL-30B-A3B-Instruct-AWQ
M_FT=$REPO/runs/part2/examiner_merged

SR_SEEDS="${SR_SEEDS:-0 1 2}"
SR_ITERS="${SR_ITERS:-3}"
SR_MAXTASKS="${SR_MAXTASKS:-3}"
SR_Q="${SR_Q:-0.85}"
TASKS="${TASKS:-$REPO/data/part3/tasks/test.jsonl}"

PIDS=()
cleanup(){ for p in "${PIDS[@]:-}"; do kill -9 "$p" 2>/dev/null; done; pkill -9 -f "VLLM::EngineCore" 2>/dev/null; }
trap cleanup EXIT
cd /tmp

serve(){ local dev="$1" model="$2" name="$3" port="$4" extra="${5:-}"
  echo "[serve] $name on GPU$dev :$port ..."
  CUDA_VISIBLE_DEVICES="$dev" HF_HUB_OFFLINE=1 "$VLLM" serve "$model" \
    --served-model-name "$name" --port "$port" --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.85 --max-model-len 8192 --limit-mm-per-prompt '{"image":1}' \
    $extra --enforce-eager --disable-custom-all-reduce --trust-remote-code \
    > "$LOG/sr_serve_${name}.log" 2>&1 &
  PIDS+=($!); }
wait_ready(){ for _ in $(seq 1 180); do curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "$2" && { echo "[ready] $2"; return 0; }; sleep 4; done; echo "[FAIL] $2"; tail -25 "$LOG/sr_serve_${2}.log"; return 1; }

run_sr(){ # conds outfile examiner-args...
  local conds="$1" out="$2"; shift 2
  echo "[sr] conds=[$conds] iters=$SR_ITERS seeds=[$SR_SEEDS] -> $(basename "$out")"
  "$PY" "$REPO/scripts/part3_self_refine.py" --conditions $conds --seeds $SR_SEEDS \
    --n-iters "$SR_ITERS" --max-tasks "$SR_MAXTASKS" --q "$SR_Q" --weak-seed --tasks "$TASKS" \
    --out "$out" --summary "${out%.jsonl}_summary.json" "$@" >> "$LOG/sr_run.log" 2>&1; }

: > "$LOG/sr_run.log"

# ----- Phase A : 8B + ft-8B -----
serve "0,1" "$M_8B" qwen3vl-8b 8108
serve "2,3" "$M_FT" ft-8b 8101
wait_ready 8108 qwen3vl-8b || exit 1
wait_ready 8101 ft-8b      || exit 1
run_sr "linter zero_shot_8b finetuned_8b hybrid" "$REPO/runs/probe/part3/self_refine_A.jsonl" \
  --api-examiner-base-url http://127.0.0.1:8108/v1 --api-examiner-model qwen3vl-8b \
  --ft-examiner-base-url  http://127.0.0.1:8101/v1 --ft-examiner-model  ft-8b
cleanup; PIDS=(); sleep 5

# ----- Phase B : 30B-A3B -----
serve "0,1" "$M_30B" qwen3vl-30b 8130 "--kv-cache-dtype fp8"
wait_ready 8130 qwen3vl-30b || exit 1
run_sr "zero_shot_30b" "$REPO/runs/probe/part3/self_refine_B.jsonl" \
  --api-examiner-base-url http://127.0.0.1:8130/v1 --api-examiner-model qwen3vl-30b
cleanup; PIDS=()

# ----- merge + aggregate -----
cat "$REPO/runs/probe/part3/self_refine_A.jsonl" "$REPO/runs/probe/part3/self_refine_B.jsonl" > "$REPO/runs/probe/part3/self_refine.jsonl"
"$PY" "$REPO/scripts/part3_self_refine.py" --from-jsonl "$REPO/runs/probe/part3/self_refine.jsonl" \
  --summary "$REPO/runs/probe/part3/self_refine_summary.json" >> "$LOG/sr_run.log" 2>&1
echo "[done] self_refine.jsonl ($(wc -l < "$REPO/runs/probe/part3/self_refine.jsonl") records)"
