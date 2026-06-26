#!/usr/bin/env python3
"""Regenerate fig5 (C3 vs C0 on G7 across the roster) from the p1e1 decomposition run.

Single-sources the G7 recovery figure on the E1 decomposition run (p1e1_*, full
manifest, n=60/89/90/90) so it matches the §5.1 quartet and the decomposition
paragraph. See specs/todo_0625.md Issue #1 and memory data-generations-provenance.
"""
import json
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "part3")
OUT = os.path.join(os.path.dirname(__file__), "..", "paper", "figs", "fig5_c3_vs_c0_g7.png")
G7 = "G7_RENDER_CONTAINMENT_OVERFLOW"

MODELS = [
    ("qwen35-9b", "Qwen3.5\n9B"),
    ("qwen35-27b", "Qwen3.5\n27B"),
    ("qwen36-27b", "Qwen3.6\n27B"),
    ("gemma4-31b", "Gemma4\n31B"),
    ("internvl-8b", "InternVL\n8B"),
    ("ovis-9b", "Ovis2.5\n9B"),
]
N_CAPABLE = 4
C0_COLOR = "#b3b3b3"
C3_COLOR = "#2e6e87"
CHANCE_COLOR = "#b5413b"


def bal(model, cond):
    f = os.path.join(DATA, f"p1e1_{model}_g7_{cond}.json")
    d = json.load(open(f))
    return d["metrics"]["A"]["per_defect"][G7]["detection"]["bal_acc"]


def main():
    c0 = [bal(m, "C0") for m, _ in MODELS]
    c3 = [bal(m, "C3") for m, _ in MODELS]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = list(range(len(MODELS)))
    w = 0.38
    b0 = ax.bar([i - w / 2 for i in x], c0, w, color=C0_COLOR,
                label="C0 pointwise+rubric (whole taxonomy)")
    b3 = ax.bar([i + w / 2 for i in x], c3, w, color=C3_COLOR,
                label="C3 atomic-binary + forced evidence")
    for bars, vals in ((b0, c0), (b3, c3)):
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.02, f"{v:.2f}",
                    ha="center", va="bottom", fontsize=11)

    ax.axhline(0.5, ls="--", lw=1.4, color=CHANCE_COLOR, zorder=0)
    ax.text(len(MODELS) - 0.55, 0.515, "chance", color=CHANCE_COLOR,
            fontsize=11, style="italic")

    # capable-subset annotation bar over the first N_CAPABLE groups
    ax.plot([-w, N_CAPABLE - 1 + w], [1.12, 1.12], color="#7a7a7a", lw=1.3)
    ax.text((N_CAPABLE - 1) / 2.0, 1.145,
            "capable models $\\rightarrow$ ceiling ($\\geq$0.93, prec 0.88-1.0)",
            ha="center", va="bottom", fontsize=11, color="#555555")
    ax.text(N_CAPABLE + 0.5, 1.145, "weak: honest floor", ha="center",
            va="bottom", fontsize=11, color="#555555", style="italic")

    ax.set_ylim(0, 1.25)
    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab in MODELS], fontsize=12)
    ax.set_ylabel("G7 balanced accuracy", fontsize=13, style="italic")
    ax.set_title("Atomic-binary elicitation (C3) recovers the linter-blind render "
                 "class G7\nacross 4 model families and 3 scales",
                 fontsize=15, fontweight="bold")
    ax.legend(loc="lower left", fontsize=10, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT, dpi=150, bbox_inches="tight")
    print("wrote", os.path.normpath(OUT))
    print("C0:", {m: round(v, 3) for (m, _), v in zip(MODELS, c0)})
    print("C3:", {m: round(v, 3) for (m, _), v in zip(MODELS, c3)})


if __name__ == "__main__":
    main()
