"""P1 — end-to-end generator smoke test (real render).

brief -> content JSON -> Deck IR -> rendered PNGs, validated with
check_render_artifact. Requires a served generator LLM (vLLM) unless
--content-json is supplied (skips the LLM, tests render only).

Outputs: runs/rendered/part3_smoke/smoke_summary.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.generator import DEFAULT_PROMPT_MODULES, GeneratorConfig, generate_deck
from slide_examiner.render import check_render_artifact


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default="smoke_launch")
    ap.add_argument("--brief", default="Create a launch deck for a retail enterprise about an AI churn prediction platform. About 6 slides. Cover background, problem, solution, call to action.")
    ap.add_argument("--model", default="qwen3.6-27b")
    ap.add_argument("--base-url", default="http://127.0.0.1:8200/v1")
    ap.add_argument("--renderer", default="html", choices=["html", "pptx"])
    ap.add_argument("--long-edge", type=int, default=1024)
    ap.add_argument("--content-json", default=None, help="optional content JSON to skip the LLM")
    ap.add_argument("--out", default=str(REPO / "runs/rendered/part3_smoke"))
    args = ap.parse_args()

    cfg = GeneratorConfig(model=args.model, base_url=args.base_url, renderer=args.renderer, long_edge=args.long_edge)
    complete = None
    if args.content_json:
        content = json.loads(Path(args.content_json).read_text(encoding="utf-8"))
        complete = lambda messages: json.dumps(content)  # noqa: E731

    task = {"task_id": args.task_id, "brief": args.brief}
    art = generate_deck(task, DEFAULT_PROMPT_MODULES, cfg, out_dir=args.out, seed=0, complete=complete, render=True)

    checks = []
    for slide, img, spec in zip(art.deck.slides, art.page_image_paths, art.render_specs):
        q = check_render_artifact(img, slide, spec)
        checks.append({"slide_id": slide.slide_id, "image": str(img), "ok": q.ok, "issues": list(q.issues)})

    summary = {
        "task_id": args.task_id,
        "degenerate": art.degenerate,
        "n_slides": len(art.deck.slides),
        "n_images": len(art.page_image_paths),
        "all_renders_ok": bool(checks) and all(c["ok"] for c in checks),
        "checks": checks,
    }
    out_summary = Path(args.out) / "smoke_summary.json"
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if art.degenerate:
        raise SystemExit("generation degenerate (empty deck)")
    if not summary["all_renders_ok"]:
        raise SystemExit("render quality check failed")


if __name__ == "__main__":
    main()
