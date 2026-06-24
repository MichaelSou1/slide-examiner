#!/usr/bin/env python3
"""E8 strict — aggregate the magnitude-stratified perceptual test.

Reads manifest_strict.json + labels_strict.json (schema:
``{pair_id: {cls, stratum, unaided: yes|no, aided: yes|no, note}}``) and reports,
per class x magnitude-stratum, the **unaided** salience rate (Q1: visible at first
look, side-by-side) and the **aided** confirmation rate (Q2: confirmable with
blink/diff), each with a Wilson CI. The expected, publishable shape is a
psychometric curve: unaided rate rises with injected magnitude, while the aided
rate stays ~1.0 (a perceptual re-confirmation that every injection is present).

Emits reports/_e8_strict.md + data/part3/e8_strict.json.

Usage: python scripts/part3_spotcheck_strict_report.py --labels docs/spotcheck/labels_strict.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.statistics import wilson_interval  # noqa: E402

# stratum display order per class (ascending magnitude)
ORDER = {
    "G3_ALIGNMENT_OFFSET": ["4px", "32px", "rel·48px", "rel·96px"],
    "G5_BRAND_COLOR_VIOLATION": ["ΔE≈3", "ΔE≈12", "ΔE≈24",
                                 "ΔE≈12·hue", "ΔE≈24·hue", "ΔE≈40·hue"],
    "G6_MARGIN_VIOLATION": ["gap(x->28)", "flush(x->0)"],
}


def _yes(v):
    return True if v in ("yes", "y", True, 1) else (False if v in ("no", "n", False, 0) else None)


def _ci(flags):
    n = len(flags)
    k = sum(1 for f in flags if f)
    return k, n, (wilson_interval(k, n) if n else None)


def _fmt(ci):
    return f"{ci.estimate:.2f} [{ci.low:.2f}, {ci.high:.2f}]" if ci else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(REPO / "docs/spotcheck/manifest_strict.json"))
    ap.add_argument("--labels", required=True)
    ap.add_argument("--md-out", default=str(REPO / "reports/_e8_strict.md"))
    ap.add_argument("--json-out", default=str(REPO / "data/part3/e8_strict.json"))
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    labels = json.loads(Path(args.labels).read_text())
    strat = {m["pair_id"]: (m["class"], m["stratum"]) for m in manifest}

    # collect flags by (class, stratum)
    cells: dict[tuple[str, str], dict[str, list]] = {}
    for pid, (cls, st) in strat.items():
        rec = labels.get(pid, {})
        u, a = _yes(rec.get("unaided")), _yes(rec.get("aided"))
        c = cells.setdefault((cls, st), {"unaided": [], "aided": []})
        if u is not None:
            c["unaided"].append(u)
        if a is not None:
            c["aided"].append(a)

    md = ["# E8 strict — magnitude-stratified perceptual test", "",
          "G3/G5/G6 re-tested with **blink overlay + normalized difference image** and "
          "**magnitude strata**. Q1 = unaided (first-look side-by-side salience); "
          "Q2 = aided (confirmable with blink/diff). Strata were hidden during labelling.", "",
          "| class | stratum | unaided visible (Q1) | aided confirmed (Q2) | n |",
          "|---|---|---|---|---|"]
    js: dict = {}
    for cls in ["G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]:
        for st in ORDER.get(cls, []):
            c = cells.get((cls, st))
            if not c:
                continue
            uk, un, uci = _ci(c["unaided"])
            ak, an, aci = _ci(c["aided"])
            md.append(f"| {cls} | {st} | {_fmt(uci)} | {_fmt(aci)} | {un} |")
            js[f"{cls}|{st}"] = {"unaided": {"k": uk, "n": un, "ci": uci.to_dict() if uci else None},
                                 "aided": {"k": ak, "n": an, "ci": aci.to_dict() if aci else None}}
    # per-class rollups
    md += ["", "### Per-class rollup", "", "| class | unaided | aided | n |", "|---|---|---|---|"]
    for cls in ["G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]:
        u = [f for st in ORDER.get(cls, []) if (cells.get((cls, st))) for f in cells[(cls, st)]["unaided"]]
        a = [f for st in ORDER.get(cls, []) if (cells.get((cls, st))) for f in cells[(cls, st)]["aided"]]
        uk, un, uci = _ci(u)
        ak, an, aci = _ci(a)
        md.append(f"| {cls} | {_fmt(uci)} | {_fmt(aci)} | {un} |")
        js[f"{cls}|ALL"] = {"unaided": {"k": uk, "n": un}, "aided": {"k": ak, "n": an}}

    notes = [(pid, labels[pid].get("note")) for pid in strat if labels.get(pid, {}).get("note")]
    if notes:
        md += ["", "### Notes", ""]
        for pid, nt in sorted(notes):
            md.append(f"- {pid} ({strat[pid][0]} {strat[pid][1]}): {nt}")

    Path(args.md_out).write_text("\n".join(md))
    Path(args.json_out).write_text(json.dumps(js, indent=2))
    print("[E8-strict] per (class,stratum) unaided/aided:")
    for cls in ["G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]:
        for st in ORDER.get(cls, []):
            c = cells.get((cls, st))
            if not c:
                continue
            uk, un, _ = _ci(c["unaided"])
            ak, an, _ = _ci(c["aided"])
            print(f"  {cls:26s} {st:12s} unaided {uk}/{un}  aided {ak}/{an}")
    print(f"[write] {args.md_out}\n[write] {args.json_out}")


if __name__ == "__main__":
    main()
