"""Part 3 R2 — aggregate the real-layout A/B/C attribution across models.

Reads ``data/part3/pc_real_<model>.json`` (one per served model) and emits:
  * a combined per-class x modality balanced-accuracy table (markdown),
  * the perception / capability verdict per class (consensus across models),
  * a figure: per-class A/B/C balanced accuracy with the structure-rescue arrow.

Usage:
  ~/anaconda3/envs/slide-examiner/bin/python scripts/part3_pc_real_summary.py \
    --glob 'data/part3/pc_real_*.json' --out reports/_pc_real_tables.md \
    --json data/part3/pc_real_summary.json --fig docs/figs/pc_real_attribution.png
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLASSES = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
           "G4_FONT_SIZE_INCONSISTENCY", "G6_MARGIN_VIOLATION"]
SHORT = {"G1_TEXT_OVERFLOW": "G1 overflow", "G2_ELEMENT_OVERLAP": "G2 overlap",
         "G3_ALIGNMENT_OFFSET": "G3 align", "G4_FONT_SIZE_INCONSISTENCY": "G4 font",
         "G6_MARGIN_VIOLATION": "G6 margin"}
MOD = ["A", "B", "C"]
CHANCE = 0.6


def load(glob_pat: str) -> dict:
    out = {}
    for p in sorted(glob.glob(str(REPO / glob_pat))):
        if any(s in p for s in ("_rows", "fidelity", "summary")):
            continue
        d = json.loads(Path(p).read_text())
        if "model" not in d:
            continue
        out[d["model"]] = d
    return out


def verdict(a, b, c):
    a_fail = a < CHANCE
    if a_fail and max(b, c) >= CHANCE:
        return "perception"
    if a_fail and c < CHANCE:
        return "capability"
    return "image-sufficient"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/part3/pc_real_*.json")
    ap.add_argument("--out", default="reports/_pc_real_tables.md")
    ap.add_argument("--json", default="data/part3/pc_real_summary.json")
    ap.add_argument("--fig", default="docs/figs/pc_real_attribution.png")
    ap.add_argument("--fidelity", default="data/part3/pc_real_fidelity.json")
    args = ap.parse_args()

    models = load(args.glob)
    if not models:
        raise SystemExit("no pc_real_*.json found")

    # per (class, modality) -> list of (model, bal_acc, ci)
    table: dict = {}
    for cls in CLASSES:
        table[cls] = {}
        for m in MOD:
            vals = []
            for name, d in models.items():
                cell = d["per_modality"].get(m, {}).get("per_class", {}).get(cls)
                if cell:
                    vals.append((name, cell["bal_acc"], cell.get("bal_acc_ci"),
                                 cell.get("n_pos"), cell.get("n_neg")))
            table[cls][m] = vals

    # consensus verdict per class (mean bal-acc across models)
    agg = {}
    for cls in CLASSES:
        means = {}
        for m in MOD:
            xs = [v[1] for v in table[cls][m]]
            means[m] = round(statistics.fmean(xs), 3) if xs else None
        if None in means.values():
            continue
        agg[cls] = {"mean_A": means["A"], "mean_B": means["B"], "mean_C": means["C"],
                    "verdict": verdict(means["A"], means["B"], means["C"]),
                    "delta_C_minus_A": round(means["C"] - means["A"], 3),
                    "delta_B_minus_A": round(means["B"] - means["A"], 3)}

    # markdown
    lines = ["# Part 3 R2 — real-layout modality A/B/C attribution\n",
             f"Models: {', '.join(models)}\n",
             "Balanced accuracy on paired clean controls (real LibreOffice renders + lossless "
             "python-pptx oracle). A = image-only, B = structured oracle, C = image+oracle.\n",
             "## Per-class mean balanced accuracy across models\n",
             "| Class | A (image) | B (oracle) | C (both) | ΔC−A | ΔB−A | verdict |",
             "|---|---|---|---|---|---|---|"]
    for cls in CLASSES:
        a = agg.get(cls)
        if not a:
            lines.append(f"| {SHORT[cls]} | — | — | — | — | — | — |")
            continue
        lines.append(f"| {SHORT[cls]} | {a['mean_A']:.2f} | {a['mean_B']:.2f} | {a['mean_C']:.2f} | "
                     f"{a['delta_C_minus_A']:+.2f} | {a['delta_B_minus_A']:+.2f} | **{a['verdict']}** |")

    lines.append("\n## Per-model detail (bal-acc [CI], McNemar C-vs-A)\n")
    for name, d in models.items():
        lines.append(f"\n### {name} (n_pairs={d['n_pairs']}, failures={d.get('failures')})\n")
        lines.append("| Class | A | B | C | McNemar C-vs-A (p, +/−) | localize C | repair A |")
        lines.append("|---|---|---|---|---|---|---|")
        for cls in CLASSES:
            attr = d["attribution"].get(cls)
            if not attr:
                lines.append(f"| {SHORT[cls]} | — | — | — | — | — | — |")
                continue
            mc = attr["mcnemar_C_vs_A"]
            lines.append(f"| {SHORT[cls]} | {attr['A_bal_acc']:.2f} | {attr['B_bal_acc']:.2f} | "
                         f"{attr['C_bal_acc']:.2f} | p={mc['p']} ({mc['gain']}/{mc['loss']}) | "
                         f"{attr.get('localize_rate_C')} | {attr.get('repair_rate_A')} |")

    # fidelity
    fid_path = REPO / args.fidelity
    if fid_path.exists():
        fid = json.loads(fid_path.read_text())
        lines.append("\n## Render-fidelity audit on REAL decks (vs synthetic 45% absorption)\n")
        lines.append(f"Overall rendered_rate = **{fid['overall'].get('rendered_rate')}** "
                     f"(absorption_rate {fid['overall'].get('absorption_rate')}), "
                     f"n_scored={fid['overall'].get('n_scored')}.\n")
        lines.append("| Class | rendered_rate | absorption_rate | changed_frac median |")
        lines.append("|---|---|---|---|")
        for cls in CLASSES:
            pf = fid["per_defect"].get(cls, {})
            lines.append(f"| {SHORT[cls]} | {pf.get('rendered_rate')} | {pf.get('absorption_rate')} "
                         f"| {pf.get('changed_frac_median')} |")

    Path(REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO / args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(REPO / args.json).write_text(json.dumps(
        {"models": list(models), "table": table, "aggregate": agg}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print("\n".join(lines[:18]))
    print(f"\n[summary] -> {args.out} ; {args.json}")

    # figure
    try:
        make_fig(agg, models, table, REPO / args.fig)
        print(f"[figure] -> {args.fig}")
    except Exception as exc:  # noqa: BLE001
        print(f"[figure] skipped: {exc}")


def make_fig(agg, models, table, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    classes = [c for c in CLASSES if c in agg]
    x = np.arange(len(classes))
    w = 0.26
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    colors = {"A": "#d9534f", "B": "#5bc0de", "C": "#5cb85c"}
    labels = {"A": "A: image-only", "B": "B: structured oracle", "C": "C: image+oracle"}
    for i, m in enumerate(MOD):
        vals = [agg[c][f"mean_{m}"] for c in classes]
        ax.bar(x + (i - 1) * w, vals, w, label=labels[m], color=colors[m], edgecolor="#333", linewidth=0.5)
    ax.axhline(0.5, ls="--", c="#888", lw=1)
    ax.text(len(classes) - 0.5, 0.51, "chance", color="#888", fontsize=8, va="bottom", ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[c] for c in classes], fontsize=9)
    ax.set_ylabel("balanced accuracy (paired clean)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Real-layout perception/capability attribution\n(Zenodo10K real renders + lossless python-pptx oracle)",
                 fontsize=10)
    ax.legend(fontsize=8, loc="upper left", ncol=3, framealpha=0.9)
    # annotate verdict under each class
    for i, c in enumerate(classes):
        ax.text(i, -0.12, agg[c]["verdict"], ha="center", va="top", fontsize=7.5,
                color="#444", transform=ax.get_xaxis_transform())
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
