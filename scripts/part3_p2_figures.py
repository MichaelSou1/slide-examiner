"""Part 3 main figures for reports/part3_hybrid.md (Phase 5).

Fig 1: per-defect coverage heatmap (linter / VLM-C0 / hybrid) — shows the
       bottleneck dichotomy and that the hybrid takes the per-class best.
Fig 2: DocReward preference accuracy per defect with the chance line — the G7
       (and G5) blind spot of a published neural reward model.

Outputs -> docs/figs/*.png (tracked; reports/ is gitignored for non-md).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
D = REPO / "data/part3"
FIGS = REPO / "docs/figs"
FIGS.mkdir(parents=True, exist_ok=True)

SHORT = {
    "G1_TEXT_OVERFLOW": "G1\noverflow", "G2_ELEMENT_OVERLAP": "G2\noverlap",
    "G3_ALIGNMENT_OFFSET": "G3\nalign", "G5_BRAND_COLOR_VIOLATION": "G5\ncolour",
    "G6_MARGIN_VIOLATION": "G6\nmargin", "G7_RENDER_CONTAINMENT_OVERFLOW": "G7\nrender",
    "S1_TITLE_BODY_MISMATCH": "S1\ntitle-body", "S4_DENSITY_RULE_VIOLATION": "S4\ndensity",
    "S6_IMAGE_TEXT_CONTRADICTION": "S6\nimg-text",
}
ORDER = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
         "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION",
         "G7_RENDER_CONTAINMENT_OVERFLOW", "S1_TITLE_BODY_MISMATCH",
         "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION"]


def fig_coverage():
    d = json.loads((D / "p2_synth.json").read_text())
    # read the authoritative per-config cells the merge computed (do NOT recompute
    # routing from the json's `router` field, which can be stale after a re-route).
    cp = d["config_per_class"]
    cfgs = ["linter_only", "vlm_only", "hybrid"]
    labels = ["linter\nonly", "VLM only\n(C0)", "hybrid\n(routed)"]
    M = np.full((len(cfgs), len(ORDER)), np.nan)
    for j, dd in enumerate(ORDER):
        for i, c in enumerate(cfgs):
            v = (cp[c].get(dd) or {}).get("bal_acc")
            if v is not None:
                M[i, j] = v

    fig, ax = plt.subplots(figsize=(11, 3.4))
    im = ax.imshow(M, cmap="RdYlGn", vmin=0.4, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(ORDER)))
    ax.set_xticklabels([SHORT[d] for d in ORDER], fontsize=9)
    ax.set_yticks(range(len(cfgs)))
    ax.set_yticklabels(labels, fontsize=10)
    for i in range(len(cfgs)):
        for j in range(len(ORDER)):
            if not np.isnan(M[i, j]):
                ax.text(j, i, f"{M[i, j]:.2f}", ha="center", va="center", fontsize=9,
                        color="black")
    cov = d["coverage"]
    ax.set_title("Per-defect detection (balanced accuracy) — symbolic linter vs a single VLM vs the routed hybrid\n"
                 f"covered (≥0.70 & prec≥0.70):  linter {cov['linter_only']['n_covered_0.70']}/9   "
                 f"VLM {cov['vlm_only']['n_covered_0.70']}/9   "
                 f"hybrid {cov['hybrid']['n_covered_0.70']}/9   |   "
                 f"mean bal-acc {cov['linter_only']['mean_bal_acc']} / {cov['vlm_only']['mean_bal_acc']} / {cov['hybrid']['mean_bal_acc']}",
                 fontsize=9.5)
    # highlight G7 column
    g7 = ORDER.index("G7_RENDER_CONTAINMENT_OVERFLOW")
    ax.add_patch(plt.Rectangle((g7 - 0.5, -0.5), 1, len(cfgs), fill=False, edgecolor="blue", lw=2))
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, label="balanced accuracy")
    fig.tight_layout()
    out = FIGS / "p3_coverage_heatmap.png"
    fig.savefig(out, dpi=150)
    print("wrote", out)


def fig_reward():
    d = json.loads((D / "p3_audit.json").read_text())
    rows = [r for r in d["results"] if r["variant"] == "freeform"]
    rows.sort(key=lambda r: r["preference_accuracy"])
    names = [SHORT.get(r["defect"], r["defect"]).replace("\n", " ") for r in rows]
    acc = [r["preference_accuracy"] for r in rows]
    lo = [r["preference_accuracy"] - r["preference_ci"][0] for r in rows]
    hi = [r["preference_ci"][1] - r["preference_accuracy"] for r in rows]
    colors = ["#d62728" if a < 0.6 else "#2ca02c" for a in acc]

    fig, ax = plt.subplots(figsize=(8, 3.6))
    y = np.arange(len(names))
    ax.barh(y, acc, xerr=[lo, hi], color=colors, alpha=0.85, capsize=3)
    ax.axvline(0.5, color="black", ls="--", lw=1)
    ax.text(0.5, len(names) - 0.3, " chance", fontsize=8, va="center")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("preference accuracy  P(reward(clean) > reward(defective))", fontsize=9)
    ax.set_title("DocReward-3B is blind to the render class G7 (and to G5 colour)\n"
                 "0.5 = chance; G7 = 0.28 (CI entirely below chance — it prefers the broken slide)",
                 fontsize=9.5)
    fig.tight_layout()
    out = FIGS / "p3_reward_blindspot.png"
    fig.savefig(out, dpi=150)
    print("wrote", out)


def fig_reward_multi():
    """Multi-RM blind-spot heatmap (Figure 5): preference accuracy per reward
    model x defect class, G7 column highlighted, diverging colour centred on
    chance (0.5). The model-agnostic evidence: every trained reward sits at/below
    chance on G7 while seeing the in-taxonomy classes."""
    from matplotlib.colors import TwoSlopeNorm
    fp = D / "p3_audit_multi.json"
    if not fp.exists():
        print("skip fig_reward_multi (no p3_audit_multi.json)")
        return
    d = json.loads(fp.read_text())
    # classes present in freeform runs, in canonical order
    classes = [c for c in ORDER if any(c in m["freeform"] for m in d["models"])]
    # order models: trained first (document, general_mm, design), aesthetic last
    cat_rank = {"document": 0, "general_mm": 1, "design": 2, "aesthetic": 9}
    models = sorted(d["models"], key=lambda m: (cat_rank.get(m["category"], 5), m["display_name"]))
    M = np.full((len(models), len(classes)), np.nan)
    for i, m in enumerate(models):
        for j, c in enumerate(classes):
            cell = m["freeform"].get(c)
            if cell is not None:
                M[i, j] = cell["preference_accuracy"]

    fig, ax = plt.subplots(figsize=(1.15 * len(classes) + 2.5, 0.62 * len(models) + 2.0))
    norm = TwoSlopeNorm(vmin=0.0, vcenter=0.5, vmax=1.0)
    im = ax.imshow(M, cmap="RdYlGn", norm=norm, aspect="auto")
    ax.set_xticks(range(len(classes)))
    ax.set_xticklabels([SHORT[c] for c in classes], fontsize=9)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([f"{m['display_name']}\n({m['category'].replace('_','-')})" for m in models],
                       fontsize=8.5)
    for i in range(len(models)):
        for j in range(len(classes)):
            if not np.isnan(M[i, j]):
                v = M[i, j]
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8.5,
                        color="black", fontweight="bold" if v <= 0.5 else "normal")
    # highlight the G7 column
    if "G7_RENDER_CONTAINMENT_OVERFLOW" in classes:
        g7 = classes.index("G7_RENDER_CONTAINMENT_OVERFLOW")
        ax.add_patch(plt.Rectangle((g7 - 0.5, -0.5), 1, len(models), fill=False,
                                   edgecolor="blue", lw=2.2))
    g7row = d.get("g7_cross_model", [])
    n_reli = sum(1 for r in g7row if r.get("reliably_detects_g7"))
    n_tot = len(g7row)
    ax.set_title("Reward preference  P(reward(clean) > reward(defective))  per reward model x defect class\n"
                 f"diverging at chance=0.5 (red=mis-ranks, green=sensitive);  G7 render-containment (boxed): "
                 f"{n_reli}/{n_tot} reliably detect it\n"
                 "the symbolic linter and narrow (document / aesthetic) rewards miss G7; a general-VLM reward detects it",
                 fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, label="preference accuracy")
    fig.tight_layout()
    out = FIGS / "p3_reward_blindspot_multi.png"
    fig.savefig(out, dpi=150)
    print("wrote", out)


if __name__ == "__main__":
    fig_coverage()
    fig_reward()
    fig_reward_multi()
