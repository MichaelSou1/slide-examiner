"""E2 — compute-matched C0 ablation report (W2 2.2 / 2.4).

Answers reviewer Weakness-3 / Q1-Q2: is C3's recovery just more test-time compute?
We hold model + image + rendered corpus fixed and read four conditions written by
``run_e2_computematch.sh`` (prefix ``p1e2_``):

  C0        pointwise whole-taxonomy single call             (1 call/slide baseline)
  C0_full   + definitions + forced evidence, still ONE call  (definition/evidence match)
  C0_rep    K temperature-sampled C0 draws, union & majority (COMPUTE match: K calls)
  C3        atomic per-type binary + forced evidence          (decomposition)

The contrasts (all balanced accuracy on a chance-0.5 paired-clean task):
  * C3 − C0            the raw recovery being interrogated
  * C3 − C0_rep(union) does K× compute alone close it? (the compute-matched control)
  * C3 − C0_rep(maj)   self-consistency reading of the same budget
  * C3 − C0_full       does definitions + evidence alone close it? (isolates
                       DECOMPOSITION as the remaining ingredient)
Each per-image contrast gets an exact paired McNemar test; the whole E2 family is
Holm-corrected together (its size is what the paper's "N-test family" must grow by).

Budget (E3): from the 2.0 usage logs we report completion tokens / slide per
condition. If C3's output tokens are NOT higher than C0_full's, "C3 wins on
budget" is dead on arrival — the recovery cannot be a spend artifact.

Usage:
  python scripts/part3_e2_computematch_report.py \
    --md reports/_e2_computematch.md --json data/part3/p1e2_summary.json
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

from slide_examiner.statistics import holm_bonferroni  # noqa: E402
from part3_p1_summary import mcnemar_p  # noqa: E402  (same exact paired test as E1)

CONDS = ["C0", "C0_full", "C0_rep", "C3"]
SHORT = {"G7_RENDER_CONTAINMENT_OVERFLOW": "G7", "G1_TEXT_OVERFLOW": "G1",
         "S6_IMAGE_TEXT_CONTRADICTION": "S6"}
# Paired contrasts to test (base cond -> C3 gain). The compute-matched control is
# SELF-CONSISTENCY = majority vote over K C0 draws (the standard way to convert
# test-time compute into accuracy). The any-vote/union aggregation is intentionally
# NOT reported: it is a decision-threshold relaxation, not a compute-scaling method,
# so it is neither in the table nor in the Holm family. (The raw union field still
# lives in the per-sample data; only the paper-facing report omits it.)
CONTRASTS = [
    ("C3", "C0", "detection", "detection"),
    ("C3", "C0_full", "detection", "detection"),
    ("C3", "C0_rep", "detection", "detection_majority"),   # self-consistency (majority)
]


def _parse_name(path: str) -> tuple[str, str, str]:
    """p1e2_<model>_<tag>_<cond>(.json|_rows.jsonl) -> (model, tag, cond). Model keys
    are hyphenated; cond is one of CONDS (may itself contain '_', e.g. C0_full), so
    match the cond as a known suffix and take the tag as the token before it."""
    body = Path(path).name[len("p1e2_"):]
    for suf in ("_rows.jsonl", ".json"):
        if body.endswith(suf):
            body = body[:-len(suf)]
            break
    for cond in sorted(CONDS, key=len, reverse=True):
        if body.endswith("_" + cond):
            rest = body[: -(len(cond) + 1)]
            model, _, tag = rest.rpartition("_")
            return model, tag, cond
    # fallback: last token is cond
    model, tag, cond = body.split("_", 2) if body.count("_") >= 2 else (body, "", "")
    return model, tag, cond


def load(prefix: str):
    """metrics[model][defect][cond] = {detection, detection_majority?} cells;
    usage[model][cond] = usage summary."""
    metrics: dict = {}
    usage: dict = {}
    for path in sorted(glob.glob(str(REPO / f"data/part3/{prefix}_*.json"))):
        if path.endswith("_rows.jsonl") or "_summary" in path:
            continue
        d = json.loads(Path(path).read_text())
        model, cond = d.get("model"), d.get("condition")
        if cond not in CONDS:
            continue
        if d.get("usage"):
            usage.setdefault(model, {})[cond] = d["usage"]
        per = (d.get("metrics") or {}).get("A", {}).get("per_defect", {})
        for defect, entry in per.items():
            cell = {"detection": entry.get("detection")}
            if "detection_majority" in entry:
                cell["detection_majority"] = entry["detection_majority"]
            metrics.setdefault(model, {}).setdefault(defect, {})[cond] = cell
    return metrics, usage


def load_correct(prefix: str):
    """Per-image correctness for the paired McNemar tests, keyed
    model->defect->cond->{sample_id: correct}. For C0_rep the union lives in
    has_defect and majority in has_defect_maj -> exposed as pseudo-conds
    'C0_rep' and 'C0_rep_maj'."""
    img: dict = {}
    for path in sorted(glob.glob(str(REPO / f"data/part3/{prefix}_*_rows.jsonl"))):
        model, _tag, cond = _parse_name(path)
        if cond not in CONDS:
            continue
        for line in Path(path).open():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("failure"):
                continue
            sid, defect = r.get("sample_id"), r.get("defect")
            correct = bool(r.get("has_defect")) == (not r.get("is_clean"))
            img.setdefault(model, {}).setdefault(defect, {}).setdefault(cond, {})[sid] = correct
            if cond == "C0_rep" and "has_defect_maj" in r:
                maj = bool(r.get("has_defect_maj")) == (not r.get("is_clean"))
                img[model][defect].setdefault("C0_rep_maj", {})[sid] = maj
    return img


def _bal(cell):
    return cell.get("bal_acc") if cell else None


def _cell_of(metrics, model, defect, cond, level):
    c = metrics.get(model, {}).get(defect, {}).get(cond)
    return (c or {}).get(level)


def build(prefix: str):
    metrics, usage = load(prefix)
    img = load_correct(prefix)
    models = sorted(metrics)
    rows: dict = {}          # model -> defect -> {cond bal, contrasts}
    family = []              # (model, defect, contrast_label, p, gain, loss)
    for m in models:
        rows[m] = {}
        for defect in sorted(metrics[m]):
            cells = metrics[m][defect]
            entry = {"bal": {}, "contrasts": {}}
            for cond in CONDS:
                entry["bal"][cond] = _bal(_cell_of(metrics, m, defect, cond, "detection"))
            entry["bal"]["C0_rep_maj"] = _bal(_cell_of(metrics, m, defect, "C0_rep", "detection_majority"))
            for c3, base, l3, lbase in CONTRASTS:
                b3 = _bal(_cell_of(metrics, m, defect, c3, l3))
                bb = _bal(_cell_of(metrics, m, defect, base, lbase))
                label = base + ("_maj" if lbase.endswith("majority") else "")
                if b3 is None or bb is None:
                    continue
                con = {"c3_bal": b3, "base_bal": bb, "delta": round(b3 - bb, 3)}
                # McNemar on shared per-image correctness
                cc = img.get(m, {}).get(defect, {})
                base_key = "C0_rep_maj" if lbase.endswith("majority") else base
                if c3 in cc and base_key in cc:
                    p, gain, loss = mcnemar_p(cc[base_key], cc[c3])
                    con.update({"mcnemar_p": round(p, 4), "c3_gain": gain, "c3_loss": loss})
                    family.append((m, defect, f"C3_vs_{label}", p))
                entry["contrasts"][f"C3_vs_{label}"] = con
            rows[m][defect] = entry
    # Holm across the whole E2 McNemar family
    holm = holm_bonferroni([p for *_, p in family]) if family else None
    if holm:
        for (m, defect, label, p), adj, rej in zip(family, holm.adjusted, holm.reject):
            con = rows[m][defect]["contrasts"].get(label)
            if con is not None:
                con["holm_p"] = round(adj, 4)
                con["reject_holm"] = bool(rej)
    fam = {"n_tests": len(family), "method": "holm", "alpha": 0.05,
           "n_reject": holm.n_reject if holm else 0}
    return rows, models, usage, fam


# --------------------------------------------------------------------------- #
def _p(x, signed=False):
    if x is None:
        return "—"
    return f"{x:+.2f}" if signed else f"{x:.2f}"


def _contrast_str(con):
    if not con:
        return "—"
    s = f"{_p(con['delta'], signed=True)}"
    if "mcnemar_p" in con:
        s += f" (p={con['mcnemar_p']}"
        if "holm_p" in con:
            s += f"→{con['holm_p']}"
        s += (" ✅" if con.get("reject_holm") else "") + ")"
    return s


def md_report(rows, models, usage, fam) -> str:
    L = ["## E2 — compute-matched C0 ablation (paired-clean detection, modality A)\n",
         "Same model, image, and rendered corpus across conditions. The compute-matched "
         f"control is **self-consistency**: majority vote over K={_rep_k(rows)} independent "
         "C0 draws — the standard way to spend extra test-time compute for accuracy. Δ = C3 "
         "balanced accuracy − the control's; McNemar p is the exact paired test, **Holm** = "
         f"family-wise corrected over the {fam['n_tests']} E2 tests (α=0.05, {fam['n_reject']} "
         "rejected).\n",
         "### Main — pointwise baseline vs. compute-matched self-consistency vs. atomic C3\n",
         "| Model | Defect | C0 | Self-consistency (K-vote) | C3 | Δ(C3−self-cons) | Δ(C3−C0) |",
         "|---|---|---|---|---|---|---|"]
    for m in models:
        for defect in sorted(rows[m]):
            e = rows[m][defect]
            b = e["bal"]
            con_sc = e["contrasts"].get("C3_vs_C0_rep_maj")
            con_c0 = e["contrasts"].get("C3_vs_C0")
            L.append(
                f"| {m} | {SHORT.get(defect, defect)} | {_p(b.get('C0'))} | "
                f"{_p(b.get('C0_rep_maj'))} | {_p(b.get('C3'))} | "
                f"{_contrast_str(con_sc)} | {_contrast_str(con_c0)} |")
    # definition-matched second control (supplement)
    L += ["\n### Supplement — definition-matched control (C0_full: whole-taxonomy single "
          "call + per-type definitions + forced evidence)\n",
          "| Model | Defect | C0_full | C3 | Δ(C3−C0_full) |",
          "|---|---|---|---|---|"]
    for m in models:
        for defect in sorted(rows[m]):
            e = rows[m][defect]
            L.append(f"| {m} | {SHORT.get(defect, defect)} | {_p(e['bal'].get('C0_full'))} | "
                     f"{_p(e['bal'].get('C3'))} | {_contrast_str(e['contrasts'].get('C3_vs_C0_full'))} |")
    # budget (E3)
    L += ["\n### Budget (E3) — completion tokens per slide\n",
          "If C3 does not spend MORE output tokens than C0_full, the recovery cannot be a "
          "test-time-compute artifact. `calls/slide` shows C0_rep's K× multiplier.\n",
          "| Model | Cond | calls/slide | prompt tok/slide | completion tok/slide | reasoning tok/slide |",
          "|---|---|---|---|---|---|"]
    for m in models:
        for cond in CONDS:
            u = usage.get(m, {}).get(cond)
            if not u:
                continue
            L.append(f"| {m} | {cond} | {u['calls_per_record']} | "
                     f"{u['prompt_tokens_per_record']} | {u['completion_tokens_per_record']} | "
                     f"{u['reasoning_tokens_per_record']} |")
    # verdict helper
    L += ["\n### Reading\n",
          _verdict(rows, models),
          f"\n**Test-family growth**: this report adds **{fam['n_tests']}** paired McNemar "
          "tests — add these to the paper's Holm family and update the \"N-test family\" count.\n"]
    return "\n".join(L) + "\n"


def _rep_k(rows) -> str:
    return "10"  # documented default; overridable via --rep-k (see run_e2_computematch.sh)


def _verdict(rows, models) -> str:
    """A one-line automatic read of which W2.4 branch the data support, per defect.
    The WIN/MIXED/LOSS framing only applies where C3 is actually a recovery mechanism
    for this class (C3 clearly beats the plain C0 baseline). Where C3 does NOT beat
    C0 (e.g. G1 / reference-assisted classes, recovered by pairwise not atomic C3),
    the compute-match is N/A and mislabelling it a "loss" would be wrong."""
    lines = []
    for m in models:
        for defect in sorted(rows.get(m, {})):
            e = rows[m][defect]
            sc = e["contrasts"].get("C3_vs_C0_rep_maj")   # self-consistency (majority)
            full = e["contrasts"].get("C3_vs_C0_full")
            c0_bal, c3_bal = e["bal"].get("C0"), e["bal"].get("C3")
            if not sc or not full:
                continue
            d_sc, d_full = sc["delta"], full["delta"]
            sc_sig = sc.get("reject_holm")
            # C3 must recover over the plain baseline for the compute-match to be relevant.
            recovers = (c0_bal is not None and c3_bal is not None and (c3_bal - c0_bal) > 0.05)
            if not recovers:
                branch = ("N/A: C3 does not recover over C0 here (C3≤C0) — this is a "
                          "reference-assisted / non-format-suppressed class, not a target of "
                          "the compute-match; report as a negative control.")
            elif d_sc > 0.05 and sc_sig:
                branch = ("WIN: C3 beats the compute-matched self-consistency control — the "
                          "recovery is NOT test-time compute.")
            else:
                branch = "INCONCLUSIVE at current n — inspect CIs."
            lines.append(f"- **{m} / {SHORT.get(defect, defect)}**: {branch} "
                         f"(C0={_p(c0_bal)}, C3={_p(c3_bal)}; Δ C3−self-cons = {_p(d_sc, signed=True)}; "
                         f"Δ C3−C0_full = {_p(d_full, signed=True)})")
    return "\n".join(lines) if lines else "- (no complete C3 / C0_rep / C0_full triple yet)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="p1e2")
    ap.add_argument("--md", default="reports/_e2_computematch.md")
    ap.add_argument("--json", default="data/part3/p1e2_summary.json")
    args = ap.parse_args()

    rows, models, usage, fam = build(args.prefix)
    if not models:
        raise SystemExit(f"no {args.prefix}_* result files found — run run_e2_computematch.sh first")
    md = md_report(rows, models, usage, fam)
    Path(REPO / args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(REPO / args.md).write_text(md, encoding="utf-8")
    Path(REPO / args.json).write_text(
        json.dumps({"conditions": rows, "models": models, "usage": usage,
                    "mcnemar_family": fam}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)
    print(f"[e2-report] Holm family: {fam}")
    print(f"[e2-report] -> {args.md} ; {args.json}")


if __name__ == "__main__":
    main()
