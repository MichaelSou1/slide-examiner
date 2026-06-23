"""Aggregate the Protocol-1 elicitation sweep into the A.4 tables.

Reads the per-(model,tag,condition) result JSONs written by part3_elicit.py
(data/part3/p1_<model>_<tag>_<cond>.json) and emits:
  * a per (model x defect) table of C0/C1/C2/C3 at the HEADLINE level
    (named for in-taxonomy G1/S6, detection for the G7 extension), with
    bal-acc [Wilson CI], precision, recall, FPR, n;
  * the C3-vs-C0 special table (the "format suppression, not capability"
    evidence) with a two-proportion z-test on recall;
  * the A.4 rescue judgment per (model,defect): rescued iff some elicitation
    beats C0 on bal-acc with non-overlapping CIs AND precision >= 0.70.

Usage:
  python scripts/part3_p1_summary.py --glob 'data/part3/p1_*_*_*.json' \
    --out data/part3/p1_summary.json --md reports/_p1_tables.md
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.statistics import two_proportion_z_test  # noqa: E402

CONDS = ["C0", "C1", "C2", "C3"]
DEFECT_ORDER = ["G1_TEXT_OVERFLOW", "S6_IMAGE_TEXT_CONTRADICTION", "G7_RENDER_CONTAINMENT_OVERFLOW"]
SHORT = {"G1_TEXT_OVERFLOW": "G1", "S6_IMAGE_TEXT_CONTRADICTION": "S6",
         "G7_RENDER_CONTAINMENT_OVERFLOW": "G7"}
PRECISION_BAR = 0.70


def _headline(per_defect_entry: dict) -> dict:
    lvl = per_defect_entry.get("headline_level", "named")
    cell = dict(per_defect_entry[lvl])
    cell["level"] = lvl
    return cell


def load(glob_pat: str) -> dict:
    """results[model][defect][cond] = {headline cell, detection, named}."""
    results: dict = {}
    for path in sorted(glob.glob(str(REPO / glob_pat))):
        data = json.loads(Path(path).read_text())
        model, cond = data.get("model"), data.get("condition")
        per_mod = (data.get("metrics") or {}).get("A") or {}
        for defect, entry in (per_mod.get("per_defect") or {}).items():
            results.setdefault(model, {}).setdefault(defect, {})[cond] = {
                "headline": _headline(entry),
                "detection": entry.get("detection"),
                "named": entry.get("named"),
            }
    return results


def load_correct(glob_pat: str) -> dict:
    """per-image CORRECTNESS map for the paired McNemar test (captures BOTH recall
    AND specificity gains — e.g. when C0 already flags every positive, the rescue
    shows up as fewer false alarms on the clean controls, which a recall-only test
    would miss). correct = (has_defect == is a defective image). Keyed by sample_id
    (clean variants carry a __CLEAN suffix, so pos/clean rows are distinct keys)."""
    hits: dict = {}
    for path in sorted(glob.glob(str(REPO / glob_pat))):
        # filename: p1_<model>_<tag>_<cond>_rows.jsonl
        body = Path(path).name[len("p1_"):-len("_rows.jsonl")]
        model, cond = body.split("_")[0], body.split("_")[-1]
        for line in Path(path).open():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("failure"):
                continue
            correct = bool(r["has_defect"]) == (not r.get("is_clean"))
            hits.setdefault(model, {}).setdefault(r.get("defect"), {}).setdefault(
                cond, {})[r["sample_id"]] = correct
    return hits


def mcnemar_p(c0: dict, cx: dict) -> tuple[float, int, int]:
    """Exact two-sided McNemar over positives shared by C0 and Cx.
    b = C0 miss & Cx hit (Cx gains); c = C0 hit & Cx miss (Cx loses)."""
    shared = set(c0) & set(cx)
    b = sum(1 for s in shared if (not c0[s]) and cx[s])
    c = sum(1 for s in shared if c0[s] and (not cx[s]))
    n = b + c
    if n == 0:
        return 1.0, b, c
    k = min(b, c)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) * (0.5 ** n))
    return p, b, c


def _fmt(cell: dict | None) -> str:
    if not cell:
        return "—"
    h = cell["headline"]
    ci = h.get("bal_acc_ci") or [0, 0]
    return (f"{h['bal_acc']:.2f} [{ci[0]:.2f}-{ci[1]:.2f}] "
            f"p={h['precision']:.2f} r={h['recall']:.2f} fpr={h['fpr']:.2f} n={h['n_pos']}/{h['n_neg']}")


def _baccstr(h: dict | None) -> str:
    """bal-acc [95% Wilson CI] (n=pos+neg) — no bare point estimate (E2)."""
    if not h:
        return "—"
    ci = h.get("bal_acc_ci") or [0, 0]
    n = (h.get("n_pos") or 0) + (h.get("n_neg") or 0)
    return f"{h['bal_acc']:.2f} [{ci[0]:.2f}-{ci[1]:.2f}] (n={n})"


def judge(defect_results: dict, pos_hits: dict | None) -> dict:
    """A.4 rescue judgment for one (model,defect), two tiers:
      RESCUED  = Δbal-acc>0 AND McNemar p<0.05 (paired, same images) AND precision>=0.70
      IMPROVED = Δbal-acc>=0.10 AND precision>=0.70 (usable lift, not significant)
    McNemar tests the paired positive-detection gain of Cx over C0 on shared images."""
    c0 = defect_results.get("C0", {}).get("headline")
    out = {"rescued": False, "by": None, "improved": [], "detail": {}}
    if not c0:
        return out
    c0_b = c0["bal_acc"]
    pos_hits = pos_hits or {}
    for cond in ["C1", "C2", "C3"]:
        cx = defect_results.get(cond, {}).get("headline")
        if not cx:
            continue
        delta = cx["bal_acc"] - c0_b
        prec_ok = cx["precision"] >= PRECISION_BAR
        p_mc, b, c = mcnemar_p(pos_hits.get("C0", {}), pos_hits.get(cond, {}))  # per-image correctness
        ztest = two_proportion_z_test(cx["tp"], cx["n_pos"], c0["tp"], c0["n_pos"])
        rescued = (delta > 0) and (p_mc < 0.05) and prec_ok and (b > c)
        improved = (not rescued) and (delta >= 0.10) and prec_ok
        out["detail"][cond] = {
            "delta_bal_acc": round(delta, 3), "precision": cx["precision"],
            "precision_ok": prec_ok, "mcnemar_p": round(p_mc, 4), "mcnemar_gain_loss": [b, c],
            "recall_z_p": round(ztest.p_value, 4), "rescued": rescued, "improved": improved,
        }
        if rescued and not out["rescued"]:
            out["rescued"], out["by"] = True, cond
        if improved:
            out["improved"].append(cond)
    return out


G7_DEFECT = "G7_RENDER_CONTAINMENT_OVERFLOW"
_VARIANT_KW = {
    "card_height": ["bullet", "list", "item", "card", "below", "bottom"],
    "unbreakable_text": ["text", "url", "endpoint", "string", "right", "edge", "link", "address"],
    "image_objectfit": ["image", "figure", "picture", "frame", "bleed", "overflow", "graphic"],
}


def load_g7_gt() -> dict:
    """sample_id -> {region, variant} ground truth for the synthetic G7 set."""
    gt: dict = {}
    p = REPO / "data/part3/manifest_g7_rendered.jsonl"
    if not p.exists():
        return gt
    for line in p.open():
        if not line.strip():
            continue
        r = json.loads(line)
        gt[r["sample_id"]] = {"region": r["metadata"]["overflow_region"],
                              "variant": r["metadata"]["g7_variant"]}
    return gt


def localization_g7(glob_pat: str, gt: dict) -> dict:
    """loc[model][cond] = {region_acc, elem_acc, n} over the TRUE-POSITIVE G7
    detections, checking the model's forced evidence (locator.region / .element)
    against ground truth. This is the anti-hallucination check: a model that
    bluffed 'yes' cannot point to the right region or name the spilling element."""
    loc: dict = {}
    for path in sorted(glob.glob(str(REPO / glob_pat))):
        name = Path(path).name
        if "_g7_" not in name:
            continue
        body = name[len("p1_"):-len("_rows.jsonl")]
        model, cond = body.split("_")[0], body.split("_")[-1]
        reg = el = n = 0
        for line in Path(path).open():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("is_clean") or r.get("failure") or not r.get("has_defect"):
                continue
            g = gt.get(r["sample_id"])
            if not g:
                continue
            locd = r.get("locator") or {}
            mreg = str(locd.get("region", "") or "").lower()
            mel = str(locd.get("element", "") or "").lower()
            n += 1
            if g["region"] and any(w in mreg for w in g["region"].split("-")):
                reg += 1
            if any(k in mel for k in _VARIANT_KW.get(g["variant"], [])):
                el += 1
        if n:
            loc.setdefault(model, {})[cond] = {"region_acc": round(reg / n, 3),
                                               "elem_acc": round(el / n, 3), "n": n}
    return loc


def md_tables(results: dict, judgments: dict, loc: dict) -> str:
    lines = ["### Protocol-1 — elicitation recovery (modality A, paired-clean)\n",
             "Cell = **detection** bal-acc [95% Wilson CI] · p=precision · r=recall · fpr · n=pos/neg "
             "(detection = the model asserts a defect + localizes; a free-form critic that sees an "
             "overflow but the cheap classifier labels it a neighbour type still *detected* it). "
             "Verdict: ✅=rescued (Δbal-acc>0, McNemar p<0.05, precision≥0.70); "
             "⬆=improved (Δbal-acc≥0.10, precision≥0.70, n.s.); ❌=neither.\n",
             "| Model | Defect | C0 (baseline) | C1 free-form | C2 synth-twin | C3 atomic-binary | Verdict |",
             "|---|---|---|---|---|---|---|"]
    for model in sorted(results):
        for defect in DEFECT_ORDER:
            if defect not in results.get(model, {}):
                continue
            dr = results[model][defect]
            j = judgments[model][defect]
            if j["rescued"]:
                verdict = f"✅ {j['by']}"
            elif j["improved"]:
                verdict = "⬆ " + ",".join(j["improved"])
            else:
                verdict = "❌"
            lines.append(f"| {model} | {SHORT[defect]} | " + " | ".join(
                _fmt(dr.get(c)) for c in CONDS) + f" | {verdict} |")

    lines += ["\n### C3 vs C0 — \"format suppression, not capability\" (same model/taxonomy/image)\n",
              "Cells = bal-acc [95% Wilson CI] (n=pos+neg). McNemar p is the paired exact test on "
              "per-image correctness; the family-wise Holm-corrected p is reported in "
              "`reports/part3_multiplicity.md` (E2).\n",
              "| Model | Defect | C0 bal-acc [CI] (n) | C3 bal-acc [CI] (n) | Δ | C3 precision | McNemar p (paired) |",
              "|---|---|---|---|---|---|---|"]
    for model in sorted(results):
        for defect in DEFECT_ORDER:
            if defect not in results.get(model, {}):
                continue
            dr = results[model][defect]
            c0 = dr.get("C0", {}).get("headline")
            c3 = dr.get("C3", {}).get("headline")
            if not c0 or not c3:
                continue
            d = judgments[model][defect]["detail"].get("C3", {})
            lines.append(f"| {model} | {SHORT[defect]} | {_baccstr(c0)} | {_baccstr(c3)} | "
                         f"{c3['bal_acc']-c0['bal_acc']:+.2f} | {c3['precision']:.2f} | "
                         f"{d.get('mcnemar_p','—')} |")

    lines += ["\n### Localization verification — is the G7 rescue real perception or hallucination?\n",
              "For every C3 *yes* on a G7 **defective**, we check the forced evidence against ground truth (the "
              "synthetic G7 set knows the overflow region + which element spills). A model that bluffed *yes* "
              "could not point to the right region or name the spilling element. (C3 only — it carries a "
              "region+element locator; n = true-positive detections.)\n",
              "| Model | C3 G7 detections (n) | region correct | element correct |",
              "|---|---|---|---|"]
    for model in sorted(results):
        cell = (loc.get(model) or {}).get("C3")
        if not cell:
            continue
        lines.append(f"| {model} | {cell['n']} | {cell['region_acc']:.0%} | {cell['elem_acc']:.0%} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/part3/p1_*_*_*.json")
    ap.add_argument("--out", default="data/part3/p1_summary.json")
    ap.add_argument("--md", default="reports/_p1_tables.md")
    args = ap.parse_args()

    results = load(args.glob)
    if not results:
        raise SystemExit(f"no result files matched {args.glob}")
    rows_glob = args.glob.replace(".json", "_rows.jsonl")
    correct = load_correct(rows_glob)
    judgments = {m: {d: judge(results[m][d], correct.get(m, {}).get(d))
                     for d in results[m]} for m in results}
    loc = localization_g7(rows_glob, load_g7_gt())

    summary = {"results": results, "judgments": judgments, "localization_g7": loc,
               "rescued_cells": [f"{m}/{SHORT.get(d,d)}:{judgments[m][d]['by']}"
                                 for m in judgments for d in judgments[m] if judgments[m][d]["rescued"]]}
    Path(REPO / args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md = md_tables(results, judgments, loc)
    Path(REPO / args.md).write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[summary] rescued cells: {summary['rescued_cells'] or 'none'}")
    print(f"[summary] -> {args.out} + {args.md}")


if __name__ == "__main__":
    main()
