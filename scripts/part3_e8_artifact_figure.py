"""E8 fig — the re-op as a falsifiable test: 2-AFC separates a DATA ARTIFACT (S6,
recovers) from a GENUINE blind spot (G6 page-offset, stays blind).

Both sit at chance under single-image pointwise; the discriminative 2-AFC (which one
of the paired slides carries the defect, scored over ALL pairs incl. ties) splits them:
S6 -> high (the model sees the contradiction once the figure is actually rendered),
G6 -> ~0 (no model can tell a page-offset slide from a balanced one). -> paper/figs/fig11.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
MODELS = ["qwen35-9b", "internvl-8b", "ovis-9b", "qwen36-27b", "qwen35-27b", "gemma4-31b"]
LBL = {"qwen35-9b": "Qwen3.5-9B", "internvl-8b": "InternVL3.5-8B", "ovis-9b": "Ovis2.5-9B",
       "qwen36-27b": "Qwen3.6-27B", "qwen35-27b": "Qwen3.5-27B", "gemma4-31b": "Gemma4-31B"}


def discrimination(model, tag):
    """fraction of AFC pairs where the model consistently called the DEFECTIVE worse in
    both presentation orders (ties / inconsistent count as not-discriminated)."""
    f = REPO / f"data/part3/p1e8g6s6_{model}_{tag}_AFC.json"
    if not f.exists():
        return None
    d = json.load(f.open())
    c = list(d["afc"].values())[0] if d.get("afc") else None
    if not c or not c.get("n_pairs"):
        return None
    return c.get("n_probe_worse_both", 0) / c["n_pairs"]


def main():
    s6 = [discrimination(m, "s6") for m in MODELS]
    g6 = [discrimination(m, "g6") for m in MODELS]
    x = range(len(MODELS))
    w = 0.38
    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    ax.bar([i - w / 2 for i in x], s6, w, label="S6 image/text (data bug fixed)", color="#2a9d8f")
    ax.bar([i + w / 2 for i in x], g6, w, label="G6 page-offset (re-operationalised)", color="#e76f51")
    ax.axhline(0.5, ls=":", c="gray", lw=1)
    ax.text(len(MODELS) - 0.5, 0.52, "chance", color="gray", fontsize=8, ha="right")
    ax.set_xticks(list(x)); ax.set_xticklabels([LBL[m] for m in MODELS], rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("2-AFC discrimination\n(defective called worse, both orders)")
    ax.set_ylim(0, 1.02)
    ax.set_title("The re-operationalisation is falsifiable: 2-AFC separates a data artifact "
                 "(S6, recovers)\nfrom a genuine blind spot (G6 page-offset, stays at chance on every model)",
                 fontsize=9)
    ax.legend(loc="upper center", fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out = REPO / "paper/figs/fig11_artifact_vs_genuine.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[wrote {out}]")
    print("S6:", [round(v, 2) if v is not None else None for v in s6])
    print("G6:", [round(v, 2) if v is not None else None for v in g6])


if __name__ == "__main__":
    main()
