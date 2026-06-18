"""Fetch the SlideAudit dataset (real human-annotated slide design flaws) via the
kkgithub mirror (github.com / raw.githubusercontent.com are blocked here) and
build a Part 2 *real-data transfer* eval manifest mapped onto our taxonomy.

SlideAudit (arXiv 2508.03630, github zhuohaouw/SlideAudit): 2400 real slides,
per-slide boolean flaw annotations (19 dims, crowd-annotated, with strong-agreement
flags). It is IMAGE + flaw-labels only (no element structure), so this is an
image-only (modality A) transfer eval; linter/structure modalities are N/A.

Mapping SlideAudit design_deficiency -> our DefectType (overlap subset):
  Content Overflow/Cut-off            -> G1_TEXT_OVERFLOW
  Occluded Content                    -> G2_ELEMENT_OVERLAP
  Content Alignment Issues            -> G3_ALIGNMENT_OFFSET
  Improper Font Sizing                -> G4_FONT_SIZE_INCONSISTENCY
  Excessive or Inconsistent Color Usage / Inappropriate or Mismatched Color
                                      -> G5_BRAND_COLOR_VIOLATION
  Unbalanced Space Distribution       -> G6_MARGIN_VIOLATION
  Excessive Text Volume               -> S4_DENSITY_RULE_VIOLATION
"""
from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIRROR = "https://raw.kkgithub.com/zhuohaouw/SlideAudit/main"
RAW = REPO / "data" / "raw" / "slideaudit"
ANN = RAW / "annotations"
IMG = RAW / "images"
OUT_MANIFEST = REPO / "data" / "part2" / "manifest_slideaudit.jsonl"

MAP = {
    "Content Overflow/Cut-off": "G1_TEXT_OVERFLOW",
    "Occluded Content": "G2_ELEMENT_OVERLAP",
    "Content Alignment Issues": "G3_ALIGNMENT_OFFSET",
    "Improper Font Sizing": "G4_FONT_SIZE_INCONSISTENCY",
    "Excessive or Inconsistent Color Usage": "G5_BRAND_COLOR_VIOLATION",
    "Inappropriate or Mismatched Color Combinations": "G5_BRAND_COLOR_VIOLATION",
    "Unbalanced Space Distribution": "G6_MARGIN_VIOLATION",
    "Excessive Text Volume": "S4_DENSITY_RULE_VIOLATION",
}
N_SLIDES = 2400


def fetch(url: str, dest: Path, binary: bool, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if not data:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return False


def download_all(kind: str, ext: str, dest_dir: Path, workers: int = 24) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(f"{MIRROR}/data/{kind}/slide_{i:04d}.{ext}", dest_dir / f"slide_{i:04d}.{ext}", ext == "png")
            for i in range(1, N_SLIDES + 1)]
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch, u, d, b): u for (u, d, b) in jobs}
        done = 0
        for fut in as_completed(futs):
            ok += int(fut.result())
            done += 1
            if done % 200 == 0:
                print(f"  {kind}: {done}/{len(jobs)} ({ok} ok)")
    print(f"{kind}: {ok}/{len(jobs)} downloaded")
    return ok


def build_manifest() -> dict:
    records = []
    import collections
    present = collections.Counter()
    absent = collections.Counter()
    for i in range(1, N_SLIDES + 1):
        ann = ANN / f"slide_{i:04d}.json"
        img = IMG / f"slide_{i:04d}.png"
        if not ann.exists() or not img.exists():
            continue
        try:
            d = json.loads(ann.read_text())
        except Exception:
            continue
        labels = []          # mapped defects present with strong agreement
        confident_absent = set()
        for a in d.get("annotations", []):
            our = MAP.get(a.get("design_deficiency"))
            if not our:
                continue
            if not a.get("has_strong_agreement"):
                continue
            if a.get("response"):
                labels.append({"type": our, "severity": 1.0, "target_element_ids": []})
                present[our] += 1
            else:
                confident_absent.add(our)
                absent[our] += 1
        # dedup labels (G5 has two source dims)
        seen = set(); uniq = []
        for lb in labels:
            if lb["type"] not in seen:
                seen.add(lb["type"]); uniq.append(lb)
        records.append({
            "sample_id": f"slideaudit_{i:04d}",
            "image_path": str(img),
            "labels": uniq,
            "metadata": {"source": "slideaudit", "confident_absent": sorted(confident_absent)},
        })
    OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MANIFEST.open("w", encoding="utf-8") as h:
        for r in records:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"n_records": len(records), "present_per_defect": dict(present),
            "confident_absent_per_defect": dict(absent), "manifest": str(OUT_MANIFEST)}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    if not args.skip_download:
        download_all("annotations", "json", ANN)
        download_all("images", "png", IMG)
    summary = build_manifest()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
