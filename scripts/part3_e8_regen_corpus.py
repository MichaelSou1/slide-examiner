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
import random
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner import synthetic as synth  # noqa: E402
from slide_examiner.ingest import load_deck_json  # noqa: E402
from slide_examiner.dataset import slide_sample_from_injection  # noqa: E402
from slide_examiner.injection import (  # noqa: E402
    inject_alignment_offset,
    inject_brand_color_violation,
    inject_density_rule_violation,
    inject_image_text_contradiction,
    inject_margin_violation,
    inject_overlap,
    inject_text_overflow,
    inject_title_body_mismatch,
)
from slide_examiner.render import render_manifest  # noqa: E402
from slide_examiner.schemas import BBox, Element, Slide  # noqa: E402
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

HELDOUT_CLASSES = (
    "G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
    "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION",
    "S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION",
    "S6_IMAGE_TEXT_CONTRADICTION",
)


def _heldout_slides(seed: int, n: int, template_family: str = "w5_novel_seeded") -> list[Slide]:
    """Create seed-controlled, visually new calibration templates.

    These are not resampled Part-1/2 decks: every slide has a coloured header,
    accent rail, footer, seeded palette/layout variant, and a visible chart.  The
    resulting base IDs and pixels therefore cannot collide with development data.
    """
    rng = random.Random(seed)
    topics = [
        ("Circular packaging rollout", "ReuseLoop", "returns", "rose", "fell"),
        ("Regional water resilience", "AquaPlan", "coverage", "improved", "declined"),
        ("Battery recycling network", "CellCycle", "recovery", "increased", "decreased"),
        ("Cold-chain modernization", "FreshTrack", "compliance", "climbed", "dropped"),
        ("Accessible transit program", "MoveAll", "ridership", "grew", "contracted"),
        ("Industrial heat recovery", "HeatBack", "efficiency", "advanced", "regressed"),
    ]
    palettes = [
        ("#132a3a", "#24b6a4", "#eaf8f6"), ("#36213e", "#f08a5d", "#fff3ed"),
        ("#173f5f", "#f6d55c", "#fffbea"), ("#243b2f", "#8fc93a", "#f4fae9"),
    ]
    slides: list[Slide] = []
    for i in range(n):
        title, product, metric, up, down = topics[i % len(topics)]
        dark, accent, pale = palettes[(i // len(topics)) % len(palettes)]
        d3_layout = template_family == "d3_split_panel_v1"
        rail_left = (i % 2 == 0) if not d3_layout else (i % 3 == 0)
        x0 = (900 if d3_layout else (180 if rail_left else 120))
        body_w = 820 if d3_layout else (1080 if rail_left else 1140)
        els = [
            # Treat the header as page chrome rather than a foreground shape so
            # the overlap linter does not count the intentional title-on-header
            # composition as a clean G2 defect.
            Element(f"h{i}", "background", BBox(48, 36, 1824, 114), "",
                    {"fill_color": dark}, z=0, metadata={"role": "decoration"}),
            Element(f"rail{i}", "shape", BBox((840 if d3_layout else (54 if rail_left else 1818)), 180, 48, 820), "",
                    {"fill_color": accent}, z=0, metadata={"role": "decoration"}),
            Element(f"title{i}", "title", BBox(120, 58, 1600, 64),
                    f"{title}: cohort {i + 1}", {"font_size_pt": 30, "color": "#ffffff"},
                    z=2, metadata={"role": "title", "text_level": "title",
                                   "allow_overlap_with": [f"h{i}"]}),
        ]
        bullets = [
            f"{product} completed the independent baseline audit",
            f"The first region established a measurable {metric} baseline",
            f"Operators approved the staged deployment safeguards",
            f"The next checkpoint links funding to verified {metric}",
        ]
        for j, text in enumerate(bullets):
            els.append(Element(f"body{i}_{j}", "text", BBox(x0, 225 + j * 125, body_w, 82),
                               text, {"font_size_pt": 22, "color": "#263238"}, z=2,
                               metadata={"role": "body", "text_level": "body"}))
        claim = f"Verified {metric} {up} in every measured quarter"
        false_claim = f"Verified {metric} {down} in every measured quarter"
        els.append(Element(f"fig{i}", "diagram", BBox((190 if d3_layout else 1390), 240,
                                                       (560 if d3_layout else 390), 410), "",
                           {"fill_color": pale, "color": accent}, z=1,
                           metadata={"role": "diagram", "diagram_claim": claim,
                                     "diagram_false_claim": false_claim, "diagram_trend": "up"}))
        # Keep the footer off the body column's x-coordinate.  Otherwise the
        # internal G5 injector can legitimately include it in the bullet colour
        # group, making the clean twin non-uniform.
        els.append(Element(f"footer{i}", "text", BBox(260, 940, 1420, 44),
                           f"CALIBRATION {seed} · {product} · independently generated",
                           {"font_size_pt": 13, "color": "#59636a"}, z=2,
                           metadata={"role": "footer", "text_level": "footer"}))
        slides.append(Slide(f"w5cal_{seed}_{i:04d}", tuple(els),
                            metadata={"source": template_family, "seed": seed,
                                      "template_family": template_family,
                                      "template_variant": f"{template_family}_{i % 8}"}))
    rng.shuffle(slides)
    return slides


def build_heldout(seed: int, pairs_per_class: int, runs: Path, out: Path,
                  template_family: str = "w5_novel_seeded") -> None:
    # Allocate a disjoint clean base slide to every class/pair.  This prevents a
    # clean render from being reused across labels and keeps paired controls
    # independent of the development corpora and of one another.
    slides = _heldout_slides(seed, pairs_per_class * len(HELDOUT_CLASSES), template_family)
    injectors = {
        "G1_TEXT_OVERFLOW": lambda s: inject_text_overflow(s, element_id=next(e.element_id for e in s.elements if e.metadata.get("role") == "body"), overflow_px=64),
        "G2_ELEMENT_OVERLAP": lambda s: inject_overlap(s, source_element_id=next(e.element_id for e in s.elements if e.metadata.get("role") == "diagram"), target_element_id=next(e.element_id for e in s.elements if e.metadata.get("role") == "body"), dx=(760 if template_family == "d3_split_panel_v1" else -400), dy=0, severity_iou=.35),
        "G3_ALIGNMENT_OFFSET": lambda s: inject_alignment_offset(s, offset_px=32),
        "G5_BRAND_COLOR_VIOLATION": lambda s: inject_brand_color_violation(s, delta_e=40),
        "G6_MARGIN_VIOLATION": lambda s: inject_margin_violation(s, page_margin_px=-32),
        "S1_TITLE_BODY_MISMATCH": inject_title_body_mismatch,
        "S4_DENSITY_RULE_VIOLATION": lambda s: inject_density_rule_violation(s, element_id=next(e.element_id for e in s.elements if e.metadata.get("role") == "body"), target_words=150),
        "S6_IMAGE_TEXT_CONTRADICTION": inject_image_text_contradiction,
    }
    samples = []
    for class_index, defect in enumerate(HELDOUT_CLASSES):
        class_slides = slides[class_index * pairs_per_class:(class_index + 1) * pairs_per_class]
        for slide in class_slides:
            injected = injectors[defect](slide)
            sample = slide_sample_from_injection(
                injected, sample_id=f"{slide.slide_id}_{defect}",
                output_dir=runs / "freeform", template_condition="freeform")
            sample = replace(sample, metadata={**sample.metadata, "split": "w5_heldout",
                                               "generation_seed": seed,
                                               "template_family": template_family})
            samples.append(sample)
    from slide_examiner.dataset import write_manifest
    out.parent.mkdir(parents=True, exist_ok=True)
    write_manifest(samples, out)
    print(f"[heldout] rendering {len(samples)} defective/clean pairs ...")
    render_manifest(out, runs / "freeform", output_manifest=out)
    print(f"[heldout] wrote {out}: {len(samples)} pairs, seed={seed}")


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
    ap.add_argument("--target", choices=["part1", "coverage", "both", "heldout"], default="both")
    ap.add_argument("--conditions", nargs="+", default=["freeform", "template"])
    ap.add_argument("--seed", type=int, default=20260716)
    ap.add_argument("--pairs-per-class", type=int, default=150)
    ap.add_argument("--heldout-runs", type=Path, default=REPO / "runs/part3/w5_heldout")
    ap.add_argument("--heldout-out", type=Path, default=REPO / "data/part3/w5_heldout.jsonl")
    args = ap.parse_args()

    if args.target == "heldout":
        if args.pairs_per_class < 1:
            ap.error("--pairs-per-class must be >= 1")
        build_heldout(args.seed, args.pairs_per_class, args.heldout_runs, args.heldout_out)
        return

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
