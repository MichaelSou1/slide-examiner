"""E5 figure — open-world coverage ladder: native-IR vs pixel-recovered vs VLM.

Two panels, both at the linter's shipped operating point:
  (A) synthetic real-layout (GT IR + render): per geometry class, native-IR linter
      vs pixel-recovered linter vs VLM-only floor, with Wilson CIs and the chance
      line; recovery-fidelity recall@IoU0.5 annotated under each class.
  (B) image-only SlideAudit (no IR): pixel-recovered linter vs VLM C0/C3 floor.

The picture: structure recovered from pixels does not restore the symbolic
linter's coverage — it rescues only overlap, partially, and the VLM engine
dominates every coarse class. The hybrid's symbolic advantage is a native-IR
phenomenon (R3-W1 / EIC-W1 deployment-scope bound).

Outputs -> docs/figs/p3_e5_recovered.png + paper/figs/fig8_open_world_recovery.png.
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
SHORT = {"G1_TEXT_OVERFLOW": "G1\noverflow", "G2_ELEMENT_OVERLAP": "G2\noverlap",
         "G3_ALIGNMENT_OFFSET": "G3\nalign", "G4_FONT_SIZE_INCONSISTENCY": "G4\nfont",
         "G5_BRAND_COLOR_VIOLATION": "G5\ncolour", "G6_MARGIN_VIOLATION": "G6\nmargin"}


def _ci_err(cell):
    lo, hi = cell["bal_acc_ci"]
    return [[cell["bal_acc"] - lo], [hi - cell["bal_acc"]]]


def main():
    synth = json.load(open(D / "e5_recovered_synth.json"))
    sa = json.load(open(D / "e5_recovered_slideaudit.json"))

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(13.5, 5.0))

    # ---- Panel A: synthetic real-layout, 3-way ladder ----
    classes = [c for c in SHORT if c in synth["per_class"]]
    x = np.arange(len(classes))
    w = 0.26
    nat = [synth["per_class"][c]["native_ir"] for c in classes]
    rec = [synth["per_class"][c]["recovered"] for c in classes]
    vlm = [synth["per_class"][c].get("vlm_only_A") for c in classes]
    axA.bar(x - w, [c["bal_acc"] for c in nat], w, label="native-IR linter",
            color="#4C72B0", yerr=np.hstack([_ci_err(c) for c in nat]), capsize=2, ecolor="#333")
    axA.bar(x, [c["bal_acc"] for c in rec], w, label="pixel-recovered linter",
            color="#DD8452", yerr=np.hstack([_ci_err(c) for c in rec]), capsize=2, ecolor="#333")
    axA.bar(x + w, [(v or {}).get("bal_acc", 0) for v in vlm], w, label="VLM-only (image)",
            color="#55A868", alpha=0.95)
    axA.axhline(0.5, ls="--", lw=1, color="gray")
    axA.text(len(classes) - 0.45, 0.515, "chance", color="gray", fontsize=8)
    # annotate recovery-fidelity recall@IoU0.5 just above each recovered (orange) bar
    for i, c in enumerate(classes):
        fid = synth["per_class"][c].get("recovery_fidelity") or {}
        if fid:
            axA.text(i, rec[i]["bal_acc_ci"][1] + 0.015, f"IoU rec\n{fid['recall_at_iou']:.2f}",
                     ha="center", va="bottom", fontsize=6.5, color="#A0522D")
    axA.set_xticks(x); axA.set_xticklabels([SHORT[c] for c in classes], fontsize=9)
    axA.set_ylim(0, 1.0); axA.set_ylabel("balanced accuracy")
    axA.set_title("(A) real-layout decks (GT IR + render, n≈40/class)", fontsize=10)
    axA.legend(fontsize=8, loc="upper right")

    # ---- Panel B: image-only SlideAudit, recovered vs VLM ----
    sclasses = [c for c in SHORT if c in sa["per_class"]]
    xs = np.arange(len(sclasses))
    srec = [sa["per_class"][c]["recovered"] for c in sclasses]
    sc0 = [(sa["per_class"][c].get("vlm_only") or {}).get("C0") for c in sclasses]
    sc3 = [(sa["per_class"][c].get("vlm_only") or {}).get("C3") for c in sclasses]
    axB.bar(xs - w, [c["bal_acc"] for c in srec], w, label="pixel-recovered linter",
            color="#DD8452", yerr=np.hstack([_ci_err(c) for c in srec]), capsize=2, ecolor="#333")
    axB.bar(xs, [v or 0 for v in sc0], w, label="VLM C0 (pointwise)", color="#8172B3")
    axB.bar(xs + w, [v or 0 for v in sc3], w, label="VLM C3 (atomic-binary)", color="#55A868")
    axB.axhline(0.5, ls="--", lw=1, color="gray")
    axB.set_xticks(xs); axB.set_xticklabels([SHORT[c] for c in sclasses], fontsize=9)
    axB.set_ylim(0, 1.0)
    axB.set_title("(B) image-only SlideAudit (no IR, third-party)", fontsize=10)
    axB.legend(fontsize=8, loc="upper right")

    fig.suptitle("E5 — open-world hybrid: structure recovered from pixels does not "
                 "restore the symbolic linter (the VLM dominates coarse geometry)",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    for out in [REPO / "docs/figs/p3_e5_recovered.png",
                REPO / "paper/figs/fig8_open_world_recovery.png"]:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
        print("wrote", out)


if __name__ == "__main__":
    main()
