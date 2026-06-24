#!/usr/bin/env python3
"""E8 Data-regen — synthetic internal-contrast G3/G5 corpora (no GPU, Playwright).

The E8 re-operationalisation (G3 alignment / G5 brand-colour become an INTERNAL
contrast — one member shifted/recoloured out of an aligned sibling column, decidable
from the slide alone) invalidated the G3/G5 cells of two synthetic datasets:

  * the **Part-1** Modality-A/B/C attribution corpus  (paper Sec.4, Fig. attribution)
  * the **Part-3** hybrid-coverage set                (paper Table 2, Result 2a)

This rebuilds *only* the {G3,G5} cells through the SAME production pipeline the rest of
the corpus uses — ``build_synthetic_manifest`` (now driving the internal injectors via the
canonical ``inject_slide_defect`` dispatcher) then ``render_manifest`` (real Playwright
render of every clean + defective slide). Restricting to G3/G5 leaves every other class's
frozen numbers untouched; the other classes keep reusing their existing rendered manifests.

Each record carries the full schema (defective ``slide`` IR + ``oracle`` + ``pair`` with
clean/defective IR JSONs + ``metadata.render`` + ``labels``) plus matched NO_DEFECT
negatives, so Modality B/C (structure channel) and the symbolic linter both work, and the
VLM clean control (``clean_variant``) finds the paired clean image.

Usage (slide-examiner env — has playwright):
  python scripts/part3_e8_regen_corpus.py --target part1
  python scripts/part3_e8_regen_corpus.py --target coverage
  python scripts/part3_e8_regen_corpus.py --target both
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

G3G5 = ("G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION")
# Severity grids spanning the floor -> recovery range the E8 diagnosis established
# (G3 recovers by 16-32 px; chromatic G5 by dE2000 ~40). The taxonomy ceiling is
# dE 24, so we extend G5 to 40 here so the corpus can exhibit the very recovery the
# attribution / coverage are meant to measure; G3 keeps the canonical grid (its 2 px
# stratum is the re-anchored well-posed sub-threshold residue).
SEVERITIES = {
    "G3_ALIGNMENT_OFFSET": (2, 4, 8, 16, 32),
    "G5_BRAND_COLOR_VIOLATION": (6, 12, 24, 40),
}

# target -> (clean-deck dir, examples_per_cell, runs subdir, output manifest)
TARGETS = {
    "part1": dict(
        decks=REPO / "data/part1/decks",
        epc=8,  # G3 5 sev x8 = 40, G5 4 sev x8 = 32  -> matches the legacy Part-1 counts
        runs=REPO / "runs/part3/e8_part1_internal",
        out=REPO / "data/part1/manifest_geometry_internal.jsonl",
    ),
    "coverage": dict(
        decks=REPO / "data/part2/decks",
        epc=10,  # G3 50, G5 40 over the 28-deck Part-2 pool -> ample for Table-2 n=36-40
        runs=REPO / "runs/part3/e8_coverage_internal",
        out=REPO / "data/part3/manifest_coverage_internal.jsonl",
    ),
}


def build_one(target: str, condition: str) -> Path:
    cfg_t = TARGETS[target]
    decks = [load_deck_json(p) for p in sorted(Path(cfg_t["decks"]).glob("*.json"))]
    slides = [s for d in decks for s in d.slides]
    print(f"[{target}/{condition}] {len(decks)} decks, {len(slides)} slides")

    # restrict the production builder to G3/G5 (so no other class's frozen data is
    # touched) and override their severity grids to span floor -> recovery.
    synth.DEFECTS = {k: replace(DEFECTS[k], severities=SEVERITIES[k]) for k in G3G5}
    try:
        cfg = SyntheticBuildConfig(
            examples_per_cell=cfg_t["epc"],
            template_condition=condition,
            heldout_severities=(),
            heldout_defect_types=(),
            negative_ratio=0.3,
        )
        out_dir = Path(cfg_t["runs"]) / condition
        manifest = Path(cfg_t["out"]).with_suffix(f".{condition}.jsonl")
        build_synthetic_manifest(slides, decks, output_dir=out_dir, manifest_path=manifest, config=cfg)
    finally:
        synth.DEFECTS = DEFECTS  # restore
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["part1", "coverage", "both"], default="both")
    ap.add_argument("--conditions", nargs="+", default=["freeform", "template"])
    args = ap.parse_args()

    targets = ["part1", "coverage"] if args.target == "both" else [args.target]
    for target in targets:
        per_cond = []
        for cond in args.conditions:
            manifest = build_one(target, cond)
            print(f"[{target}/{cond}] rendering clean+defective via Playwright ...")
            render_manifest(manifest, Path(TARGETS[target]["runs"]) / cond, output_manifest=manifest)
            per_cond.append(manifest)

        # merge the per-condition manifests into the single target file, qualifying
        # sample_ids by template_condition (mirrors part2_build_dataset).
        records: list[dict] = []
        for manifest in per_cond:
            for line in manifest.open():
                if not line.strip():
                    continue
                r = json.loads(line)
                c = r.get("metadata", {}).get("template_condition", "freeform")
                r["sample_id"] = f"{r['sample_id']}__{c}"
                records.append(r)
        records.sort(key=lambda r: str(r.get("sample_id")))
        out = Path(TARGETS[target]["out"])
        with out.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        for manifest in per_cond:
            manifest.unlink(missing_ok=True)  # keep only the merged file

        by_def = collections.Counter(
            (r["labels"][0]["type"] if r.get("labels") else "NO_DEFECT") for r in records)
        modes = collections.Counter(
            r["labels"][0].get("metadata", {}).get("mode")
            for r in records if r.get("labels") and r["labels"][0]["type"] in G3G5)
        conds = collections.Counter(r.get("metadata", {}).get("template_condition") for r in records)
        rendered = sum(1 for r in records if r.get("image_path") and Path(r["image_path"]).exists())
        print(f"[{target}] wrote {out} ({len(records)} records)")
        print(f"  by_defect : {dict(by_def)}")
        print(f"  G3/G5 mode: {dict(modes)} (want all 'internal')")
        print(f"  condition : {dict(conds)}")
        print(f"  rendered  : {rendered}/{len(records)} have an on-disk image")


if __name__ == "__main__":
    main()
