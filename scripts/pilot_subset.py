"""Build a bounded, balanced Part 1 pilot subset manifest.

Takes the freeform + template synthetic manifests, keeps only the pilot defect
types, and deterministically downsamples to a small, balanced set so a real-VLM
probe stays cheap while still covering: 2+ severity tiers per geometry defect,
both template conditions, and a ~30% clean-negative floor.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FREEFORM = REPO / "data" / "pilot" / "manifest_freeform.jsonl"
TEMPLATE = REPO / "data" / "pilot" / "manifest_template.jsonl"
OUT = REPO / "data" / "pilot" / "manifest.jsonl"

PILOT = {
    "G1_TEXT_OVERFLOW",
    "G2_ELEMENT_OVERLAP",
    "S1_TITLE_BODY_MISMATCH",
    "S2_NARRATIVE_ORDER_BREAK",
    "NO_DEFECT",
}

# Per-(defect, condition) caps. Geometry defects are sampled evenly across their
# severity grid; semantic defects (single severity) keep their full small set.
PER_SEVERITY_CAP = {  # (defect, condition) -> max examples per severity bucket
    "G1_TEXT_OVERFLOW": 2,   # 5 severities x 2 x 2 conditions = 20
    "G2_ELEMENT_OVERLAP": 2,  # 4 severities x 2 x 2 conditions = 16
}
SEMANTIC_CAP = 6   # per condition -> S1 = 12, S2 = 12
NEGATIVE_CAP = 12  # per condition -> 24 negatives (~22% of ~84)


def dtype(rec: dict) -> str:
    labels = [item.get("type") for item in rec.get("labels", [])]
    return labels[0] if labels else "NO_DEFECT"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


def main() -> None:
    records = load(FREEFORM) + load(TEMPLATE)
    by_sev: dict[tuple, list[dict]] = collections.defaultdict(list)
    semantic: dict[tuple, list[dict]] = collections.defaultdict(list)
    negatives: dict[str, list[dict]] = collections.defaultdict(list)

    for rec in records:
        t = dtype(rec)
        if t not in PILOT:
            continue
        cond = rec.get("metadata", {}).get("template_condition")
        if t == "NO_DEFECT":
            negatives[cond].append(rec)
        elif t in PER_SEVERITY_CAP:
            sev = rec.get("metadata", {}).get("severity_grid_value")
            by_sev[(t, cond, sev)].append(rec)
        else:
            semantic[(t, cond)].append(rec)

    kept: list[dict] = []
    for (t, cond, sev), bucket in by_sev.items():
        kept.extend(bucket[: PER_SEVERITY_CAP[t]])
    for (t, cond), bucket in semantic.items():
        kept.extend(bucket[:SEMANTIC_CAP])
    for cond, bucket in negatives.items():
        kept.extend(bucket[:NEGATIVE_CAP])

    # The synthetic builder reuses identical sample_ids across the freeform and
    # template runs (the condition lives only in metadata). Make ids unique per
    # condition so renders, probe keys, and sample-paired attribution don't
    # collide between the two conditions.
    for rec in kept:
        cond = rec.get("metadata", {}).get("template_condition", "freeform")
        rec["sample_id"] = f"{rec['sample_id']}__{cond}"

    # Stable order by sample_id for reproducibility.
    kept.sort(key=lambda r: str(r.get("sample_id")))
    with OUT.open("w", encoding="utf-8") as handle:
        for rec in kept:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")

    bt = collections.Counter(dtype(r) for r in kept)
    bc = collections.Counter((dtype(r), r.get("metadata", {}).get("template_condition")) for r in kept)
    lvl = collections.Counter("deck" if r.get("deck") else "slide" for r in kept)
    print(json.dumps({
        "total": len(kept),
        "by_type": dict(bt),
        "by_level": dict(lvl),
        "by_type_condition": {f"{a}|{b}": n for (a, b), n in sorted(bc.items())},
        "out": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
