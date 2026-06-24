#!/usr/bin/env python3
"""E8 — relative-misalignment G3 variant (perceptually anchored).

The shipped G3 injector translates one *full-width* element by a few px against an
invisible absolute reference (expected x). It breaks no VISIBLE alignment relation:
the title (x=96, width 1728) was never lined up with the body bullets (x=144), so a
32px shift just moves it slightly — "acceptable" to a human, by design. That makes
G3-as-injected ill-posed as a standalone perceptual defect (you can only judge it
against the clean twin).

A defect humans actually catch is a RELATIVE misalignment: one element out of line
with its *aligned siblings*. This generator builds that — it takes a clean slide with
a column of aligned body bullets (all at the same x) and shifts the MIDDLE bullet
right by Δ, so it is visibly indented out of the column with no reference needed.
Two strata (Δ=48px subtle, Δ=96px obvious). Renders via the real Playwright pipeline.

Emits runs/part3/g3_rel/<id>/{clean,defective}.png + data/part3/g3_relmisalign.jsonl
(strict-sampler-compatible, explicit stratum rel·{Δ}px).

Usage: python scripts/part3_g3_relmisalign.py --per-cell 4 --deltas 48 96
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.ingest import load_slide_json  # noqa: E402
from slide_examiner.render import _RasterJob, _rasterize_jobs, slide_to_html  # noqa: E402

PART2 = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
RUNS = REPO / "runs/part3/g3_rel"
OUT_MANIFEST = REPO / "data/part3/g3_relmisalign.jsonl"


def aligned_bullet_bases(limit):
    """(sample_id, clean_slide, [aligned body element_ids]) for clean G3 slides whose
    body bullets share one x (a real alignment column to break)."""
    out = []
    seen = set()
    with PART2.open() as fh:
        for line in fh:
            r = json.loads(line)
            if (r.get("labels") or [{}])[0].get("type") != "G3_ALIGNMENT_OFFSET":
                continue
            if "__template" in (r.get("image_path") or ""):
                continue
            csp = r["metadata"].get("clean_slide_path")
            if not csp or not Path(csp).exists() or csp in seen:
                continue
            slide = load_slide_json(csp)
            bodies = [e for e in slide.elements if e.type in ("text", "body")]
            xs = {round(e.bbox.x) for e in bodies}
            if len(bodies) >= 3 and len(xs) == 1:  # >=3 bullets sharing one x
                seen.add(csp)
                out.append((r.get("sample_id"), slide, [e.element_id for e in bodies]))
            if len(out) >= limit:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=4)
    ap.add_argument("--deltas", type=float, nargs="+", default=[48.0, 96.0])
    ap.add_argument("--seed", type=int, default=20260624)
    ap.add_argument("--width", type=int, default=1024)
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    bases = aligned_bullet_bases(args.per_cell * len(args.deltas) + 4)
    if not bases:
        print("[err] no aligned-bullet clean G3 bases found", file=sys.stderr)
        sys.exit(1)

    jobs, records, k = [], [], 0
    for dx in args.deltas:
        for j in range(args.per_cell):
            sid, slide, body_ids = bases[k % len(bases)]
            mid = body_ids[len(body_ids) // 2]  # shift the MIDDLE bullet out of the column
            el = slide.get(mid)
            new_bbox = replace(el.bbox, x=el.bbox.x + dx)
            defslide = slide.replace_element(replace(el, bbox=new_bbox))
            scale = args.width / slide.width
            h = max(1, round(args.width * slide.height / slide.width))
            pid = f"g3rel_{int(dx)}_{k:02d}"
            ddir = RUNS / pid; ddir.mkdir(exist_ok=True)
            cpng, dpng = ddir / "clean.png", ddir / "defective.png"
            jobs.append(_RasterJob(html=slide_to_html(slide, scale=scale), output=cpng, width=args.width, height=h))
            jobs.append(_RasterJob(html=slide_to_html(defslide, scale=scale), output=dpng, width=args.width, height=h))
            records.append({
                "sample_id": pid, "image_path": str(dpng),
                "labels": [{"type": "G3_ALIGNMENT_OFFSET", "target_element_ids": [mid],
                            "metadata": {"axis": "x", "offset_px": dx, "mode": "relative",
                                         "sibling_x": el.bbox.x}}],
                "metadata": {"clean_image_path": str(cpng), "defective_image_path": str(dpng),
                             "stratum": f"rel·{int(dx)}px", "mode": "relative"},
            })
            k += 1

    print(f"[render] {len(jobs)} pages via playwright ...")
    _rasterize_jobs(jobs)
    with OUT_MANIFEST.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[write] {OUT_MANIFEST} ({len(records)} relative-misalignment G3 pairs)")
    for rec in records:
        m = rec["labels"][0]["metadata"]
        print(f"  {rec['sample_id']:18s} shift {rec['labels'][0]['target_element_ids'][0]} +{int(m['offset_px'])}px  ({rec['metadata']['stratum']})")


if __name__ == "__main__":
    main()
