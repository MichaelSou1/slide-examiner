"""P2-1 — build + render deck-level paired-clean controls.

Deck-scope semantic defects (S2 narrative-order-break, S5 missing-logic-section)
need a same-source clean deck as the negative control so balanced accuracy can be
computed. The defective deck records already carry `pair.clean_deck_path` (the
unperturbed deck IR); this script materialises one clean *control record* per
deck positive — clean deck structure + freshly rendered clean page images +
empty labels — keyed by `<defective_sample_id>__CLEAN`.

`part2_eval.py --deck-clean <out>` consumes these so deck S2/S5 cells stop
showing '—'. CPU only (Playwright HTML render), no model calls.

Usage:
  python scripts/part2_render_clean_decks.py \
    --manifest data/part2/manifest_eval_test_rendered.jsonl \
    --out data/part2/deck_clean_test.jsonl
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from slide_examiner.ingest import deck_caption, load_deck_json
from slide_examiner.render import render_manifest
from slide_examiner.schemas import oracle_view

REPO = Path(__file__).resolve().parents[1]
RENDER_DIR = REPO / "runs" / "part2" / "rendered_clean"


def is_deck_positive(rec: dict) -> bool:
    return bool(rec.get("deck")) and bool([x for x in rec.get("labels", []) if x.get("type")])


def clean_control_record(rec: dict) -> dict | None:
    md = rec.get("metadata", {}) or {}
    pair = rec.get("pair", {}) or {}
    clean_deck_path = pair.get("clean_deck_path") or md.get("clean_deck_path")
    if not clean_deck_path or not Path(clean_deck_path).exists():
        return None
    clean = load_deck_json(clean_deck_path)
    clean_dict = clean.to_dict()
    return {
        "sample_id": rec["sample_id"] + "__CLEAN",
        "slide": None,
        "deck": clean_dict,
        "image_path": None,
        "oracle": oracle_view(clean_dict),
        "caption": deck_caption(clean),
        "labels": [],  # negative control
        "pair": {"clean_deck_path": clean_deck_path},
        "metadata": {
            "template_condition": md.get("template_condition", "freeform"),
            "split": md.get("split"),
            "clean_deck_path": clean_deck_path,
            "is_deck_clean": True,
            "source_defect": [x.get("type") for x in rec.get("labels", [])],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--long-edge", type=int, default=1024)
    args = ap.parse_args()

    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    deck_pos = [r for r in recs if is_deck_positive(r)]
    controls = [c for r in deck_pos if (c := clean_control_record(r))]
    # de-dup by sample_id (each defective deck → one clean control)
    seen: dict[str, dict] = {}
    for c in controls:
        seen[c["sample_id"]] = c
    controls = list(seen.values())
    print(f"[{Path(args.manifest).name}] {len(deck_pos)} deck positives -> {len(controls)} clean controls")
    if not controls:
        Path(args.out).write_text("", encoding="utf-8")
        return

    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, dir=str(RENDER_DIR)) as tmp:
        for c in controls:
            tmp.write(json.dumps(c, ensure_ascii=False) + "\n")
        tmp_path = tmp.name

    # render_clean=False → render only the deck's own pages (the clean deck IR)
    render_manifest(tmp_path, RENDER_DIR, output_manifest=args.out,
                    render_clean=False, long_edge=args.long_edge)
    out_recs = [json.loads(l) for l in Path(args.out).open() if l.strip()]
    with_pages = sum(1 for r in out_recs if r.get("metadata", {}).get("page_image_paths"))
    Path(tmp_path).unlink(missing_ok=True)
    print(f"  wrote {len(out_recs)} controls to {args.out}; with page_image_paths: {with_pages}")


if __name__ == "__main__":
    main()
