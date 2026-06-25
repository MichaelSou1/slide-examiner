"""E8 GPU re-run — body-model phase (Rows 3 & 5).

Serve the paper's body model (qwen35-27b, AWQ-4bit local checkpoint) ONCE, then run
both internal-口径 evals against that single endpoint before teardown:

  Row 3 — Table-2 coverage: linter + VLM-C0 + VLM-C3 on internal G3/G5
           (data/part3/manifest_coverage_internal.jsonl)  -> p2_synth_internal_g3g5.json
  Row 5 — real-CC reproduction: internal-G3 on real Zenodo10k slides, modalities A/B/C
           (data/part3/manifest_real_internal_g3.jsonl)   -> pc_real_internal_g3_<model>.json

Reuses serve/wait/teardown from part3_p1_roster so the per-model vLLM flags stay
in one place. Launch as ONE background command:
    /home/gpus/anaconda3/bin/python scripts/part3_e8_bodyrun.py --gpus 0,1 --port 8101
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/gpus/slide-examiner")
sys.path.insert(0, str(REPO / "scripts"))
import part3_p1_roster as R  # noqa: E402

HARNESS_PY = "/home/gpus/anaconda3/envs/slide-examiner/bin/python"
OUT = REPO / "data/part3"
COVERAGE = OUT / "manifest_coverage_internal.jsonl"
REAL_G3 = OUT / "manifest_real_internal_g3.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen35-27b")
    ap.add_argument("--gpus", default="0,1")
    ap.add_argument("--port", type=int, default=8101)
    ap.add_argument("--vllm", default=R.VLLM)
    ap.add_argument("--mpd", type=int, default=120, help="Row-3 max-per-defect (G3/G5)")
    ap.add_argument("--no-stray-kill", action="store_true")
    ap.add_argument("--skip-row3", action="store_true")
    ap.add_argument("--skip-row5", action="store_true")
    args = ap.parse_args()

    # configure the shared roster module globals
    R.GPUS, R.PORT, R.VLLM = args.gpus, args.port, args.vllm
    R.KILL_STRAY = not args.no_stray_kill
    R.LOG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    m = R.BY_KEY[args.model]
    path = R.ensure_on_disk(m)
    if not path:
        R.log(f"no model on disk for {args.model}"); sys.exit(2)
    R.gpu_free_wait()
    proc = R.serve(m, path)
    if not R.wait_ready(args.model, proc):
        R.teardown(proc); R.log("serve failed"); sys.exit(3)

    base = f"http://127.0.0.1:{args.port}/v1"
    logf = R.LOG / f"e8_bodyrun_{args.model}.log"
    # qwen35-27b is a THINKING VLM -> p2_eval/pc_real (via part2_eval.call -> elicit_common)
    # must disable thinking or every call spins to max_tokens. Forward the model's chat_kwargs.
    import json as _json
    sub_env = {**os.environ}
    ck = R.BY_KEY[args.model].get("chat_kwargs")
    if ck:
        sub_env["PART3_CHAT_KWARGS"] = _json.dumps(ck)
    else:
        sub_env.pop("PART3_CHAT_KWARGS", None)
    try:
        if not args.skip_row3:
            R.log(f"=== Row 3: coverage internal G3/G5 ({args.model}) ===")
            cmd = [HARNESS_PY, str(REPO / "scripts/part3_p2_eval.py"),
                   "--base-url", base, "--model", args.model, "--style", "scoped",
                   "--manifest", str(COVERAGE), "--g7", str(REPO / "data/part3/manifest_g7_rendered.jsonl"),
                   "--modality", "A", "--max-per-defect", str(args.mpd), "--max-tokens", "1024",
                   "--workers", "8", "--force-c3",
                   "--classes", "G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION",
                   "--out", str(OUT / "p2_synth_internal_g3g5.json")]
            with open(logf, "a") as lf:
                rc = subprocess.run(cmd, cwd=str(REPO), env=sub_env, stdout=lf, stderr=subprocess.STDOUT).returncode
            R.log(f"  Row 3 rc={rc}")

        if not args.skip_row5:
            R.log(f"=== Row 5: real-CC internal-G3 ({args.model}) ===")
            cmd = [HARNESS_PY, str(REPO / "scripts/part3_pc_real.py"),
                   "--manifest", str(REAL_G3), "--base-url", base, "--model", args.model,
                   "--max-tokens", "512", "--workers", "8", "--max-per-class", "0",
                   "--out", str(OUT / f"pc_real_internal_g3_{args.model}.json"),
                   "--dump-rows", str(OUT / f"pc_real_internal_g3_{args.model}_rows.jsonl")]
            with open(logf, "a") as lf:
                rc = subprocess.run(cmd, cwd=str(REPO), env=sub_env, stdout=lf, stderr=subprocess.STDOUT).returncode
            R.log(f"  Row 5 rc={rc}")
    finally:
        R.teardown(proc)
    R.log("e8_bodyrun DONE")


if __name__ == "__main__":
    main()
