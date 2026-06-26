"""E2 — collect every reported p-value and correct for multiplicity.

R1-W3 / EIC-W3: dozens of significance tests are reported across the paper with no
family-wise / FDR correction. This script gathers the full reported family from the
stored artifacts, applies Holm (FWER) and Benjamini-Hochberg (FDR) at alpha=0.05,
and writes the corrected table the paper footnotes. Pure offline.

Family collected:
  * elicitation  — every (model, defect, condition) paired McNemar from
                   ``data/part3/p1_summary.json`` (C0 vs C1/C2/C3 recovery tests).
  * examiner     — the two reported two-proportion-z recall contrasts recomputed
                   from ``runs/probe/part2_summary.json`` (S4 density synth + real).
  * reward       — each reward model's G7 preference vs chance (one-proportion z),
                   from ``data/part3/p3_audit_multi.json``.

Usage:
  python scripts/part3_multiplicity.py \
    --md reports/part3_multiplicity.md --json data/part3/p3_multiplicity.json
"""
from __future__ import annotations

import argparse
import json
import sys
from math import sqrt
from pathlib import Path
from statistics import NormalDist

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from slide_examiner.statistics import benjamini_hochberg, holm_bonferroni, stratified_mcnemar  # noqa: E402

G7 = "G7_RENDER_CONTAINMENT_OVERFLOW"
G1 = "G1_TEXT_OVERFLOW"
SHORT = {"G1_TEXT_OVERFLOW": "G1", "S6_IMAGE_TEXT_CONTRADICTION": "S6", G7: "G7"}
# The paper's actual headline elicitation claims (not every cell): C3 recovers G7 on
# the four CAPABLE models; C2 recovers declared-geometry G1 on the two strong Qwens.
CAPABLE_G7_C3 = {"qwen35-9b", "qwen35-27b", "qwen36-27b", "gemma4-31b"}
STRONG_G1_C2 = {"qwen35-27b", "qwen36-27b"}


def _is_headline_elicit(model: str, defect: str, cond: str) -> bool:
    if cond == "C3" and defect == G7 and model in CAPABLE_G7_C3:
        return True
    if cond == "C2" and defect == G1 and model in STRONG_G1_C2:
        return True
    return False


def one_prop_z(k: int, n: int, p0: float = 0.5) -> float:
    """Two-sided one-proportion z-test p-value of phat vs chance p0."""
    if not n:
        return 1.0
    phat = k / n
    se = sqrt(p0 * (1 - p0) / n)
    if se == 0:
        return 1.0
    z = (phat - p0) / se
    return 2 * (1 - NormalDist().cdf(abs(z)))


def _p1e1_g7_c3() -> dict:
    """Single-source the G7 C3-vs-C0 recovery on the E1 decomposition run
    (``p1e1_*``, full 90-pair manifest) rather than the capped-60 original p1 run,
    so the released multiplicity report matches the paper body and Fig. 5. Returns
    ``{model: (b, c, exact_mcnemar_p)}`` using the identical paired-clean per-image
    correctness map and exact McNemar test that ``part3_p1_summary`` applies to p1."""
    from part3_p1_summary import mcnemar_p  # exact two-sided binomial, same definition
    out: dict = {}
    for model in CAPABLE_G7_C3:
        hits: dict = {}
        for cond in ("C0", "C3"):
            f = REPO / f"data/part3/p1e1_{model}_g7_{cond}_rows.jsonl"
            if not f.exists():
                hits = {}
                break
            cm = {}
            for line in f.open():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("failure"):
                    continue
                cm[r["sample_id"]] = bool(r["has_defect"]) == (not r.get("is_clean"))
            hits[cond] = cm
        if hits.get("C0") and hits.get("C3"):
            p, b, c = mcnemar_p(hits["C0"], hits["C3"])
            out[model] = (b, c, p)
    return out


def collect_elicitation() -> list[dict]:
    p = REPO / "data/part3/p1_summary.json"
    if not p.exists():
        return []
    s = json.loads(p.read_text())
    g7 = _p1e1_g7_c3()  # single-source G7 C3 on the full-manifest E1 run
    out = []
    for model, defects in s.get("judgments", {}).items():
        for defect, j in defects.items():
            for cond, detail in (j.get("detail") or {}).items():
                pv = detail.get("mcnemar_p")
                if pv is None:
                    continue
                if defect == G7 and cond == "C3" and model in g7:
                    pv = g7[model][2]
                out.append({"source": "elicitation",
                            "contrast": f"{model}/{SHORT.get(defect, defect)}/{cond}-vs-C0 McNemar",
                            "p": float(pv), "headline": _is_headline_elicit(model, defect, cond)})
    return out


def pooled_headline() -> list[dict]:
    """The cross-model claims ("C3 recovers G7 across capable models", "C2 recovers
    G1 on the strong Qwens") are properly tested as ONE pooled/stratified McNemar,
    not per-model — that is the analysis that matches the claim and dissolves the
    per-cell multiplicity penalty. Reads the per-model discordant counts already
    stored in p1_summary.json (mcnemar_gain_loss = [b, c])."""
    p = REPO / "data/part3/p1_summary.json"
    if not p.exists():
        return []
    s = json.loads(p.read_text())
    g7 = _p1e1_g7_c3()  # single-source G7 C3 on the full-manifest E1 run
    out = []
    plans = [("G7 C3-vs-C0 (capable models)", G7, "C3", CAPABLE_G7_C3),
             ("G1 C2-vs-C0 (strong Qwens)", G1, "C2", STRONG_G1_C2)]
    for label, defect, cond, models in plans:
        strata = []
        for m in models:
            if defect == G7 and cond == "C3" and m in g7:
                strata.append((g7[m][0], g7[m][1]))
                continue
            gl = (s.get("judgments", {}).get(m, {}).get(defect, {})
                  .get("detail", {}).get(cond, {}).get("mcnemar_gain_loss"))
            if gl:
                strata.append((gl[0], gl[1]))
        if not strata:
            continue
        res = stratified_mcnemar(strata)
        out.append({"label": label, "b": res.b_total, "c": res.c_total,
                    "chi2": round(res.chi2, 1), "p": res.p_value,
                    "n_strata": res.n_strata, "max_c_in_stratum": res.max_c_in_stratum,
                    "consistent": res.max_c_in_stratum == 0})
    return out


def collect_examiner() -> list[dict]:
    p = REPO / "runs/probe/part2_summary.json"
    if not p.exists():
        return []
    try:
        from part2_synthesis import best_cell_semantic, g, p_recall
    except Exception:  # noqa: BLE001
        return []
    s = json.loads(p.read_text())
    models = s.get("models", {})
    out = []
    res = p_recall(best_cell_semantic(models.get("ft-8b", {}), "S4_DENSITY_RULE_VIOLATION"),
                   best_cell_semantic(models.get("zs-30b", {}), "S4_DENSITY_RULE_VIOLATION"))
    if res:
        out.append({"source": "examiner", "contrast": "examiner:S4-density-synth(ft8b>zs30b)",
                    "p": float(res.p_value), "headline": True})
    res = p_recall(g(models.get("zs-30b", {}), "slideaudit", "metrics", "S4_DENSITY_RULE_VIOLATION"),
                   g(models.get("ft-8b", {}), "slideaudit", "metrics", "S4_DENSITY_RULE_VIOLATION"))
    if res:
        out.append({"source": "examiner", "contrast": "examiner:S4-density-real(zs30b>ft8b)",
                    "p": float(res.p_value), "headline": True})
    return out


def collect_reward() -> list[dict]:
    p = REPO / "data/part3/p3_audit_multi.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    out = []
    for m in d.get("models", []):
        cell = m.get("freeform", {}).get(G7)
        if not cell or not cell.get("n"):
            continue
        n = cell["n"]
        k = round(cell["preference_accuracy"] * n)
        # the general-mm reward (Skywork) detecting G7 is the headline reward claim;
        # the narrow rewards being at chance is the *expected* null, not a headline test.
        is_general = "skywork" in m.get("key", "").lower() or m.get("category") == "general_mm"
        out.append({"source": "reward",
                    "contrast": f"reward:{m['display_name']}/G7-pref-vs-chance",
                    "p": one_prop_z(k, n), "headline": bool(is_general)})
    return out


def correct(tests: list[dict]) -> dict:
    pvals = [t["p"] for t in tests]
    holm = holm_bonferroni(pvals)
    bh = benjamini_hochberg(pvals)
    for t, hadj, hrej, badj, brej in zip(tests, holm.adjusted, holm.reject, bh.adjusted, bh.reject):
        t["holm_p"], t["holm_reject"] = round(hadj, 6), hrej
        t["bh_p"], t["bh_reject"] = round(badj, 6), brej
    return {"n_tests": len(tests), "alpha": 0.05,
            "n_reject_holm": holm.n_reject, "n_reject_bh": bh.n_reject}


def md_pooled(pooled: list[dict]) -> str:
    if not pooled:
        return ""
    L = ["## Primary cross-model tests (pooled / stratified McNemar)\n",
         "The \"recovers across models\" claims are tested as ONE stratified McNemar over the "
         "per-model matched pairs — the analysis that matches the claim and is immune to the "
         "per-cell multiplicity penalty. `c=0` means not a single reversal in any model.\n",
         "| Claim | b (gain) | c (loss) | χ² | p | strata | fully consistent |",
         "|---|---|---|---|---|---|---|"]
    for r in pooled:
        L.append(f"| {r['label']} | {r['b']} | {r['c']} | {r['chi2']} | {_e(r['p'])} | "
                 f"{r['n_strata']} | {'yes (no reversal)' if r['consistent'] else f'no (max c={r['max_c_in_stratum']})'} |")
    return "\n".join(L) + "\n"


def md(tests: list[dict], summ: dict, pooled: list[dict]) -> str:
    L = [f"# Multiplicity correction (E2)\n",
         md_pooled(pooled),
         f"Family of **{summ['n_tests']}** reported significance tests across elicitation "
         f"(paired McNemar), examiner (two-proportion z), and reward (G7 preference vs chance). "
         f"Holm (FWER) survivors: **{summ['n_reject_holm']}**; Benjamini-Hochberg (FDR) "
         f"survivors: **{summ['n_reject_bh']}** at α=0.05.\n",
         "| Source | Contrast | raw p | Holm p | Holm✓ | BH p | BH✓ | headline |",
         "|---|---|---|---|---|---|---|---|"]
    order = {"examiner": 0, "elicitation": 1, "reward": 2}
    for t in sorted(tests, key=lambda x: (order.get(x["source"], 9), x["p"])):
        L.append(f"| {t['source']} | {t['contrast']} | {_e(t['p'])} | {_e(t['holm_p'])} | "
                 f"{'✓' if t['holm_reject'] else '·'} | {_e(t['bh_p'])} | "
                 f"{'✓' if t['bh_reject'] else '·'} | {'★' if t['headline'] else ''} |")
    # headline survival callout
    L.append("\n## Headline-claim survival\n")
    for t in [t for t in tests if t["headline"]]:
        verdict = "**survives**" if t["holm_reject"] else ("survives BH only" if t["bh_reject"] else "**does NOT survive**")
        L.append(f"- {t['contrast']}: raw p={_e(t['p'])} → Holm p={_e(t['holm_p'])} → {verdict}.")
    return "\n".join(L) + "\n"


def _e(x):
    if x is None:
        return "—"
    return f"{x:.2e}" if (x < 1e-3 and x > 0) else f"{x:.4f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default="reports/part3_multiplicity.md")
    ap.add_argument("--json", default="data/part3/p3_multiplicity.json")
    args = ap.parse_args()

    tests = collect_elicitation() + collect_examiner() + collect_reward()
    if not tests:
        raise SystemExit("no p-values collected — are the summary artifacts present?")
    pooled = pooled_headline()
    summ = correct(tests)
    body = md(tests, summ, pooled)
    Path(REPO / args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO / args.md).write_text(body, encoding="utf-8")
    Path(REPO / args.json).write_text(
        json.dumps({"summary": summ, "pooled_cross_model": pooled, "tests": tests},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(body)
    print(f"[multiplicity] {summ}")
    print(f"[multiplicity] -> {args.md} ; {args.json}")


if __name__ == "__main__":
    main()
