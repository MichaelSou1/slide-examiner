"""Freeze the Part 1 dataset: snapshot every manifest with a content hash and
record the coverage / pairing / held-out / degradation facts the three-track
design (SPEC §3.0, todo §7) requires before the full matrix is reported.

Writes:
  runs/probe/part1_dataset_freeze.json  — machine-readable freeze record + sha256
  reports/part1_dataset_freeze.md       — human-readable freeze note

Usage: PYTHONPATH=. python scripts/part1_freeze_dataset.py
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUMMARY = REPO / "runs" / "probe" / "part1_dataset_freeze.json"
REPORT = REPO / "reports" / "part1_dataset_freeze.md"

MANIFESTS = {
    "full": "data/part1/manifest.jsonl",
    "rendered": "data/part1/manifest_rendered.jsonl",
    "geometry": "data/part1/manifest_geometry.jsonl",
    "sgroup": "data/part1/manifest_sgroup.jsonl",
    "freeform": "data/part1/manifest_freeform.jsonl",
    "template": "data/part1/manifest_template.jsonl",
    "s6_img": "data/part1_img/manifest_s6_rendered.jsonl",
    "g13_fc_1536": "data/part1_fc/manifest_1536.jsonl",
    "g13_fc_2048": "data/part1_fc/manifest_2048.jsonl",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load(path: Path):
    return [json.loads(line) for line in path.open() if line.strip()]


def main() -> None:
    full = load(REPO / MANIFESTS["full"])
    rendered = load(REPO / MANIFESTS["rendered"])

    def typ(rec):
        labs = rec.get("labels") or []
        t = labs[0]["type"] if labs else "NO_DEFECT"
        return "NO_DEFECT" if t == "NO_DEFECT" else t

    types = collections.Counter(typ(r) for r in full)
    splits = collections.Counter(r["metadata"].get("split", "?") for r in full)
    conds = collections.Counter(r["metadata"].get("template_condition", "none") for r in full)
    held_out = {
        sp: dict(collections.Counter(typ(r) for r in full if r["metadata"].get("split") == sp))
        for sp in ("ood_severity", "ood_defect")
    }
    n_neg = types["NO_DEFECT"]
    paired_img = sum(1 for r in rendered
                     if r["metadata"].get("clean_image_path") and r["metadata"].get("defective_image_path"))

    record = {
        "frozen": True,
        "n_samples": len(full),
        "defect_types": dict(sorted(types.items())),
        "splits": dict(splits),
        "template_conditions": dict(conds),
        "held_out": held_out,
        "negative_ratio": round(n_neg / len(full), 3),
        "paired_clean_image_coverage": [paired_img, len(rendered)],
        "sha256": {name: sha256(REPO / rel) for name, rel in MANIFESTS.items()},
        "degradations": [
            f"negative ratio {round(n_neg/len(full),3)} < 0.30 target "
            "(80 paired clean negatives; pairing prioritized over absolute count)",
            f"page-level paired-clean image coverage {paired_img}/{len(rendered)}; "
            "the 24 unpaired are deck-level S2/S3/S5 (paired at deck granularity, not single-image)",
            "S3 terminology + S6 image-text pairs are deck-level / image-corpus "
            "(data/part1_img); single-image clean pairing not applicable",
        ],
        "measurability": {
            "S6_image_text": "data/part1_img/manifest_s6_rendered.jsonl — figures drawn "
                             "with ▲/▼ + claim, contradiction only in pixels (measurable)",
            "S3_terminology": "deck-level canonical-vs-variant term swap present in sgroup "
                             "manifest (measurable; Track P forced-choice built separately)",
            "template_is_real_snap_to_master": "verified by linter absorption "
                             "(runs/probe/part1_linter_summary.json: G1/G2/G3/G6 absorb=1.0)",
        },
    }
    SUMMARY.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# Part 1 dataset — FROZEN\n",
         f"`{len(full)}` samples, frozen by sha256 (see `part1_dataset_freeze.json`). "
         "Pairing-first per SPEC §3.0: every positive carries a same-base clean counterpart "
         "for balanced-accuracy / pairwise control.\n",
         "## Coverage\n",
         "| defect | n |", "|---|---|"]
    for t, c in sorted(types.items()):
        L.append(f"| {t} | {c} |")
    L.append("")
    L.append(f"- **splits**: {dict(splits)}")
    L.append(f"- **template conditions**: {dict(conds)} (template = real snap-to-master, "
             "linter-verified absorption)")
    L.append(f"- **held-out severity** (`ood_severity`): {held_out['ood_severity']}")
    L.append(f"- **held-out defect** (`ood_defect`): {held_out['ood_defect']}")
    L.append(f"- **negative ratio**: {round(n_neg/len(full),3)} ({n_neg}/{len(full)})")
    L.append(f"- **paired-clean image coverage**: {paired_img}/{len(rendered)} page-level "
             "(deck-level S2/S3/S5 paired at deck granularity)")
    L.append("\n## Recorded degradations\n")
    for d in record["degradations"]:
        L.append(f"- {d}")
    L.append("\n## Measurability gates (SPEC §3.0)\n")
    for k, v in record["measurability"].items():
        L.append(f"- **{k}**: {v}")
    L.append("\n## Frozen manifest hashes\n")
    for name, h in record["sha256"].items():
        L.append(f"- `{MANIFESTS[name]}` — `{h[:16]}…`")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY.relative_to(REPO)} and {REPORT.relative_to(REPO)}")
    print(f"  {len(full)} samples, neg {record['negative_ratio']}, "
          f"paired {paired_img}/{len(rendered)}")


if __name__ == "__main__":
    main()
