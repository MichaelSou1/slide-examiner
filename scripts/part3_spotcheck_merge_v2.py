#!/usr/bin/env python3
"""Merge the valid v1 spot-check labels with corrected replacement labels.

Supports either:
1) one combined replacement manifest/labels pair, or
2) multiple replacement manifest/labels pairs (for example G3-only + G5-only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPLACE_CLASSES = {"G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION"}


def load_json(path: Path):
    return json.loads(path.read_text())


def _collect_many(values: list[str] | None) -> list[Path]:
    return [Path(v) for v in (values or [])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-manifest", required=True)
    ap.add_argument("--base-labels", required=True)
    ap.add_argument("--replacement-manifest")
    ap.add_argument("--replacement-labels")
    ap.add_argument("--replacement-manifests", nargs="*")
    ap.add_argument("--replacement-label-files", nargs="*")
    ap.add_argument("--out-manifest", required=True)
    ap.add_argument("--out-labels", required=True)
    args = ap.parse_args()

    base_manifest = load_json(Path(args.base_manifest))
    base_labels = load_json(Path(args.base_labels))
    repl_manifest_paths = _collect_many(args.replacement_manifests)
    repl_label_paths = _collect_many(args.replacement_label_files)
    if args.replacement_manifest:
        repl_manifest_paths.insert(0, Path(args.replacement_manifest))
    if args.replacement_labels:
        repl_label_paths.insert(0, Path(args.replacement_labels))

    if not repl_manifest_paths or not repl_label_paths:
        raise SystemExit("need at least one replacement manifest and one replacement labels file")
    if len(repl_manifest_paths) != len(repl_label_paths):
        raise SystemExit("replacement manifests and label files must have the same count")

    repl_manifest = []
    repl_labels = {}
    for mp, lp in zip(repl_manifest_paths, repl_label_paths):
        repl_manifest.extend(load_json(mp))
        repl_labels.update(load_json(lp))

    kept_manifest = [m for m in base_manifest if m["class"] not in REPLACE_CLASSES]
    kept_pair_ids = {m["pair_id"] for m in kept_manifest}
    kept_labels = {pid: rec for pid, rec in base_labels.items() if pid in kept_pair_ids}

    merged_manifest = kept_manifest + repl_manifest
    merged_labels = dict(kept_labels)
    for item in repl_manifest:
        pid = item["pair_id"]
        merged_labels[pid] = repl_labels.get(pid, {"cls": item["class"]})

    Path(args.out_manifest).write_text(json.dumps(merged_manifest, ensure_ascii=False, indent=2))
    Path(args.out_labels).write_text(json.dumps(merged_labels, ensure_ascii=False, indent=2))

    print(f"[merge] kept old pairs: {len(kept_manifest)}")
    print(f"[merge] replacement pairs: {len(repl_manifest)}")
    print(f"[merge] total v2 pairs: {len(merged_manifest)}")
    print(f"[write] {args.out_manifest}")
    print(f"[write] {args.out_labels}")


if __name__ == "__main__":
    main()
