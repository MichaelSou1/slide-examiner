"""Track E — S-group (S1/S4/S5 + S2/S3/S6 context) pointwise attribution across
model sizes, scored with **balanced accuracy + paired clean** (not recall-only).

Reads the three S-group probe jsonls (4B / 8B / 30B, A/B/B'/C × T1 over the frozen
sgroup subset: 64 defectives + 40 paired clean negatives) and reports, per
(model, defect, modality):
  recall      = TP rate on the defective samples of that type
  specificity = TN rate on the level-matched clean negatives w.r.t. that type
  bal_acc     = (recall + specificity) / 2     <-- main metric (SPEC §3.0 轨 E)

Per SPEC §3.0: recall alone is misleading (models over-report / abstain); the
attribution claim (A-fail / B-success perceptual gap) only holds under
balanced accuracy with the paired clean control.

Usage: PYTHONPATH=. python scripts/part1_sgroup_crosssize.py
"""
from __future__ import annotations

import json
from pathlib import Path

from slide_examiner.analysis import classify_probe_record

REPO = Path(__file__).resolve().parents[1]
PROBES = {"4B": "runs/probe/part1_sgroup_4b.jsonl",
          "8B": "runs/probe/part1_sgroup_8b.jsonl",
          "30B": "runs/probe/part1_sgroup_30b.jsonl"}
# Deck-level clean negatives (24 decks), needed for deck-level specificity/bal_acc.
# A/B/C come from the deckneg probe; B' from the captioned-deckneg probe.
DECKNEG = {"4B": ["runs/probe/part1_sgroup_deckneg_4b.jsonl",
                  "runs/probe/part1_sgroup_deckneg_bprime_4b.jsonl"],
           "8B": ["runs/probe/part1_sgroup_deckneg_8b.jsonl",
                  "runs/probe/part1_sgroup_deckneg_bprime_8b.jsonl"],
           "30B": ["runs/probe/part1_sgroup_deckneg_30b.jsonl",
                   "runs/probe/part1_sgroup_deckneg_bprime_30b.jsonl"]}
SUMMARY = REPO / "runs" / "probe" / "part1_sgroup_crosssize_summary.json"
REPORT = REPO / "reports" / "part1_sgroup_crosssize.md"

DECK = {"S2_NARRATIVE_ORDER_BREAK", "S3_TERMINOLOGY_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION"}
PAGE_S = ["S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION"]
DECK_S = ["S2_NARRATIVE_ORDER_BREAK", "S3_TERMINOLOGY_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION"]
ALL_S = PAGE_S + DECK_S
MODS = ("A", "B", "B_prime", "C")


def level_of(defect: str) -> str:
    return "deck" if defect in DECK else "page"


def bal_acc(model_rows, defect, modality):
    pos = [r for r in model_rows if r["modality"] == modality and defect in r["expected"]]
    # level-matched clean negatives: clean samples probed at the same scope level
    lvl = level_of(defect)
    neg = [r for r in model_rows if r["modality"] == modality and not r["expected"]
           and r["level"] == lvl]
    if not pos or not neg:
        return None
    recall = sum(defect in r["predicted"] for r in pos) / len(pos)
    spec = sum(defect not in r["predicted"] for r in neg) / len(neg)
    return {"recall": round(recall, 3), "specificity": round(spec, 3),
            "bal_acc": round((recall + spec) / 2, 3), "n_pos": len(pos), "n_neg": len(neg)}


def main() -> None:
    def load(paths):
        rows = []
        for path in ([paths] if isinstance(paths, str) else paths):
            for line in (REPO / path).open():
                raw = json.loads(line)
                c = classify_probe_record(raw)
                if c.task != "T1":
                    continue
                rows.append({"modality": c.modality, "expected": c.expected_types,
                             "predicted": c.predicted_types,
                             "level": raw.get("level", "deck" if raw.get("deck") else "page")})
        return rows

    summary = {"metric": "balanced_accuracy (recall on positives + specificity on "
                          "level-matched paired clean negatives)",
               "models": list(PROBES),
               "deck_negatives": "24 clean decks (A/B/C + 30B-captioned B') folded in for "
                                 "deck-level specificity",
               "by_defect": {}, "group_bal_acc": {}}

    models = {m: load(p) + load(DECKNEG[m]) for m, p in PROBES.items()}

    for d in ALL_S:
        summary["by_defect"][d] = {"level": level_of(d)}
        for m in PROBES:
            summary["by_defect"][d][m] = {mod: bal_acc(models[m], d, mod) for mod in MODS}

    # group-level: mean bal_acc over the defects of each level, per model/modality
    for lvl, defects in (("page", PAGE_S), ("deck", DECK_S)):
        summary["group_bal_acc"][lvl] = {}
        for m in PROBES:
            summary["group_bal_acc"][lvl][m] = {}
            for mod in MODS:
                vals = [bal_acc(models[m], d, mod) for d in defects]
                vals = [v["bal_acc"] for v in vals if v]
                summary["group_bal_acc"][lvl][m][mod] = round(sum(vals) / len(vals), 3) if vals else None

    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# Part 1 — Track E: S-group pointwise attribution across sizes (balanced accuracy)\n",
         "Real VLM probe (vLLM Qwen3-VL 4B / 8B / 30B-A3B), A/B/B'/C × T1 over the frozen "
         "S-group subset (64 defectives + 40 paired clean). **Main metric = balanced accuracy** "
         "(recall + specificity on level-matched clean), per SPEC §3.0 轨 E. B' = VLM-image "
         "caption (held fixed at the 30B caption across sizes, so the cross-size comparison "
         "isolates *reasoning over a fixed caption* from caption quality).\n",
         "## Group balanced accuracy (mean over level's defects)\n",
         "| level | model | A | B | B′ | C |", "|---|---|---|---|---|---|"]
    for lvl in ("page", "deck"):
        for m in PROBES:
            g = summary["group_bal_acc"][lvl][m]
            L.append(f"| {lvl} | {m} | {g['A']} | {g['B']} | {g['B_prime']} | {g['C']} |")
    L.append("\n## Per-defect balanced accuracy (best channel bolded mentally)\n")
    L.append("| defect | level | model | A | B | B′ | C |")
    L.append("|---|---|---|---|---|---|---|")
    for d in ALL_S:
        for m in PROBES:
            cells = summary["by_defect"][d][m]
            def show(mod):
                v = cells[mod]
                return f"{v['bal_acc']}" if v else "—"
            L.append(f"| {d} | {level_of(d)} | {m} | {show('A')} | {show('B')} "
                     f"| {show('B_prime')} | {show('C')} |")
    L.append("\n## Reading\n")
    L.append("- Recall-only would inflate (the 30B S6 channel reports 100% recall at 0.50 "
             "bal-acc — pure over-report). Balanced accuracy on the paired clean is the honest "
             "number; see `part1_s6_manifest.md` for the canonical example.")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY.relative_to(REPO)} and {REPORT.relative_to(REPO)}")
    for lvl in ("page", "deck"):
        for m in PROBES:
            print(f"  {lvl:4s} {m:4s} bal_acc {summary['group_bal_acc'][lvl][m]}")


if __name__ == "__main__":
    main()
