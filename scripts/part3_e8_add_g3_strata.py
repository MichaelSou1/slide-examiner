#!/usr/bin/env python3
"""E8 — incrementally ADD large G3 strata (48, 64 px) to the saturation tail.

The audited-clean coverage_internal / geometry_internal corpora top out at 32 px
(= 1.67 % of the 1920-wide render). To show VLM detection SATURATES on clearly
visible misalignment we add two larger strata (48 px = 2.5 %, 64 px = 3.3 %) WITHOUT
re-sampling/re-rendering the existing 2-32 px records (which passed the integrity
audit). Uses the SAME production builder (`build_synthetic_manifest` -> internal G3
injector -> Playwright `render_manifest`), filters to G3 only, qualifies sample_ids
by template_condition exactly like the main regen, and APPENDS to the existing file.

Usage (slide-examiner env, has playwright):
  python scripts/part3_e8_add_g3_strata.py --target both --severities 48 64
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner import synthetic as synth  # noqa: E402
from slide_examiner.ingest import load_deck_json  # noqa: E402
from slide_examiner.render import render_manifest  # noqa: E402
from slide_examiner.synthetic import SyntheticBuildConfig, build_synthetic_manifest  # noqa: E402
from slide_examiner.taxonomy import DEFECTS  # noqa: E402

G3 = "G3_ALIGNMENT_OFFSET"
TARGETS = {
    "part1": dict(decks=REPO / "data/part1/decks", epc=8,
                  runs=REPO / "runs/part3/e8_part1_internal",
                  out=REPO / "data/part1/manifest_geometry_internal.jsonl"),
    "coverage": dict(decks=REPO / "data/part2/decks", epc=10,
                     runs=REPO / "runs/part3/e8_coverage_internal",
                     out=REPO / "data/part3/manifest_coverage_internal.jsonl"),
}


def build_g3(target: str, condition: str, severities) -> list[dict]:
    cfg_t = TARGETS[target]
    decks = [load_deck_json(p) for p in sorted(Path(cfg_t["decks"]).glob("*.json"))]
    slides = [s for d in decks for s in d.slides]
    # restrict the builder to G3 only, at the new severities
    synth.DEFECTS = {G3: replace(DEFECTS[G3], severities=tuple(severities))}
    try:
        cfg = SyntheticBuildConfig(examples_per_cell=cfg_t["epc"], template_condition=condition,
                                   heldout_severities=(), heldout_defect_types=(), negative_ratio=0.0)
        out_dir = Path(cfg_t["runs"]) / f"{condition}_g3sat"
        manifest = Path(cfg_t["out"]).with_suffix(f".g3sat.{condition}.jsonl")
        build_synthetic_manifest(slides, decks, output_dir=out_dir, manifest_path=manifest, config=cfg)
        print(f"[{target}/{condition}] rendering new G3 strata via Playwright ...")
        render_manifest(manifest, out_dir, output_manifest=manifest)
        recs = [json.loads(l) for l in manifest.open() if l.strip()]
        manifest.unlink(missing_ok=True)
    finally:
        synth.DEFECTS = DEFECTS
    # keep ONLY G3 defectives (no negatives; existing manifest already has them)
    g3 = [r for r in recs if (r.get("labels") or [{}])[0].get("type") == G3]
    for r in g3:
        c = r.get("metadata", {}).get("template_condition", condition)
        if not str(r["sample_id"]).endswith(f"__{c}"):
            r["sample_id"] = f"{r['sample_id']}__{c}"
    return g3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["part1", "coverage", "both"], default="both")
    ap.add_argument("--severities", nargs="+", type=int, default=[48, 64])
    ap.add_argument("--conditions", nargs="+", default=["freeform", "template"])
    args = ap.parse_args()
    targets = ["coverage", "part1"] if args.target == "both" else [args.target]

    for target in targets:
        out = Path(TARGETS[target]["out"])
        existing = [json.loads(l) for l in out.open() if l.strip()]
        have = {r["sample_id"] for r in existing}
        new = []
        for cond in args.conditions:
            for r in build_g3(target, cond, args.severities):
                if r["sample_id"] not in have:
                    new.append(r); have.add(r["sample_id"])
        merged = existing + new
        merged.sort(key=lambda r: str(r.get("sample_id")))
        with out.open("w", encoding="utf-8") as fh:
            for r in merged:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        # report
        addstrat = collections.Counter(
            (r["labels"][0]["metadata"] or {}).get("offset_px") for r in new)
        rendered = sum(1 for r in new if r.get("image_path") and Path(r["image_path"]).exists())
        print(f"[{target}] appended {len(new)} G3 records -> {out} (total {len(merged)})")
        print(f"  new strata: {dict(addstrat)}   rendered on disk: {rendered}/{len(new)}")


if __name__ == "__main__":
    main()
