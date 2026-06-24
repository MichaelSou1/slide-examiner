#!/usr/bin/env bash
# E8 injection-validity re-examination — focused decisive re-run.
#
# Runs the SAME elicitation protocol (C0 pointwise / C3 atomic / AFC 2-AFC) on the
# REALISTIC defect variants vs the ORIGINAL (ill-posed) injections, to test whether
# the paper's "at chance" results are real perceptual/model limits or injection
# artifacts:
#   G3  relative-misalignment (bullet out of an aligned column)  vs  absolute translation
#   G5  chromatic / hue swap                                     vs  achromatic lightness
#   S6  valid figure-text contradiction (figure present)        (degenerate set has no twin path here)
#
# Endpoint-agnostic: point it at a local vLLM OR a cloud OpenAI-compatible API
# (e.g. Aliyun Bailian / DashScope). Images are sent as base64 data-URIs, so the
# cloud sees them. NO GPU needed for the cloud path.
#
# Usage (cloud / Bailian):
#   export OPENAI_API_KEY=sk-xxxx            # your DashScope / Bailian key
#   BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
#   MODEL=qwen-vl-max \
#   bash scripts/part3_e8_revalidate.sh
#
# Usage (local vLLM, when GPU frees):
#   BASE_URL=http://127.0.0.1:8101/v1 MODEL=qwen35-27b bash scripts/part3_e8_revalidate.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env: the DashScope (Aliyun Bailian) config lives in PART3_GEN_* (the general
# OPENAI_* points at a separate MiMo gateway that has no Qwen-VL).
set -a; [ -f .env ] && source .env; set +a

PY=/home/gpus/anaconda3/envs/slide-examiner/bin/python
BASE_URL="${BASE_URL:-${PART3_GEN_BASE_URL:?need PART3_GEN_BASE_URL in .env}}"   # dashscope compatible-mode
MODEL="${MODEL:-qwen-vl-max}"                                                     # strong non-thinking VL on dashscope
export OPENAI_API_KEY="${OPENAI_API_KEY_OVERRIDE:-${PART3_GEN_API_KEY:?need PART3_GEN_API_KEY in .env}}"
CONDS="${CONDS:-C0 C3 AFC}"          # the at-chance-vs-recovery protocol
MPD="${MPD:-60}"                      # max per defect
WORKERS="${WORKERS:-6}"               # cloud rate-limit friendly
OUT=data/part3/e8_reval
mkdir -p "$OUT"
# cloud Qwen-VL: do NOT pass enable_thinking chat-template kwargs (local-only)
unset PART3_CHAT_KWARGS || true

P2=data/part2/manifest_eval_test_rendered.jsonl
# contrast | manifest | defect | freeform_only(0/1)
CONTRASTS=(
  "g3_rel|data/part3/g3_relmisalign.jsonl|G3_ALIGNMENT_OFFSET|0"
  "g3_abs|$P2|G3_ALIGNMENT_OFFSET|1"
  "g5_chroma|data/part3/g5_chromatic.jsonl|G5_BRAND_COLOR_VIOLATION|0"
  "g5_achroma|$P2|G5_BRAND_COLOR_VIOLATION|1"
  "s6_valid|data/part1_img/manifest_s6_rendered.jsonl|S6_IMAGE_TEXT_CONTRADICTION|0"
)

echo "[e8-reval] model=$MODEL base=$BASE_URL conds='$CONDS' mpd=$MPD"
for row in "${CONTRASTS[@]}"; do
  IFS='|' read -r tag manifest defect ff <<<"$row"
  ffflag=""; [ "$ff" = "1" ] && ffflag="--freeform-only"
  for cond in $CONDS; do
    out="$OUT/${tag}_${cond}.json"
    echo "  -> $tag $cond"
    OPENAI_API_KEY="$OPENAI_API_KEY" "$PY" scripts/part3_elicit.py \
      --condition "$cond" --manifest "$manifest" --base-url "$BASE_URL" --model "$MODEL" \
      --style scoped --defects "$defect" --modalities A --max-per-defect "$MPD" \
      --max-tokens 512 --workers "$WORKERS" \
      --out "$out" --dump-rows "$OUT/${tag}_${cond}_rows.jsonl" || echo "  [warn] $tag $cond failed"
  done
done

echo "[e8-reval] merging ..."
"$PY" scripts/part3_e8_revalidate_merge.py --in-dir "$OUT" --model "$MODEL"
echo "[e8-reval] done -> $OUT/comparison.md"
