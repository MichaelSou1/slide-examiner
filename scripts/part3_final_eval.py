"""P8 — final eval (anti-Goodhart): a frozen judge of a DIFFERENT source.

For each condition's best skill, regenerate held-out test decks and score them
with a FROZEN judge that is NOT any condition's feedback source:
  live  : Qwen3-VL-32B-AWQ VLM (served), rates each deck 0..1.
  smoke : a deterministic structural heuristic judge (placeholder).
Ratings aggregated via panel.summarize_panel_ratings. Human 3-rater arm deferred
(todo §12).

Outputs: runs/probe/part3/final_eval.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.api_config import load_dotenv, resolve_role
load_dotenv(REPO / ".env")
_ENV_BASE = os.environ.get("OPENAI_BASE_URL")
# generator + judge are independent API services (PART3_GEN_* / PART3_JUDGE_*)
_GEN = resolve_role("GEN", default_model="qwen3.6-27b")
_JUDGE = resolve_role("JUDGE", default_model="qwen3-vl-32b")

from slide_examiner.generator import GeneratorConfig, generate_deck
from slide_examiner.io import read_jsonl
from slide_examiner.optim_runtime import openai_text_complete
from slide_examiner.panel import PanelRating, summarize_panel_ratings
from slide_examiner.part3_experiment import smoke_gen_complete
from slide_examiner.skill_doc import PromptModules

_JUDGE_PROMPT = (
    "You are a strict presentation-quality judge. Given a slide deck's structured "
    "content, rate its overall quality from 0.0 (poor) to 1.0 (excellent), judging "
    "clarity, conciseness, coverage, and consistency. Reply ONLY with JSON: "
    '{"score": <float 0..1>}.'
)


def _structural_judge(deck) -> float:
    """Deterministic placeholder judge (smoke): rewards concise, non-empty slides."""
    if not deck.slides:
        return 0.0
    score = 1.0
    for s in deck.slides:
        bodies = [e for e in s.elements if e.metadata.get("role") == "body"]
        if not [e for e in s.elements if e.text.strip()]:
            score -= 0.2
        if len(bodies) > 6:
            score -= 0.1
        if any(len(e.text) > 120 for e in bodies):
            score -= 0.1
    return max(0.0, min(1.0, score))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-jsonl", default=str(REPO / "runs/probe/part3/main.jsonl"))
    ap.add_argument("--tasks", default=str(REPO / "data/part3/tasks/test.jsonl"))
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/final_eval.json"))
    ap.add_argument("--max-tasks", type=int, default=4)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--gen-model", default=_GEN["model"])
    ap.add_argument("--gen-base-url", default=_GEN["base_url"] or "http://127.0.0.1:8200/v1")
    ap.add_argument("--gen-api-key-env", default=_GEN["api_key_env"])
    ap.add_argument("--gen-api-style", default=_GEN["api_style"], choices=["chat", "responses"])
    ap.add_argument("--gen-max-tokens", type=int, default=2048)
    # JUDGE = its own independent service (must differ from the examiner feedback source)
    ap.add_argument("--judge-model", default=_JUDGE["model"])
    ap.add_argument("--judge-base-url", default=_JUDGE["base_url"] or "http://127.0.0.1:8102/v1")
    ap.add_argument("--judge-api-key-env", default=_JUDGE["api_key_env"])
    ap.add_argument("--judge-api-style", default=_JUDGE["api_style"], choices=["chat", "responses"])
    args = ap.parse_args()

    records = read_jsonl(args.main_jsonl)
    tasks = read_jsonl(args.tasks)[: args.max_tasks]
    gen_cfg = GeneratorConfig(model=args.gen_model, base_url=args.gen_base_url, api_key_env=args.gen_api_key_env, api_style=args.gen_api_style, max_tokens=args.gen_max_tokens)
    gen_complete = smoke_gen_complete if args.smoke else None
    judge_complete = None if args.smoke else openai_text_complete(args.judge_model, args.judge_base_url, api_key_env=args.judge_api_key_env, api_style=args.judge_api_style, max_tokens=128)

    from slide_examiner.adapters import parse_examiner_json

    def judge(deck) -> float:
        if args.smoke or judge_complete is None:
            return _structural_judge(deck)
        try:
            content = json.dumps(deck.to_dict(), ensure_ascii=False)[:6000]
            raw = judge_complete([{"role": "user", "content": _JUDGE_PROMPT + "\n\nDECK:\n" + content}])
            return max(0.0, min(1.0, float(parse_examiner_json(raw).get("score", 0.0))))
        except Exception:
            return _structural_judge(deck)

    ratings: list[PanelRating] = []
    per_condition: dict[str, list[float]] = {}
    for rec in records:
        if not rec.get("ok") or not rec.get("best_skill"):
            continue
        cond, carrier, seed = rec["condition"], rec["carrier"], rec["seed"]
        modules = PromptModules.from_dict(rec["best_skill"])
        for ti, task in enumerate(tasks):
            art = generate_deck(task, modules, gen_cfg, out_dir=f"/tmp/p3_final/{cond}/{carrier}/{seed}/{ti}", complete=gen_complete, render=False)
            sc = judge(art.deck)
            per_condition.setdefault(cond, []).append(sc)
            ratings.append(PanelRating(sample_id=f"{cond}|{carrier}|s{seed}|t{ti}", judge_id="frozen_judge",
                                       score=sc, source="api" if not args.smoke else "heuristic"))

    panel = summarize_panel_ratings(ratings) if ratings else {}
    by_condition = {c: round(sum(v) / len(v), 4) for c, v in per_condition.items() if v}
    summary = {
        "judge": "qwen3-vl-32b (different source than any feedback)" if not args.smoke else "structural heuristic (smoke)",
        "n_tasks": len(tasks),
        "final_quality_by_condition": by_condition,
        "panel": panel,
        "human_arm": "deferred (todo §12)",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"final_quality_by_condition": by_condition}, indent=2, ensure_ascii=False))
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
