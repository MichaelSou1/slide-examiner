"""Generate the two new data figures for the paper.

Numbers are transcribed directly from the frozen reports:
  - Fig 2  : Part-1 Track-P (reports/slideprobe.md Table 2) + Part-2 Table 3.
  - Fig 5  : Part-3 hybrid Result-1 "C3 vs C0 on G7" (reports/part3_hybrid.md).
Run:  /home/gpus/anaconda3/envs/slide-examiner/bin/python paper/figs/make_figs.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent
plt.rcParams.update({
    "font.size": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "figure.dpi": 200,
})

GREY = "#9AA0A6"   # absolute / C0  (the suppressed format)
TEAL = "#1F6F8B"   # relative / C3  (the recovering elicitation)
CHANCE = "#C44E52"


# ----------------------------------------------------------------------------
# Fig 2 — relative judgement revives format-suppressed defects, not sub-perceptual
# ----------------------------------------------------------------------------
def fig2():
    defects = ["G1\noverflow", "S6\nimage-text", "G3\nalignment"]
    pointwise = [0.50, 0.50, 0.50]
    forced    = [1.00, 1.00, 0.50]
    verdict   = ["revived", "revived", "floor"]

    x = np.arange(len(defects))
    w = 0.36
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    b1 = ax.bar(x - w/2, pointwise, w, label="pointwise (absolute)", color=GREY)
    b2 = ax.bar(x + w/2, forced,    w, label="forced-choice (relative)", color=TEAL)
    ax.axhline(0.5, ls="--", lw=1, color=CHANCE)
    ax.text(-0.62, 0.505, "chance", color=CHANCE, fontsize=9, va="bottom", ha="left")

    for b in list(b1) + list(b2):
        h = b.get_height()
        ax.text(b.get_x() + b.get_width()/2, h + 0.015, f"{h:.2f}",
                ha="center", va="bottom", fontsize=9)
    # verdict sits just above each defect group (no collision with tick labels)
    for xi, v, top in zip(x, verdict, [1.00, 1.00, 0.50]):
        ax.text(xi, top + 0.085, v, ha="center", va="bottom", fontsize=10,
                color=(TEAL if v == "revived" else CHANCE), fontweight="bold")

    ax.set_xticks(x); ax.set_xticklabels(defects)
    ax.set_ylim(0, 1.22); ax.set_ylabel("balanced accuracy")
    ax.set_title("Relative judgement revives format-suppressed defects,\nnot sub-perceptual ones",
                 pad=10)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2,
              frameon=False, fontsize=9.5, handlelength=1.2)
    ax.margins(x=0.08)
    fig.subplots_adjust(bottom=0.30, top=0.84)
    fig.savefig(OUT / "fig2_relative_vs_absolute.png", bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------
# Fig 5 — C3 atomic-binary recovers the linter-blind render class G7, across families
# ----------------------------------------------------------------------------
def fig5():
    models = ["Qwen3.5\n9B", "Qwen3.5\n27B", "Qwen3.6\n27B",
              "Gemma4\n31B", "InternVL\n8B", "Ovis2.5\n9B"]
    family_capable = [True, True, True, True, False, False]
    c0 = [0.50, 0.93, 0.52, 0.75, 0.47, 0.59]
    c3 = [0.93, 1.00, 1.00, 1.00, 0.50, 0.61]

    x = np.arange(len(models))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    b1 = ax.bar(x - w/2, c0, w, label="C0 pointwise+rubric (whole taxonomy)", color=GREY)
    b2 = ax.bar(x + w/2, c3, w, label="C3 atomic-binary + forced evidence", color=TEAL)
    ax.axhline(0.5, ls="--", lw=1, color=CHANCE)
    ax.text(5.45, 0.515, "chance", color=CHANCE, fontsize=9, va="bottom", ha="right")

    for b in list(b1) + list(b2):
        h = b.get_height()
        ax.text(b.get_x() + b.get_width()/2, h + 0.012, f"{h:.2f}",
                ha="center", va="bottom", fontsize=8.5)

    # bracket the 4 capable models that reach the ceiling
    ax.annotate("", xy=(3.5, 1.08), xytext=(-0.5, 1.08),
                arrowprops=dict(arrowstyle="-", color="#555"))
    ax.text(1.5, 1.10, "capable models -> ceiling (>=0.93, prec 0.88-1.0)",
            ha="center", va="bottom", fontsize=8.5, color="#555")
    ax.text(4.5, 1.10, "weak: honest floor", ha="center", va="bottom",
            fontsize=8.5, color="#555", style="italic")

    ax.set_xticks(x); ax.set_xticklabels(models)
    ax.set_ylim(0, 1.20); ax.set_ylabel("G7 balanced accuracy")
    ax.set_title("Atomic-binary elicitation (C3) recovers the linter-blind render class G7\n"
                 "across 4 model families and 3 scales")
    ax.legend(loc="lower left", frameon=False, fontsize=9, handlelength=1.2)
    fig.subplots_adjust(bottom=0.18, top=0.82)
    fig.savefig(OUT / "fig5_c3_vs_c0_g7.png", bbox_inches="tight")
    plt.close(fig)


def fig1():
    """Teaser: diagnosis -> architecture. Route each defect to its bottleneck engine."""
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    fig, ax = plt.subplots(figsize=(9.4, 5.3))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5.95); ax.axis("off")

    def box(x, y, w, h, title, body, fc, ec, tcolor="black"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.10",
                     linewidth=1.4, facecolor=fc, edgecolor=ec))
        ax.text(x + w/2, y + h - 0.22, title, ha="center", va="top",
                fontsize=10.5, fontweight="bold", color=tcolor)
        ax.text(x + w/2, y + h - 0.55, body, ha="center", va="top",
                fontsize=8.6, color="#222")

    def arrow(x0, y0, x1, y1, color="#444"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                     mutation_scale=14, lw=1.6, color=color,
                     connectionstyle="arc3,rad=0.0"))

    BLUE, TEALc, GREYc, GOLD = "#DCE7EE", "#CFE3EA", "#ECEDEE", "#FBE9D0"

    box(0.15, 2.05, 2.0, 1.25, "Slide", "declared IR\n+ rendered pixels", "#F4F6F7", "#888")
    box(2.75, 2.05, 1.9, 1.25, "Router", "per-defect bottleneck\n(diagnosis, Sec. 4)", BLUE, "#3B6E8F")

    # three engines
    box(5.55, 3.75, 4.30, 1.40, "Symbolic linter",
        "G2-G6 geometry  -  S3 terms  -  S4 rules\n~0 FP,  bal-acc 0.75-1.0", GREYc, "#777")
    box(5.55, 2.05, 4.30, 1.40, "VLM  (changed elicitation: C3 / pairwise)",
        "G1 overflow  -  G7 render-overflow  -  S1  -  S6\nrecovers format-suppressed perception", TEALc, "#1F6F8B")
    box(5.55, 0.35, 4.30, 1.40, "Text LLM",
        "S2 narrative order  -  deck semantics\ntext-only structural reasoning", "#EDEFF0", "#777")

    arrow(2.15, 2.68, 2.73, 2.68)
    arrow(4.70, 2.95, 5.53, 4.35, "#8a8a8a")     # -> linter  (sub-perceptual)
    arrow(4.70, 2.70, 5.53, 2.75, "#1F6F8B")     # -> VLM     (format-suppressed)
    arrow(4.70, 2.45, 5.53, 1.05, "#8a8a8a")     # -> LLM

    # routing key in the empty lower-left (kept clear of arrows and boxes)
    ax.text(0.30, 1.98, "routing rationale (arrow colour):", fontsize=8.3,
            style="italic", color="#444", ha="left", va="center")
    for yk, col, txt in [(1.58, "#1F6F8B", "format-suppressed  ->  VLM"),
                         (1.21, "#8a8a8a", "sub-perceptual geom  ->  linter"),
                         (0.84, "#8a8a8a", "text / deck semantics  ->  LLM")]:
        ax.plot([0.32, 0.72], [yk, yk], color=col, lw=2.8)
        ax.text(0.82, yk, txt, fontsize=8.2, color="#333", ha="left", va="center")

    # G7 callout
    ax.add_patch(FancyBboxPatch((5.55, -0.0), 4.30, 0.0, boxstyle="round", linewidth=0))
    ax.text(7.70, -0.10,
            "G7: linter-blind (declared bbox legal) + narrow-reward-blind (DocReward 0.48, LAION 0.57 ~ chance)\n"
            "=> caught by a capable VLM: re-elicited (C3, 0.93-1.0) or a general-mm reward (Skywork 0.79)",
            ha="center", va="top", fontsize=8.0, color="#7A3B00",
            bbox=dict(boxstyle="round,pad=0.35", fc=GOLD, ec="#D9A24B", lw=1.0))

    ax.text(5.0, 5.78, "Diagnosis -> architecture: route each defect to its bottleneck-appropriate engine",
            ha="center", va="top", fontsize=12, fontweight="bold")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.13)
    fig.savefig(OUT / "fig1_routing.png", bbox_inches="tight", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    fig1()
    fig2()
    fig5()
    print("wrote fig1_routing.png, fig2_relative_vs_absolute.png, fig5_c3_vs_c0_g7.png")
