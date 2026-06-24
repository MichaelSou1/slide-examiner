"""Part 3 Protocol-1 sweep over a MODEL-AGNOSTIC roster (8 VLMs, 5 families).

One self-contained process: per model -> ensure-on-disk (ModelScope download if
needed) -> vLLM serve (per-model flags) -> run C0/C1/C2/C3 x {geo,g7} -> teardown.
Launch as ONE background command (the harness reaps bg procs between tool calls):
    /home/gpus/anaconda3/bin/python scripts/part3_p1_roster.py [--validate] [--mpd 60]

Envs: base python here (has modelscope); subprocesses use vllm-qwen (serve) and
slide-examiner (harness: openai+playwright). Thinking VLMs (ERNIE) get
PART3_CHAT_KWARGS=enable_thinking:false + a larger token budget.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/gpus/slide-examiner")
VLLM = "/home/gpus/anaconda3/envs/vllm-qwen/bin/vllm"  # overridden by --vllm (use vllm-latest for gemma4)
HARNESS_PY = "/home/gpus/anaconda3/envs/slide-examiner/bin/python"
MODELS_DIR = Path("/home/gpus/models")
OUT = REPO / "data/part3"
LOG = REPO / "runs/part3/p1"
PORT = 8101
GPUS = "0,1"  # overridden by --gpus; the TP=2 card pair to serve on
GPU_UTIL = None  # overridden by --gpu-util (e.g. 0.55 when sharing the user's GPUs)
KILL_STRAY = True  # set False (--no-stray-kill) for a parallel 2-server shard so one
#                    shard's teardown does not kill the OTHER shard's EngineCore workers
GEO = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
G7 = REPO / "data/part3/manifest_g7_rendered.jsonl"
INTERNAL = REPO / "data/part3/manifest_g3g5_internal.jsonl"  # E8 redo: internal-contrast G3/G5
NOTHINK = {"chat_template_kwargs": {"enable_thinking": False}}

# key | source (local path or ms:owner/name) | family | tier | serve_extra | max_tokens | chat_kwargs
# NOTE: Qwen3.5/3.6 are thinking VLMs (enable_thinking in chat template) -> reasoning
# ate the C3 token budget -> empty/truncated JSON. Fixed with NOTHINK + bigger budget
# (vision itself works). gemma4-31b (transformers<gemma4) and glm46v-flash (AWQ missing
# HF processor) fail to serve in this env -> dropped this round (env-version casualties).
ROSTER = [
    dict(key="qwen35-9b",    src="ms:cyankiwi/Qwen3.5-9B-AWQ-4bit",                       fam="Qwen",      tier="weak",   max_tokens=1024, chat_kwargs=NOTHINK),
    dict(key="internvl-8b",  src=str(MODELS_DIR / "InternVL3_5-8B"),                      fam="OpenGVLab", tier="weak"),
    dict(key="ovis-9b",      src=str(MODELS_DIR / "Ovis2.5-9B"),                          fam="AIDC-Ovis", tier="weak", max_tokens=2048),  # thinking model, no disable toggle -> needs budget for <think>+JSON
    dict(key="glm46v-flash", src="ms:cyankiwi/GLM-4.6V-Flash-AWQ-8bit",                   fam="Zhipu-GLM", tier="weak",   max_num_seqs=6, workers=6, max_tokens=2048, chat_kwargs=NOTHINK),   # vllm-new (transformers5); thinking model
    dict(key="qwen36-27b",   src=str(MODELS_DIR / "Qwen3.6-27B-AWQ-INT4"),                fam="Qwen",      tier="strong", serve_extra=["--kv-cache-dtype", "fp8"], max_tokens=1024, chat_kwargs=NOTHINK, gpu_util=0.80, max_num_seqs=6, workers=6),
    dict(key="gemma4-31b",   src="ms:cyankiwi/gemma-4-31B-it-AWQ-4bit",                   fam="Google",    tier="strong", gpu_util=0.85, max_num_seqs=6, workers=6),  # vllm-latest(0.23+cu129); NO fp8 KV (Ampere can't do fp8e4nv)
    dict(key="qwen35-27b",   src="ms:cyankiwi/Qwen3.5-27B-AWQ-4bit",                      fam="Qwen",      tier="strong", serve_extra=["--kv-cache-dtype", "fp8"], max_tokens=1024, chat_kwargs=NOTHINK, gpu_util=0.80, max_num_seqs=6, workers=6),
    dict(key="ernie-vl-28b", src="ms:cyankiwi/ERNIE-4.5-VL-28B-A3B-Thinking-AWQ-8bit",    fam="Baidu",     tier="strong", serve_extra=["--kv-cache-dtype", "fp8"], max_tokens=1024, chat_kwargs=NOTHINK, gpu_util=0.80, max_num_seqs=6, workers=6),
]
WORKING = ["qwen35-9b", "internvl-8b", "ovis-9b", "qwen36-27b", "qwen35-27b", "ernie-vl-28b"]
BY_KEY = {m["key"]: m for m in ROSTER}


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure_on_disk(m) -> str | None:
    """Return a local path; download from ModelScope if src is ms:owner/name."""
    src = m["src"]
    if not src.startswith("ms:"):
        return src if Path(src).exists() else None
    repo_id = src[3:]
    local = MODELS_DIR / repo_id.split("/")[-1]
    cfg = local / "config.json"
    if cfg.exists():
        log(f"  {m['key']}: already on disk ({local})")
        return str(local)
    log(f"  {m['key']}: downloading {repo_id} -> {local} ...")
    from modelscope import snapshot_download
    try:
        snapshot_download(repo_id, local_dir=str(local))
    except Exception as exc:  # noqa: BLE001
        log(f"  {m['key']}: DOWNLOAD FAILED: {exc}")
        return None
    m["_downloaded"] = str(local)
    return str(local) if cfg.exists() else None


def serve(m, path: str) -> subprocess.Popen:
    extra = list(m.get("serve_extra", []))
    # cap concurrent sequences for tight strong models -> bounds peak (esp. C2
    # 2-image) vision-encoder activation memory that otherwise OOMs a TP worker.
    if m.get("max_num_seqs"):
        extra += ["--max-num-seqs", str(m["max_num_seqs"])]
    util = GPU_UTIL if GPU_UTIL is not None else m.get("gpu_util", 0.85)
    cmd = [VLLM, "serve", path, "--served-model-name", m["key"], "--port", str(PORT),
           "--tensor-parallel-size", "2", "--gpu-memory-utilization", str(util),
           "--max-model-len", "8192", "--limit-mm-per-prompt", '{"image":6}',
           "--enforce-eager", "--disable-custom-all-reduce", "--trust-remote-code", *extra]
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": GPUS, "HF_HUB_OFFLINE": "1", "VLLM_USE_MODELSCOPE": "False"}
    logf = open(LOG / f"serve_{m['key']}.log", "w")
    log(f"  serving {m['key']} (tp=2, extra={extra}) ...")
    return subprocess.Popen(cmd, cwd="/tmp", env=env, stdout=logf, stderr=subprocess.STDOUT,
                            start_new_session=True)


def wait_ready(name: str, proc: subprocess.Popen, timeout=900) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            log(f"  serve process exited early (rc={proc.returncode})")
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=3) as r:
                if name in r.read().decode():
                    log(f"  ready: {name} ({time.time()-t0:.0f}s)")
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(4)
    log(f"  TIMEOUT waiting for {name}")
    return False


def teardown(proc: subprocess.Popen):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    # belt-and-suspenders: reap stray EngineCore workers (orchestrator cmdline
    # doesn't contain the pattern, so pgrep can't match self). Skipped for a
    # parallel shard (KILL_STRAY=False) — it would reap the sibling shard's workers.
    if KILL_STRAY:
        subprocess.run("for p in $(pgrep -f 'VLLM::EngineCore'); do kill -9 $p; done",
                       shell=True, stderr=subprocess.DEVNULL)
    time.sleep(4)


def gpu_free_wait(timeout=120):
    idx = [int(x) for x in GPUS.split(",")]
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True)
            used = [int(x) for x in out.split()]
            if all(used[i] < 2000 for i in idx):
                return
        except Exception:  # noqa: BLE001
            return
        time.sleep(4)


def run_elicit(m, mpd: int, conds: list[str], tags: list[str], freeform_only: bool = False,
               out_prefix: str = "p1"):
    base = f"http://127.0.0.1:{PORT}/v1"
    env = {**os.environ}
    if m.get("chat_kwargs"):
        env["PART3_CHAT_KWARGS"] = json.dumps(m["chat_kwargs"])
    else:
        env.pop("PART3_CHAT_KWARGS", None)
    mt = str(m.get("max_tokens", 512))
    workers = str(m.get("workers", 12))
    jobs = {"geo": (GEO, ["G1_TEXT_OVERFLOW", "S6_IMAGE_TEXT_CONTRADICTION"]),
            "g7": (G7, ["G7_RENDER_CONTAINMENT_OVERFLOW"])}
    logf = LOG / f"elicit_{m['key']}.log"
    for tag in tags:
        manifest, defects = jobs[tag]
        for cond in conds:
            log(f"  elicit {m['key']} {tag} {cond} (mpd={mpd}, workers={workers}, freeform_only={freeform_only})")
            cmd = [HARNESS_PY, str(REPO / "scripts/part3_elicit.py"), "--condition", cond,
                   "--manifest", str(manifest), "--base-url", base, "--model", m["key"],
                   "--style", "scoped", "--defects", *defects, "--modalities", "A",
                   "--max-per-defect", str(mpd), "--max-tokens", mt, "--workers", workers,
                   "--out", str(OUT / f"{out_prefix}_{m['key']}_{tag}_{cond}.json"),
                   "--dump-rows", str(OUT / f"{out_prefix}_{m['key']}_{tag}_{cond}_rows.jsonl")]
            if freeform_only:
                cmd.append("--freeform-only")
            with open(logf, "a") as lf:
                rc = subprocess.run(cmd, cwd=str(REPO), env=env, stdout=lf, stderr=subprocess.STDOUT).returncode
            if rc != 0:
                log(f"    [warn] {m['key']} {tag} {cond} rc={rc}")


def main():
    global GPUS, VLLM, PORT, KILL_STRAY, GPU_UTIL
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[m["key"] for m in ROSTER])
    ap.add_argument("--mpd", type=int, default=60)
    ap.add_argument("--conds", nargs="+", default=["C0", "C1", "C2", "C3"])
    ap.add_argument("--tags", nargs="+", default=["geo", "g7"])
    ap.add_argument("--validate", action="store_true",
                    help="quick servability pass: mpd=2, C3 only, g7 only")
    ap.add_argument("--delete-downloads", action="store_true")
    ap.add_argument("--gpus", default="0,1", help="TP=2 card pair, e.g. '2,3'")
    ap.add_argument("--port", type=int, default=PORT,
                    help="vLLM port; use a 2nd port (e.g. 8102) for a parallel 2-server shard.")
    ap.add_argument("--gpu-util", type=float, default=None,
                    help="override gpu-memory-utilization for ALL models (e.g. 0.55 when sharing the box).")
    ap.add_argument("--freeform-only", action="store_true",
                    help="E1: drop __template renders on the geo manifest (no-op on g7).")
    ap.add_argument("--out-prefix", default="p1",
                    help="output file prefix (use 'p1e1' for the E1 decomposition so it "
                         "does not clobber the unfiltered Result-1 p1_* files).")
    ap.add_argument("--no-stray-kill", action="store_true",
                    help="don't pgrep-kill stray EngineCore on teardown (use for a parallel 2-server shard).")
    ap.add_argument("--vllm", default=VLLM, help="vllm binary (use vllm-latest for gemma4)")
    args = ap.parse_args()
    GPUS = args.gpus
    VLLM = args.vllm
    PORT = args.port
    GPU_UTIL = args.gpu_util
    KILL_STRAY = not args.no_stray_kill
    LOG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.validate:
        args.mpd, args.conds, args.tags = 2, ["C3", "C1"], ["g7"]

    ok, failed = [], []
    for key in args.models:
        m = BY_KEY[key]
        log(f"=== {key} [{m['fam']}/{m['tier']}] ===")
        path = ensure_on_disk(m)
        if not path:
            failed.append((key, "no-model")); continue
        gpu_free_wait()
        proc = serve(m, path)
        if not wait_ready(key, proc):
            teardown(proc); failed.append((key, "serve-fail")); continue
        try:
            run_elicit(m, args.mpd, args.conds, args.tags, freeform_only=args.freeform_only,
                       out_prefix=args.out_prefix)
            ok.append(key)
        finally:
            teardown(proc)
        if args.delete_downloads and m.get("_downloaded"):
            subprocess.run(["rm", "-rf", m["_downloaded"]])
            log(f"  deleted download {m['_downloaded']}")
    log(f"DONE. ok={ok} failed={failed}")


if __name__ == "__main__":
    main()
