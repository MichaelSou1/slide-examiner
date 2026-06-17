"""S6 (image-text contradiction) once it is actually manifest.

The synthetic corpus now has image-bearing decks: a figure element visibly
depicts a claim (an up/down trend + caption) whose content is stripped from the
structure oracle, and the body either agrees (clean) or is flipped to the
authored contradiction (S6). This measures whether the model can *discriminate*
contradiction from agreement, using paired clean controls and balanced accuracy
-- not recall, which over-firing would inflate to 100%.
"""
from __future__ import annotations

import json
from pathlib import Path

from slide_examiner.analysis import classify_probe_record

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "runs" / "probe" / "part1_s6_30b.jsonl"
SUMMARY = REPO / "runs" / "probe" / "part1_s6_summary.json"
REPORT = REPO / "reports" / "part1_s6_manifest.md"
D = "S6_IMAGE_TEXT_CONTRADICTION"
MODS = ("A", "B", "B_prime", "C")


def main() -> None:
    t1 = [r for r in (classify_probe_record(x) for x in (json.loads(l) for l in PROBE.open())) if r.task == "T1"]
    summary = {"model": "qwen3vl-30b", "subset": "data/part1_img/manifest_s6_rendered.jsonl", "by_modality": {}}
    for m in MODS:
        pos = [r for r in t1 if r.modality == m and D in r.expected_types]
        neg = [r for r in t1 if r.modality == m and not r.expected_types]
        tp = sum(D in r.predicted_types for r in pos)
        fp = sum(D in r.predicted_types for r in neg)
        tpr = tp / len(pos) if pos else 0.0
        tnr = 1 - fp / len(neg) if neg else 0.0
        summary["by_modality"][m] = {
            "recall_tp": tp, "n_pos": len(pos), "fp": fp, "n_neg": len(neg),
            "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
            "balanced_accuracy": round((tpr + tnr) / 2, 3),
        }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    L = []
    L.append("# Part 1 — S6 image-text contradiction, now manifest\n")
    L.append("Image-bearing decks (`scripts/part1_image_corpus.py`): each figure element draws an "
             "up/down trend glyph + a caption of what it depicts; that depicted claim is **stripped from "
             "the structure oracle** (`diagram_claim`/`diagram_false_claim`/`diagram_trend` are hidden), so a "
             "contradiction is perceivable only from the image. The body agrees with the figure in the clean "
             "control and is flipped to the authored contradiction for S6. 30B-A3B, A/B/B'/C, T1, 24 S6 + 24 "
             "agreeing-clean, 0% parse failure.\n")
    L.append("## Discrimination (contradiction vs agreement) — paired controls\n")
    L.append("| Modality | recall (TP/P) | false-pos (FP/N) | precision | balanced accuracy |")
    L.append("|---|---|---|---|---|")
    for m in MODS:
        s = summary["by_modality"][m]
        L.append(f"| {m} | {s['recall_tp']}/{s['n_pos']} | {s['fp']}/{s['n_neg']} | {s['precision']} | {s['balanced_accuracy']} |")
    L.append("")
    L.append("## Finding — a negative result, and a methodology warning\n")
    L.append("- **The defect is now genuinely manifest** (verified by eye and in the VLM caption: \"a green "
             "upward-pointing triangle ... 'revenue rose' ... text reads 'revenue fell'\"). So S6's earlier 0/8 "
             "was a non-manifest-data artifact — that part is fixed.")
    L.append("- **But the 30B model cannot actually do S6**: on the image channels (A and C) it asserts a "
             "contradiction on essentially *every* figure slide — 24/24 on true S6 **and** 24/24 on the "
             "agreeing-clean controls — i.e. precision 0.50 and **balanced accuracy 0.50, exactly chance**. The "
             "100% 'recall' is blanket over-firing, not detection.")
    L.append("- **Structure-only B is precise but blind**: 0 false positives, but only 3/24 recall, because the "
             "figure's depicted claim is intentionally absent from the oracle. B cannot be the S6 detector.")
    L.append("- **The caption channel B' is only just above chance** (balanced accuracy 0.58): even though the "
             "caption transcribes both the figure trend and the contradicting text, the model still over-asserts "
             "(15/24 false positives).")
    L.append("- **Methodology warning for the matrix**: S6 (and any agreement-checking defect) MUST be scored "
             "with paired clean controls and balanced accuracy / precision, never recall alone — a recall-only "
             "view here would have reported '100% S6 detection' when the true discrimination is chance. The "
             "scope prompt that names S6 as a candidate likely primes the over-firing; an open-scope or "
             "forced-choice (which of these two slides has the contradiction?) eval is the fairer follow-up.\n")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {SUMMARY}\nWrote {REPORT}")


if __name__ == "__main__":
    main()
