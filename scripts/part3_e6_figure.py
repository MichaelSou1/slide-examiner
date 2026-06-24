"""E6 figure + numbers — floored (strong gen) vs unfloored (weak gen) downstream.

Reads the two self-refine regime summaries and emits:
  * stdout: the compare_regimes() decomposition (headroom, correlations, gain
    spread + amplification, per-dimension Δ, verdict) — the numbers for the writeup.
  * a 2-panel figure:
      (A) examiner-quality gradient vs best refinement gain, strong vs weak regime,
          with Pearson r annotated — the headline "does unflooring make it material".
      (B) the weak regime's mechanism: per-dimension first-draft headroom
          (1 − dim_initial) vs the Δ the BEST examiner actually recovers — coverage
          carries the headroom but neither feedback channel can move it.

Outputs -> docs/figs/p3_e6_unfloored.png + paper/figs/fig9_unfloored_downstream.png.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
from slide_examiner.downstream_regime import (  # noqa: E402
    ADDRESSABLE_DIMS, UNADDRESSABLE_DIMS, compare_regimes, ordered_conditions,
)

STRONG = REPO / "runs/probe/part3/self_refine_summary.json"
WEAK = REPO / "data/part3/e6_unfloored_synth.json"
ACT = REPO / "data/part3/e6_actionability.json"
COND_LABEL = {"linter": "linter", "zero_shot_8b": "zs-8B", "zero_shot_30b": "zs-30B",
              "finetuned_8b": "ft-8B", "hybrid": "hybrid"}


def _gradient(summary):
    pc = summary["per_condition"]
    conds = ordered_conditions(summary)
    return conds, [pc[c]["quality_scalar"] for c in conds], [pc[c].get("mean_best_gain", 0.0) for c in conds]


def main():
    strong = json.load(open(STRONG))
    weak = json.load(open(WEAK))
    cmp = compare_regimes(strong, weak)
    print(json.dumps(cmp, indent=2, ensure_ascii=False))

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(13.0, 5.0))

    # ---- Panel A: gradient vs best gain, both regimes ----
    cs, qs_s, bg_s = _gradient(strong)
    cw, qs_w, bg_w = _gradient(weak)
    axA.plot(qs_s, bg_s, "o-", color="#8C8C8C", label=f"strong gen (floored, r={cmp['strong']['corr_quality_vs_best_gain']:+.2f})")
    axA.plot(qs_w, bg_w, "s-", color="#C44E52", label=f"weak gen (unfloored, r={cmp['weak']['corr_quality_vs_best_gain']:+.2f})")
    for x, y, c in zip(qs_s, bg_s, cs):
        axA.annotate(COND_LABEL.get(c, c), (x, y), fontsize=7, color="#8C8C8C",
                     xytext=(0, -10), textcoords="offset points", ha="center")
    for x, y, c in zip(qs_w, bg_w, cw):
        axA.annotate(COND_LABEL.get(c, c), (x, y), fontsize=7, color="#C44E52",
                     xytext=(0, 6), textcoords="offset points", ha="center")
    axA.axhline(cmp["material_gain_threshold"], ls=":", lw=1, color="#2A7", label=f"material ≥{cmp['material_gain_threshold']:.02g}")
    axA.set_xlabel("examiner intrinsic quality (IV)")
    axA.set_ylabel("mean best refinement gain (model-free DV)")
    axA.set_title("(A) examiner quality → refinement gain", fontsize=10)
    axA.legend(fontsize=8, loc="upper left")
    axA.grid(alpha=0.25)

    # ---- Panel B: mechanism = critique-axis mismatch (actionability A/B) ----
    # weak-gen first-draft headroom by dim (where the room is), then the controlled
    # A/B showing the real geometry critique moves nothing while an explicit coverage
    # critique recovers it -> the null is an axis mismatch, not revision incapacity.
    dims = (*UNADDRESSABLE_DIMS, *ADDRESSABLE_DIMS)
    pcw = weak["per_condition"]
    headroom = []
    for d in dims:
        vals = [1.0 - (pcw[c]["dim_initial"][d]) for c in cw if (pcw[c].get("dim_initial") or {}).get(d) is not None]
        headroom.append(float(np.mean(vals)) if vals else 0.0)
    act = json.load(open(ACT)) if ACT.exists() else None
    x = np.arange(len(dims)); w = 0.55
    colors = ["#C44E52" if d in UNADDRESSABLE_DIMS else "#4C72B0" for d in dims]
    axB.bar(x, headroom, w, color=colors,
            hatch=["xx" if d in UNADDRESSABLE_DIMS else "" for d in dims], edgecolor="white")
    axB.set_xticks(x); axB.set_xticklabels([d[:4] for d in dims], fontsize=9)
    axB.set_ylim(0, 1.0); axB.set_ylabel("weak-gen first-draft headroom (1−init)")
    axB.set_title("(B) where the headroom is — and the critique-axis A/B", fontsize=10)
    axB.annotate("coverage (red) = critiqued by\nNEITHER linter nor examiner",
                 (0, headroom[0]), fontsize=7.5, color="#C44E52", xytext=(8, 0),
                 textcoords="offset points", va="center")
    if act:
        txt = ("Actionability A/B (gen+task+seed fixed, vary critique):\n"
               f"  real geometry critique:  Δq={act['mean_dq_A_real_linter']:+.2f}  "
               f"Δcov={act['mean_dcov_A_real_linter']:+.2f}\n"
               f"  explicit coverage critique: Δq={act['mean_dq_B_explicit_coverage']:+.2f}  "
               f"Δcov={act['mean_dcov_B_explicit_coverage']:+.2f}")
        axB.text(0.5, 0.97, txt, transform=axB.transAxes, fontsize=8, va="top", ha="left",
                 family="monospace", bbox=dict(boxstyle="round", fc="#FFF6E5", ec="#DD8452"))

    fig.suptitle("E6 — unfloored downstream: the weak generator has MORE headroom yet the "
                 "examiner→gain effect vanishes; the headroom is coverage (off the critique axis)",
                 fontsize=10.5)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    for out in [REPO / "docs/figs/p3_e6_unfloored.png",
                REPO / "paper/figs/fig9_unfloored_downstream.png"]:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
        print("wrote", out)


if __name__ == "__main__":
    main()
