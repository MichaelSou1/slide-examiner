"""R7 — closed frontier VLM-as-judge row for the reward audit.

The reward table reports paired preference accuracy:

    P(score(clean_slide) > score(defective_slide))

This script makes a prompted frontier VLM behave like a pointwise judge by asking
it for a 0-100 visual/layout quality score for each image independently, then
computing the same paired-clean preference metric used by the reward-model audit.

Output is intentionally shaped like the p3 reward artifacts so the paper table
can add one row without changing the measurement contract.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.api_config import load_dotenv  # noqa: E402
from slide_examiner.examiner_contract import image_content_from_path  # noqa: E402
from slide_examiner.statistics import wilson_interval  # noqa: E402

SHORT = {
    "G1_TEXT_OVERFLOW": "G1 overflow",
    "G2_ELEMENT_OVERLAP": "G2 overlap",
    "G5_BRAND_COLOR_VIOLATION": "G5 colour",
    "G7_RENDER_CONTAINMENT_OVERFLOW": "G7 render-overflow",
    "S4_DENSITY_RULE_VIOLATION": "S4 density",
    "S6_IMAGE_TEXT_CONTRADICTION": "S6 image-text",
}

DEFAULT_DEFECTS = [
    "G7_RENDER_CONTAINMENT_OVERFLOW",
    "G1_TEXT_OVERFLOW",
    "G2_ELEMENT_OVERLAP",
    "S4_DENSITY_RULE_VIOLATION",
]

JUDGE_SYSTEM = (
    "You are a strict visual-quality judge for presentation slides. Judge only "
    "what is visible in the rendered image. Return a single JSON object and no "
    "extra prose."
)

JUDGE_PROMPT = (
    "Score this slide's overall rendered visual quality and layout integrity on "
    "a 0-100 scale. Penalize text overflow or clipping, element overlap, overly "
    "dense layout, broken containment, and unprofessional visual artifacts. "
    "Do not infer intent from hidden metadata; use only the pixels.\n\n"
    'Return exactly: {"score": <number 0-100>, "rationale": "<brief visible reason>"}'
)


def defect_of(rec: dict[str, Any]) -> str:
    labels = rec.get("labels") or []
    return labels[0].get("type") if labels else "NO_DEFECT"


def clean_path(rec: dict[str, Any]) -> str | None:
    pair = rec.get("pair") or {}
    return pair.get("clean_image_path") or (rec.get("metadata") or {}).get("clean_image_path")


def is_template_render(rec: dict[str, Any]) -> bool:
    metadata = rec.get("metadata") or {}
    if metadata.get("template_condition") == "template":
        return True
    path = rec.get("image_path") or ""
    return "__template" in path or "/template/" in path


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def load_records(manifest: str, defects: set[str], max_per_defect: int) -> list[dict[str, Any]]:
    by_defect: dict[str, list[dict[str, Any]]] = {d: [] for d in defects}
    with Path(manifest).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            defect = defect_of(rec)
            if defect not in by_defect or len(by_defect[defect]) >= max_per_defect:
                continue
            if is_template_render(rec):
                continue
            img = rec.get("image_path")
            cp = clean_path(rec)
            if not img or not cp:
                continue
            if not resolve(img).exists() or not resolve(cp).exists():
                continue
            by_defect[defect].append(rec)
    return [r for d in defects for r in by_defect.get(d, [])]


def extract_score(raw: str) -> float | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        score = float(data["score"])
        return max(0.0, min(100.0, score))
    except Exception:
        pass
    m = re.search(r'"?score"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', text, flags=re.I)
    if not m:
        m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\b", text)
    if not m:
        return None
    score = float(m.group(1))
    return max(0.0, min(100.0, score))


def judge_image(client: Any, model: str, image_path: str, max_tokens: int) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {
            "role": "user",
            "content": [
                image_content_from_path(str(resolve(image_path))),
                {"type": "text", "text": JUDGE_PROMPT},
            ],
        },
    ]
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.0,
        extra_body={"enable_thinking": False},
    )
    raw = resp.choices[0].message.content or ""
    score = extract_score(raw)
    return {"score": score, "raw": raw[:500], "latency_s": round(time.time() - t0, 3)}


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for defect in sorted({r["defect"] for r in rows}):
        rs = [r for r in rows if r["defect"] == defect]
        valid = [r for r in rs if r.get("clean_score") is not None and r.get("def_score") is not None]
        n = len(valid)
        if not n:
            continue
        clean_pref = sum(1 for r in valid if r["clean_score"] > r["def_score"])
        ties = sum(1 for r in valid if r["clean_score"] == r["def_score"])
        gaps = [r["clean_score"] - r["def_score"] for r in valid]
        ci = wilson_interval(clean_pref, n)
        out.append({
            "defect": defect,
            "render": "freeform",
            "n": n,
            "n_clean_preferred": clean_pref,
            "n_ties": ties,
            "preference_accuracy": round(clean_pref / n, 3),
            "preference_ci": [round(ci.low, 3), round(ci.high, 3)],
            "mean_reward_gap_clean_minus_def": round(sum(gaps) / n, 4),
            "median_gap": round(sorted(gaps)[n // 2], 4),
            "mean_clean_score": round(sum(r["clean_score"] for r in valid) / n, 3),
            "mean_defective_score": round(sum(r["def_score"] for r in valid) / n, 3),
            "n_failures": len(rs) - n,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.7-max-2026-06-08")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key-env", default="PART3_GEN_API_KEY")
    ap.add_argument("--manifest", action="append", required=True,
                    help="manifest(s) to scan; records are filtered by --defects")
    ap.add_argument("--defects", nargs="+", default=DEFAULT_DEFECTS)
    ap.add_argument("--max-per-defect", type=int, default=90)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--out", default="data/part3/r7_vlm_judge.json")
    ap.add_argument("--rows-out", default="data/part3/r7_vlm_judge_rows.jsonl")
    args = ap.parse_args()

    load_dotenv(REPO / ".env")
    base_url = args.base_url or os.environ.get("PART3_GEN_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get(args.api_key_env) or os.environ.get("OPENAI_API_KEY") or "EMPTY"

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout, max_retries=0)

    defects = set(args.defects)
    records: list[dict[str, Any]] = []
    seen = set()
    for manifest in args.manifest:
        for rec in load_records(manifest, defects, args.max_per_defect):
            key = (rec["sample_id"], defect_of(rec))
            if key not in seen:
                records.append(rec)
                seen.add(key)

    print(f"[r7] model={args.model} records={len(records)} defects={sorted(defects)}", flush=True)
    rows: list[dict[str, Any]] = []

    def work(rec: dict[str, Any]) -> dict[str, Any]:
        defect = defect_of(rec)
        dp = rec["image_path"]
        cp = clean_path(rec)
        assert cp
        d = judge_image(client, args.model, dp, args.max_tokens)
        c = judge_image(client, args.model, cp, args.max_tokens)
        return {
            "sample_id": rec["sample_id"],
            "defect": defect,
            "def_image": dp,
            "clean_image": cp,
            "def_score": d["score"],
            "clean_score": c["score"],
            "gap_clean_minus_def": (
                None if d["score"] is None or c["score"] is None else round(c["score"] - d["score"], 4)
            ),
            "def_raw": d["raw"],
            "clean_raw": c["raw"],
            "latency_s": round(d["latency_s"] + c["latency_s"], 3),
        }

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, rec) for rec in records]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                row = {"sample_id": "UNKNOWN", "defect": "UNKNOWN", "failure": str(exc)[:500]}
            rows.append(row)
            if i % 10 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)} done", flush=True)

    results = summarize(rows)
    out = {
        "key": "qwen37-max-vlm-judge",
        "display_name": "Qwen3.7-Max VLM judge",
        "category": "frontier_vlm_judge",
        "contract": "pointwise_prompted_score",
        "backbone": "Qwen3.7-Max",
        "trained_reward": False,
        "model": args.model,
        "base_url": base_url,
        "metric": "paired preference accuracy = P(score(clean) > score(defective)); "
                  "0.5 = blind, 1.0 = always prefers the clean slide",
        "elicitation": {"question": JUDGE_PROMPT, "answer": "0-100 scalar score"},
        "results": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.rows_out:
        Path(args.rows_out).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
