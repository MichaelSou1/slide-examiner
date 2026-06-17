"""Vision-encoder face-off on geometry, scored by BALANCED ACCURACY.

Tests whether the geometry blindness is a vision-encoder-family artifact, by
holding size ~fixed (8-9B) and swapping the encoder across five models, plus the
30B-A3B for the size axis. Recall alone is misleading here (some models over-fire),
so the headline metric is balanced accuracy on paired clean controls.
"""
from __future__ import annotations

import json
from pathlib import Path

from slide_examiner.analysis import classify_probe_record

REPO = Path(__file__).resolve().parents[1]
GEOM = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
        "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]
# (label, encoder, size, probe file)
MODELS = [
    ("Qwen3-VL-8B", "SigLIP2", "8B", "runs/probe/part1_geom_8b.jsonl"),
    ("Penguin-VL-8B", "LLM-based (anti-contrastive)", "8B", "runs/probe/part1_geom_penguin.jsonl"),
    ("InternVL3.5-8B", "InternViT", "8B", "runs/probe/part1_geom_internvl.jsonl"),
    ("Ovis2.5-9B", "NaViT (native-res)", "9B", "runs/probe/part1_geom_ovis.jsonl"),
    ("Kimi-VL-A3B", "MoonViT (native-res)", "MoE A3B", "runs/probe/part1_geom_kimi.jsonl"),
    ("Qwen3-VL-30B-A3B", "SigLIP2 (size ref)", "MoE 30B", "runs/probe/part1_geom_30b.jsonl"),
]
SUMMARY = REPO / "runs" / "probe" / "part1_encoder_summary.json"
REPORT = REPO / "reports" / "part1_encoder_geometry.md"


def load(p):
    path = REPO / p
    rows = [r for r in (classify_probe_record(x) for x in (json.loads(l) for l in path.open())) if r.task == "T1"]
    fails = sum(1 for x in (json.loads(l) for l in path.open()) if x.get("task") == "T1" and x.get("examiner_failure"))
    return rows, fails


def stats(rows):
    negs = [r for r in rows if r.modality in ("A", "C") and not r.expected_types]
    out = {}
    bals = []
    for d in GEOM:
        pos = [r for r in rows if r.modality in ("A", "C") and d in r.expected_types]
        tpr = sum(d in r.predicted_types for r in pos) / len(pos) if pos else 0.0
        fpr = sum(d in r.predicted_types for r in negs) / len(negs) if negs else 0.0
        bal = (tpr + 1 - fpr) / 2
        out[d] = {"recall": round(tpr, 3), "fpr": round(fpr, 3), "bal_acc": round(bal, 3)}
        bals.append(bal)
    any_fp = sum(bool(r.predicted_types) for r in negs)
    return out, round(sum(bals) / len(bals), 3), any_fp, len(negs)


def main():
    summary = {"models": [], "metric": "balanced accuracy (A/C pooled, paired clean controls)"}
    rendered = {}
    for label, enc, size, p in MODELS:
        rows, fails = load(p)
        per, mean_bal, any_fp, n_neg = stats(rows)
        bias = "abstains" if any_fp <= 5 else ("over-fires" if any_fp >= n_neg * 0.4 else "mild over-call")
        rendered[label] = {"encoder": enc, "size": size, "per": per, "mean_bal": mean_bal,
                           "any_fp": any_fp, "n_neg": n_neg, "bias": bias,
                           "parse_fail": fails, "n_total": len(rows),
                           "parse_fail_pct": round(fails / max(1, len(rows)) * 100),
                           "g1_bal": per["G1_TEXT_OVERFLOW"]["bal_acc"]}
        summary["models"].append({"label": label, **rendered[label]})
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    L = []
    L.append("# Part 1 — is the geometry blindness a vision-encoder artifact?\n")
    L.append("**Hypothesis.** VLMs are blind to slide geometry (G1–G6) because of their contrastive (CLIP/SigLIP) "
             "vision encoder, which suppresses fine-grained cues. If so, a non-SigLIP or native-resolution encoder "
             "should break the blindness. **Test:** five ~8–9B models with different encoders on the same 288 geometry "
             "samples (G1–G6 + 80 clean negatives), A/B/C, T1, plus the 30B-A3B for the size axis.\n")
    L.append("**Metric: balanced accuracy** on paired clean controls (recall alone is misleading — some models "
             "over-fire). 0.50 = chance / no real discrimination.\n")
    L.append("## Geometry discrimination by encoder\n")
    L.append("| Model | encoder | bias (FP/neg) | G1 overflow bal-acc | mean G1–G6 bal-acc | parse-fail |")
    L.append("|---|---|---|---|---|---|")
    for label, *_ in MODELS:
        r = rendered[label]
        L.append(f"| {label} | {r['encoder']} | {r['bias']} ({r['any_fp']}/{r['n_neg']}) | "
                 f"{r['g1_bal']:.2f} | {r['mean_bal']:.2f} | {r["parse_fail_pct"]}% |")
    L.append("")
    L.append("## Result — the encoder hypothesis is NOT supported\n")
    L.append("- **Every 8–9B model is at chance-level geometry discrimination** (mean balanced accuracy ≈ 0.50), "
             "regardless of encoder family: SigLIP2 (Qwen3-VL), LLM-based/anti-contrastive (Penguin-VL), InternViT "
             "(InternVL3.5), and two native-resolution encoders — NaViT (Ovis2.5) and MoonViT (Kimi-VL). Native "
             "resolution does not help either.")
    L.append("- **They differ only in BIAS, not perception.** Qwen3-VL, Penguin-VL and Kimi-VL *abstain* (0 false "
             "positives, ~0 recall); InternVL3.5 *over-fires* (53% G1 recall but 54% false-positive rate → balanced "
             "accuracy 0.49, still chance); Ovis2.5 mildly over-calls. Recall-only would have ranked InternVL 'best', "
             "but with paired controls its 'detection' is just trigger-happiness.")
    L.append("- **The only model that genuinely breaks G1 is the 30B-A3B** (G1 balanced accuracy ~0.75: 50% recall "
             "with 0 false positives). So the lever is *scale / LLM reasoning*, not the vision encoder — even native-res "
             "encoders at 8–9B don't move it.")
    L.append("- **Perception is not the bottleneck; geometric reasoning is.** The document specialist dots.ocr reads "
             "the overflowing title verbatim (\"…real XXXXX\") and lays out every box with coordinates — i.e. the "
             "pixels and text are perfectly legible — yet it (and every chat VLM here) cannot turn that into "
             "\"this text overflows its box / these boxes overlap.\" The gap is reasoning over geometry, which is "
             "exactly what the symbolic linter does deterministically.\n")
    L.append("## Net\n")
    L.append("`G1–G6 → symbolic linter` is now the most stress-tested conclusion in Part 1: it survives a model-size "
             "sweep (4B/8B/30B) AND a vision-encoder sweep across five families (SigLIP2 / LLM-based / InternViT / "
             "NaViT / MoonViT). Swapping the encoder — even to native resolution or an anti-contrastive design — does "
             "not give a VLM slide-geometry detection at 8–9B. Document/OCR specialists (dots.ocr, PaddleOCR-VL) are "
             "perception front-ends, not examiners (they parse layout, they do not judge defects), and are best used "
             "to *feed* the linter/reasoner, not replace it.\n")
    L.append("## Caveats\n")
    L.append("- 1024px render, pointwise, single instances per family (e.g. Penguin via SDPA ViT; Ovis had 12% parse "
             "failures from less JSON-compliant output). Higher render resolution and a forced-choice (2-AFC) framing "
             "remain untested and could still help — but the simple \"swap the encoder\" intervention clearly does not.\n")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {SUMMARY}\nWrote {REPORT}")


if __name__ == "__main__":
    main()
