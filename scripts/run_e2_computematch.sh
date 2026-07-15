#!/usr/bin/env bash
# W2 2.2 — compute-matched C0 ablation sweep (E2).
#
# Runs the four elicitation conditions {C0, C0_full, C3, C0_rep} on ONE online-API
# model over the G7 and/or G1 corpora, holding model + image + rendered corpus
# fixed. Product: data/part3/p1e2_<model>_<tag>_<cond>.json (+ _rows.jsonl).
# Every call goes through part3_elicit.py --resume so a daily-quota abort mid-sweep
# loses nothing — just re-run the identical command to continue.
#
#   C0        pointwise whole-taxonomy single call            (1 call/slide, baseline)
#   C0_full   + definitions (C3 binary questions) + forced evidence, still ONE call
#   C3        atomic per-type binary + forced evidence         (1 call/slide here)
#   C0_rep    K temperature-sampled C0 draws, union+majority  (K calls/slide — the
#             compute-matched control; run LAST as it is the token hog)
#
# Usage:
#   bash scripts/run_e2_computematch.sh <model> [tag ...]
#   bash scripts/run_e2_computematch.sh qwen3-vl-plus g7          # G7 only
#   bash scripts/run_e2_computematch.sh qwen3-vl-plus             # g7 then g1
#   CONDS="C0_rep" bash scripts/run_e2_computematch.sh qwen3-vl-plus g7
#   WORKERS=2 bash scripts/run_e2_computematch.sh gemini-2.5-flash g7
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:-${MODEL:-qwen3-vl-plus}}"
shift || true
TAGS=("$@"); [ ${#TAGS[@]} -eq 0 ] && TAGS=(g7 g1)

BASE_URL="${BASE_URL:-https://aigc.sankuai.com/v1/openai/native}"
WORKERS="${WORKERS:-3}"
REP_K="${REP_K:-10}"                 # deployed router's page-taxonomy atomic-question count (9 page types + G7)
REP_TEMP="${REP_TEMP:-0.7}"
MAX_TOKENS="${MAX_TOKENS:-768}"
STYLE=scoped
# Order matters: cheap single-call conditions first, C0_rep (K× tokens) last so a
# quota death still leaves the compute-match's counterparts complete.
CONDS="${CONDS:-C0 C0_full C3 C0_rep}"

# .env carries OPENAI_API_KEY + PART3_CHAT_KWARGS (thinking-off). export-all so the
# python client and elicit_common both see them.
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export PART3_CHAT_KWARGS="${PART3_CHAT_KWARGS:-{\"enable_thinking\":false}}"

manifest_for() { case "$1" in
  g7)      echo data/part3/manifest_g7_rendered.jsonl ;;
  g1|geo)  echo data/part2/manifest_eval_test_rendered.jsonl ;;
  *) echo "unknown tag: $1" >&2; exit 2 ;; esac; }
defect_for()   { case "$1" in
  g7)      echo G7_RENDER_CONTAINMENT_OVERFLOW ;;
  g1|geo)  echo G1_TEXT_OVERFLOW ;; esac; }
mpd_for()      { case "$1" in g7) echo 90 ;; g1|geo) echo 40 ;; esac; }

for tag in "${TAGS[@]}"; do
  manifest=$(manifest_for "$tag"); defect=$(defect_for "$tag"); mpd=$(mpd_for "$tag")
  for cond in $CONDS; do
    out="data/part3/p1e2_${MODEL}_${tag}_${cond}.json"
    echo "=== [$MODEL] tag=$tag cond=$cond mpd=$mpd -> $out ==="
    extra=()
    [ "$cond" = "C0_rep" ] && extra=(--rep-k "$REP_K" --rep-temp "$REP_TEMP")
    # ${extra[@]+...} guard: macOS bash 3.2 + `set -u` errors on an empty array expansion.
    python scripts/part3_elicit.py --condition "$cond" \
      --manifest "$manifest" --base-url "$BASE_URL" --model "$MODEL" \
      --style "$STYLE" --defects "$defect" --modalities A \
      --max-per-defect "$mpd" --max-tokens "$MAX_TOKENS" \
      --workers "$WORKERS" --freeform-only \
      --out "$out" --dump-rows "${out%.json}_rows.jsonl" --resume ${extra[@]+"${extra[@]}"}
  done
done
echo "[run_e2] done: $MODEL tags=${TAGS[*]} conds=$CONDS"
