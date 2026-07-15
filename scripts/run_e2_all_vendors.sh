#!/usr/bin/env bash
# W2 2.2 — full compute-match sweep for the remaining two API vendors
# (Gemini + GPT), G7 + G1, four conditions each. Runs the two vendors in PARALLEL
# (429 quota is per-model, so their RPM budgets are independent), each with two
# passes of run_e2_computematch.sh (initial + resume top-up to fill 429/None
# failures), then regenerates the combined 3-vendor report + cost table.
#
# Fully resumable: if the daily quota walls a vendor mid-sweep, just re-run this
# script — every part3_elicit call is --resume, so finished probes are skipped.
#
# Vendor knobs (from the 2.-1(c) smoke + a 2.2 recheck): workers=2 (conservative
# under the shared endpoint). Gemini ignores enable_thinking on the long structured
# C0/C0_full/C0_rep prompts and burns ~770 reasoning tokens/call (vs ~59 on the
# short C3 smoke), truncating to None content at 768-1024 -> give it max-tokens=2048
# so content survives (Gemini is the cheap vendor; the detection metric is unaffected
# by reasoning spend, which the usage log records separately). GPT is clean at 768.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

run_vendor() {
  local model=$1 workers=$2 maxtok=$3 log=$4
  echo "[$model] START $(pass_stamp)" >> "$log"
  for pass in 1 2; do
    echo "[$model] pass $pass" >> "$log"
    WORKERS="$workers" MAX_TOKENS="$maxtok" \
      bash scripts/run_e2_computematch.sh "$model" g7 g1 >> "$log" 2>&1 || true
  done
  echo "[$model] DONE" >> "$log"
}
pass_stamp() { date +%H:%M 2>/dev/null || echo "?"; }

run_vendor gemini-2.5-flash    2 2048 logs/e2_gemini.log &
GEM=$!
run_vendor gpt-5.1-nothinking  2 768  logs/e2_gpt.log &
GPT=$!
wait "$GEM" "$GPT"

echo "[all-vendors] both sweeps ended; regenerating combined report + cost table" >> logs/e2_allvendors.log
python scripts/part3_e2_computematch_report.py --prefix p1e2 \
  --md reports/_e2_computematch.md --json data/part3/p1e2_summary.json >> logs/e2_allvendors.log 2>&1 || true
python scripts/part3_cost_table.py --out reports/cost_table.md \
  --json data/part3/cost_table.json >> logs/e2_allvendors.log 2>&1 || true
echo "ALL_VENDORS_DONE" >> logs/e2_allvendors.log
