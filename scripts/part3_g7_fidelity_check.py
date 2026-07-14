"""G7 corpus fidelity gate (TODO 2.-1 (b)).

Verifies a freshly rebuilt G7 manifest + rendered PNGs against the release
reference before any elicitation run is allowed. Three checks:

  1. IR consistency  — every sample's ``slide`` (IR) and ``labels`` must be
     byte-identical to release/part3/manifests/manifest_g7_rendered.jsonl
     (image paths are machine-local and excluded by construction: neither
     ``slide`` nor ``labels`` carries a path).
  2. Render validity — each def/clean PNG is exactly 1280x720, non-empty, and
     the defective render differs from its clean twin.
  3. Overflow localization — the defective render has real ink spilling past
     its container boundary in the manifest's ``overflow_region`` strip, while
     the clean twin has essentially none there. Container boundaries are the
     deterministic geometry emitted by part3_build_g7.py:
        card_height     : card bottom  y = 510  -> overflow strip y >= 520
        unbreakable_text: card right   x = 1232 -> overflow strip x >= 1233
        image_objectfit : frame b/r  (470,430)  -> overflow strip below+right of frame

Exit code is non-zero on ANY failure: "过不了这道门不许跑实验".

Usage:
  python scripts/part3_g7_fidelity_check.py \
    --manifest data/part3/manifest_g7_rendered.jsonl \
    --reference release/part3/manifests/manifest_g7_rendered.jsonl \
    --per-variant-samples 5
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
W, H = 1280, 720
INK_THRESHOLD = 245  # a pixel is "ink" if any RGB channel is below this (not near-white)

# Deterministic container geometry from part3_build_g7.py. Each entry is the
# overflow strip (x0, y0, x1, y1) where the DEFECTIVE render must show spill and
# the CLEAN twin must not. Coordinates are in rendered pixels (1280x720).
#   card:  x in [48, 1232], y in [150, 510]     (MARGIN=48, card_y=150, card_h=360)
#   frame: x in [70, 430],  y in [220, 470]     (inside card at rel (22,70), 360x250)
OVERFLOW_STRIP = {
    "card_height":      (48, 520, 1232, 720),   # below the card's bottom edge
    "unbreakable_text": (1233, 150, 1280, 510),  # right of the card's right edge
    # The 1.6x image bleeds down to y~620; the strip below the card (y>510) is pure
    # white background in the clean twin, so the card's non-white tint can't pollute
    # the count. (An in-card strip would be full of tint ink in BOTH renders.)
    "image_objectfit":  (70, 515, 660, 645),    # image bleed below the card's bottom edge
}


def _ink_mask(img: np.ndarray) -> np.ndarray:
    """Boolean mask of non-near-white pixels."""
    return (img[:, :, :3] < INK_THRESHOLD).any(axis=2)


def _strip_count(mask: np.ndarray, strip) -> int:
    x0, y0, x1, y1 = strip
    return int(mask[y0:y1, x0:x1].sum())


def _load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def check_ir_consistency(new_recs, ref_recs) -> list[str]:
    errs = []
    ref_by_id = {r["sample_id"]: r for r in ref_recs}
    new_ids = {r["sample_id"] for r in new_recs}
    ref_ids = set(ref_by_id)
    missing = ref_ids - new_ids
    extra = new_ids - ref_ids
    if missing:
        errs.append(f"IR: {len(missing)} reference sample_ids missing from new manifest "
                    f"(e.g. {sorted(missing)[:3]})")
    if extra:
        errs.append(f"IR: {len(extra)} new sample_ids absent from reference "
                    f"(e.g. {sorted(extra)[:3]})")
    for rec in new_recs:
        sid = rec["sample_id"]
        ref = ref_by_id.get(sid)
        if ref is None:
            continue
        if rec.get("slide") != ref.get("slide"):
            errs.append(f"IR: slide mismatch on {sid}")
        if rec.get("labels") != ref.get("labels"):
            errs.append(f"IR: labels mismatch on {sid}")
    return errs


def check_renders(new_recs, per_variant_samples) -> tuple[list[str], list[dict]]:
    errs: list[str] = []
    report: list[dict] = []
    by_variant: dict[str, list[dict]] = {}
    for rec in new_recs:
        v = rec["metadata"]["g7_variant"]
        by_variant.setdefault(v, []).append(rec)

    for variant, recs in sorted(by_variant.items()):
        strip = OVERFLOW_STRIP[variant]
        checked = 0
        for rec in recs:
            def_path = Path(rec["pair"]["defective_image_path"])
            clean_path = Path(rec["pair"]["clean_image_path"])
            if not def_path.exists() or not clean_path.exists():
                errs.append(f"RENDER: missing PNG for {rec['sample_id']}")
                continue
            d = _load_rgb(def_path)
            c = _load_rgb(clean_path)
            # (2a) dims
            if d.shape[:2] != (H, W) or c.shape[:2] != (H, W):
                errs.append(f"RENDER: {rec['sample_id']} wrong dims def={d.shape[:2]} clean={c.shape[:2]}")
            # (2b) non-empty
            d_ink = _ink_mask(d)
            c_ink = _ink_mask(c)
            if int(d_ink.sum()) < 500 or int(c_ink.sum()) < 500:
                errs.append(f"RENDER: {rec['sample_id']} near-empty render "
                            f"(def_ink={int(d_ink.sum())} clean_ink={int(c_ink.sum())})")
            # (2c) def differs from clean
            n_diff = int((d != c).any(axis=2).sum())
            if n_diff < 300:
                errs.append(f"RENDER: {rec['sample_id']} def≈clean (only {n_diff} px differ)")
            # (3) overflow localization
            d_strip = _strip_count(d_ink, strip)
            c_strip = _strip_count(c_ink, strip)
            overflow_ok = d_strip >= 150 and d_strip >= 4 * max(c_strip, 1)
            if checked < per_variant_samples and not overflow_ok:
                errs.append(f"OVERFLOW: {rec['sample_id']} strip def_ink={d_strip} clean_ink={c_strip} "
                            f"(need def>=150 and >=4x clean) region={rec['metadata']['overflow_region']}")
            if checked < per_variant_samples:
                report.append({
                    "sample_id": rec["sample_id"], "variant": variant,
                    "region": rec["metadata"]["overflow_region"],
                    "n_diff_px": n_diff, "def_strip_ink": d_strip, "clean_strip_ink": c_strip,
                    "overflow_ok": overflow_ok,
                })
                checked += 1
        if checked < per_variant_samples:
            errs.append(f"RENDER: variant {variant} only had {checked} checkable pairs "
                        f"(< {per_variant_samples})")
    return errs, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/part3/manifest_g7_rendered.jsonl")
    ap.add_argument("--reference", default="release/part3/manifests/manifest_g7_rendered.jsonl")
    ap.add_argument("--per-variant-samples", type=int, default=5)
    args = ap.parse_args()

    new_path = (REPO / args.manifest) if not Path(args.manifest).is_absolute() else Path(args.manifest)
    ref_path = (REPO / args.reference) if not Path(args.reference).is_absolute() else Path(args.reference)
    new_recs = [json.loads(line) for line in new_path.open() if line.strip()]
    ref_recs = [json.loads(line) for line in ref_path.open() if line.strip()]
    print(f"[fidelity] new={len(new_recs)} recs  reference={len(ref_recs)} recs")

    errs_ir = check_ir_consistency(new_recs, ref_recs)
    errs_rd, report = check_renders(new_recs, args.per_variant_samples)

    print("\n[check 1: IR/labels consistency]")
    print("  PASS" if not errs_ir else "\n".join("  FAIL " + e for e in errs_ir))
    print("\n[check 2+3: render validity & overflow localization] (sampled pairs)")
    for r in report:
        flag = "ok" if r["overflow_ok"] else "BAD"
        print(f"  [{flag}] {r['sample_id']:<28} region={r['region']:<12} "
              f"diff_px={r['n_diff_px']:>7} def_strip={r['def_strip_ink']:>6} clean_strip={r['clean_strip_ink']:>5}")
    if errs_rd:
        print("\n".join("  FAIL " + e for e in errs_rd))

    all_errs = errs_ir + errs_rd
    print("\n" + "=" * 60)
    if all_errs:
        print(f"FIDELITY GATE FAILED — {len(all_errs)} problem(s). 不带病跑实验。")
        raise SystemExit(1)
    print("FIDELITY GATE PASSED — all three checks green. 可进实验。")


if __name__ == "__main__":
    main()
