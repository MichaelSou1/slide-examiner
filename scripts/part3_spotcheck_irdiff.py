#!/usr/bin/env python3
"""E8 follow-up — IR-faithfulness check for the spot-check sample.

Answers the reviewer/author question "is a not-perceptible injected defect a real
sub-perceptual effect, or just a broken injector?" by diffing the DEFECTIVE vs
CLEAN *source IR* (slide JSON) for each sampled pair and confirming the injected
change is actually present in the structure (independent of whether a human could
SEE it in the render). A "not-visible" label on an IR-present injection is a
perception/format effect; a not-visible label on an IR-ABSENT injection would be a
tooling failure.

Covers two sources:
1) classes sourced from the part-2 generic manifest (G1/G2/G6/S1/S4 and legacy G3/G5),
   where the source slide JSON carries defective_slide_path / clean_slide_path; and
2) the corrected replacement G3/G5 corpora, where the generated HTML render artifacts
   are the authoritative structure snapshot for the sampled pair.

S6 (figure-bearing imgslide corpus) and G7 are sourced from dedicated corpora and are
left as not-audited rows here; the human spot-check report carries their visibility.

Emits a JSON summary and prints a per-pair table.

Usage:
  python scripts/part3_spotcheck_irdiff.py
  python scripts/part3_spotcheck_irdiff.py \
      --manifest docs/spotcheck/manifest_v2.json \
      --out data/part3/e8_ir_faithfulness_v2.json
"""
from __future__ import annotations

import argparse
import re
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PART2 = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
G3_REPL = REPO / "data/part3/g3_relmisalign.jsonl"
G5_REPL = REPO / "data/part3/g5_chromatic.jsonl"
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


def _load_jsonl(path: Path) -> dict[str, dict]:
    out = {}
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            out[rec["sample_id"]] = rec
    return out


def _elem(slide, eid):
    for e in slide.get("elements", []):
        if e.get("element_id") == eid:
            return e
    return None


def _resolve_from_manifest(manifest_path: Path, rel_or_abs: str | None) -> Path | None:
    if not rel_or_abs:
        return None
    p = Path(rel_or_abs)
    return p if p.is_absolute() else (manifest_path.parent / p).resolve()


def _parse_html_elements(path: Path) -> dict[str, dict]:
    text = path.read_text()
    out = {}
    for eid, style in re.findall(r'<div data-element-id="([^"]+)"[^>]*style="([^"]*)"', text):
        style_map = {}
        for part in style.split(";"):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            style_map[k.strip()] = v.strip()
        out[eid] = style_map
    return out


def _px(v: str | None) -> float | None:
    if not v:
        return None
    return float(v[:-2]) if v.endswith("px") else float(v)


def _lower(v: str | None) -> str | None:
    return v.lower() if isinstance(v, str) else None


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


def inspect_replacement(rec: dict, manifest_item: dict, manifest_path: Path):
    cls = manifest_item["class"]
    lab = rec["labels"][0]
    meta = lab.get("metadata", {})
    tgt = (lab.get("target_element_ids") or [None])[0]
    clean_html = _resolve_from_manifest(manifest_path, manifest_item.get("clean_path"))
    def_html = _resolve_from_manifest(manifest_path, manifest_item.get("defective_path"))
    if not clean_html or not def_html:
        return None, "missing replacement html path"
    clean_html = clean_html.with_suffix(".html")
    def_html = def_html.with_suffix(".html")
    if not clean_html.exists() or not def_html.exists():
        return None, "replacement html missing"
    ce = _parse_html_elements(clean_html).get(tgt)
    de = _parse_html_elements(def_html).get(tgt)
    if not ce or not de:
        return None, f"target {tgt} missing in replacement html"
    if cls == "G3_ALIGNMENT_OFFSET":
        clean_left = _px(ce.get("left"))
        def_left = _px(de.get("left"))
        sibling_x = float(meta.get("sibling_x", 0.0))
        offset_px = float(meta.get("offset_px", 0.0))
        scale = (clean_left / sibling_x) if sibling_x else (RENDER_W / IR_W)
        delta = (def_left - clean_left) if clean_left is not None and def_left is not None else None
        expected = offset_px * scale
        ok = delta is not None and abs(delta - expected) < 0.6
        return ok, f"left +{delta:.1f}px html (expected {expected:.1f}px; label {offset_px:.1f}px @IR)"
    if cls == "G5_BRAND_COLOR_VIOLATION":
        c0 = _lower(ce.get("color"))
        c1 = _lower(de.get("color"))
        exp = _lower(meta.get("expected_color"))
        act = _lower(meta.get("actual_color"))
        ok = (c0 == exp and c1 == act and c0 != c1)
        return ok, f"color {c0}->{c1} (expected {exp}->{act}; ΔE2000 {meta.get('delta_e', 0):.1f})"
    return None, "unsupported replacement class"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out)
    sample = json.loads(manifest_path.read_text())
    by_pid = {x["pair_id"]: x for x in sample}
    idx = {}
    with PART2.open() as fh:
        for line in fh:
            r = json.loads(line)
            idx[r.get("sample_id")] = r
    g3_repl = _load_jsonl(G3_REPL)
    g5_repl = _load_jsonl(G5_REPL)

    rows, present, total = [], 0, 0
    per_class = {}
    for pid in sorted(by_pid):
        rec = by_pid[pid]
        cls, src = rec["class"], rec["src_id"]
        repl = g3_repl.get(src) or g5_repl.get(src)
        if repl:
            ok, detail = inspect_replacement(repl, rec, manifest_path)
            if ok is None:
                rows.append({"pair_id": pid, "class": cls, "ir_present": None, "detail": detail})
                continue
            total += 1
            present += ok
            pc = per_class.setdefault(cls, [0, 0])
            pc[1] += 1
            pc[0] += ok
            rows.append({"pair_id": pid, "class": cls, "scope": "replacement", "ir_present": bool(ok), "detail": detail})
            continue
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
        rows.append({"pair_id": pid, "class": cls, "scope": "part2-generic", "ir_present": bool(ok), "detail": detail})

    summary = {"audited_pairs": total, "ir_present": present,
               "per_class": {k: {"present": v[0], "n": v[1]} for k, v in per_class.items()},
               "rows": rows}
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"IR-faithfulness (audited pairs): {present}/{total} injections present in the source structure\n")
    for r in rows:
        if r.get("ir_present") is None:
            continue
        tag = "IR-PRESENT" if r["ir_present"] else "** IR-ABSENT (injector failure) **"
        print(f" {r['pair_id']} {r['class']:26s} {tag:12s} | {r.get('detail','')}")
    print(f"\nper class (present/n):", {k: f"{v[0]}/{v[1]}" for k, v in per_class.items()})
    print(f"[write] {out_path}")
    if present != total:
        sys.exit(1)  # any IR-absent injection is a real tooling failure -> nonzero exit


if __name__ == "__main__":
    main()
