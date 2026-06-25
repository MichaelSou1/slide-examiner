"""E8 saturation figure — G3/G5 detection vs injected magnitude (corrected roster).

Reads the corrected coverage-freeform diagnosis (p1e8c / covint) via the summary
loaders and plots roster-mean balanced accuracy across the magnitude sweep for
C0 (open pointwise), C3 (atomic targeted) and 2-AFC (paired). Shows the SATURATION
point the 48/64 px strata were added to map. -> paper/figs/fig10_g3_saturation.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import part3_e8_summary as S  # noqa: E402


def roster_mean(metric_key, defect, strata, models, data, afc=False):
    ys = []
    for s in strata:
        vals = []
        for m in models:
            if afc:
                c = (data[m]["AFC"] or {}).get((defect, s))
                if c:
                    vals.append(c["afc_strict"])
            else:
                c = (data[m][metric_key] or {}).get((defect, s))
                if c:
                    vals.append(c["bal_acc"])
        ys.append(sum(vals) / len(vals) if vals else None)
    return ys


def main():
    smap = S.stratum_map()
    models = [m for m in S.MODEL_ORDER
              if (REPO / f"data/part3/{S.PREFIX}_{m}_{S.TAG}_C0_rows.jsonl").exists()]
    data = {m: {"C0_named": S.load_pointwise(m, "C0", smap, "named_target"),
                "C3_named": S.load_pointwise(m, "C3", smap, "named_target"),
                "AFC": S.load_afc(m, smap)} for m in models}

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    panels = [("G3_ALIGNMENT_OFFSET", "G3 alignment offset", "offset (px)", "% width", 1920),
              ("G5_BRAND_COLOR_VIOLATION", "G5 brand colour", "ΔE2000", None, None)]
    for ax, (d, title, xlab, _pct, frame) in zip(axes, panels):
        strata = S.STRATA[d]
        for key, lab, mk, afc in [("C0_named", "C0 (open pointwise)", "o", False),
                                  ("C3_named", "C3 (atomic targeted)", "s", False),
                                  (None, "2-AFC (paired)", "^", True)]:
            ys = roster_mean(key, d, strata, models, data, afc=afc)
            xs = [s for s, y in zip(strata, ys) if y is not None]
            yv = [y for y in ys if y is not None]
            ax.plot(xs, yv, marker=mk, label=lab, linewidth=1.8, markersize=6)
        ax.axhline(0.5, ls=":", c="gray", lw=1, label="chance")
        ax.set_xscale("log", base=2)
        ax.set_xticks(strata); ax.set_xticklabels([f"{int(s)}" for s in strata])
        ax.set_ylim(0.4, 1.03); ax.set_xlabel(xlab); ax.set_ylabel("roster-mean bal-acc")
        ax.set_title(title); ax.grid(alpha=0.25)
        if frame:
            sec = ax.secondary_xaxis("top", functions=(lambda v, f=frame: v / f * 100,
                                                        lambda v, f=frame: v * f / 100))
            sec.set_xlabel("% of slide width")
    axes[0].legend(loc="lower right", fontsize=8, framealpha=0.9)
    fig.suptitle(f"E8 internal-contrast G3/G5 detection vs magnitude — roster mean ({len(models)} VLMs, "
                 "coverage-freeform, matched twins)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = REPO / "paper/figs/fig10_g3_saturation.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[wrote {out}]  models={models}")


if __name__ == "__main__":
    main()
