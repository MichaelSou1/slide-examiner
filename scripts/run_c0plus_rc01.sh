#!/bin/bash
# RC-01 / DA-1 control — the C0+ experiment.
# C0+ = the C0 whole-taxonomy single pointwise call, but with G7 ADDED to the
# candidate catalog (and CHECK_SCOPE list). Same overloaded format as C0; the
# only change is that the off-taxonomy render class G7 is now *named* among the
# candidates. Separates the two readings of the C0->C3 G7 recovery:
#   * prompt-coverage artifact -> C0+ recovers G7 (effect is "C0 never asked").
#   * format suppression        -> C0+ still floors G7, only atomic C3 recovers.
#
# Runs ONLY the condition+models needed: C0plus x g7 on the four CAPABLE models,
# prefix p1e1 so it sits next to the existing p1e1_*_g7_{C0,C3}.json the §5.1
# quartet / decomposition already use. Self-contained serve+run+teardown per
# model (part3_p1_roster.py); launch as ONE background command (no trailing &).
#
# Usage:  bash scripts/run_c0plus_rc01.sh
set -u
cd /home/gpus/slide-examiner
ORCH=/home/gpus/anaconda3/bin/python
VLLM_QWEN=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
VLLM_LATEST=/home/gpus/anaconda3/envs/vllm-latest/bin/vllm
MPD_LIGHT="${MPD_LIGHT:-60}"   # matches existing p1e1 qwen35-9b n_pos=60
MPD_HEAVY="${MPD_HEAVY:-90}"   # matches existing p1e1 27B/31B n_pos=89/90

run_roster() {  # $1=models  $2=mpd  $3=vllm
  $ORCH scripts/part3_p1_roster.py --models $1 \
    --conds C0plus --tags g7 --mpd "$2" \
    --gpus 0,1 --port 8101 --vllm "$3" \
    --freeform-only --out-prefix p1e1
}

echo "[c0plus] GPU used/card: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | paste -sd' ')"
echo "[c0plus] === light tier: qwen35-9b (mpd $MPD_LIGHT, vllm-qwen) ==="
run_roster "qwen35-9b" "$MPD_LIGHT" "$VLLM_QWEN"
echo "[c0plus] === heavy qwen: qwen36-27b qwen35-27b (mpd $MPD_HEAVY, vllm-qwen) ==="
run_roster "qwen36-27b qwen35-27b" "$MPD_HEAVY" "$VLLM_QWEN"
echo "[c0plus] === gemma4-31b (mpd $MPD_HEAVY, vllm-latest) ==="
run_roster "gemma4-31b" "$MPD_HEAVY" "$VLLM_LATEST"

echo "[c0plus] DONE. result files:"
ls -1 data/part3/p1e1_*_g7_C0plus.json 2>/dev/null
