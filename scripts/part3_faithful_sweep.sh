#!/usr/bin/env bash
# Part 3 FAITHFUL sweep — examiner-quality gradient with the ACTUAL models measured
# in Parts 1/2 (Qwen3-VL-8B / 30B-A3B / finetuned-8B), so the H3 x-axis (intrinsic
# quality) matches the examiner actually used. The generator + FROZEN reflection
# LLM run on the online API (mimo-v2.5-pro, thinking disabled) — this frees all 4
# GPUs for the examiners and keeps the generator identical across every condition.
#
# Two serve phases (4x20GB box can hold two ~8B TP=2 models, not three):
#   Phase A: Qwen3-VL-8B (GPU0,1 :8108) + ft-8B (GPU2,3 :8101) together
#            -> runs linter, zero_shot_8b, finetuned_8b, hybrid  (page + deck)
#   Phase B: Qwen3-VL-30B-A3B-AWQ (GPU0,1 :8130, fp8 KV)
#            -> runs zero_shot_30b                                (page + deck)
# Everything in ONE process (the harness reaps background procs between tool calls).
set -u
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/bin/python      # base env: gepa + skillopt + openai + sklearn-fixed
LOG=$REPO/runs/part3/sweep
mkdir -p "$LOG" "$REPO/runs/probe/part3"
# Start every sweep from a clean optimizer state — GEPA/SkillOpt persist + RESUME
# from out-root, so a stale dir would cache prior (e.g. buggy) eval scores.
rm -rf "$REPO/runs/part3/sweep_runs"
: > "$LOG/run.log"

M_8B=/home/gpus/models/Qwen3-VL-8B-Instruct
M_30B=/home/gpus/models/Qwen3-VL-30B-A3B-Instruct-AWQ
M_FT=$REPO/runs/part2/examiner_merged

CARRIER="${CARRIER:-gepa}"          # gepa | skillopt (optimizer-agnostic second carrier)
RUN_PAGE="${RUN_PAGE:-1}"            # set 0 to skip the page pilot (reuse existing)
PAGE_BUDGET="${PAGE_BUDGET:-8}"
DECK_BUDGET="${DECK_BUDGET:-12}"
PAGE_SEEDS="${PAGE_SEEDS:-0 1}"
DECK_SEEDS="${DECK_SEEDS:-0 1 2}"
# tasks_opt = small train(6)/val(4) for bounded GEPA valset evals over the slow API
# (test stays the full frozen 10; final eval/hacking use the frozen test set).
TASKS="${TASKS:-$REPO/data/part3/tasks_opt}"
PILOT_TASKS="${PILOT_TASKS:-$REPO/data/part3/tasks_pilot}"

PIDS=()
cleanup(){ for p in "${PIDS[@]:-}"; do kill -9 "$p" 2>/dev/null; done; pkill -9 -f "VLLM::EngineCore" 2>/dev/null; }
trap cleanup EXIT
cd /tmp   # avoid torch-inductor reading ./specs (memory: vllm-serving-gotchas)

serve(){  # devices model name port extra...
  local dev="$1" model="$2" name="$3" port="$4"; shift 4
  echo "[serve] $name on GPU$dev :$port ..."
  CUDA_VISIBLE_DEVICES="$dev" HF_HUB_OFFLINE=1 "$VLLM" serve "$model" \
    --served-model-name "$name" --port "$port" --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.85 --max-model-len 8192 --limit-mm-per-prompt '{"image":1}' \
    --enforce-eager --disable-custom-all-reduce --trust-remote-code \
    > "$LOG/serve_${name}.log" 2>&1 &
  PIDS+=($!)
}
wait_ready(){ # port name
  for _ in $(seq 1 180); do
    curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "$2" && { echo "[ready] $2"; return 0; }
    sleep 4
  done; echo "[FAIL] $2 not ready"; tail -30 "$LOG/serve_${2}.log"; return 1; }

run_cell(){ # level conditions outfile budget seeds tasks examiner-args...
  local level="$1" conds="$2" out="$3" budget="$4" seeds="$5" tasks="$6"; shift 6
  # Convergence threshold: deck (8-12 slides) can reach the full deck-quality bar
  # (0.8); a page (2 slides) structurally cannot cover a 4-6 section rubric, so the
  # page PILOT uses a lower, reachable bar (0.55) purely to estimate cross-seed
  # variance for budget gating — the deck-level MAIN is the reported H3 result.
  # deck q=0.82: weak-seed mean common-quality ~0.79 < 0.82 < DEFAULT-skill ~0.844,
  # so the best-candidate-mean DV requires real optimization (not a freebie). page=0.55.
  local q=0.82; [ "$level" = page ] && q=0.55
  echo "[run] level=$level q=$q conds=[$conds] budget=$budget seeds=[$seeds] -> $(basename "$out")"
  # gen-max-tokens 2048 at BOTH levels: the generator emits a FULL deck JSON
  # (max_slides only truncates afterward), so the page default of 700 truncates
  # the JSON -> unparseable -> degenerate. 2048 fits the full deck either way.
  # out-root is LEVEL-separated: GEPA persists+resumes state per (out-root,cond,seed),
  # so page and deck of the same cell must NOT share a dir or deck resumes page state.
  "$PY" "$REPO/scripts/part3_run.py" --carriers "$CARRIER" --conditions $conds --seeds $seeds \
    --budget "$budget" --level "$level" --q "$q" --gen-max-tokens 2048 --no-render --weak-seed --tasks-dir "$tasks" \
    --out "$out" --best-dir "$REPO/runs/part3/best_skill_$(basename "$out" .jsonl)" \
    --out-root "$REPO/runs/part3/sweep_runs/${CARRIER}_${level}" "$@" >> "$LOG/run.log" 2>&1
}

# ----- Phase A : 8B + ft-8B -----
serve "0,1" "$M_8B" qwen3vl-8b 8108
serve "2,3" "$M_FT" ft-8b 8101
wait_ready 8108 qwen3vl-8b || exit 1
wait_ready 8101 ft-8b      || exit 1
EX_A=(--api-examiner-base-url http://127.0.0.1:8108/v1 --api-examiner-model qwen3vl-8b \
      --ft-examiner-base-url  http://127.0.0.1:8101/v1 --ft-examiner-model  ft-8b)
CONDS_A="linter zero_shot_8b finetuned_8b hybrid"
run_cell page "$CONDS_A" "$REPO/runs/probe/part3/page_A.jsonl" "$PAGE_BUDGET" "$PAGE_SEEDS" "$PILOT_TASKS" "${EX_A[@]}"
run_cell deck "$CONDS_A" "$REPO/runs/probe/part3/deck_A.jsonl" "$DECK_BUDGET" "$DECK_SEEDS" "$TASKS"       "${EX_A[@]}"
cleanup; PIDS=(); sleep 5

# ----- Phase B : 30B-A3B -----
CUDA_VISIBLE_DEVICES="0,1" HF_HUB_OFFLINE=1 "$VLLM" serve "$M_30B" \
  --served-model-name qwen3vl-30b --port 8130 --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.90 --max-model-len 8192 --limit-mm-per-prompt '{"image":1}' \
  --kv-cache-dtype fp8 --enforce-eager --disable-custom-all-reduce --trust-remote-code \
  > "$LOG/serve_qwen3vl-30b.log" 2>&1 &
PIDS+=($!)
wait_ready 8130 qwen3vl-30b || exit 1
EX_B=(--api-examiner-base-url http://127.0.0.1:8130/v1 --api-examiner-model qwen3vl-30b)
run_cell page "zero_shot_30b" "$REPO/runs/probe/part3/page_B.jsonl" "$PAGE_BUDGET" "$PAGE_SEEDS" "$PILOT_TASKS" "${EX_B[@]}"
run_cell deck "zero_shot_30b" "$REPO/runs/probe/part3/deck_B.jsonl" "$DECK_BUDGET" "$DECK_SEEDS" "$TASKS"       "${EX_B[@]}"
cleanup; PIDS=()

# ----- merge -----
cat "$REPO/runs/probe/part3/page_A.jsonl" "$REPO/runs/probe/part3/page_B.jsonl" > "$REPO/runs/probe/part3/pilot_main.jsonl"
cat "$REPO/runs/probe/part3/deck_A.jsonl" "$REPO/runs/probe/part3/deck_B.jsonl" > "$REPO/runs/probe/part3/main.jsonl"
echo "[done] pilot_main.jsonl ($(wc -l < "$REPO/runs/probe/part3/pilot_main.jsonl") cells) + main.jsonl ($(wc -l < "$REPO/runs/probe/part3/main.jsonl") cells)"
