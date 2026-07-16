#!/usr/bin/env python3
"""E8 — generate the internal-contrast / magnitude G6 (margin) corpus (no GPU, Playwright).

Mirrors the GOOD G3/G5 pipeline (`part3_e8_regen_corpus`) so it inherits all the
bug-fixes: matched PER-DECK clean twins, freeform+template both rendered with
`metadata.template_condition`, 1920-frame magnitudes (render px == label), real
Playwright render.

G6 re-operationalisation (PAGE-OFFSET口径): the WHOLE content block translates toward the
left edge so the shifted-side (left) margin shrinks to `left_margin_px`, leaving asymmetric
whitespace on the right. Distinct from G3 misalignment by construction — every element moves
together, internal alignment preserved; only the block-vs-page position is wrong (a single
shifted element would instead be misalignment). Decidable from the slide alone (asymmetric
margins + edge-crowding). The balanced clean (96px both sides) is the matched twin; the
existing absolute linter (`detect_margin_violations`, 32px) fires once the leftmost element
< 32px from the edge, never on the balanced clean. Full range generated; report per-stratum.

Output: data/part3/manifest_g6_internal.jsonl (part2/coverage deck pool).

Usage (slide-examiner env, has playwright):
  python scripts/part3_e8_make_g6_internal.py
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

G6 = "G6_MARGIN_VIOLATION"
# the resulting shifted-side (left) margin after the whole block translates left (px in the
# 1920 frame); content starts balanced at 96px both sides. 80=mild asymmetry ... 0=leftmost
# flush with the edge ... -16=content overruns the edge (clipped). Smaller = worse.
SEVERITIES = (80, 64, 48, 32, 16, 8, 0, -16)
DECKS = REPO / "data/part2/decks"
RUNS = REPO / "runs/part3/e8_g6_internal"
OUT = REPO / "data/part3/manifest_g6_internal.jsonl"
EPC = 10  # 8 strata x 10 = 80 defective + matched clean twins + NO_DEFECT negatives


def build_one(condition: str, *, severities: tuple[int, ...], epc: int,
              runs: Path, out: Path) -> Path:
    decks = [load_deck_json(p) for p in sorted(DECKS.glob("*.json"))]
    slides = [s for d in decks for s in d.slides]
    synth.DEFECTS = {G6: replace(DEFECTS[G6], severities=severities)}
    try:
        cfg = SyntheticBuildConfig(examples_per_cell=epc, template_condition=condition,
                                   heldout_severities=(), heldout_defect_types=(), negative_ratio=0.3)
        out_dir = runs / condition
        manifest = out.with_suffix(f".{condition}.jsonl")
        build_synthetic_manifest(slides, decks, output_dir=out_dir, manifest_path=manifest, config=cfg)
        print(f"[{condition}] rendering clean+defective via Playwright ...")
        render_manifest(manifest, out_dir, output_manifest=manifest)
    finally:
        synth.DEFECTS = DEFECTS
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--severities", nargs="+", type=int, default=list(SEVERITIES))
    ap.add_argument("--examples-per-cell", type=int, default=EPC)
    ap.add_argument("--conditions", nargs="+", choices=("freeform", "template"),
                    default=["freeform", "template"])
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    severities = tuple(args.severities)
    if not severities or args.examples_per_cell < 1:
        ap.error("--severities must be non-empty and --examples-per-cell >= 1")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    per_cond = []
    for cond in args.conditions:
        per_cond.append(build_one(cond, severities=severities,
                                  epc=args.examples_per_cell,
                                  runs=args.runs, out=args.out))
    records: list[dict] = []
    for manifest in per_cond:
        for line in manifest.open():
            if not line.strip():
                continue
            r = json.loads(line)
            c = r.get("metadata", {}).get("template_condition", "freeform")
            r["sample_id"] = f"{r['sample_id']}__{c}"
            records.append(r)
        manifest.unlink(missing_ok=True)
    records.sort(key=lambda r: str(r.get("sample_id")))
    with args.out.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    by_def = collections.Counter((r["labels"][0]["type"] if r.get("labels") else "NO_DEFECT") for r in records)
    modes = collections.Counter(r["labels"][0].get("metadata", {}).get("mode")
                                for r in records if r.get("labels") and r["labels"][0]["type"] == G6)
    conds = collections.Counter(r.get("metadata", {}).get("template_condition") for r in records)
    rendered = sum(1 for r in records if r.get("image_path") and Path(r["image_path"]).exists())
    print(f"\n[g6_internal] wrote {args.out} ({len(records)} records)")
    print(f"  by_defect : {dict(by_def)}")
    print(f"  G6 mode   : {dict(modes)} (want all 'internal')")
    print(f"  condition : {dict(conds)}")
    print(f"  rendered  : {rendered}/{len(records)} on-disk")


if __name__ == "__main__":
    main()
