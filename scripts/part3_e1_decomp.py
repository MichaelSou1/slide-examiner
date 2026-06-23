"""E1 — decompose the 0.50 -> 1.00 elicitation recovery into its components.

Gate G-E1 (todo_0623): is the recovery *elicitation* (format suppression — the
model perceives the defect all along) or *reduced task difficulty* (the forced
choice hands the model a clean reference + a named target)? We factor the gap,
holding model + image fixed, into three pieces measured on the SAME freeform
items (prefix ``p1e1_``, written by the roster with --freeform-only):

  C0          pointwise whole-taxonomy single call            (baseline ~0.50)
  C0_named    NAMED atomic yes/no, single slide, NO reference (naming component)
  AFC         true 2-AFC: defective vs its CLEAN twin, both orders (pairing)
  AFC_clean   clean vs distinct-clean, both orders            (guess-floor control)

All four scores are balanced accuracies on a chance-0.5 task, so they compose:
  naming  = C0_named_bal - C0_bal           (format-suppression proper)
  pairing = AFC_bal      - C0_named_bal      (availability-of-reference / difficulty)
AFC_bal folds the guess-floor in directly: it is the balanced accuracy of the
forced choice, with the AFC_clean "consistent invention" rate as the specificity
side — so a model that picks a winner even between two clean slides is penalised.

Gate decision (per the falsification branch): if naming >= pairing the
"format suppression, not capability" claim is SUPPORTED; if pairing dominates the
claim weakens to "availability-of-reference" and the framing must change.

Usage:
  python scripts/part3_e1_decomp.py --prefix p1e1 \
    --md reports/_e1_decomp.md --json data/part3/p1_decomp_summary.json \
    --fig paper/figs/fig7_elicitation_decomp.png
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from slide_examiner.statistics import balanced_accuracy_ci, holm_bonferroni, wilson_interval  # noqa: E402
from part3_p1_summary import mcnemar_p  # noqa: E402  (reuse the exact paired test)

ENGINE_CONDS = ["C0", "C0_named", "C3"]
AFC_CONDS = ["AFC", "AFC_clean"]
DEFECT_ORDER = ["G1_TEXT_OVERFLOW", "S6_IMAGE_TEXT_CONTRADICTION", "G7_RENDER_CONTAINMENT_OVERFLOW"]
SHORT = {"G1_TEXT_OVERFLOW": "G1", "S6_IMAGE_TEXT_CONTRADICTION": "S6",
         "G7_RENDER_CONTAINMENT_OVERFLOW": "G7"}
# models that actually recover (AFC_bal high) drive the gate; we report all but the
# figure aggregates over models whose 2-AFC clears this bar (paper "capable models").
RECOVER_BAR = 0.70


def _parse_name(path: str, prefix: str) -> tuple[str, str, str]:
    """p1e1_<model>_<tag>_<cond>(.json|_rows.jsonl) -> (model, tag, cond). Model keys
    are hyphenated (no underscores) and tag in {geo,g7}, so the split is unambiguous."""
    name = Path(path).name
    body = name[len(prefix) + 1:]
    for suf in ("_rows.jsonl", ".json"):
        if body.endswith(suf):
            body = body[: -len(suf)]
            break
    parts = body.split("_")
    return parts[0], parts[1], "_".join(parts[2:])


def load(prefix: str):
    """eng[model][defect][cond]=detection cell ; afc[model][defect][cond]=afc cell."""
    eng: dict = {}
    afc: dict = {}
    for path in sorted(glob.glob(str(REPO / f"data/part3/{prefix}_*_*.json"))):
        if path.endswith("_rows.jsonl") or "_summary" in path or "_decomp" in path:
            continue
        d = json.loads(Path(path).read_text())
        model, cond = d.get("model"), d.get("condition")
        if cond in AFC_CONDS:
            for defect, cell in (d.get("afc") or {}).items():
                afc.setdefault(model, {}).setdefault(defect, {})[cond] = cell
        else:
            per = (d.get("metrics") or {}).get("A", {}).get("per_defect", {})
            for defect, entry in per.items():
                eng.setdefault(model, {}).setdefault(defect, {})[cond] = entry.get("detection")
    return eng, afc


def load_correct(prefix: str):
    """per-image correctness for the engine conds (C0/C0_named/C3), keyed
    model->defect->cond->sample_id, plus AFC per-pair catch keyed by the DEFECTIVE
    (probe) sample_id for the AFC-vs-C0_named paired test."""
    img: dict = {}
    afc_catch: dict = {}
    for path in sorted(glob.glob(str(REPO / f"data/part3/{prefix}_*_rows.jsonl"))):
        model, _tag, cond = _parse_name(path, prefix)
        for line in Path(path).open():
            if not line.strip():
                continue
            r = json.loads(line)
            if cond in AFC_CONDS:
                if cond != "AFC":
                    continue
                caught = (r.get("pick_order0"), r.get("pick_order1")) == ("a", "b")
                afc_catch.setdefault(model, {}).setdefault(r["defect"], {})[r["probe_id"]] = caught
            else:
                if r.get("failure"):
                    continue
                correct = bool(r["has_defect"]) == (not r.get("is_clean"))
                img.setdefault(model, {}).setdefault(r.get("defect"), {}).setdefault(
                    cond, {})[r["sample_id"]] = correct
    return img, afc_catch


def afc_balanced(paired: dict | None, clean: dict | None):
    """Balanced accuracy of the forced choice. Recall side = how often the DEFECTIVE
    is consistently called worse in BOTH orders (paired AFC). Specificity side =
    1 - consistent-invention on clean-vs-clean (AFC_clean), where a clean pair the
    model correctly does NOT name a winner (a tie, or an order-flip) is a TRUE
    NEGATIVE. The specificity denominator is therefore ALL clean pairs, not just the
    decisive ones — otherwise a model that correctly TIES on every clean pair (the
    ideal: no false alarm) would have n_neg=0 and the cell would vanish. This is the
    G1/S6 case (model ties on clean) vs the G7 case (model invents a winner on
    every clean pair -> specificity 0 -> the 2-AFC 'recovery' is a forced-pick
    artifact, correctly discounted to ~0.5)."""
    if not paired:
        return None
    # recall over ALL defective pairs: a tie/flip on a defective is a detection miss
    n_pos = paired.get("n_pairs", 0)
    tp = paired.get("n_probe_worse_both", 0)
    if clean and clean.get("n_pairs"):
        n_neg = clean["n_pairs"]                          # ALL clean pairs
        tn = n_neg - clean.get("n_consistent_invention", 0)  # tie/flip on clean = true negative
    else:                       # no clean control -> assume perfect specificity (optimistic)
        tn = n_neg = n_pos
    if not n_pos or not n_neg:
        return None
    return balanced_accuracy_ci(tp, n_pos, tn, n_neg)


def _bal(cell):
    return cell.get("bal_acc") if cell else None


def decompose(eng_md: dict, afc_md: dict):
    """One (model,defect) -> the 3-way decomposition with CIs."""
    c0 = eng_md.get("C0")
    c0n = eng_md.get("C0_named")
    c3 = eng_md.get("C3")
    afc_clean = afc_md.get("AFC_clean") or {}
    afc_bal = afc_balanced(afc_md.get("AFC"), afc_clean)
    # TRUE guess-floor = fabricated consistent winners over ALL clean pairs (ties count
    # as correctly-not-inventing). The stored consistent_invention_rate is over DECISIVE
    # pairs only and badly overstates the floor when the model mostly ties on clean.
    inv_true = (round(afc_clean.get("n_consistent_invention", 0) / afc_clean["n_pairs"], 3)
                if afc_clean.get("n_pairs") else None)
    out = {
        "c0_bal": _bal(c0), "c0_named_bal": _bal(c0n), "c3_bal": _bal(c3),
        "c0_ci": c0.get("bal_acc_ci") if c0 else None,
        "c0_named_ci": c0n.get("bal_acc_ci") if c0n else None,
        "afc_bal": round(afc_bal.estimate, 3) if afc_bal else None,
        "afc_ci": [round(afc_bal.low, 3), round(afc_bal.high, 3)] if afc_bal else None,
        "afc_strict": (afc_md.get("AFC") or {}).get("afc_accuracy_strict"),
        "afc_clean_invention": inv_true,                     # over ALL clean pairs (honest)
        "afc_clean_invention_decisive": afc_clean.get("consistent_invention_rate"),
        "afc_clean_tie_rate": afc_clean.get("tie_rate"),
        "afc_clean_pick_first": afc_clean.get("pick_first_rate"),
        "n_pos": c0.get("n_pos") if c0 else None, "n_neg": c0.get("n_neg") if c0 else None,
    }
    b0, bn, ba = out["c0_bal"], out["c0_named_bal"], out["afc_bal"]
    if None not in (b0, bn):
        out["naming"] = round(bn - b0, 3)
    if None not in (bn, ba):
        out["pairing"] = round(ba - bn, 3)
    if None not in (b0, bn, ba):
        gap = ba - b0
        out["total_gap"] = round(gap, 3)
        if abs(gap) > 1e-6:
            out["naming_share"] = round((bn - b0) / gap, 3)
            out["pairing_share"] = round((ba - bn) / gap, 3)
            out["gate"] = "naming>=pairing (format-suppression SUPPORTED)" \
                if (bn - b0) >= (ba - bn) else "pairing dominates (availability-of-reference)"
    return out


def build(prefix: str):
    eng, afc = load(prefix)
    img_correct, afc_catch = load_correct(prefix)
    models = sorted(set(eng) | set(afc))
    rows = {}                    # model -> defect -> decomposition
    mcnemar_family = []          # (model, defect, test, p)
    for m in models:
        rows[m] = {}
        for d in DEFECT_ORDER:
            eng_md = eng.get(m, {}).get(d, {})
            afc_md = afc.get(m, {}).get(d, {})
            if not eng_md and not afc_md:
                continue
            dec = decompose(eng_md, afc_md)
            # McNemar 1: C0_named vs C0 (per-image, paired on the same items)
            cc = img_correct.get(m, {}).get(d, {})
            if "C0" in cc and "C0_named" in cc:
                p, b, c = mcnemar_p(cc["C0"], cc["C0_named"])
                dec["mcnemar_named_vs_c0"] = {"p": round(p, 4), "gain": b, "loss": c}
                mcnemar_family.append((m, d, "named_vs_c0", p))
            # McNemar 2: AFC catch vs C0_named catch, on the shared DEFECTIVE items
            ac = afc_catch.get(m, {}).get(d, {})
            cn = cc.get("C0_named", {})
            # C0_named correctness on a defective == it flagged the defect (has_defect)
            cn_def = {sid: corr for sid, corr in cn.items() if not sid.endswith("__CLEAN")}
            if ac and cn_def:
                p, b, c = mcnemar_p(cn_def, ac)
                dec["mcnemar_afc_vs_named"] = {"p": round(p, 4), "gain": b, "loss": c}
                mcnemar_family.append((m, d, "afc_vs_named", p))
            rows[m][d] = dec
    # Holm-correct the whole E1 McNemar family
    holm = holm_bonferroni([p for *_, p in mcnemar_family]) if mcnemar_family else None
    corrected = {}
    if holm:
        for (m, d, test, p), adj, rej in zip(mcnemar_family, holm.adjusted, holm.reject):
            corrected[(m, d, test)] = {"raw": round(p, 4), "holm": round(adj, 4), "reject": rej}
            key = "mcnemar_named_vs_c0" if test == "named_vs_c0" else "mcnemar_afc_vs_named"
            if d in rows.get(m, {}) and key in rows[m][d]:
                rows[m][d][key]["holm_p"] = round(adj, 4)
                rows[m][d][key]["reject_holm"] = rej
    return rows, models, {"n_tests": len(mcnemar_family),
                          "method": "holm", "alpha": 0.05,
                          "n_reject": holm.n_reject if holm else 0}


# --------------------------------------------------------------------------- #
def md_tables(rows, models, fam) -> str:
    L = ["### E1 — elicitation-recovery decomposition (freeform items, modality A)\n",
         "All scores are balanced accuracy on a chance-0.5 task, so the components add: "
         "**naming** = C0_named − C0 (format suppression proper); **pairing** = AFC_bal − "
         "C0_named (availability of a clean reference). AFC_bal is the balanced accuracy of "
         "the true 2-AFC (defective vs clean twin) with the AFC_clean *consistent-invention* "
         "rate as its specificity side (so a forced-pick artifact is penalised). McNemar p is "
         "the exact paired test; **Holm** = family-wise corrected over the "
         f"{fam['n_tests']} E1 tests (α=0.05).\n",
         "| Model | Defect | C0 | C0_named | AFC_bal [CI] | naming | pairing | gate | McNemar named·vs·C0 (Holm) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        for d in DEFECT_ORDER:
            dec = rows.get(m, {}).get(d)
            if not dec:
                continue
            afc_ci = dec.get("afc_ci")
            afc_s = (f"{dec['afc_bal']:.2f} [{afc_ci[0]:.2f}-{afc_ci[1]:.2f}]"
                     if dec.get("afc_bal") is not None and afc_ci else "—")
            mc = dec.get("mcnemar_named_vs_c0", {})
            mc_s = (f"{mc.get('p')}" + (f"→{mc.get('holm_p')}" if "holm_p" in mc else "")
                    + (" ✅" if mc.get("reject_holm") else "")) if mc else "—"
            gate = dec.get("gate", "—")
            gate_s = "✅naming" if gate.startswith("naming") else ("⚠pairing" if gate.startswith("pairing") else "—")
            L.append(
                f"| {m} | {SHORT[d]} | {_p(dec.get('c0_bal'))} | {_p(dec.get('c0_named_bal'))} | "
                f"{afc_s} | {_p(dec.get('naming'),signed=True)} | {_p(dec.get('pairing'),signed=True)} | "
                f"{gate_s} | {mc_s} |")
    # guess-floor companion table
    L += ["\n#### Guess-floor control (AFC_clean — two clean slides)\n",
          "invention = fabricated consistent winner over ALL clean pairs (the artifact that would "
          "inflate a forced choice — low is good); tie-rate = how often the model correctly calls two "
          "clean slides a tie (high = it abstains rather than guessing); pick-first = position bias.\n",
          "| Model | Defect | AFC strict acc | invention (all pairs) | tie-rate | pick-first |",
          "|---|---|---|---|---|---|"]
    for m in models:
        for d in DEFECT_ORDER:
            dec = rows.get(m, {}).get(d)
            if not dec or dec.get("afc_strict") is None:
                continue
            L.append(f"| {m} | {SHORT[d]} | {_p(dec.get('afc_strict'))} | "
                     f"{_p(dec.get('afc_clean_invention'))} | {_p(dec.get('afc_clean_tie_rate'))} | "
                     f"{_p(dec.get('afc_clean_pick_first'))} |")
    return "\n".join(L) + "\n"


def _p(x, signed=False):
    if x is None:
        return "—"
    return f"{x:+.2f}" if signed else f"{x:.2f}"


def make_fig(rows, models, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    # aggregate over models that actually recover (AFC_bal >= bar) per defect
    defects = [d for d in DEFECT_ORDER]
    naming, pairing, base, afc_floor, ns = [], [], [], [], []
    for d in defects:
        decs = [rows[m][d] for m in models if d in rows.get(m, {})
                and rows[m][d].get("afc_bal") is not None]
        recov = [x for x in decs if x["afc_bal"] >= RECOVER_BAR] or decs
        if not recov:
            naming.append(0); pairing.append(0); base.append(0.5); afc_floor.append(0); ns.append(0)
            continue
        base.append(float(np.mean([x.get("c0_bal", 0.5) for x in recov])))
        naming.append(float(np.mean([x.get("naming", 0) or 0 for x in recov])))
        pairing.append(float(np.mean([x.get("pairing", 0) or 0 for x in recov])))
        afc_floor.append(float(np.mean([x.get("afc_clean_invention", 0) or 0 for x in recov])))
        ns.append(len(recov))

    x = np.arange(len(defects))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(x, base, 0.55, color="#bbb", label="C0 baseline", edgecolor="#333", linewidth=0.5)
    ax.bar(x, naming, 0.55, bottom=base, color="#5cb85c", label="naming (C0_named−C0)",
           edgecolor="#333", linewidth=0.5)
    b2 = [b + n for b, n in zip(base, naming)]
    ax.bar(x, pairing, 0.55, bottom=b2, color="#5bc0de", label="pairing (AFC−C0_named)",
           edgecolor="#333", linewidth=0.5)
    ax.axhline(0.5, ls="--", c="#888", lw=1)
    for i, inv in enumerate(afc_floor):
        if inv:
            ax.plot([x[i] - 0.27, x[i] + 0.27], [0.5 + inv / 2, 0.5 + inv / 2],
                    color="#d9534f", lw=1.6, ls=":")
    ax.plot([], [], color="#d9534f", ls=":", lw=1.6, label="AFC_clean guess-floor")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{SHORT[d]}\n(n={ns[i]} models)" for i, d in enumerate(defects)], fontsize=9)
    ax.set_ylabel("balanced accuracy (chance 0.5)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Decomposing the elicitation recovery:\nnaming vs paired-reference vs guess-floor",
                 fontsize=11)
    ax.legend(fontsize=8, loc="lower right", framealpha=0.95)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="p1e1")
    ap.add_argument("--md", default="reports/_e1_decomp.md")
    ap.add_argument("--json", default="data/part3/p1_decomp_summary.json")
    ap.add_argument("--fig", default="paper/figs/fig7_elicitation_decomp.png")
    args = ap.parse_args()

    rows, models, fam = build(args.prefix)
    if not models:
        raise SystemExit(f"no {args.prefix}_* result files found — run the E1 sweep first")
    md = md_tables(rows, models, fam)
    Path(REPO / args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO / args.md).write_text(md, encoding="utf-8")
    Path(REPO / args.json).write_text(
        json.dumps({"decomposition": rows, "models": models, "mcnemar_family": fam},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)
    print(f"[e1-decomp] Holm family: {fam}")
    print(f"[e1-decomp] -> {args.md} ; {args.json}")
    try:
        make_fig(rows, models, REPO / args.fig)
        print(f"[figure] -> {args.fig}")
    except Exception as exc:  # noqa: BLE001
        print(f"[figure] skipped: {exc}")


if __name__ == "__main__":
    main()
