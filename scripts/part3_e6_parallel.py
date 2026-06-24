"""E6 — UNFLOORED downstream sweep, PARALLEL across all 4 GPUs.

Same experiment as part3_e6_unfloored_sweep.sh (weak Qwen3-VL-4B generator + the
5-condition examiner gradient, held identical to the strong-gen baseline), but
serves a SHARED generator and runs two examiner shards concurrently so all four
3080s are busy:

    GPU0  : gen-4B (shared by both shards; vLLM batches the two request streams)
    GPU1,2: shard 1 (TP=2) ft-8b  -> finetuned_8b + hybrid + linter
    GPU3  : shard 2 (TP=1) 30B-AWQ -> zero_shot_30b ; then cycle to 8B -> zero_shot_8b

Teardown is GPU-targeted (``nvidia-smi -i <idx>`` -> kill only that card's compute
apps), so a shard freeing its own GPU never disturbs the other shard or the shared
generator. Balanced by wall-time: shard 1 = 27 fast (ft-8B) trajectories; shard 2 =
9 slow (30B) + 9 (8B) ~= 27 units.

Launch as ONE background process:
    /home/gpus/anaconda3/bin/python scripts/part3_e6_parallel.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/gpus/slide-examiner")
VLLM = "/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm"
PY = "/home/gpus/anaconda3/bin/python"
MODELS = Path("/home/gpus/models")
LOG = REPO / "runs/part3/e6"
PROBE = REPO / "runs/probe/part3"
LOG.mkdir(parents=True, exist_ok=True)
PROBE.mkdir(parents=True, exist_ok=True)

M_GEN = MODELS / "Qwen3-VL-4B-Instruct"
M_8B = MODELS / "Qwen3-VL-8B-Instruct"
M_30B = MODELS / "Qwen3-VL-30B-A3B-Instruct-AWQ"
M_FT = REPO / "runs/part2/examiner_merged_v2"

SEEDS = ["0", "1", "2"]
ITERS = "3"
MAXTASKS = "3"
Q = "0.85"
TASKS = REPO / "data/part3/tasks/test.jsonl"
GEN_PORT = 8204
GEN_BASE = f"http://127.0.0.1:{GEN_PORT}/v1"

# Regime knobs (env): TAG names the run; SEED_MODULES = weak (coverage-bound headroom,
# the primary E6 null) | verbose (addressable geometry/conciseness headroom).
TAG = os.environ.get("E6_TAG", "weakgen")
SEED_MODULES = os.environ.get("E6_SEED_MODULES", "weak")
SUMMARY_OUT = Path(os.environ.get("E6_SUMMARY", str(REPO / "data/part3/e6_unfloored_synth.json")))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def serve(gpus: str, model: str, name: str, port: int, tp: int, *, util: float,
          max_len: int = 8192, extra: list[str] | None = None, eager: bool = True) -> subprocess.Popen:
    cmd = [VLLM, "serve", str(model), "--served-model-name", name, "--port", str(port),
           "--tensor-parallel-size", str(tp), "--gpu-memory-utilization", str(util),
           "--max-model-len", str(max_len), "--limit-mm-per-prompt", '{"image":1}',
           "--disable-custom-all-reduce", "--trust-remote-code", *(extra or [])]
    if eager:
        cmd.append("--enforce-eager")
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": gpus, "HF_HUB_OFFLINE": "1", "VLLM_USE_MODELSCOPE": "False"}
    logf = open(LOG / f"par_serve_{name}.log", "w")
    log(f"  serve {name} on GPU{gpus} :{port} (tp={tp}, util={util}) ...")
    return subprocess.Popen(cmd, cwd="/tmp", env=env, stdout=logf, stderr=subprocess.STDOUT,
                            start_new_session=True)


def wait_ready(name: str, port: int, proc: subprocess.Popen, timeout: int = 1000) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            log(f"  !! serve {name} exited early (rc={proc.returncode}) — see par_serve_{name}.log")
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as r:
                if name in r.read().decode():
                    log(f"  ready: {name} ({time.time()-t0:.0f}s)")
                    return True
        except Exception:
            pass
        time.sleep(4)
    log(f"  TIMEOUT waiting for {name}")
    return False


def free_gpus(idxs: list[int], *, keep: set[int] | None = None) -> None:
    """Kill compute apps on the given GPU indices ONLY (targeted teardown)."""
    keep = keep or set()
    sel = ",".join(str(i) for i in idxs)
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "-i", sel, "--query-compute-apps=pid", "--format=csv,noheader"],
            text=True, stderr=subprocess.DEVNULL)
    except Exception:
        out = ""
    for line in out.split():
        pid = line.strip()
        if pid.isdigit() and int(pid) not in keep:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except Exception:
                pass
    # wait for the cards to drain
    t0 = time.time()
    while time.time() - t0 < 90:
        try:
            used = subprocess.check_output(
                ["nvidia-smi", "-i", sel, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True).split()
            if all(int(u) < 2000 for u in used):
                return
        except Exception:
            return
        time.sleep(4)


def teardown(proc: subprocess.Popen, gpus: list[int]) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    time.sleep(3)
    free_gpus(gpus)


def run_sr(conds: list[str], out: Path, examiner_args: list[str], tag: str) -> int:
    env = {**os.environ,
           "PART3_GEN_MODEL": "qwen3vl-4b", "PART3_GEN_BASE_URL": GEN_BASE,
           "PART3_GEN_API_STYLE": "chat", "PART3_GEN_API_KEY": "EMPTY"}
    cmd = [PY, str(REPO / "scripts/part3_self_refine.py"), "--conditions", *conds,
           "--seeds", *SEEDS, "--n-iters", ITERS, "--max-tasks", MAXTASKS, "--q", Q,
           "--seed-modules", SEED_MODULES, "--tasks", str(TASKS), "--gen-max-tokens", "2048",
           "--out", str(out), "--summary", str(out.with_name(out.stem + "_summary.json")),
           *examiner_args]
    log(f"  [sr:{tag}] conds={conds} -> {out.name}")
    with open(LOG / f"par_run_{tag}.log", "w") as lf:
        rc = subprocess.run(cmd, cwd=str(REPO), env=env, stdout=lf, stderr=subprocess.STDOUT).returncode
    log(f"  [sr:{tag}] done rc={rc}")
    return rc


def examiner_pipeline() -> None:
    """Single examiner shard on GPU1,2 (TP=2), cycled across the gradient.

    Every examiner model (8B / ft / 30B) is ~16-17 GB and OOMs on a single 3080's
    KV cache, so each needs the full TP=2 pair; with the generator on GPU0 there is
    no room for a concurrent second pair. We therefore cycle one examiner server on
    GPU1,2 (GPU-targeted teardown between models) while the generator stays warm on
    GPU0. GPU3 is idle (no examiner fits a single card).
    """
    # ft-8b: finetuned_8b + hybrid (+ linter rides free, ignores the examiner)
    p = serve("1,2", M_FT, "ft-8b", 8131, 2, util=0.85)
    if wait_ready("ft-8b", 8131, p):
        run_sr(["finetuned_8b", "hybrid", "linter"], PROBE / f"self_refine_{TAG}_S1.jsonl",
               ["--ft-examiner-base-url", "http://127.0.0.1:8131/v1", "--ft-examiner-model", "ft-8b"], "ft")
    teardown(p, [1, 2])
    # 8B zero-shot
    p = serve("1,2", M_8B, "qwen3vl-8b", 8131, 2, util=0.85)
    if wait_ready("qwen3vl-8b", 8131, p):
        run_sr(["zero_shot_8b"], PROBE / f"self_refine_{TAG}_S2.jsonl",
               ["--api-examiner-base-url", "http://127.0.0.1:8131/v1", "--api-examiner-model", "qwen3vl-8b"], "zs8b")
    teardown(p, [1, 2])
    # 30B-A3B-AWQ zero-shot
    p = serve("1,2", M_30B, "qwen3vl-30b", 8131, 2, util=0.85, extra=["--kv-cache-dtype", "fp8"])
    if wait_ready("qwen3vl-30b", 8131, p):
        run_sr(["zero_shot_30b"], PROBE / f"self_refine_{TAG}_S3.jsonl",
               ["--api-examiner-base-url", "http://127.0.0.1:8131/v1", "--api-examiner-model", "qwen3vl-30b"], "zs30b")
    teardown(p, [1, 2])


def main() -> None:
    log("=== E6 sweep (gen GPU0 + cycled TP=2 examiner on GPU1,2; GPU3 idle) ===")
    gen = serve("0", M_GEN, "qwen3vl-4b", GEN_PORT, 1, util=0.60, eager=False)
    if not wait_ready("qwen3vl-4b", GEN_PORT, gen):
        teardown(gen, [0]); raise SystemExit("gen failed to serve")
    examiner_pipeline()
    teardown(gen, [0])

    # merge + aggregate
    parts = [PROBE / f"self_refine_{TAG}_S{i}.jsonl" for i in (1, 2, 3)]
    merged = PROBE / f"self_refine_{TAG}.jsonl"
    with merged.open("w", encoding="utf-8") as out:
        for p in parts:
            if p.exists():
                out.write(p.read_text(encoding="utf-8"))
    n = sum(1 for _ in merged.open())
    subprocess.run([PY, str(REPO / "scripts/part3_self_refine.py"),
                    "--from-jsonl", str(merged), "--summary", str(SUMMARY_OUT)],
                   cwd=str(REPO), stdout=open(LOG / "par_aggregate.log", "w"), stderr=subprocess.STDOUT)
    log(f"DONE. merged {n} records -> {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
