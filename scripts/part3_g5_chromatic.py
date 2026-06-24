#!/usr/bin/env python3
"""E8 — chromatic (hue) G5 brand-colour variant.

The shipped G5 injector (`_color_at_delta_e`) walks a fixed gray-axis direction, so
for a near-black title (#111111) it only *lightens* — an **achromatic** change that
reads as "thinner", not "wrong colour" (the spot-check caught this). A realistic
brand-colour violation is a **hue** swap. This generator builds the same defect as a
chromatic change: the brand near-black title is recoloured toward a saturated
off-brand hue, calibrated to a target ΔE2000 with the *same* `color_delta_e` used by
the achromatic injector — so the perceptual test can contrast achromatic-vs-chromatic
**at matched ΔE2000**. Renders go through the real Playwright pipeline (faithful).

Emits renders under runs/part3/g5_chroma/<id>/{clean,defective}.png and a manifest
data/part3/g5_chromatic.jsonl (strict-sampler-compatible records, with an explicit
`stratum`).

Usage: python scripts/part3_g5_chromatic.py --per-cell 5 --seed 20260624
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.geometry import color_delta_e  # noqa: E402
from slide_examiner.ingest import load_slide_json  # noqa: E402
from slide_examiner.render import _RasterJob, _rasterize_jobs, slide_to_html  # noqa: E402

PART2 = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
RUNS = REPO / "runs/part3/g5_chroma"
OUT_MANIFEST = REPO / "data/part3/g5_chromatic.jsonl"

# Saturated, clearly off-brand hues (endpoints of the recolour ray). Distinct enough
# that none is mistakable for a near-black brand colour.
HUES = {
    "red": (203, 36, 41), "blue": (26, 95, 180), "green": (38, 162, 105),
    "orange": (224, 120, 20), "purple": (129, 61, 156),
}


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def _rgb(hx):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))


def chromatic_color_at_delta_e(expected_rgb, target_delta_e, endpoint):
    """Point on the segment expected_rgb -> endpoint (a saturated hue) whose ΔE2000 to
    expected_rgb is closest to target (so it's clearly hued, calibrated in magnitude)."""
    best, best_err = expected_rgb, abs(color_delta_e(expected_rgb, expected_rgb) - target_delta_e)
    for i in range(1, 201):
        t = i / 200.0
        cand = tuple(int(round(e + (p - e) * t)) for e, p in zip(expected_rgb, endpoint))
        err = abs(color_delta_e(expected_rgb, cand) - target_delta_e)
        if err < best_err:
            best, best_err = cand, err
    return best


def clean_g5_slides(limit):
    """(sample_id, target_element_id, expected_color, clean_slide) for distinct clean G5 bases."""
    out = []
    with PART2.open() as fh:
        for line in fh:
            r = json.loads(line)
            lab = (r.get("labels") or [{}])[0]
            if lab.get("type") != "G5_BRAND_COLOR_VIOLATION":
                continue
            if "__template" in (r.get("image_path") or ""):
                continue
            csp = r["metadata"].get("clean_slide_path")
            if not csp or not Path(csp).exists():
                continue
            tgt = (lab.get("target_element_ids") or [None])[0]
            exp = lab.get("metadata", {}).get("expected_color", "#111111")
            out.append((r.get("sample_id"), tgt, exp, load_slide_json(csp)))
            if len(out) >= limit:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=5, help="pairs per ΔE level (hues cycled)")
    ap.add_argument("--deltas", type=float, nargs="+", default=[12.0, 24.0])
    ap.add_argument("--seed", type=int, default=20260624)
    ap.add_argument("--width", type=int, default=1024)
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    hue_names = list(HUES)
    bases = clean_g5_slides(args.per_cell * len(args.deltas) + 4)
    if len(bases) < args.per_cell:
        print(f"[warn] only {len(bases)} clean G5 bases available", file=sys.stderr)

    jobs, records = [], []
    k = 0
    for de in args.deltas:
        for j in range(args.per_cell):
            base = bases[(k) % len(bases)]
            sid, tgt, exp_hex, slide = base
            hue = hue_names[j % len(hue_names)]
            exp_rgb = _rgb(exp_hex)
            new_rgb = chromatic_color_at_delta_e(exp_rgb, de, HUES[hue])
            realized = round(color_delta_e(exp_rgb, new_rgb), 1)
            el = slide.get(tgt)
            new_style = dict(el.style); new_style["color"] = _hex(new_rgb)
            defslide = slide.replace_element(replace(el, style=new_style))
            h = max(1, round(args.width * slide.height / slide.width))
            pid = f"g5chroma_{int(de)}_{hue}_{k:02d}"
            ddir = RUNS / pid; ddir.mkdir(exist_ok=True)
            cpng, dpng = ddir / "clean.png", ddir / "defective.png"
            jobs.append(_RasterJob(html=slide_to_html(slide, scale=args.width / slide.width),
                                   output=cpng, width=args.width, height=h))
            jobs.append(_RasterJob(html=slide_to_html(defslide, scale=args.width / slide.width),
                                   output=dpng, width=args.width, height=h))
            records.append({
                "sample_id": pid, "image_path": str(dpng),
                "labels": [{"type": "G5_BRAND_COLOR_VIOLATION", "target_element_ids": [tgt],
                            "metadata": {"expected_color": exp_hex, "actual_color": _hex(new_rgb),
                                         "delta_e": realized, "hue": hue, "mode": "chromatic"}}],
                "metadata": {"clean_image_path": str(cpng), "defective_image_path": str(dpng),
                             "stratum": f"ΔE≈{int(de)}·hue", "mode": "chromatic"},
            })
            k += 1

    print(f"[render] {len(jobs)} pages via playwright ...")
    _rasterize_jobs(jobs)
    with OUT_MANIFEST.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[write] {OUT_MANIFEST} ({len(records)} chromatic G5 pairs)")
    for rec in records:
        m = rec["labels"][0]["metadata"]
        print(f"  {rec['sample_id']:26s} {m['hue']:7s} ΔE2000={m['delta_e']:5.1f} {m['expected_color']}->{m['actual_color']}")


if __name__ == "__main__":
    main()
