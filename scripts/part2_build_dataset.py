"""Build the Part 2 training dataset (all 12 defects, full severity grids).

Freeform + template (real snap-to-master), >=30% clean negatives, held-out
severity and held-out defect splits for OOD generalization eval. Writes:
  data/part2/manifest.jsonl              (everything)
  data/part2/manifest_train.jsonl        (split == train)
  data/part2/manifest_eval_test.jsonl    (split == test/val, in-domain held-out)
  data/part2/manifest_eval_ood_severity.jsonl
  data/part2/manifest_eval_ood_defect.jsonl
and prints the composition.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from slide_examiner.ingest import load_deck_json
from slide_examiner.synthetic import SyntheticBuildConfig, build_synthetic_manifest

REPO = Path(__file__).resolve().parents[1]
DECKS_DIR = REPO / "data" / "part2" / "decks"
OUT = REPO / "data" / "part2" / "manifest.jsonl"

HELDOUT_SEVERITIES = (16.0, 0.1, 8.0, 2.0, 6.0, 90.0)
HELDOUT_DEFECTS = ("G4_FONT_SIZE_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION")
EXAMPLES_PER_CELL = 60


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
    out_dir = REPO / "runs" / "part2" / f"build_{cond}"
    manifest = REPO / "data" / "part2" / f"manifest_{cond}.jsonl"
    build_synthetic_manifest(slides, decks, output_dir=out_dir, manifest_path=manifest, config=cfg)
    return [json.loads(l) for l in manifest.open() if l.strip()]


def main() -> None:
    records: list[dict] = []
    for cond in ("freeform", "template"):
        recs = build_condition(cond)
        for r in recs:
            c = r.get("metadata", {}).get("template_condition", cond)
            r["sample_id"] = f"{r['sample_id']}__{c}"
        records.extend(recs)
    records.sort(key=lambda r: str(r.get("sample_id")))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as h:
        for r in records:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")

    def split_of(r):
        return r.get("metadata", {}).get("split", "train")

    buckets = {
        "train": [r for r in records if split_of(r) == "train"],
        "eval_test": [r for r in records if split_of(r) in ("test", "val")],
        "eval_ood_severity": [r for r in records if split_of(r) == "ood_severity"],
        "eval_ood_defect": [r for r in records if split_of(r) == "ood_defect"],
    }
    for name, recs in buckets.items():
        path = REPO / "data" / "part2" / f"manifest_{name}.jsonl"
        with path.open("w", encoding="utf-8") as h:
            for r in recs:
                h.write(json.dumps(r, ensure_ascii=False) + "\n")

    bt = collections.Counter(dtype(r) for r in records)
    split = collections.Counter(split_of(r) for r in records)
    neg = sum(1 for r in records if dtype(r) == "NO_DEFECT")
    print(json.dumps({
        "total": len(records),
        "negatives_pct": round(neg / len(records), 3),
        "by_type": dict(sorted(bt.items())),
        "by_split": dict(split),
        "bucket_sizes": {k: len(v) for k, v in buckets.items()},
        "out": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
