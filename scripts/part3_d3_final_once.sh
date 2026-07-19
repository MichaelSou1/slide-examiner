#!/usr/bin/env bash
# Frozen W7.7 final-test runner. This script intentionally refuses a second attempt.
set -Eeuo pipefail

REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
GUARD_REPO="${GUARD_REPO:-$REPO}"
CODE_ROOT="$GUARD_REPO"
PYTHON="${PYTHON:-python}"
BASE_MODEL="${BASE_MODEL:-/data/public_data/xzs_data/Qwen3-VL-8B-Instruct}"
CUDA_DEVICE="${CUDA_DEVICE:-0}"
REGISTRY="${1:-$GUARD_REPO/release/part3/d3/final_test_unlock.json}"
OUT="$REPO/runs/part3/w77/final_test"
REPORT="$REPO/reports/part3/w77/final_test"
LOG_DIR="$REPO/logs/part3/w77"
ATTEMPT="$REPORT/attempt.json"
LOG="$LOG_DIR/final_test_once.log"

cd "$REPO"

# The attempt marker is the one-shot boundary. A failed attempt is never silently resumed;
# any policy-permitted infrastructure retry must first be documented and explicitly unlocked.
if [[ -d "$REPORT" || -e "$LOG" || -d "$OUT" ]]; then
  echo "Refusing final_test: an attempt marker, log, or output directory already exists." >&2
  exit 64
fi

"$PYTHON" "$CODE_ROOT/scripts/part3_d3_evaluate.py" assert-unlocked \
  --repo "$GUARD_REPO" --freeze-registry "$REGISTRY"

mkdir -p "$OUT/raw" "$OUT/normalized" "$OUT/rendered_decks" "$REPORT/plots" "$LOG_DIR"
"$PYTHON" - "$ATTEMPT" "$REGISTRY" <<'PY'
import datetime, json, socket, sys
from pathlib import Path
path, registry = map(Path, sys.argv[1:])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({
    "schema_version": 1,
    "status": "started",
    "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "host": socket.gethostname(),
    "unlock_registry": str(registry),
    "attempt": 1,
}, indent=2) + "\n")
PY

exec > >(tee -a "$LOG") 2>&1
export CUDA_VISIBLE_DEVICES="$CUDA_DEVICE"
export PYTHONPATH="$CODE_ROOT${PYTHONPATH:+:$PYTHONPATH}"

finish_attempt() {
  local code="$?"
  trap - EXIT
  local finalize_code=0
  "$PYTHON" - "$ATTEMPT" "$code" "$REPORT/run_inventory.json" "$OUT" "$REPORT" "$LOG" <<'PY' || finalize_code=$?
import datetime, hashlib, json, sys
from pathlib import Path
path, code, target, out, report, log = (
    Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]),
    Path(sys.argv[6])
)
payload = json.loads(path.read_text())
payload.update({
    "status": "completed" if code == 0 else "failed",
    "exit_code": code,
    "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
})
path.write_text(json.dumps(payload, indent=2) + "\n")
files = sorted({p for root in (out, report) for p in root.rglob("*") if p.is_file()}
               | ({log} if log.is_file() else set()))
target.write_text(json.dumps({
    "schema_version": 1,
    "final_test_read": True,
    "attempt_status": payload["status"],
    "files": [{"path": str(p), "bytes": p.stat().st_size,
               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files
              if p != target],
}, indent=2) + "\n")
PY
  if [[ "$code" -eq 0 && "$finalize_code" -ne 0 ]]; then
    code="$finalize_code"
  fi
  exit "$code"
}
trap finish_attempt EXIT

EVAL=("$PYTHON" "$CODE_ROOT/scripts/part3_d3_evaluate.py")
INFER=("$PYTHON" -u "$CODE_ROOT/scripts/part3_d3_infer.py")
GUARD=(--repo "$REPO" --guard-repo "$GUARD_REPO" --freeze-registry "$REGISTRY")
COMMON=(--base "$BASE_MODEL" --max-image-pixels 262144 --max-new-tokens 384 --batch-size 1)
RUN="$REPO/runs/part3/d3_formal_v2/train_seed73"
POLICY="$CODE_ROOT/runs/part3/d3_selection/frozen_policy.json"

# Guarded materialization is the first operation that reads either frozen manifest.
"${EVAL[@]}" materialize "${GUARD[@]}" \
  --manifest "$CODE_ROOT/data/part3/d3/final_test_image.jsonl" \
  --output "$OUT/final_image_runtime.jsonl" --split final_test --per-class 30

"${EVAL[@]}" render-decks "${GUARD[@]}" \
  --manifest "$CODE_ROOT/data/part3/d3/final_test_deck.jsonl" \
  --output-dir "$OUT/rendered_decks" \
  --output-manifest "$OUT/final_deck_rendered.jsonl" \
  --long-edge 1024 --split final_test
"${EVAL[@]}" materialize-decks "${GUARD[@]}" \
  --manifest "$OUT/final_deck_rendered.jsonl" \
  --clean-manifest "$OUT/final_deck_rendered.jsonl" \
  --output "$OUT/final_deck_runtime.jsonl" --per-class 20 --split final_test

run_image_arm() {
  local arm="$1"; shift
  "${INFER[@]}" "${COMMON[@]}" --input "$OUT/final_image_runtime.jsonl" \
    --output "$OUT/raw/${arm}.jsonl" --limit 540 --prompt-mode generic "$@"
  "${EVAL[@]}" normalize "${GUARD[@]}" --input "$OUT/raw/${arm}.jsonl" \
    --output "$OUT/normalized/${arm}.jsonl" --arm "$arm" --split final_test
}

# Frozen primary arms: full D3, Part-2 vanilla, manual route, and no-escalation D3.
run_image_arm d3_generic_sample_escalation \
  --run "$RUN" --policy "$POLICY" --route-mode sample
run_image_arm part2_v2_generic \
  --lm-adapter "$REPO/runs/part2/examiner_lora_v2/adapter" --route-mode answer --max-escalations 0
run_image_arm manual_frozen_route \
  --run "$RUN" --policy "$POLICY" --route-mode class \
  --class-router "$CODE_ROOT/runs/part3/w76/manual_frozen_router.json"
run_image_arm learned_sample_route_no_escalation \
  --run "$RUN" --route-mode sample --confidence-threshold 0.0 --max-escalations 0

"${INFER[@]}" "${COMMON[@]}" --input "$OUT/final_deck_runtime.jsonl" \
  --output "$OUT/raw/d3_generic_deck_s2_s5.jsonl" --limit 80 --prompt-mode generic \
  --run "$RUN" --policy "$POLICY" --route-mode sample
"${EVAL[@]}" normalize "${GUARD[@]}" \
  --input "$OUT/raw/d3_generic_deck_s2_s5.jsonl" \
  --output "$OUT/normalized/d3_generic_deck_s2_s5.jsonl" \
  --arm d3_generic_deck_s2_s5 --split final_test

IMAGE_NORMALIZED=(
  "$OUT/normalized/d3_generic_sample_escalation.jsonl"
  "$OUT/normalized/part2_v2_generic.jsonl"
  "$OUT/normalized/manual_frozen_route.jsonl"
  "$OUT/normalized/learned_sample_route_no_escalation.jsonl"
)
"${EVAL[@]}" score --input "${IMAGE_NORMALIZED[@]}" \
  --output "$REPORT/image_scores.json"
"${EVAL[@]}" compare --input "${IMAGE_NORMALIZED[@]}" \
  --comparisons "$CODE_ROOT/reports/part3/w77_primary_comparisons.json" \
  --output "$REPORT/primary_comparisons.json"
"${EVAL[@]}" plot --scores "$REPORT/image_scores.json" --output-dir "$REPORT/plots"
"${EVAL[@]}" score --input "$OUT/normalized/d3_generic_deck_s2_s5.jsonl" \
  --output "$REPORT/deck_scores.json"
