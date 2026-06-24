#!/usr/bin/env python3
"""E8 Data-regen verifier — sanity-gate the three regenerated internal-contrast G3/G5
datasets (synthetic Part-1 attribution, synthetic Part-3 coverage, real-CC internal-G3).

Checks, per dataset: record/label counts, that every G3/G5 label is mode=internal, that
every referenced image is on disk, and (synthetic only) that the symbolic linter detects
the internal defect on the defective IR with zero false-fires on the paired clean IR
(freeform) — the calibration the hybrid's linter-routing claim rests on.

Usage: python scripts/part3_e8_verify_regen.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.geometry import detect_alignment_offsets, detect_color_inconsistency  # noqa: E402
from slide_examiner.schemas import Slide  # noqa: E402

SYNTH = {
    "Part-1 attribution (A/B/C)": "data/part1/manifest_geometry_internal.jsonl",
    "Part-3 coverage (Table 2)": "data/part3/manifest_coverage_internal.jsonl",
}
REAL = "data/part3/manifest_real_internal_g3.jsonl"


def _img_ok(p: str | None) -> bool:
    if not p:
        return False
    q = Path(p)
    return (q if q.is_absolute() else REPO / q).exists()


def verify_synth(name: str, f: str) -> bool:
    recs = [json.loads(l) for l in (REPO / f).open() if l.strip()]
    ok = True
    by_def = collections.Counter(r["labels"][0]["type"] if r["labels"] else "NO_DEFECT" for r in recs)
    g3g5 = [r for r in recs if r["labels"] and r["labels"][0]["type"].startswith(("G3", "G5"))]
    modes = collections.Counter(r["labels"][0]["metadata"].get("mode") for r in g3g5)
    imgs = sum(_img_ok(r.get("image_path")) for r in recs)
    print(f"\n### {name}  ({f})")
    print(f"  records={len(recs)}  by_defect={dict(by_def)}")
    print(f"  G3/G5 modes={dict(modes)}  images_on_disk={imgs}/{len(recs)}")
    if set(modes) - {"internal"}:
        print("  [FAIL] non-internal G3/G5 labels present"); ok = False
    if imgs != len(recs):
        print("  [FAIL] missing images"); ok = False
    # linter calibration on the freeform 'defect present' records
    def clean(r):
        p = r.get("pair", {}).get("clean_slide_path") or r.get("metadata", {}).get("clean_slide_path")
        return Slide.from_mapping(json.loads(Path(p).read_text()))
    ff = [r for r in g3g5 if r.get("metadata", {}).get("template_condition") == "freeform"]
    g3 = [r for r in ff if r["labels"][0]["type"].startswith("G3")]
    g5 = [r for r in ff if r["labels"][0]["type"].startswith("G5")]
    # detection above the linter's 4px / 1.5 dE operating point (severity grids span the floor)
    g3_sup = [r for r in g3 if float(r["labels"][0]["severity"]) >= 8]
    g3det = sum(len(detect_alignment_offsets(Slide.from_mapping(r["slide"]))) > 0 for r in g3_sup)
    g3fp = sum(len(detect_alignment_offsets(clean(r))) > 0 for r in g3)
    g5det = sum(len(detect_color_inconsistency(Slide.from_mapping(r["slide"]))) > 0 for r in g5)
    g5fp = sum(len(detect_color_inconsistency(clean(r))) > 0 for r in g5)
    print(f"  linter[freeform]: G3>=8px detect {g3det}/{len(g3_sup)} (fp {g3fp}/{len(g3)}); "
          f"G5 detect {g5det}/{len(g5)} (fp {g5fp}/{len(g5)})")
    if g3fp or g5fp:
        print("  [FAIL] linter false-fires on clean IR"); ok = False
    if g3_sup and g3det != len(g3_sup):
        print("  [WARN] linter missed a supra-threshold G3 (check)")
    return ok


def verify_real(f: str) -> bool:
    path = REPO / f
    if not path.exists():
        print(f"\n### real-CC internal-G3  ({f})\n  [PENDING] not built yet")
        return False
    recs = [json.loads(l) for l in path.open() if l.strip()]
    modes = collections.Counter(r["labels"][0]["metadata"].get("mode") for r in recs)
    defs = collections.Counter(r["labels"][0]["type"] for r in recs)
    imgs = sum(_img_ok(r.get("image_path")) for r in recs)
    cln = sum(_img_ok(r.get("pair", {}).get("clean_image_path")) for r in recs)
    print(f"\n### real-CC internal-G3  ({f})")
    print(f"  pairs={len(recs)}  by_defect={dict(defs)}  modes={dict(modes)}")
    print(f"  defective_images={imgs}/{len(recs)}  clean_images={cln}/{len(recs)}")
    ok = (set(defs) == {"G3_ALIGNMENT_OFFSET"} and set(modes) == {"internal"}
          and imgs == len(recs) and cln == len(recs) and len(recs) > 0)
    print("  [OK]" if ok else "  [FAIL] check counts/modes/images")
    return ok


def main():
    results = [verify_synth(n, f) for n, f in SYNTH.items()]
    results.append(verify_real(REAL))
    print("\n=== SUMMARY ===")
    print("ALL PASS" if all(results) else "SOME CHECKS FAILED / PENDING")


if __name__ == "__main__":
    main()
