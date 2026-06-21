#!/usr/bin/env bash
# Part 3 Protocol-1 elicitation sweep (A.4): C0/C1/C2/C3 x {G1,S6,G7} x {zs-8b, ft-8b, zs-30b}.
# Self-contained serve+wait+run+teardown in ONE process (the harness reaps bg procs
# between tool calls; see memory vllm-serving-gotchas / part3-impl-and-serving).
# Launch as a single background command:  bash scripts/part3_p1_sweep.sh   (no trailing &, no leading pkill)
#
# Env knobs:  MODELS="zs8b ft8b zs30b"   MPD=60   (max per defect)
set -u
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/envs/slide-examiner/bin/python   # has openai + playwright + project deps
OUT=$REPO/data/part3
LOG=$REPO/runs/part3/p1
mkdir -p "$LOG" "$OUT"

MPD="${MPD:-60}"
MODELS="${MODELS:-zs8b ft8b zs30b}"
PORT="${PORT:-8101}"; PORT30="${PORT30:-8130}"
M_8B=/home/gpus/models/Qwen3-VL-8B-Instruct
M_30B=/home/gpus/models/Qwen3-VL-30B-A3B-Instruct-AWQ
M_FT=$REPO/runs/part2/examiner_merged_v2          # A.7: v2 is the publishable ft adapter
M_GEO=$REPO/data/part2/manifest_eval_test_rendered.jsonl
M_G7=$REPO/data/part3/manifest_g7_rendered.jsonl
GEO_DEFECTS="G1_TEXT_OVERFLOW S6_IMAGE_TEXT_CONTRADICTION"
G7_DEFECT="G7_RENDER_CONTAINMENT_OVERFLOW"

PIDS=()
cleanup(){ for p in "${PIDS[@]:-}"; do kill -9 "$p" 2>/dev/null; done; pkill -9 -f "VLLM::EngineCore" 2>/dev/null; sleep 3; }
trap cleanup EXIT
cd /tmp   # avoid torch-inductor reading ./specs

serve(){ # model name port extra...
  local model="$1" name="$2" port="$3"; shift 3
  echo "[serve] $name :$port ..."
  CUDA_VISIBLE_DEVICES=0,1 HF_HUB_OFFLINE=1 "$VLLM" serve "$model" \
    --served-model-name "$name" --port "$port" --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.85 --max-model-len 8192 --limit-mm-per-prompt '{"image":6}' \
    --enforce-eager --disable-custom-all-reduce --trust-remote-code "$@" \
    > "$LOG/serve_${name}.log" 2>&1 &
  PIDS+=($!)
}
wait_ready(){ # port name
  for _ in $(seq 1 300); do
    curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "$2" && { echo "[ready] $2"; return 0; }
    sleep 4
  done; echo "[FAIL] $2 not ready"; tail -40 "$LOG/serve_${2}.log"; return 1; }

elicit(){ # name style base manifest defects tag
  local name="$1" style="$2" base="$3" manifest="$4" defects="$5" tag="$6"
  for cond in ${CONDS:-C0 C1 C2 C3}; do
    echo "[elicit] $name $tag $cond (mpd=$MPD)"
    # Run the harness from $REPO (NOT /tmp) so relative manifest image paths resolve.
    ( cd "$REPO" && "$PY" "$REPO/scripts/part3_elicit.py" --condition "$cond" --manifest "$manifest" \
        --base-url "$base" --model "$name" --style "$style" --defects $defects \
        --modalities A --max-per-defect "$MPD" --workers 12 \
        --out "$OUT/p1_${name}_${tag}_${cond}.json" \
        --dump-rows "$OUT/p1_${name}_${tag}_${cond}_rows.jsonl" ) \
      >> "$LOG/elicit_${name}.log" 2>&1 || echo "  [warn] $name $tag $cond returned nonzero"
  done
}

run_model(){ # key
  case "$1" in
    zs8b)  serve "$M_8B"  zs-8b  "$PORT";   wait_ready "$PORT"   zs-8b  || return 1
           local B="http://127.0.0.1:$PORT/v1"
           elicit zs-8b  scoped  "$B" "$M_GEO" "$GEO_DEFECTS" geo
           elicit zs-8b  scoped  "$B" "$M_G7"  "$G7_DEFECT"   g7 ;;
    ft8b)  serve "$M_FT"  ft-8b  "$PORT";   wait_ready "$PORT"   ft-8b  || return 1
           local B="http://127.0.0.1:$PORT/v1"
           elicit ft-8b  trained "$B" "$M_GEO" "$GEO_DEFECTS" geo
           elicit ft-8b  trained "$B" "$M_G7"  "$G7_DEFECT"   g7 ;;
    zs30b) serve "$M_30B" zs-30b "$PORT30" --kv-cache-dtype fp8; wait_ready "$PORT30" zs-30b || return 1
           local B="http://127.0.0.1:$PORT30/v1"
           elicit zs-30b scoped  "$B" "$M_GEO" "$GEO_DEFECTS" geo
           elicit zs-30b scoped  "$B" "$M_G7"  "$G7_DEFECT"   g7 ;;
    *) echo "unknown model $1"; return 1 ;;
  esac
  cleanup; PIDS=(); sleep 5
}

echo "=== Part3 P1 sweep: models=[$MODELS] mpd=$MPD ==="
for m in $MODELS; do run_model "$m" || { echo "[ABORT] $m"; exit 1; }; done
echo "[ALL DONE] result files:"; ls -1 "$OUT"/p1_*_*.json 2>/dev/null
