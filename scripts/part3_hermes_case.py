"""Part 3 lightweight Hermes case-study (real-world confirmation arm).

A REAL pre-sales deck produced by the Hermes agent (powerpoint skill) is messy in
a way our synthetic toy never is: it ships with unfilled TEMPLATE PLACEHOLDERS
(添加标题 / 添加内文 …) — a *semantic completeness* defect a geometry linter is
blind to by construction. We feed the rendered deck to the SAME examiner gradient
(the IV) and ask: does a better examiner detect more of the real mess?

Ground truth = verifiable placeholder count per slide (model-free string match).
DV per examiner condition = detection recall on placeholder slides + mean quality
score (placeholder slides vs clean slides) + critique text.

Examiner routing mirrors part3_self_refine.py: zero_shot_* -> served API examiner;
finetuned_8b/hybrid -> local ft-8B. linter is offline (blind baseline, reported).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.adapters import normalize_examiner_output, parse_examiner_json
from slide_examiner.api_config import build_completion, load_dotenv, resolve_role
from slide_examiner.examiner_contract import build_messages_from_sample
from slide_examiner.feedback_sources import _SCOPE_SUFFIX, LinterOnlyFeedback
from slide_examiner.generator import GeneratedArtifact
from slide_examiner.pptx_ingest import deck_from_pptx, placeholder_stats
from slide_examiner.skill_doc import DEFAULT_PROMPT_MODULES

load_dotenv(REPO / ".env")
_EXAM = resolve_role("EXAMINER", default_model="qwen3vl-8b")

PLACEHOLDER_MARKERS = ("添加", "点击此处", "请输入", "占位")


def _has_placeholder(text: str) -> bool:
    return any(m in (text or "") for m in PLACEHOLDER_MARKERS)


def _slide_has_placeholder(slide) -> bool:
    return any(_has_placeholder(e.text or "") for e in slide.elements)


def _probe(complete, slide, img, spec, prompt_style):
    rec = {"sample_id": slide.slide_id, "slide": slide.to_dict(), "labels": [], "metadata": {}}
    if img:
        rec["image_path"] = str(img)
    if spec:
        rec["metadata"]["render"] = spec
    messages = build_messages_from_sample(rec, modality="C" if img else "B")
    if prompt_style == "scoped":
        messages = [*messages, {"role": "user", "content": _SCOPE_SUFFIX}]
    raw = "{}"
    for _ in range(2):
        try:
            raw = complete(messages)
            return normalize_examiner_output(parse_examiner_json(raw))
        except Exception:
            messages = [*messages, {"role": "user", "content": "OUTPUT VALID JSON ONLY."}]
    try:
        return normalize_examiner_output(parse_examiner_json(raw))
    except Exception:
        return {"defects": [], "overall_score": 1.0}


def _mentions_placeholder(defects) -> bool:
    for d in defects:
        if _has_placeholder(str(d.get("evidence", "")) + str(d.get("fix", ""))):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", default=str(REPO / "data/part3/hermes_case/raw/deck.pptx"))
    ap.add_argument("--slides-dir", default=str(REPO / "data/part3/hermes_case/slides"))
    ap.add_argument("--conditions", nargs="+", default=["linter", "zero_shot_8b", "zero_shot_30b", "finetuned_8b", "hybrid"])
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/hermes_case.json"))
    ap.add_argument("--api-examiner-model", default=_EXAM["model"])
    ap.add_argument("--api-examiner-base-url", default=_EXAM["base_url"] or "http://127.0.0.1:8108/v1")
    ap.add_argument("--api-examiner-api-key-env", default=_EXAM["api_key_env"])
    ap.add_argument("--ft-examiner-model", default="ft-8b")
    ap.add_argument("--ft-examiner-base-url", default="http://127.0.0.1:8101/v1")
    args = ap.parse_args()

    deck = deck_from_pptx(args.pptx)
    n = len(deck.slides)
    imgs = [Path(args.slides_dir) / f"s{i+1:02d}.png" for i in range(n)]
    specs = [{"image_width_px": 2001, "image_height_px": 1125, "scale_x": 2001 / 12192000,
              "scale_y": 1125 / 6858000, "dpi": 150, "renderer": "libreoffice"} for _ in range(n)]
    art = GeneratedArtifact(deck=deck, content_json={}, page_image_paths=imgs, render_specs=specs,
                            prompt_modules=DEFAULT_PROMPT_MODULES, raw_completion="",
                            out_dir=Path(args.slides_dir).parent, degenerate=False)

    gt = [_slide_has_placeholder(s) for s in deck.slides]           # verifiable ground truth
    ph_idx = [i for i, g in enumerate(gt) if g]
    clean_idx = [i for i, g in enumerate(gt) if not g]
    ps = placeholder_stats(deck)
    print(f"[case] {n} slides, placeholder GT: {len(ph_idx)} slides ({ps['total_placeholders']} placeholders)")

    def examiner_for(cond):
        if cond in ("zero_shot_8b", "zero_shot_30b"):
            return build_completion(args.api_examiner_model, args.api_examiner_base_url,
                                    api_key_env=args.api_examiner_api_key_env, api_style="chat", max_tokens=900), "scoped"
        return build_completion(args.ft_examiner_model, args.ft_examiner_base_url,
                                api_key_env="OPENAI_API_KEY", api_style="chat", max_tokens=900), "trained"

    results = {}
    for cond in args.conditions:
        if cond == "linter":
            lf = LinterOnlyFeedback()
            per = []
            for s in deck.slides:
                from slide_examiner.geometry import linter_score, lint_slide
                defs = lint_slide(s)
                per.append({"score": round(linter_score(s), 3), "has_defect": len(defs) > 0,
                            "mentions_ph": False, "n_findings": len(defs)})
        else:
            complete, style = examiner_for(cond)
            per = []
            for s, img, spec in zip(deck.slides, imgs, specs):
                norm = _probe(complete, s, str(img), spec, style)
                defs = [d for d in norm.get("defects", []) if d.get("present", True)]
                per.append({"score": round(float(norm.get("overall_score", 1.0)), 3),
                            "has_defect": len(defs) > 0, "mentions_ph": _mentions_placeholder(defs),
                            "n_findings": len(defs)})
        # DV vs verifiable placeholder ground truth
        flagged_ph = sum(1 for i in ph_idx if per[i]["has_defect"])
        flagged_clean = sum(1 for i in clean_idx if per[i]["has_defect"])
        ph_mentions = sum(1 for i in ph_idx if per[i]["mentions_ph"])
        results[cond] = {
            "mean_score_all": round(statistics.mean(p["score"] for p in per), 3),
            "mean_score_placeholder_slides": round(statistics.mean(per[i]["score"] for i in ph_idx), 3),
            "mean_score_clean_slides": round(statistics.mean(per[i]["score"] for i in clean_idx), 3),
            "placeholder_detection_recall": round(flagged_ph / len(ph_idx), 3),
            "false_flag_rate_clean": round(flagged_clean / len(clean_idx), 3),
            "explicit_placeholder_mentions": ph_mentions,  # critique literally cites 添加/placeholder
            "per_slide": per,
        }
        r = results[cond]
        print(f"  [{cond:13s}] recall_ph={r['placeholder_detection_recall']:.2f} "
              f"explicit_ph_mentions={ph_mentions}/{len(ph_idx)} "
              f"score(ph={r['mean_score_placeholder_slides']:.2f} vs clean={r['mean_score_clean_slides']:.2f}) "
              f"false_flag_clean={r['false_flag_rate_clean']:.2f}", flush=True)

    out = {
        "deck": Path(args.pptx).name, "n_slides": n,
        "placeholder_ground_truth": {"slides_with_placeholders": len(ph_idx), "placeholder_slide_idx": ph_idx, **ps},
        "conditions": results,
        "note": "Real Hermes pre-sales deck; placeholders are a semantic-completeness defect the "
                "geometry linter is blind to by construction. DV = examiner detection recall vs verifiable "
                "placeholder ground truth. Examiner = the Part 1/2 quality gradient (the IV).",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
