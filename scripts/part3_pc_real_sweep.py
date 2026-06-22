"""Part 3 R2 — serve a capable roster and run the real-layout A/B/C attribution.

Reuses the Protocol-1 roster's serve/teardown machinery (``part3_p1_roster``) but
runs ``part3_pc_real.py`` (modality A/B/C x detect/localize/repair) per model.
Launch as ONE background command (the harness reaps bg procs between tool calls):

    /home/gpus/anaconda3/bin/python scripts/part3_pc_real_sweep.py \
        --models qwen35-27b internvl-8b ovis-9b --gpus 0,1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/gpus/slide-examiner")
sys.path.insert(0, str(REPO / "scripts"))

import part3_p1_roster as R  # noqa: E402

HARNESS_PY = R.HARNESS_PY
OUT = REPO / "data/part3"
MANIFEST = REPO / "data/part3/manifest_real_rendered.jsonl"


def run_pc(m, max_per_class: int, workers: int):
    base = f"http://127.0.0.1:{R.PORT}/v1"
    env = {**os.environ}
    if m.get("chat_kwargs"):
        env["PART3_CHAT_KWARGS"] = json.dumps(m["chat_kwargs"])
    else:
        env.pop("PART3_CHAT_KWARGS", None)
    mt = str(max(m.get("max_tokens", 512), 512))
    cmd = [HARNESS_PY, str(REPO / "scripts/part3_pc_real.py"),
           "--manifest", str(MANIFEST), "--base-url", base, "--model", m["key"],
           "--max-tokens", mt, "--workers", str(workers),
           "--max-per-class", str(max_per_class),
           "--out", str(OUT / f"pc_real_{m['key']}.json"),
           "--dump-rows", str(OUT / f"pc_real_{m['key']}_rows.jsonl")]
    logf = R.LOG / f"pc_real_{m['key']}.log"
    R.log(f"  pc_real {m['key']} (mpc={max_per_class}, workers={workers}) -> {logf}")
    with open(logf, "w") as lf:
        rc = subprocess.run(cmd, cwd=str(REPO), env=env, stdout=lf, stderr=subprocess.STDOUT).returncode
    R.log(f"    {m['key']} rc={rc}")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen35-27b", "internvl-8b", "ovis-9b"])
    ap.add_argument("--gpus", default="0,1")
    ap.add_argument("--vllm", default=R.VLLM)
    ap.add_argument("--max-per-class", type=int, default=0, help="0 = all pairs")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    R.GPUS = args.gpus
    R.VLLM = args.vllm
    R.LOG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    ok, failed = [], []
    for key in args.models:
        m = R.BY_KEY[key]
        R.log(f"=== {key} [{m['fam']}/{m['tier']}] ===")
        path = R.ensure_on_disk(m)
        if not path:
            failed.append((key, "no-model")); continue
        R.gpu_free_wait()
        proc = R.serve(m, path)
        if not R.wait_ready(key, proc):
            R.teardown(proc); failed.append((key, "serve-fail")); continue
        try:
            workers = int(m.get("workers", args.workers))
            run_pc(m, args.max_per_class, workers)
            ok.append(key)
        finally:
            R.teardown(proc)
    R.log(f"DONE. ok={ok} failed={failed}")


if __name__ == "__main__":
    main()
