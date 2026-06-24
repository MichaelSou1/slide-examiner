#!/usr/bin/env python3
"""E8 follow-up — IR-faithfulness check for the spot-check sample.

Answers the reviewer/author question "is a not-perceptible injected defect a real
sub-perceptual effect, or just a broken injector?" by diffing the DEFECTIVE vs
CLEAN *source IR* (slide JSON) for each sampled pair and confirming the injected
change is actually present in the structure (independent of whether a human could
SEE it in the render). A "not-visible" label on an IR-present injection is a
perception/format effect; a not-visible label on an IR-ABSENT injection would be a
tooling failure.

Covers the classes sourced from the part-2 generic manifest (G1/G2/G3/G5/G6/S1/S4),
which is where the not-visible cases (G3/G5/G6) live and which carries
defective_slide_path / clean_slide_path. S6 (figure-bearing imgslide corpus) and G7
are sourced from dedicated corpora and verified visible by the human pass (9/9 each).

Emits data/part3/e8_ir_faithfulness.json and prints a per-pair table.

Usage: python scripts/part3_spotcheck_irdiff.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PART2 = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
MANIFEST = REPO / "docs/spotcheck/manifest.json"
OUT = REPO / "data/part3/e8_ir_faithfulness.json"
RENDER_W, IR_W = 1024, 1920  # part-2 render width vs IR coordinate width (for ~px@render)


def _abs(p):
    if not p:
        return None
    pp = Path(p)
    return pp if pp.is_absolute() else REPO / pp


def _load(p):
    p = _abs(p)
    return json.loads(p.read_text()) if p and p.exists() else None


def _elem(slide, eid):
    for e in slide.get("elements", []):
        if e.get("element_id") == eid:
            return e
    return None


def inspect(cls, lab, de, ce):
    """(present_in_ir: bool, detail: str) for one pair's target element."""
    lm = lab.get("metadata", {})
    if cls == "G3_ALIGNMENT_OFFSET":
        ax = lm.get("axis", "x")
        d = de["bbox"][ax] - ce["bbox"][ax]
        return abs(d - lm.get("offset_px", 0)) < 0.5, \
            f"{ax} +{d:.0f}px IR (~{d * RENDER_W / IR_W:.0f}px @render; label {lm.get('offset_px')})"
    if cls == "G5_BRAND_COLOR_VIOLATION":
        c0, c1 = ce.get("style", {}).get("color"), de.get("style", {}).get("color")
        return c0 != c1, f"color {c0}->{c1} (ΔE2000 {lm.get('delta_e', 0):.1f})"
    if cls == "G6_MARGIN_VIOLATION":
        d = {k: (ce["bbox"][k], de["bbox"][k]) for k in de["bbox"] if ce["bbox"][k] != de["bbox"][k]}
        return bool(d), f"bbox {d}"
    # text / structural classes (G1 overflow marker, G2 overlap, S1, S4): any target diff
    diff_text = de.get("text") != ce.get("text")
    diff_box = de.get("bbox") != ce.get("bbox")
    diff_style = de.get("style") != ce.get("style")
    parts = [n for n, b in (("text", diff_text), ("bbox", diff_box), ("style", diff_style)) if b]
    return bool(parts), "changed: " + ",".join(parts) if parts else "no diff"


def main():
    sample = json.loads(MANIFEST.read_text())
    by_pid = {x["pair_id"]: x for x in sample}
    idx = {}
    with PART2.open() as fh:
        for line in fh:
            r = json.loads(line)
            idx[r.get("sample_id")] = r

    rows, present, total = [], 0, 0
    per_class = {}
    for pid in sorted(by_pid):
        rec = by_pid[pid]
        cls, src = rec["class"], rec["src_id"]
        r = idx.get(src)
        if not r:  # S6 (imgslide) / G7 — not in the part-2 manifest
            rows.append({"pair_id": pid, "class": cls, "scope": "dedicated-corpus", "ir_present": None})
            continue
        lab = r["labels"][0]
        tgt = (lab.get("target_element_ids") or [None])[0]
        ds, cs = _load(r["metadata"].get("defective_slide_path")), _load(r["metadata"].get("clean_slide_path"))
        de, ce = _elem(ds, tgt) if ds else None, _elem(cs, tgt) if cs else None
        if not (de and ce):
            rows.append({"pair_id": pid, "class": cls, "ir_present": None, "detail": "slide json missing"})
            continue
        ok, detail = inspect(cls, lab, de, ce)
        total += 1
        present += ok
        pc = per_class.setdefault(cls, [0, 0])
        pc[1] += 1
        pc[0] += ok
        rows.append({"pair_id": pid, "class": cls, "ir_present": bool(ok), "detail": detail})

    summary = {"part2_sourced_pairs": total, "ir_present": present,
               "per_class": {k: {"present": v[0], "n": v[1]} for k, v in per_class.items()},
               "rows": rows}
    OUT.write_text(json.dumps(summary, indent=2))

    print(f"IR-faithfulness (part-2-sourced pairs): {present}/{total} injections present in the source IR\n")
    for r in rows:
        if r.get("ir_present") is None:
            continue
        tag = "IR-PRESENT" if r["ir_present"] else "** IR-ABSENT (injector failure) **"
        print(f" {r['pair_id']} {r['class']:26s} {tag:12s} | {r.get('detail','')}")
    print(f"\nper class (present/n):", {k: f"{v[0]}/{v[1]}" for k, v in per_class.items()})
    print(f"[write] {OUT}")
    if present != total:
        sys.exit(1)  # any IR-absent injection is a real tooling failure -> nonzero exit


if __name__ == "__main__":
    main()
