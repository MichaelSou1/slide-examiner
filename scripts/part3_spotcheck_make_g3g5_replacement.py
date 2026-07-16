#!/usr/bin/env python3
"""Build a small replacement manifest for the invalid G3/G5 v1 spot-check pairs."""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from part3_spotcheck_sample import _composite, _load_rgb  # noqa: E402

G3_MANIFEST = REPO / "data/part3/g3_relmisalign.jsonl"
G5_MANIFEST = REPO / "data/part3/g5_chromatic.jsonl"
OUT_MANIFEST = REPO / "docs/spotcheck/manifest_g3g5_replacement.json"
OUT_DIR = REPO / "docs/spotcheck"
PAIRS_DIR = OUT_DIR / "pairs_g3g5_replacement"

PHRASE = {
    "G3_ALIGNMENT_OFFSET": "同一组 bullets 里，有一项没有和其他项对齐（缩进/位置明显不同）",
    "G5_BRAND_COLOR_VIOLATION": "同一组 bullets 里，有一项的文字颜色与其他项明显不同",
}
SHORT = {
    "G3_ALIGNMENT_OFFSET": "G3",
    "G5_BRAND_COLOR_VIOLATION": "G5",
}


def _load_jsonl(path: Path, cls: str) -> list[dict]:
    items = []
    if not path.exists():
        return items
    with path.open() as fh:
        for line in fh:
            rec = json.loads(line)
            def_path = Path(rec["image_path"])
            clean_path = Path(rec["metadata"]["clean_image_path"])
            if not (def_path.exists() and clean_path.exists()):
                continue
            def_rel = os.path.relpath(def_path, OUT_DIR)
            clean_rel = os.path.relpath(clean_path, OUT_DIR)
            items.append({
                "class": cls,
                "src_id": rec.get("sample_id") or def_path.parent.name,
                "stratum": rec.get("metadata", {}).get("stratum"),
                "defective_path": def_rel,
                "clean_path": clean_rel,
            })
    return items


def build_manifest(seed: int = 20260715) -> list[dict]:
    picks = []
    picks.extend(_load_jsonl(G3_MANIFEST, "G3_ALIGNMENT_OFFSET"))
    picks.extend(_load_jsonl(G5_MANIFEST, "G5_BRAND_COLOR_VIOLATION"))
    rng = random.Random(seed)
    rng.shuffle(picks)
    for i, item in enumerate(picks):
        item["pair_id"] = f"r{i:02d}"
        item["short"] = SHORT[item["class"]]
        item["phrase"] = PHRASE[item["class"]]
    return picks


def write_composites(manifest: list[dict], img_width: int = 1024) -> None:
    PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    for item in manifest:
        defim = _load_rgb((OUT_DIR / item["defective_path"]).resolve(), img_width)
        clim = _load_rgb((OUT_DIR / item["clean_path"]).resolve(), img_width)
        header = f"{item['short']} replacement · {item.get('stratum') or 'corrected'} · {item['pair_id']}"
        comp = _composite(defim, clim, header)
        out = PAIRS_DIR / f"pair_{item['pair_id']}_{item['short']}.png"
        comp.save(out)
        item["composite"] = os.path.relpath(out, OUT_DIR)


def main() -> None:
    manifest = build_manifest()
    write_composites(manifest)
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    by_cls = {}
    for item in manifest:
        by_cls[item["class"]] = by_cls.get(item["class"], 0) + 1
    print(f"[sample] replacement pairs: {len(manifest)} -> {by_cls}")
    print(f"[write] {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
