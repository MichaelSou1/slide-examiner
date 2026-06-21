#!/usr/bin/env bash
# Part 3 Hermes case-study: serve the examiner gradient (8B/ft/30B) and run the
# 5-condition detection probe on the REAL rendered deck. Mirrors the 2-phase serving
# of part3_self_refine_sweep.sh. One deck (16 slides) -> fast once served.
set -u
REPO=/home/gpus/slide-examiner
VLLM=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
PY=/home/gpus/anaconda3/bin/python
LOG=$REPO/runs/part3/sweep
mkdir -p "$LOG" "$REPO/runs/probe/part3"
M_8B=/home/gpus/models/Qwen3-VL-8B-Instruct
M_30B=/home/gpus/models/Qwen3-VL-30B-A3B-Instruct-AWQ
M_FT=$REPO/runs/part2/examiner_merged

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
    > "$LOG/hc_serve_${name}.log" 2>&1 &
  PIDS+=($!); }
wait_ready(){ for _ in $(seq 1 180); do curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "$2" && { echo "[ready] $2"; return 0; }; sleep 4; done; echo "[FAIL] $2"; tail -25 "$LOG/hc_serve_${2}.log"; return 1; }

: > "$LOG/hc_run.log"

# ---- Phase A: 8B + ft ----
serve "0,1" "$M_8B" qwen3vl-8b 8108
serve "2,3" "$M_FT" ft-8b 8101
wait_ready 8108 qwen3vl-8b || exit 1
wait_ready 8101 ft-8b      || exit 1
"$PY" "$REPO/scripts/part3_hermes_case.py" \
  --conditions linter zero_shot_8b finetuned_8b hybrid \
  --api-examiner-base-url http://127.0.0.1:8108/v1 --api-examiner-model qwen3vl-8b \
  --ft-examiner-base-url  http://127.0.0.1:8101/v1 --ft-examiner-model  ft-8b \
  --out "$REPO/runs/probe/part3/hermes_case_A.json" >> "$LOG/hc_run.log" 2>&1
cleanup; PIDS=(); sleep 5

# ---- Phase B: 30B ----
serve "0,1" "$M_30B" qwen3vl-30b 8130 "--kv-cache-dtype fp8"
wait_ready 8130 qwen3vl-30b || exit 1
"$PY" "$REPO/scripts/part3_hermes_case.py" \
  --conditions zero_shot_30b \
  --api-examiner-base-url http://127.0.0.1:8130/v1 --api-examiner-model qwen3vl-30b \
  --out "$REPO/runs/probe/part3/hermes_case_B.json" >> "$LOG/hc_run.log" 2>&1
cleanup; PIDS=()

# ---- merge A + B ----
"$PY" - <<'PY' >> "$LOG/hc_run.log" 2>&1
import json
from pathlib import Path
R=Path("/home/gpus/slide-examiner/runs/probe/part3")
a=json.loads((R/"hermes_case_A.json").read_text())
b=json.loads((R/"hermes_case_B.json").read_text())
a["conditions"].update(b["conditions"])
(R/"hermes_case.json").write_text(json.dumps(a,indent=2,ensure_ascii=False))
print("[merge] conditions:", list(a["conditions"]))
PY
echo "[done] hermes_case.json" | tee -a "$LOG/hc_run.log"
tail -30 "$LOG/hc_run.log"
