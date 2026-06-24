#!/usr/bin/env python3
"""E8 — aggregate the human perceptual spot-check (+ optional Claude cross-check).

Reads the sample manifest and one or two label files (HTML export format:
``{pair_id: {cls, defect_visible: 'yes'|'no', twin_clean: 'yes'|'no', note}}``)
and emits:

  * a per-class + overall **perceptual-verification rate** with Wilson CIs
    (defect visible on the defective render; twin actually clean),
  * the human-vs-Claude agreement (raw + Cohen's kappa) when a 2nd file is given,
  * a flagged list of every pair a labeller marked not-visible / twin-not-clean
    (candidate injector artifacts), with notes,
  * markdown -> reports/_e8_spotcheck.md and JSON -> data/part3/e8_spotcheck.json.

Usage:
  python scripts/part3_spotcheck_report.py \
      --human docs/spotcheck/labels.json \
      --claude docs/spotcheck/claude_labels.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.statistics import wilson_interval  # noqa: E402

CLASS_ORDER = [
    "G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
    "G6_MARGIN_VIOLATION", "G7_RENDER_CONTAINMENT_OVERFLOW",
    "G5_BRAND_COLOR_VIOLATION", "S1_TITLE_BODY_MISMATCH",
    "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION",
]


def _yes(v) -> bool | None:
    if v in ("yes", "y", True, 1):
        return True
    if v in ("no", "n", False, 0):
        return False
    return None  # unanswered


def load_labels(path: Path) -> dict[str, dict]:
    return json.loads(path.read_text()) if path and path.exists() else {}


def rate(flags: list[bool]):
    """(k yes, n answered, Wilson CI) over a list of bools."""
    n = len(flags)
    k = sum(1 for f in flags if f)
    ci = wilson_interval(k, n) if n else None
    return k, n, ci


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """kappa over (a, b) boolean judgements."""
    n = len(pairs)
    if not n:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa1 = sum(1 for a, _ in pairs if a) / n
    pb1 = sum(1 for _, b in pairs if b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def collect(manifest, labels, field):
    """class -> list[bool] of answered judgements for `field`."""
    by: dict[str, list[bool]] = {}
    for m in manifest:
        pid = m["pair_id"]
        rec = labels.get(pid, {})
        v = _yes(rec.get(field))
        if v is None:
            continue
        by.setdefault(m["class"], []).append(v)
    return by


def fmt_ci(ci) -> str:
    return f"{ci.estimate:.2f} [{ci.low:.2f}, {ci.high:.2f}]" if ci else "-"


def section(manifest, labels, field, title) -> tuple[str, dict]:
    by = collect(manifest, labels, field)
    lines = [f"### {title}", "", "| class | rate [95% Wilson CI] | n |", "|---|---|---|"]
    js = {}
    allflags: list[bool] = []
    for cls in CLASS_ORDER:
        flags = by.get(cls, [])
        if not flags:
            continue
        k, n, ci = rate(flags)
        allflags += flags
        lines.append(f"| {cls} | {fmt_ci(ci)} | {n} |")
        js[cls] = {"k": k, "n": n, "ci": ci.to_dict() if ci else None}
    k, n, ci = rate(allflags)
    lines.append(f"| **overall** | **{fmt_ci(ci)}** | **{n}** |")
    js["overall"] = {"k": k, "n": n, "ci": ci.to_dict() if ci else None}
    return "\n".join(lines), js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(REPO / "docs/spotcheck/manifest.json"))
    ap.add_argument("--human", required=True)
    ap.add_argument("--claude", default=None)
    ap.add_argument("--md-out", default=str(REPO / "reports/_e8_spotcheck.md"))
    ap.add_argument("--json-out", default=str(REPO / "data/part3/e8_spotcheck.json"))
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    human = load_labels(Path(args.human))
    claude = load_labels(Path(args.claude)) if args.claude else {}

    md = ["# E8 — human perceptual spot-check of injected defects", "",
          f"Sample: **{len(manifest)} defective+clean pairs**, freeform (non-template) renders, "
          f"stratified across {len({m['class'] for m in manifest})} single-slide classes "
          "(S2/S3 are deck-level, no single-slide clean twin -> out of scope).", ""]
    js: dict = {"n_pairs": len(manifest)}

    s1, j1 = section(manifest, human, "defect_visible",
                     "Defect visible on the defective render? (human)")
    s2, j2 = section(manifest, human, "twin_clean", "Twin actually clean? (human)")
    md += [s1, "", s2, ""]
    js["human"] = {"defect_visible": j1, "twin_clean": j2}

    # artifact flags (human)
    flagged = []
    for m in manifest:
        rec = human.get(m["pair_id"], {})
        dv, tc = _yes(rec.get("defect_visible")), _yes(rec.get("twin_clean"))
        if dv is False or tc is False:
            flagged.append((m, "defect not visible" if dv is False else "",
                            "twin not clean" if tc is False else "", rec.get("note", "")))
    md += ["### Flagged pairs (candidate injector artifacts)", ""]
    if flagged:
        md += ["| pair | class | flag | note | composite |", "|---|---|---|---|---|"]
        for m, f1, f2, note in flagged:
            flag = ", ".join(x for x in (f1, f2) if x)
            md.append(f"| {m['pair_id']} | {m['class']} | {flag} | {note} | {m['composite']} |")
    else:
        md.append("_None — every sampled defect was judged visible and every twin clean._")
    md.append("")
    js["flagged"] = [{"pair_id": m["pair_id"], "class": m["class"],
                      "defect_not_visible": bool(f1), "twin_not_clean": bool(f2), "note": note}
                     for m, f1, f2, note in flagged]

    # human-vs-Claude cross-check
    if claude:
        md += ["### Secondary cross-check (Claude image vision, disclosed)", "",
               "_Labelled independently of the human pass; reported as corroboration only._", ""]
        agree = {}
        for field, label in (("defect_visible", "defect visible"), ("twin_clean", "twin clean")):
            both = []
            for m in manifest:
                h = _yes(human.get(m["pair_id"], {}).get(field))
                c = _yes(claude.get(m["pair_id"], {}).get(field))
                if h is not None and c is not None:
                    both.append((h, c))
            n = len(both)
            raw = sum(1 for a, b in both if a == b) / n if n else None
            kap = cohen_kappa(both)
            agree[field] = {"n": n, "raw_agreement": raw, "kappa": kap}
            md.append(f"- **{label}**: raw agreement "
                      f"{raw:.2f} (n={n}), Cohen's kappa {kap:.2f}"
                      if n else f"- **{label}**: no overlapping labels")
        # Claude's own rates
        c1, cj1 = section(manifest, claude, "defect_visible", "Defect visible (Claude)")
        c2, cj2 = section(manifest, claude, "twin_clean", "Twin clean (Claude)")
        md += ["", c1, "", c2, ""]
        js["claude"] = {"defect_visible": cj1, "twin_clean": cj2, "agreement": agree}

    Path(args.md_out).write_text("\n".join(md))
    Path(args.json_out).write_text(json.dumps(js, indent=2))
    ov = js["human"]["defect_visible"]["overall"]
    tw = js["human"]["twin_clean"]["overall"]
    print(f"[E8] defect-visible rate {ov['k']}/{ov['n']} "
          f"({ov['ci']['estimate']:.2f} [{ov['ci']['low']:.2f},{ov['ci']['high']:.2f}])")
    print(f"[E8] twin-clean rate     {tw['k']}/{tw['n']} "
          f"({tw['ci']['estimate']:.2f} [{tw['ci']['low']:.2f},{tw['ci']['high']:.2f}])")
    print(f"[E8] flagged pairs: {len(flagged)}")
    print(f"[write] {args.md_out}\n[write] {args.json_out}")


if __name__ == "__main__":
    main()
