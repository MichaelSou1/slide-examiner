"""Print new eval/loss points + train-loss health for the Part 2 run.
Exit 42 when the run has finished (so a Monitor loop can stop)."""
import json
import netrc
import os
import sys
from pathlib import Path

os.environ.setdefault("WANDB_API_KEY", netrc.netrc().authenticators("api.wandb.ai")[2])
os.environ["WANDB_SILENT"] = "true"
import wandb

PROJECT = "michaelsou-sun-yat-sen-university/slide-examiner-part2"
STATE = Path("/home/gpus/slide-examiner/runs/part2/.wandb_eval_count")

try:
    api = wandb.Api()
    # most recently created run in the project (the active training run)
    run = api.runs(PROJECT, order="-created_at")[0]
    ev = [(r["_step"], round(r["eval/loss"], 4)) for r in run.scan_history(keys=["eval/loss", "_step"])]
    tr = [(r["_step"], r["train/loss"]) for r in run.scan_history(keys=["train/loss", "_step"])]
except Exception as e:
    print(f"[health] api error: {e}")
    sys.exit(0)

prev = 0
if STATE.exists():
    try:
        prev = int(STATE.read_text())
    except Exception:
        prev = 0

# collapse check
bad = [s for s, l in tr if l is None or l != l or l > 50]
if bad:
    print(f"[health] COLLAPSE? abnormal train/loss at steps {bad[:5]}")

if len(ev) > prev:
    new = ev[prev:]
    last_tr = tr[-1][1] if tr else None
    # overfit heuristic: eval rising while train falling
    trend = ""
    if len(ev) >= 2:
        de = ev[-1][1] - ev[-2][1]
        trend = " (eval RISING — watch overfit)" if de > 0.02 else " (eval stable/falling)"
    print(f"[health] new eval/loss {new} | latest train/loss={last_tr}{trend}")
    STATE.write_text(str(len(ev)))

if run.state != "running":
    print(f"[health] run FINISHED state={run.state} | eval/loss series={ev} | last train/loss={tr[-1][1] if tr else None}")
    sys.exit(42)
