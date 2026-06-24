#!/usr/bin/env python3
"""E8 re-examination — merge the realistic-vs-original elicitation outputs into one
comparison table + a per-contrast verdict (was 'at chance' an injection artifact?).

Reads data/part3/e8_reval/{tag}_{cond}.json written by part3_e8_revalidate.sh and
emits comparison.md + comparison.json.

Verdict logic per contrast (realistic vs original injection):
  * if the ORIGINAL injection is ~chance (bal_acc CI includes 0.5) AND the REALISTIC
    variant is clearly above chance -> the 'at chance' result was an INJECTION
    ARTIFACT (the defect is detectable when posed realistically);
  * if BOTH are ~chance -> the sub-perceptual claim survives (now tested on a
    realistic stimulus, which strengthens it);
  * if BOTH are above chance -> the class was detectable all along.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# (label, realistic_tag, original_tag_or_None, defect)
CONTRASTS = [
    ("G3 alignment", "g3_rel", "g3_abs", "G3_ALIGNMENT_OFFSET"),
    ("G5 brand-colour", "g5_chroma", "g5_achroma", "G5_BRAND_COLOR_VIOLATION"),
    ("S6 image/text", "s6_valid", None, "S6_IMAGE_TEXT_CONTRADICTION"),
]
CONDS = ["C0", "C3", "AFC"]


def _load(d: Path, tag: str, cond: str):
    p = d / f"{tag}_{cond}.json"
    return json.loads(p.read_text()) if p.exists() else None


def cell(res, cond, defect):
    """dict {est, lo, hi, n, kind, dec, tie} for one output, or None. For AFC the
    headline is decisiveness + accuracy-when-decisive: a tie=1.0 ('neither') is
    ABSTENTION (model perceives no judgeable difference), NOT a wrong pick — collapsing
    it into acc_loose=0.0 conflates 'can't see it' / 'undecidable' with 'guessed wrong'."""
    if res is None:
        return None
    if cond == "AFC":
        c = (res.get("afc") or {}).get(defect)
        if not c:
            return None
        return {"est": c.get("afc_accuracy_loose"), "lo": None, "hi": None,
                "n": c.get("n_pairs"), "kind": "AFC",
                "dec": c.get("decisive_rate"), "tie": c.get("tie_rate")}
    per = (res.get("metrics", {}).get("A", {}).get("per_defect", {}) or {}).get(defect)
    if not per:
        return None
    det = per["detection"]
    ci = det.get("bal_acc_ci") or [None, None]
    return {"est": det["bal_acc"], "lo": ci[0], "hi": ci[1], "n": det.get("n_pos"), "kind": "bal"}


def fmt(c):
    if not c:
        return "—"
    if c["kind"] == "AFC":
        dec, tie = c.get("dec"), c.get("tie")
        tail = f" — dec {dec:.0%}, tie {tie:.0%}" if dec is not None else ""
        return f"{c['est']:.2f} (n={c['n']}{tail})"
    ci = f" [{c['lo']:.2f},{c['hi']:.2f}]" if c["lo"] is not None else ""
    return f"{c['est']:.2f}{ci} (n={c['n']})"


def above_chance(c):
    if not c or c.get("est") is None:
        return None
    est, lo = c["est"], c["lo"]
    if c["kind"] == "AFC":  # decisive AND committing correctly above chance
        return (c.get("dec") or 0) >= 0.5 and est >= 0.65
    return (lo is not None and lo > 0.5) or (lo is None and est >= 0.65)


def near_chance(c):
    if not c or c.get("est") is None:
        return None
    if c["kind"] == "AFC":  # mostly tie/abstain == not decisively detected
        return (c.get("dec") or 0) < 0.5
    est, lo, hi = c["est"], c["lo"], c["hi"]
    if lo is not None:
        return lo <= 0.5 <= hi
    return abs(est - 0.5) < 0.12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="data/part3/e8_reval")
    ap.add_argument("--model", default="?")
    args = ap.parse_args()
    d = Path(args.in_dir)

    md = [f"# E8 re-examination — realistic vs original injection ({args.model})", "",
          "Same elicitation protocol (C0 pointwise / C3 atomic / AFC 2-AFC) on the realistic "
          "defect variants vs the original (ill-posed) injections. Detection = balanced accuracy "
          "[95% Wilson CI]; AFC = rate the defective is called worse (chance 0.5).", ""]
    js = {}
    for label, rtag, otag, defect in CONTRASTS:
        md += [f"## {label}", "", "| condition | realistic | original injection |", "|---|---|---|"]
        rj, verdict_bits = {}, {}
        for cond in CONDS:
            rc = cell(_load(d, rtag, cond), cond, defect)
            oc = cell(_load(d, otag, cond), cond, defect) if otag else None
            md.append(f"| {cond} | {fmt(rc)} | {fmt(oc)} |")
            rj[cond] = {"realistic": rc, "original": oc}
            verdict_bits[cond] = (rc, oc)
        # C0 is suppressed by design (the format-suppression thesis), so judge detection
        # on the SENSITIVE conditions: realistic detected if it clears chance under C3 OR
        # AFC; original counts as 'at chance' only if it stays at chance on ALL of them.
        rc = next((verdict_bits[c][0] for c in ("C3", "AFC")
                   if above_chance(verdict_bits.get(c, (None,))[0])), verdict_bits.get("C3", (None, None))[0])
        oc = verdict_bits.get("C3", (None, None))[1]
        orig_at_chance = otag and all(near_chance(verdict_bits.get(c, (None, None))[1]) is not False
                                      for c in ("C0", "C3", "AFC"))
        if otag is None:
            v = "realistic-only (original degenerate set has no clean twin; compare to paper's reported chance)."
        elif above_chance(rc) and orig_at_chance:
            v = "**INJECTION ARTIFACT** — original ~chance but realistic variant is detected; the 'at chance' claim must be rewritten."
        elif near_chance(rc) and near_chance(oc):
            v = "sub-perceptual claim **survives** — even the realistic variant stays ~chance."
        elif above_chance(rc) and above_chance(oc):
            v = "detectable in both — never really at chance."
        else:
            v = "mixed — inspect cells."
        md += ["", f"**Verdict:** {v}", ""]
        js[label] = {"defect": defect, "by_cond": rj, "verdict": v}

    Path(d / "comparison.md").write_text("\n".join(md))
    Path(d / "comparison.json").write_text(json.dumps(js, indent=2, ensure_ascii=False))
    print("\n".join(md))
    print(f"[write] {d/'comparison.md'}\n[write] {d/'comparison.json'}")


if __name__ == "__main__":
    main()
