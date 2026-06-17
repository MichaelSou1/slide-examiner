"""Build the expanded Part 1 dataset (all 12 defects, full severity grids).

Freeform + template (real snap-to-master) conditions, >=30% clean negatives,
held-out severity and held-out defect splits. Writes data/part1/manifest.jsonl
and prints the composition.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from slide_examiner.ingest import load_deck_json
from slide_examiner.synthetic import SyntheticBuildConfig, build_synthetic_manifest

REPO = Path(__file__).resolve().parents[1]
DECKS_DIR = REPO / "data" / "part1" / "decks"
OUT = REPO / "data" / "part1" / "manifest.jsonl"

# Held out for OOD generalization tests.
HELDOUT_SEVERITIES = (16.0, 0.1, 8.0, 2.0, 6.0, 90.0)  # one mid value per geometry/density grid
HELDOUT_DEFECTS = ("G4_FONT_SIZE_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION")
EXAMPLES_PER_CELL = 4


def dtype(rec: dict) -> str:
    labels = [x.get("type") for x in rec.get("labels", [])]
    return labels[0] if labels else "NO_DEFECT"


def build_condition(cond: str) -> list[dict]:
    decks = [load_deck_json(p) for p in sorted(DECKS_DIR.glob("*.json"))]
    slides = [s for d in decks for s in d.slides]
    cfg = SyntheticBuildConfig(
        examples_per_cell=EXAMPLES_PER_CELL,
        template_condition=cond,
        heldout_severities=HELDOUT_SEVERITIES,
        heldout_defect_types=HELDOUT_DEFECTS,
        negative_ratio=0.3,
    )
    out_dir = REPO / "runs" / "part1" / f"build_{cond}"
    manifest = REPO / "data" / "part1" / f"manifest_{cond}.jsonl"
    build_synthetic_manifest(slides, decks, output_dir=out_dir, manifest_path=manifest, config=cfg)
    return [json.loads(l) for l in manifest.open() if l.strip()]


def main() -> None:
    records: list[dict] = []
    for cond in ("freeform", "template"):
        recs = build_condition(cond)
        for r in recs:  # unique ids per condition (the builder reuses ids across conditions)
            c = r.get("metadata", {}).get("template_condition", cond)
            r["sample_id"] = f"{r['sample_id']}__{c}"
        records.extend(recs)

    records.sort(key=lambda r: str(r.get("sample_id")))
    with OUT.open("w", encoding="utf-8") as h:
        for r in records:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")

    bt = collections.Counter(dtype(r) for r in records)
    split = collections.Counter(r.get("metadata", {}).get("split") for r in records)
    cond = collections.Counter(r.get("metadata", {}).get("template_condition") for r in records)
    lvl = collections.Counter("deck" if r.get("deck") else "slide" for r in records)
    neg = sum(1 for r in records if dtype(r) == "NO_DEFECT")
    print(json.dumps({
        "total": len(records),
        "negatives_pct": round(neg / len(records), 3),
        "by_type": dict(sorted(bt.items())),
        "by_split": dict(split),
        "by_condition": dict(cond),
        "by_level": dict(lvl),
        "out": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
