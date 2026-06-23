"""Part 3 Protocol-2/3 summary -> markdown tables for reports/part3_hybrid.md.

Reads the Protocol-2 (hybrid coverage) and Protocol-3 (reward audit, fidelity)
artifacts and renders the Result-2 / Result-3 tables. Offline.

  data/part3/p2_synth.json       -> synthetic coverage (linter/VLM/C3 baselines/hybrid)
  data/part3/p2_slideaudit.json  -> real-data (image-only) VLM C0 vs C3
  data/part3/p3_audit.json       -> DocReward preference accuracy
  data/part3/p3_fidelity.json    -> perturbation-fidelity / snap absorption

Usage: python scripts/part3_p2_summary.py > reports/_p2_tables.md
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO / "data/part3"
SHORT = {
    "G1_TEXT_OVERFLOW": "G1 overflow", "G2_ELEMENT_OVERLAP": "G2 overlap",
    "G3_ALIGNMENT_OFFSET": "G3 alignment", "G4_FONT_SIZE_INCONSISTENCY": "G4 font",
    "G5_BRAND_COLOR_VIOLATION": "G5 colour", "G6_MARGIN_VIOLATION": "G6 margin",
    "G7_RENDER_CONTAINMENT_OVERFLOW": "G7 render-overflow",
    "S1_TITLE_BODY_MISMATCH": "S1 title-body", "S2_NARRATIVE_ORDER_BREAK": "S2 narrative",
    "S3_TERMINOLOGY_INCONSISTENCY": "S3 terminology",
    "S4_DENSITY_RULE_VIOLATION": "S4 density", "S6_IMAGE_TEXT_CONTRADICTION": "S6 image-text",
}


def cellstr(c, show_n=False):
    """bal-acc [95% Wilson CI] · p=precision (· n=pos+neg when show_n). No bare
    point estimate is emitted (E2): every cell carries its interval."""
    if not c:
        return "—"
    ci = c.get("bal_acc_ci")
    ci_str = f" [{ci[0]:.2f},{ci[1]:.2f}]" if ci else ""
    out = f"{c['bal_acc']:.2f}{ci_str} p{c['precision']:.2f}"
    if show_n:
        n = (c.get("n_pos") or 0) + (c.get("n_neg") or 0)
        if n:
            out += f" n={n}"
    return out


def load(name):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else None


def synth_tables():
    d = load("p2_synth.json")
    if not d:
        return "_p2_synth.json missing_\n"
    L = [f"### Result 2a — synthetic all-class coverage ({d['model']}, "
         f"named attribution, paired-clean bal-acc · precision; freeform renders, "
         f"mpd={d['max_per_defect']})\n"]
    L.append("| Defect | route | linter-only | VLM-only (C0) | VLM-C3 everywhere | linter+VLM-C3 | hybrid (routed) |")
    L.append("|---|---|---|---|---|---|---|")
    pc = d["per_class"]
    cp = d.get("config_per_class", {})
    route = d["router"]
    for dd, cell in pc.items():
        eng = route.get(dd, "?")
        c3 = (cp.get("vlm_c3_everywhere", {}) or {}).get(dd) or cell.get("vlm_c3")
        lpc3 = (cp.get("linter_plus_vlmc3", {}) or {}).get(dd)
        L.append(f"| {SHORT.get(dd, dd)} | {eng} | {cellstr(cell.get('linter'), show_n=True)} | "
                 f"{cellstr(cell.get('vlm_c0'), show_n=True)} | "
                 f"{cellstr(c3, show_n=True)} | "
                 f"{cellstr(lpc3, show_n=True)} | "
                 f"{cellstr(cell.get(_routed_key(eng)), show_n=True)} |")
    cov = d["coverage"]
    L.append("")
    L.append("| Critic config | mean bal-acc | classes covered (bal-acc≥0.70 & prec≥0.70) |")
    L.append("|---|---|---|")
    labels = {
        "linter_only": "linter_only",
        "vlm_only": "vlm_only (C0)",
        "vlm_c3_everywhere": "vlm_c3_everywhere",
        "linter_plus_vlmc3": "linter_plus_vlmc3",
        "hybrid": "hybrid (routed)",
    }
    for k in ["linter_only", "vlm_only", "vlm_c3_everywhere", "linter_plus_vlmc3", "hybrid"]:
        if k not in cov:
            continue
        a = cov[k]
        L.append(f"| {labels[k]} | {a['mean_bal_acc']} | {a['n_covered_0.70']} / {a['n_classes']} "
                 f"({', '.join(SHORT.get(c, c) for c in a['covered_classes'])}) |")
    return "\n".join(L) + "\n"


def _routed_key(eng):
    return {"linter": "linter", "vlm": "vlm_best", "llm": "llm"}.get(eng, "vlm_c0")


def slideaudit_table():
    d = load("p2_slideaudit.json")
    if not d:
        return "_p2_slideaudit.json missing_\n"
    L = [f"\n### Result 2b — real data (SlideAudit, image-only) — {d['model']}\n",
         f"> {d['linter_note']}\n",
         "| Defect (SlideAudit) | VLM C0 | VLM C3 (atomic) | n₊/n₋ |",
         "|---|---|---|---|"]
    for dd, cell in d["per_class"].items():
        L.append(f"| {SHORT.get(dd, dd)} | {cellstr(cell.get('C0'))} | "
                 f"{cellstr(cell.get('C3'))} | {cell.get('n_pos')}/{cell.get('n_neg')} |")
    return "\n".join(L) + "\n"


def reward_table():
    d = load("p3_audit.json")
    if not d:
        return "_p3_audit.json missing_\n"
    L = [f"\n### Result 3a — published reward-model audit ({d['model']})\n",
         f"> metric: {d['metric']}\n",
         "| Defect | render | preference acc [95% CI] | mean reward gap (clean−def) | n |",
         "|---|---|---|---|---|"]
    for r in d["results"]:
        ci = f"[{r['preference_ci'][0]:.2f}, {r['preference_ci'][1]:.2f}]"
        L.append(f"| {SHORT.get(r['defect'], r['defect'])} | {r['variant']} | "
                 f"{r['preference_accuracy']:.2f} {ci} | "
                 f"{r['mean_reward_gap_clean_minus_def']:+.3f} | {r['n']} |")
    return "\n".join(L) + "\n"


def fidelity_table():
    d = load("p3_fidelity.json")
    if not d:
        return "_p3_fidelity.json missing_\n"
    o = d["overall"]
    L = [f"\n### Result 3b — perturbation-fidelity audit (snap/template render)\n",
         f"> overall: **{o['template_absorption_rate']:.0%}** of injected defectives "
         f"({o['n_template_pairs']} pairs, all IR-injected) render under freeform but "
         f"are snapped away (pixel-clean) under the template renderer = silent label noise.\n",
         "| Defect | freeform effect (median Δpx frac) | template effect | absorption (among rendered) |",
         "|---|---|---|---|"]
    for dd, v in d["per_defect"].items():
        ff = v["freeform_effect"]["median"] if v["freeform_effect"] else 0
        tp = v["template_effect"]["median"] if v["template_effect"] else 0
        L.append(f"| {SHORT.get(dd, dd)} | {ff:.4f} | {tp:.4f} | "
                 f"{v.get('absorption_among_rendered')} |")
    return "\n".join(L) + "\n"


def main():
    print("<!-- generated by scripts/part3_p2_summary.py -->\n")
    print(synth_tables())
    print(slideaudit_table())
    print(reward_table())
    print(fidelity_table())


if __name__ == "__main__":
    main()
