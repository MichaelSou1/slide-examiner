"""Report: resolution + forced-choice on G1/G3 vs pointwise."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "reports" / "part1_resolution_forcedchoice.md"
SUMMARY = REPO / "runs" / "probe" / "part1_fc_summary.json"
# pointwise balanced-accuracy baselines (A/C pooled) from the encoder sweep
POINTWISE = {("8b", "G1_TEXT_OVERFLOW"): 0.50, ("8b", "G3_ALIGNMENT_OFFSET"): 0.50,
             ("30b", "G1_TEXT_OVERFLOW"): 0.65, ("30b", "G3_ALIGNMENT_OFFSET"): 0.50}
MODELS = [("8b", "Qwen3-VL-8B"), ("30b", "Qwen3-VL-30B-A3B")]
DEFECTS = [("G1_TEXT_OVERFLOW", "G1 text overflow"), ("G3_ALIGNMENT_OFFSET", "G3 alignment offset")]
RES = [1536, 2048]


def load(model, defect, res):
    p = REPO / "runs" / "probe" / f"fc_{model}_{defect}_{res}.json"
    return json.loads(p.read_text()) if p.exists() else None


def main():
    rows = []
    for mk, mlabel in MODELS:
        for dk, dlabel in DEFECTS:
            cells = {}
            for res in RES:
                s = load(mk, dk, res)
                cells[res] = s
            rows.append((mk, mlabel, dk, dlabel, cells))
    SUMMARY.write_text(json.dumps([{"model": r[0], "defect": r[2],
                                    "pointwise_balacc": POINTWISE.get((r[0], r[2])),
                                    "fc": {res: (r[4][res] or {}) for res in RES}} for r in rows],
                                   ensure_ascii=False, indent=2), encoding="utf-8")

    L = []
    L.append("# Part 1 — does resolution or forced-choice rescue geometry?\n")
    L.append("Pointwise detection puts every ≤30B VLM at chance on geometry. Two remaining levers, tested on the two "
             "highest-signal defects: **higher render resolution (1536 / 2048)** and a **2-AFC forced-choice** framing "
             "(show the defective slide and its matching clean slide — same base, only the defect differs — and ask "
             "*which* one has the defect; both orderings to cancel position bias). 24 pairs/defect, image-only.\n")
    L.append("## Forced-choice accuracy (chance = 50%)\n")
    L.append("| Model | Defect | pointwise bal-acc | 2-AFC @1536 | 2-AFC @2048 |")
    L.append("|---|---|---|---|---|")
    for mk, mlabel, dk, dlabel, cells in rows:
        pw = POINTWISE.get((mk, dk))
        def fmt(res):
            s = cells[res]
            if not s:
                return "—"
            acc = s["accuracy"]
            bias = "" if max(s["picks"].values()) <= s["n_trials"] * 0.6 else " (all-one-side)"
            return f"{acc:.0%}{bias}"
        L.append(f"| {mlabel} | {dlabel} | {pw:.2f} | {fmt(1536)} | {fmt(2048)} |")
    L.append("")
    L.append("## Findings — two different failure modes\n")
    L.append("- **G1 text overflow was a *calibration* failure, fully rescued by forced choice.** Qwen3-VL-8B is at "
             "chance pointwise (0.50) but scores **100%** in 2-AFC (48/48, balanced picks, robust across both "
             "orderings); the 30B is also 100%. The overflow was always perceivable — the model just couldn't set an "
             "absolute \"is this overflow?\" threshold in isolation. Given the contrast it is perfect, even at 8B.")
    L.append("- **G3 alignment offset is a genuine *perception* threshold, rescued by nothing.** Forced choice leaves "
             "it at **50% with an all-one-side bias** (the model cannot tell the slides apart, so it always answers A). "
             "This holds at both 1536 and 2048 and at both 8B and 30B. A 2–32px element shift is simply below the "
             "VLM's perceptual resolution for this task.")
    L.append("- **Render resolution made no difference** (1536 ≡ 2048 everywhere). The geometry gap is not a "
             "pixel-budget problem.\n")
    L.append("## Implication\n")
    L.append("The geometry \"blindness\" is two distinct things, and they imply different tools:\n")
    L.append("1. **Gross-but-miscalibrated defects (text overflow):** a VLM *can* do them — but only relatively. A "
             "**pairwise / forced-choice examiner** is the right framing (overflow 8B: chance → 100%). This matches "
             "the S6 result: relative judgement beats absolute scoring for the checks the model perceives but can't "
             "calibrate.")
    L.append("2. **Sub-threshold fine defects (alignment, and by extension font-size/colour/small-margin):** genuinely "
             "below VLM perception up to 30B, unrescued by framing, resolution, or scale → the **symbolic linter is "
             "irreplaceable** here.\n")
    L.append("So the refined Part 1 division of labour: linter owns the fine geometry (G2–G6 fine end); the VLM, used "
             "*pairwise*, can contribute on text overflow; pointwise VLM geometry detection should not be scored at "
             "all. Caveat: synthetic slides, one defect family each for the two mechanisms, 24 pairs — the overflow "
             "rescue is striking and clean, but the fine-geometry floor should be confirmed on real decks.\n")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {SUMMARY}\nWrote {REPORT}")


if __name__ == "__main__":
    main()
