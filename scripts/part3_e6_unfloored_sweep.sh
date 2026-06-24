#!/usr/bin/env bash
# E6 (todo_0623) — UNFLOORED downstream point. Same self-refine gradient as
# part3_self_refine_sweep.sh, but the generator is a WEAK local VLM (Qwen3-VL-4B)
# instead of the strong API model, so first drafts are no longer floored and the
# examiner has real headroom to act on. Everything else (tasks/seeds/iters/weak
# seed skill/model-free DV) is held identical to the strong-gen baseline, so the
# generator is the only changed variable.
#
# Serving: gen-4B on GPU0 (TP=1, port 8204) + ONE examiner on GPU1,2 (TP=2, port
# 8101) per phase. 3 phases (linter rides free on any examiner phase). vllm-qwen
# (0.19) for all Qwen3-VL models, matching the baseline sweep.
set -u
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/bin/python
LOG=$REPO/runs/part3/e6
mkdir -p "$LOG" "$REPO/runs/probe/part3" "$REPO/data/part3"

M_GEN=/home/gpus/models/Qwen3-VL-4B-Instruct
M_8B=/home/gpus/models/Qwen3-VL-8B-Instruct
M_30B=/home/gpus/models/Qwen3-VL-30B-A3B-Instruct-AWQ
M_FT=$REPO/runs/part2/examiner_merged_v2

# Identical experimental config to the strong-gen baseline (only the gen changes).
SR_SEEDS="${SR_SEEDS:-0 1 2}"
SR_ITERS="${SR_ITERS:-3}"
SR_MAXTASKS="${SR_MAXTASKS:-3}"
SR_Q="${SR_Q:-0.85}"
TASKS="${TASKS:-$REPO/data/part3/tasks/test.jsonl}"
GEN_NAME=qwen3vl-4b
GEN_PORT=8204
GEN_BASE="http://127.0.0.1:${GEN_PORT}/v1"

PIDS=()
cleanup(){ for p in "${PIDS[@]:-}"; do kill -9 "$p" 2>/dev/null; done; pkill -9 -f "VLLM::EngineCore" 2>/dev/null; sleep 4; }
trap cleanup EXIT
cd /tmp

serve(){ local dev="$1" model="$2" name="$3" port="$4" tp="$5" extra="${6:-}"
  echo "[serve] $name on GPU$dev :$port (tp=$tp) ..."
  CUDA_VISIBLE_DEVICES="$dev" HF_HUB_OFFLINE=1 "$VLLM" serve "$model" \
    --served-model-name "$name" --port "$port" --tensor-parallel-size "$tp" \
    --gpu-memory-utilization 0.85 --max-model-len 8192 --limit-mm-per-prompt '{"image":1}' \
    $extra --enforce-eager --disable-custom-all-reduce --trust-remote-code \
    > "$LOG/serve_${name}.log" 2>&1 &
  PIDS+=($!); }
wait_ready(){ for _ in $(seq 1 200); do curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "$2" && { echo "[ready] $2"; return 0; }; sleep 4; done; echo "[FAIL] $2"; tail -30 "$LOG/serve_${2}.log"; return 1; }

# Generator role -> the local weak 4B (resolved at import by part3_self_refine).
export PART3_GEN_MODEL="$GEN_NAME"
export PART3_GEN_BASE_URL="$GEN_BASE"
export PART3_GEN_API_STYLE=chat
export PART3_GEN_API_KEY=EMPTY

run_sr(){ # conds outfile examiner-args...
  local conds="$1" out="$2"; shift 2
  echo "[sr] conds=[$conds] gen=$GEN_NAME(weak) iters=$SR_ITERS seeds=[$SR_SEEDS] -> $(basename "$out")"
  "$PY" "$REPO/scripts/part3_self_refine.py" --conditions $conds --seeds $SR_SEEDS \
    --n-iters "$SR_ITERS" --max-tasks "$SR_MAXTASKS" --q "$SR_Q" --weak-seed --tasks "$TASKS" \
    --gen-max-tokens 2048 \
    --out "$out" --summary "${out%.jsonl}_summary.json" "$@" >> "$LOG/run.log" 2>&1; }

: > "$LOG/run.log"

# ----- Phase A : gen-4B + 8B examiner (linter rides free) -----
serve "0"   "$M_GEN" "$GEN_NAME"  "$GEN_PORT" 1
serve "1,2" "$M_8B"  qwen3vl-8b   8101        2
wait_ready "$GEN_PORT" "$GEN_NAME" || exit 1
wait_ready 8101 qwen3vl-8b         || exit 1
run_sr "linter zero_shot_8b" "$REPO/runs/probe/part3/self_refine_wgA.jsonl" \
  --api-examiner-base-url http://127.0.0.1:8101/v1 --api-examiner-model qwen3vl-8b
cleanup; PIDS=()

# ----- Phase B : gen-4B + ft-8B examiner (finetuned_8b + hybrid) -----
serve "0"   "$M_GEN" "$GEN_NAME" "$GEN_PORT" 1
serve "1,2" "$M_FT"  ft-8b       8101        2
wait_ready "$GEN_PORT" "$GEN_NAME" || exit 1
wait_ready 8101 ft-8b             || exit 1
run_sr "finetuned_8b hybrid" "$REPO/runs/probe/part3/self_refine_wgB.jsonl" \
  --ft-examiner-base-url http://127.0.0.1:8101/v1 --ft-examiner-model ft-8b
cleanup; PIDS=()

# ----- Phase C : gen-4B + 30B-A3B examiner -----
serve "0"   "$M_GEN" "$GEN_NAME"  "$GEN_PORT" 1
serve "1,2" "$M_30B" qwen3vl-30b  8101        2 "--kv-cache-dtype fp8"
wait_ready "$GEN_PORT" "$GEN_NAME" || exit 1
wait_ready 8101 qwen3vl-30b        || exit 1
run_sr "zero_shot_30b" "$REPO/runs/probe/part3/self_refine_wgC.jsonl" \
  --api-examiner-base-url http://127.0.0.1:8101/v1 --api-examiner-model qwen3vl-30b
cleanup; PIDS=()

# ----- merge + aggregate (E6 summary) -----
cat "$REPO/runs/probe/part3/self_refine_wgA.jsonl" \
    "$REPO/runs/probe/part3/self_refine_wgB.jsonl" \
    "$REPO/runs/probe/part3/self_refine_wgC.jsonl" \
    > "$REPO/runs/probe/part3/self_refine_weakgen.jsonl"
"$PY" "$REPO/scripts/part3_self_refine.py" \
  --from-jsonl "$REPO/runs/probe/part3/self_refine_weakgen.jsonl" \
  --summary "$REPO/data/part3/e6_unfloored_synth.json" >> "$LOG/run.log" 2>&1
echo "[done] weakgen ($(wc -l < "$REPO/runs/probe/part3/self_refine_weakgen.jsonl") records) -> data/part3/e6_unfloored_synth.json"
