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
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.geometry import detect_alignment_offsets, detect_color_inconsistency  # noqa: E402
from slide_examiner.geometry import lint_slide  # noqa: E402
from slide_examiner.schemas import Slide  # noqa: E402

SYNTH = {
    "Part-1 attribution (A/B/C)": "data/part1/manifest_geometry_internal.jsonl",
    "Part-3 coverage (Table 2)": "data/part3/manifest_coverage_internal.jsonl",
}
REAL = "data/part3/manifest_real_internal_g3.jsonl"


def verify_w5_heldout(manifest: str, expected_per_class: int = 150) -> tuple[bool, dict]:
    """Full fidelity gate for the W5.1 novel-template paired calibration set."""
    path = Path(manifest)
    recs = [json.loads(line) for line in path.open() if line.strip()]
    by_defect = collections.Counter(
        r["labels"][0]["type"] if r.get("labels") else "NO_DEFECT" for r in recs)
    expected = {
        "G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
        "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION",
        "S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION",
        "S6_IMAGE_TEXT_CONTRADICTION",
    }
    errors: list[str] = []
    clean_images: set[str] = set()
    clean_slide_ids: set[str] = set()
    target_detected = target_clean_fp = clean_any_lint = same_pixels = 0
    for rec in recs:
        defect = rec["labels"][0]["type"]
        pair = rec.get("pair") or {}
        d_img = Path(rec.get("image_path") or "")
        c_img = Path(pair.get("clean_image_path") or "")
        c_ir = Path(pair.get("clean_slide_path") or "")
        if not all(p.exists() for p in (d_img, c_img, c_ir)):
            errors.append(f"missing paired artifact: {rec.get('sample_id')}")
            continue
        clean_images.add(str(c_img.resolve()))
        clean = Slide.from_mapping(json.loads(c_ir.read_text()))
        clean_slide_ids.add(clean.slide_id)
        clean_types = {x.type for x in lint_slide(clean)}
        defect_types = {x.type for x in lint_slide(Slide.from_mapping(rec["slide"]))}
        if defect.startswith("G") and defect in defect_types:
            target_detected += 1
        if defect.startswith("G") and defect in clean_types:
            target_clean_fp += 1
        if clean_types:
            clean_any_lint += 1
        if hashlib.sha256(d_img.read_bytes()).digest() == hashlib.sha256(c_img.read_bytes()).digest():
            same_pixels += 1
    if set(by_defect) != expected or any(by_defect[d] != expected_per_class for d in expected):
        errors.append(f"class counts mismatch: {dict(by_defect)}")
    if len(clean_images) != len(recs) or len(clean_slide_ids) != len(recs):
        errors.append("clean twins are not unique per labeled sample")
    if target_detected != expected_per_class * 5:
        errors.append(f"geometry target detection {target_detected}/{expected_per_class * 5}")
    if target_clean_fp or clean_any_lint or same_pixels:
        errors.append(f"target_clean_fp={target_clean_fp}, clean_any_lint={clean_any_lint}, same_pixels={same_pixels}")
    report = {
        "manifest": str(path), "pairs": len(recs), "per_class": dict(by_defect),
        "unique_clean_images": len(clean_images), "unique_clean_slide_ids": len(clean_slide_ids),
        "geometry_target_detected": target_detected, "geometry_target_clean_fp": target_clean_fp,
        "clean_any_linter_finding": clean_any_lint, "pixel_identical_pairs": same_pixels,
        "errors": errors, "passed": not errors,
    }
    print(f"\n### W5 held-out fidelity ({manifest})")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return not errors, report


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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--w5-heldout", default=None)
    ap.add_argument("--expected-per-class", type=int, default=150)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    if args.w5_heldout:
        ok, report = verify_w5_heldout(args.w5_heldout, args.expected_per_class)
        if args.report:
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(0 if ok else 1)
    results = [verify_synth(n, f) for n, f in SYNTH.items()]
    results.append(verify_real(REAL))
    print("\n=== SUMMARY ===")
    print("ALL PASS" if all(results) else "SOME CHECKS FAILED / PENDING")


if __name__ == "__main__":
    main()
