#!/bin/bash
# E1 (todo_0623) — gating 2-AFC confound decomposition sweep + analysis.
# Run ONLY when the box has room. vLLM's strict startup pre-check means a serve
# that doesn't fit simply REFUSES to start (it cannot OOM a co-resident job), so
# sharing at a low --gpu-util is safe; failed serves are logged and skipped.
#
# Conditions (all on the SAME freeform items, --out-prefix p1e1 so it does NOT
# clobber the unfiltered Result-1 p1_* files):
#   C0  pointwise | C0_named named atomic y/n (naming) | AFC 2-AFC def-vs-clean (pairing)
#   AFC_clean clean-vs-clean (guess-floor) | C3 atomic-binary+evidence (G7 contrast)
#
# Tiers (G7 gets mpd=90 = all pairs on the STRONG models for extra McNemar power;
# freeform geo is naturally <=54/18 so its mpd is irrelevant):
#   light  qwen35-9b internvl-8b ovis-9b            mpd 60  (8B/9B, fit while sharing)
#   heavy  qwen36-27b qwen35-27b (vllm-qwen)        mpd 90
#          gemma4-31b (vllm-latest, NO fp8 KV)      mpd 90
#
# Usage:
#   LIGHT=1 GUTIL=0.5 bash scripts/run_e1_sweep.sh   # 8B/9B only (sharing)
#   HEAVY=1 GUTIL=0.6 bash scripts/run_e1_sweep.sh   # 27B/31B only (more room needed)
#   bash scripts/run_e1_sweep.sh                      # everything, per-model default util
#   ANALYZE_ONLY=1 bash scripts/run_e1_sweep.sh       # just rebuild decomp+multiplicity+fig
set -u
cd /home/gpus/slide-examiner
ORCH=/home/gpus/anaconda3/bin/python
HARNESS=/home/gpus/anaconda3/envs/slide-examiner/bin/python
VLLM_QWEN=/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm
VLLM_LATEST=/home/gpus/anaconda3/envs/vllm-latest/bin/vllm
CONDS="C0 C0_named AFC AFC_clean C3"
MPD_LIGHT="${MPD_LIGHT:-60}"
MPD_HEAVY="${MPD_HEAVY:-90}"      # G7 power boost on the strong models (all 90 pairs)
GUTIL="${GUTIL:-}"; UTIL_ARG=""; [ -n "$GUTIL" ] && UTIL_ARG="--gpu-util $GUTIL"
LIGHT_MODELS="qwen35-9b internvl-8b ovis-9b"
HEAVY_QWEN="qwen36-27b qwen35-27b"
DO_LIGHT=1; DO_HEAVY=1
[ "${LIGHT:-0}" = "1" ] && DO_HEAVY=0
[ "${HEAVY:-0}" = "1" ] && DO_LIGHT=0

run_roster() {  # $1=models  $2=mpd  $3=vllm
  $ORCH scripts/part3_p1_roster.py --models $1 \
    --conds $CONDS --tags geo g7 --mpd "$2" \
    --gpus 0,1 --port 8101 --vllm "$3" $UTIL_ARG \
    --freeform-only --out-prefix p1e1
}

if [ "${ANALYZE_ONLY:-0}" != "1" ]; then
  echo "[e1] GPU used/card: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | paste -sd' ')"
  [ "$DO_LIGHT" = "1" ] && { echo "[e1] === light tier (mpd $MPD_LIGHT, util ${GUTIL:-default}) ==="; run_roster "$LIGHT_MODELS" "$MPD_LIGHT" "$VLLM_QWEN"; }
  [ "$DO_HEAVY" = "1" ] && { echo "[e1] === heavy qwen (mpd $MPD_HEAVY) ==="; run_roster "$HEAVY_QWEN" "$MPD_HEAVY" "$VLLM_QWEN"; }
  [ "$DO_HEAVY" = "1" ] && { echo "[e1] === gemma4-31b vllm-latest (mpd $MPD_HEAVY) ==="; run_roster "gemma4-31b" "$MPD_HEAVY" "$VLLM_LATEST"; }
fi

# --- analysis: decomposition + figure + refresh multiplicity -----------------
echo "[e1] === decomposition + figure (whatever p1e1_* exists so far) ==="
$HARNESS scripts/part3_e1_decomp.py --prefix p1e1 \
  --md reports/_e1_decomp.md --json data/part3/p1_decomp_summary.json \
  --fig paper/figs/fig7_elicitation_decomp.png
echo "[e1] === refresh multiplicity ==="
$HARNESS scripts/part3_multiplicity.py \
  --md reports/part3_multiplicity.md --json data/part3/p3_multiplicity.json

echo "[e1] DONE. Next (gate-contingent): read reports/_e1_decomp.md, then integrate per"
echo "[e1]   specs/e1_paper_integration_staging.md (§5.1 + Fig 2 caption + Limitations)."
