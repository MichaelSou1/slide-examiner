"""Cost / compute table for the elicitation conditions (W2 2.3).

Aggregates the token-usage logs (2.0) written into every p1e1_/p1e2_ run JSON into
a per-condition cost table for the Technical Supplement: calls per slide, input and
output tokens per slide, total tokens per slide, and an estimated wall-clock latency
per slide. This is the concrete "what does each elicitation condition cost to
deploy" the reviewers asked for, and the evidence that C3's recovery is not bought
with extra test-time compute (C0_rep's K× multiplier is visible here).

Runs with ZERO new experiment cost: it reads existing JSON. Older runs written
before the usage log (most p1e1_*) carry no usage and are reported as "—" with a
count in the footnote — top them up by re-running a small slice with --resume, or
read the p1e2_* rows which always carry usage.

Usage:
  python scripts/part3_cost_table.py --out reports/cost_table.md
  python scripts/part3_cost_table.py --prefixes p1e2 --tok-per-s 40
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# All conditions we might see, longest-first so multi-underscore ids parse correctly.
_CONDS = ["C0_named", "C0_full", "C0_rep", "C0plus", "AFC_clean", "AFC", "C0", "C1", "C2", "C3"]
_TAG_OF_DEFECT = {"G7_RENDER_CONTAINMENT_OVERFLOW": "G7", "G1_TEXT_OVERFLOW": "G1",
                  "S6_IMAGE_TEXT_CONTRADICTION": "S6", "G3_ALIGNMENT_OFFSET": "G3",
                  "G5_BRAND_COLOR_VIOLATION": "G5", "G6_MARGIN_VIOLATION": "G6"}
# Rough single-call latency overhead (connection + prefill) in seconds, on top of
# decode time (completion_tokens / tok_per_s). Only used for the estimated column.
_CALL_OVERHEAD_S = 1.2


def _parse_name(path: str, prefix: str) -> tuple[str, str, str]:
    body = Path(path).name[len(prefix) + 1:]
    for suf in ("_rows.jsonl", ".json"):
        if body.endswith(suf):
            body = body[:-len(suf)]
            break
    for cond in _CONDS:
        if body.endswith("_" + cond):
            model, _, tag = body[: -(len(cond) + 1)].rpartition("_")
            return model or body, tag, cond
    parts = body.split("_")
    return parts[0], (parts[1] if len(parts) > 1 else ""), "_".join(parts[2:])


def _tag(d: dict, path: str, prefix: str) -> str:
    defects = d.get("defects") or []
    if defects and defects[0] in _TAG_OF_DEFECT:
        return _TAG_OF_DEFECT[defects[0]]
    return _parse_name(path, prefix)[1] or "?"


def collect(prefixes):
    """rows = list of dicts (one per run JSON that carries usage), plus a count of
    usage-less runs for the footnote."""
    out, missing = [], []
    for prefix in prefixes:
        for path in sorted(glob.glob(str(REPO / f"data/part3/{prefix}_*.json"))):
            if path.endswith("_rows.jsonl") or "_summary" in path:
                continue
            try:
                d = json.loads(Path(path).read_text())
            except (json.JSONDecodeError, OSError):
                continue
            cond = d.get("condition")
            model = d.get("model")
            if not cond or not model:
                continue
            u = d.get("usage")
            if not u:
                missing.append((model, _tag(d, path, prefix), cond))
                continue
            out.append({"model": model, "tag": _tag(d, path, prefix), "cond": cond,
                        "prefix": prefix, "usage": u})
    return out, missing


def est_latency(u: dict, tok_per_s: float) -> float:
    """Estimated wall-clock seconds per slide: decode time + per-call overhead."""
    return round(u["completion_tokens_per_record"] / tok_per_s
                 + u["calls_per_record"] * _CALL_OVERHEAD_S, 2)


def _fmt(x):
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def build_md(rows, missing, tok_per_s: float) -> str:
    order = {c: i for i, c in enumerate(["C0", "C0_named", "C0plus", "C0_full",
                                         "C0_rep", "C1", "C2", "C3", "AFC", "AFC_clean"])}
    rows = sorted(rows, key=lambda r: (r["model"], r["tag"], order.get(r["cond"], 99)))
    L = ["## Elicitation cost / compute per slide\n",
         f"Token counts are per probed slide (paired-clean: a slide and its clean twin "
         f"each count once). Estimated latency = completion_tokens / {tok_per_s:g} tok·s⁻¹ "
         f"+ {_CALL_OVERHEAD_S:g} s × calls (single-stream; concurrency hides most of it). "
         "`calls/slide` makes the compute budget explicit — C3 and the single-call C0 "
         "variants spend one call; **C0_rep** spends K (the deployed router's per-slide "
         "atomic-question count), so if C3 matches or beats C0_rep the recovery is not a "
         "test-time-compute effect.\n",
         "| Model | Tag | Cond | calls/slide | input tok/slide | output tok/slide | "
         "total tok/slide | est. latency (s) |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        u = r["usage"]
        L.append(f"| {r['model']} | {r['tag']} | {r['cond']} | "
                 f"{_fmt(u['calls_per_record'])} | {_fmt(u['prompt_tokens_per_record'])} | "
                 f"{_fmt(u['completion_tokens_per_record'])} | "
                 f"{_fmt(u['prompt_tokens_per_record'] + u['completion_tokens_per_record'])} | "
                 f"{est_latency(u, tok_per_s)} |")
    if not rows:
        L.append("| — | — | — | (no runs carry usage yet) | | | | |")
    # compute-ratio callout: C0_rep vs C0 per (model, tag)
    ratios = _compute_ratios(rows)
    if ratios:
        L += ["\n### Compute multiplier (C0_rep vs C0)\n",
              "| Model | Tag | C0 output tok | C0_rep output tok | C3 output tok | C0_rep/C0 calls | C3/C0 output |",
              "|---|---|---|---|---|---|---|"]
        L.extend(ratios)
    if missing:
        by_cond: dict = {}
        for _m, _t, c in missing:
            by_cond[c] = by_cond.get(c, 0) + 1
        note = ", ".join(f"{c}×{n}" for c, n in sorted(by_cond.items()))
        L.append(f"\n> {len(missing)} run(s) predate the usage log and are omitted "
                 f"({note}); re-run a slice with `--resume` to top up their token counts.\n")
    return "\n".join(L) + "\n"


def _compute_ratios(rows):
    by = {}
    for r in rows:
        by.setdefault((r["model"], r["tag"]), {})[r["cond"]] = r["usage"]
    out = []
    for (model, tag), conds in sorted(by.items()):
        c0, rep, c3 = conds.get("C0"), conds.get("C0_rep"), conds.get("C3")
        if not (c0 and rep):
            continue
        c0_out = c0["completion_tokens_per_record"]
        rep_out = rep["completion_tokens_per_record"]
        c3_out = c3["completion_tokens_per_record"] if c3 else None
        call_ratio = round(rep["calls_per_record"] / c0["calls_per_record"], 1) if c0["calls_per_record"] else "—"
        c3_ratio = (round(c3_out / c0_out, 2) if c3 and c0_out else "—")
        out.append(f"| {model} | {tag} | {_fmt(c0_out)} | {_fmt(rep_out)} | "
                   f"{_fmt(c3_out) if c3_out is not None else '—'} | {call_ratio}× | {c3_ratio} |")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefixes", nargs="+", default=["p1e1", "p1e2"])
    ap.add_argument("--tok-per-s", type=float, default=40.0,
                    help="decode throughput for the latency estimate (VLM ≈ 37-40 tok/s).")
    ap.add_argument("--out", default="reports/cost_table.md")
    ap.add_argument("--json", default="data/part3/cost_table.json")
    args = ap.parse_args()

    rows, missing = collect(args.prefixes)
    md = build_md(rows, missing, args.tok_per_s)
    Path(REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO / args.out).write_text(md, encoding="utf-8")
    Path(REPO / args.json).write_text(
        json.dumps({"rows": rows, "missing_usage": missing, "tok_per_s": args.tok_per_s},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)
    print(f"[cost-table] {len(rows)} runs with usage, {len(missing)} without -> {args.out}")


if __name__ == "__main__":
    main()
