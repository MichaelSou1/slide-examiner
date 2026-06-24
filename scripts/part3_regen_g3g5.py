#!/usr/bin/env python3
"""P2 — canonically regenerate the G3/G5 diagnosis dataset under the internal-contrast
operationalisation (E8 redo). Drives the SAME `inject_slide_defect` dispatcher the rest
of the system uses (now internal-contrast) + the real Playwright renderer, over the
pool of clean slides that have a >=3-bullet aligned column. Magnitude strata per defect
so the re-run yields a psychometric curve at solid n.

Emits runs/part3/g3g5_internal/<id>/{clean,defective}.png +
data/part3/manifest_g3g5_internal.jsonl (part3_elicit-compatible).

Usage: python scripts/part3_regen_g3g5.py --n-slides 16
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.experiment import inject_slide_defect  # noqa: E402
from slide_examiner.ingest import load_slide_json  # noqa: E402
from slide_examiner.injection import _aligned_sibling_group  # noqa: E402
from slide_examiner.render import _RasterJob, _rasterize_jobs, slide_to_html  # noqa: E402

PART2 = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
RUNS = REPO / "runs/part3/g3g5_internal"
OUT = REPO / "data/part3/manifest_g3g5_internal.jsonl"
SEVERITIES = {"G3_ALIGNMENT_OFFSET": [8.0, 16.0, 32.0], "G5_BRAND_COLOR_VIOLATION": [12.0, 24.0, 40.0]}


def clean_pool(n):
    """Distinct clean slides that have a >=3 aligned bullet column (so internal-contrast
    injection is well-defined)."""
    seen, out = set(), []
    with PART2.open() as fh:
        for line in fh:
            r = json.loads(line)
            csp = r.get("metadata", {}).get("clean_slide_path")
            if not csp or csp in seen or not Path(csp).exists():
                continue
            slide = load_slide_json(csp)
            if _aligned_sibling_group(slide) is None:
                continue
            seen.add(csp)
            out.append((Path(csp).stem, slide))
            if len(out) >= n:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-slides", type=int, default=16)
    ap.add_argument("--width", type=int, default=1024)
    args = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    pool = clean_pool(args.n_slides)
    print(f"[pool] {len(pool)} clean slides with a bullet column")

    jobs, records, k = [], [], 0
    for sid, slide in pool:
        scale = args.width / slide.width
        h = max(1, round(args.width * slide.height / slide.width))
        cdir = RUNS / f"{sid}__clean"; cdir.mkdir(exist_ok=True)
        cpng = cdir / "clean.png"
        jobs.append(_RasterJob(html=slide_to_html(slide, scale=scale), output=cpng, width=args.width, height=h))
        for defect, sevs in SEVERITIES.items():
            for sev in sevs:
                inj = inject_slide_defect(slide, defect, severity=sev)
                lab = inj.label
                pid = f"{defect.split('_')[0].lower()}i_{int(sev)}_{k:03d}"
                ddir = RUNS / pid; ddir.mkdir(exist_ok=True)
                dpng = ddir / "defective.png"
                jobs.append(_RasterJob(html=slide_to_html(inj.defective, scale=scale),
                                       output=dpng, width=args.width, height=h))
                records.append({
                    "sample_id": pid, "image_path": str(dpng),
                    "labels": [{"type": defect, "target_element_ids": list(lab.target_element_ids),
                                "severity": lab.severity, "metadata": lab.metadata}],
                    "metadata": {"clean_image_path": str(cpng), "defective_image_path": str(dpng),
                                 "stratum": f"{defect.split('_')[0]}·{int(sev)}", "mode": lab.metadata.get("mode")},
                })
                k += 1

    print(f"[render] {len(jobs)} pages ...")
    _rasterize_jobs(jobs)
    with OUT.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    import collections
    by = collections.Counter(r["metadata"]["stratum"] for r in records)
    modes = collections.Counter(r["metadata"]["mode"] for r in records)
    print(f"[write] {OUT} ({len(records)} defectives over {len(pool)} cleans)")
    print(f"  strata: {dict(by)}")
    print(f"  modes : {dict(modes)} (want all 'internal')")


if __name__ == "__main__":
    main()
