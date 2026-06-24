#!/usr/bin/env python3
"""E8 — internal-contrast G5 (the user's re-operationalisation of "colour defect").

"Brand-colour violation" needs an external brand palette to judge ("is THIS colour
wrong?") — undecidable from the slide alone, so model & human both abstain (E8
re-exam: model says "tie" 92% even on a visible hue). The fix (same principle as
relative-misalignment G3): make it an INTERNAL contrast — one bullet's text colour
differs from its sibling bullets. Now "which bullet's colour is inconsistent with the
rest?" is decidable from the slide alone, no reference needed.

Takes clean slides with a column of >=3 same-colour bullets and recolours the MIDDLE
one to a hue at a controlled ΔE2000 from its siblings (strata int·ΔE12/24/40·hue).
Renders via the real Playwright pipeline. Strict-sampler-compatible manifest.

Emits runs/part3/g5_internal/<id>/{clean,defective}.png + data/part3/g5_internal.jsonl.

Usage: python scripts/part3_g5_internal.py --per-cell 4 --deltas 12 24 40
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from slide_examiner.geometry import color_delta_e  # noqa: E402
from slide_examiner.render import _RasterJob, _rasterize_jobs, slide_to_html  # noqa: E402
from part3_g3_relmisalign import aligned_bullet_bases  # noqa: E402  (same bullet-column bases)
from part3_g5_chromatic import HUES, _hex, _rgb, chromatic_color_at_delta_e  # noqa: E402

RUNS = REPO / "runs/part3/g5_internal"
OUT_MANIFEST = REPO / "data/part3/g5_internal.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=4)
    ap.add_argument("--deltas", type=float, nargs="+", default=[12.0, 24.0, 40.0])
    ap.add_argument("--seed", type=int, default=20260624)
    ap.add_argument("--width", type=int, default=1024)
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    hue_names = list(HUES)
    bases = aligned_bullet_bases(args.per_cell * len(args.deltas) + 4)
    if not bases:
        print("[err] no aligned-bullet bases", file=sys.stderr); sys.exit(1)

    jobs, records, k = [], [], 0
    for de in args.deltas:
        for j in range(args.per_cell):
            sid, slide, body_ids = bases[k % len(bases)]
            mid = body_ids[len(body_ids) // 2]
            el = slide.get(mid)
            sib_rgb = _rgb(el.style.get("color", "#111111"))
            hue = hue_names[j % len(hue_names)]
            odd_rgb = chromatic_color_at_delta_e(sib_rgb, de, HUES[hue])
            realized = round(color_delta_e(sib_rgb, odd_rgb), 1)
            new_style = dict(el.style); new_style["color"] = _hex(odd_rgb)
            defslide = slide.replace_element(replace(el, style=new_style))
            scale = args.width / slide.width
            h = max(1, round(args.width * slide.height / slide.width))
            pid = f"g5int_{int(de)}_{hue}_{k:02d}"
            ddir = RUNS / pid; ddir.mkdir(exist_ok=True)
            cpng, dpng = ddir / "clean.png", ddir / "defective.png"
            jobs.append(_RasterJob(html=slide_to_html(slide, scale=scale), output=cpng, width=args.width, height=h))
            jobs.append(_RasterJob(html=slide_to_html(defslide, scale=scale), output=dpng, width=args.width, height=h))
            records.append({
                "sample_id": pid, "image_path": str(dpng),
                "labels": [{"type": "G5_BRAND_COLOR_VIOLATION", "target_element_ids": [mid],
                            "metadata": {"sibling_color": _hex(sib_rgb), "odd_color": _hex(odd_rgb),
                                         "delta_e": realized, "hue": hue, "mode": "internal_contrast"}}],
                "metadata": {"clean_image_path": str(cpng), "defective_image_path": str(dpng),
                             "stratum": f"int·ΔE{int(de)}·hue", "mode": "internal_contrast"},
            })
            k += 1

    print(f"[render] {len(jobs)} pages ...")
    _rasterize_jobs(jobs)
    with OUT_MANIFEST.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[write] {OUT_MANIFEST} ({len(records)} internal-contrast G5 pairs)")
    for rec in records:
        m = rec["labels"][0]["metadata"]
        print(f"  {rec['sample_id']:24s} odd bullet {rec['labels'][0]['target_element_ids'][0]} "
              f"{m['sibling_color']}->{m['odd_color']} ({m['hue']}, ΔE{m['delta_e']})")


if __name__ == "__main__":
    main()
