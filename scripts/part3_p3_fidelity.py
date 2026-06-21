"""Part 3 Protocol-3 (c) — perturbation-fidelity audit (A.6c).

Generalises the Part-2 *snap-bug* byte/structure check into a quantitative audit:
**when you inject a defect into the IR, does it actually render?**

Every Part-2 defective slide was rendered two ways from the SAME perturbed IR:
  * ``__freeform`` — the IR is drawn as-declared (the eval renderer).
  * ``__template`` — the IR is *snapped to the master template* before drawing
    (``snap_slide_to_master``); the snap re-fits element bboxes to the master's
    placeholder grid.

For geometry perturbations (overflow / overlap / offset / margin) the snap step
**absorbs** the injected defect: the template render is pixel-identical to its
clean pair even though the IR carries the defect and its label says "defective".
That silent "injected-but-not-rendered" mismatch is a label-noise hazard for any
reward/critic trained or evaluated on rendered images — and it is exactly why our
Protocol-1/2 eval uses the freeform renderer.

This script quantifies, per defect class:
  * the rendered pixel effect-size under each renderer (changed-pixel fraction),
  * the **template absorption rate** = injected in IR + renders under freeform but
    NOT under template = the fidelity failure rate of the snap pipeline,
  * a bridge to the perceptual floor: the per-class pixel footprint (tiny for the
    sub-perceptual fine-geometry classes the linter must own).

Pure offline (no GPU). Output -> data/part3/p3_fidelity.json.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
THR = 20           # per-pixel channel-sum delta to count a pixel as "changed"
EPS = 0.0005       # changed-pixel fraction above which the perturbation "rendered"


def defect_of(rec: dict) -> str:
    return rec["labels"][0]["type"] if rec.get("labels") else "NO_DEFECT"


def changed_frac(def_path: str, clean_path: str) -> float | None:
    try:
        a = Image.open(def_path).convert("RGB")
        b = Image.open(clean_path).convert("RGB").resize(a.size)
    except Exception:  # noqa: BLE001
        return None
    aa = np.asarray(a, dtype=np.int16)
    bb = np.asarray(b, dtype=np.int16)
    return float((np.abs(aa - bb).sum(-1) > THR).mean())


def ir_differs(rec: dict) -> bool | None:
    """Does the perturbed IR actually differ from its clean IR? (was a defect
    truly injected at the structural level)."""
    from slide_examiner.ingest import load_slide_json
    pair = rec.get("pair") or {}
    cp = pair.get("clean_slide_path")
    dp = pair.get("defective_slide_path")
    if not cp or not dp:
        # fall back to inline slide IR vs clean slide json
        if not cp or not rec.get("slide"):
            return None
        try:
            clean = load_slide_json(cp if Path(cp).is_absolute() else REPO / cp)
        except Exception:  # noqa: BLE001
            return None
        return rec["slide"] != clean.to_dict()
    try:
        clean = load_slide_json(cp if Path(cp).is_absolute() else REPO / cp).to_dict()
        defe = load_slide_json(dp if Path(dp).is_absolute() else REPO / dp).to_dict()
    except Exception:  # noqa: BLE001
        return None
    return clean.get("elements") != defe.get("elements")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/part2/manifest_eval_test_rendered.jsonl")
    ap.add_argument("--out", default="data/part3/p3_fidelity.json")
    args = ap.parse_args()

    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    # The manifest interleaves __freeform and __template renders of the SAME
    # perturbed IR as separate records. We audit per base slide using the
    # freeform record and derive its template counterpart, so each base is
    # counted once.
    recs = [r for r in recs if "__freeform" in (r.get("image_path") or "")]
    per = collections.defaultdict(lambda: {
        "n": 0, "ff": [], "tpl": [], "ir_injected": 0, "have_template": 0,
        "rendered_ff": 0, "rendered_tpl": 0, "absorbed": 0})

    for rec in recs:
        d = defect_of(rec)
        if d == "NO_DEFECT":
            continue
        fp = rec.get("image_path")
        fc = (rec.get("pair") or {}).get("clean_image_path")
        if not fp or not fc:
            continue
        bucket = per[d]
        bucket["n"] += 1
        inj = ir_differs(rec)
        if inj:
            bucket["ir_injected"] += 1
        ff = changed_frac(fp, fc)
        if ff is None:
            continue
        bucket["ff"].append(ff)
        rendered_ff = ff > EPS
        bucket["rendered_ff"] += int(rendered_ff)
        # template (snap) variant
        tp = fp.replace("__freeform", "__template")
        tc = fc.replace("__freeform", "__template")
        if Path(tp).exists() and Path(tc).exists():
            tpl = changed_frac(tp, tc)
            if tpl is not None:
                bucket["have_template"] += 1
                bucket["tpl"].append(tpl)
                rendered_tpl = tpl > EPS
                bucket["rendered_tpl"] += int(rendered_tpl)
                # absorbed = injected + rendered freeform but NOT under template snap
                if rendered_ff and not rendered_tpl:
                    bucket["absorbed"] += 1

    def summ(vals):
        if not vals:
            return None
        return {"median": round(statistics.median(vals), 5),
                "mean": round(statistics.fmean(vals), 5),
                "p90": round(sorted(vals)[int(0.9 * (len(vals) - 1))], 5)}

    out = {"manifest": args.manifest, "thr_channel_sum": THR, "eps_changed_frac": EPS,
           "per_defect": {}, "overall": {}}
    tot = {"n": 0, "have_template": 0, "absorbed": 0, "rendered_ff": 0, "ir_injected": 0}
    for d in sorted(per):
        b = per[d]
        ht = b["have_template"]
        out["per_defect"][d] = {
            "n": b["n"],
            "ir_injected_rate": round(b["ir_injected"] / b["n"], 3) if b["n"] else None,
            "freeform_effect": summ(b["ff"]),
            "template_effect": summ(b["tpl"]),
            "rendered_freeform_rate": round(b["rendered_ff"] / len(b["ff"]), 3) if b["ff"] else None,
            "rendered_template_rate": round(b["rendered_tpl"] / ht, 3) if ht else None,
            "template_absorption_rate": round(b["absorbed"] / ht, 3) if ht else None,
            # conditional on the perturbation actually rendering under freeform —
            # the cleanest "of the defects that are real/visible, how many does the
            # snap pipeline silently erase".
            "absorption_among_rendered": round(b["absorbed"] / b["rendered_ff"], 3) if b["rendered_ff"] else None,
            "n_template_pairs": ht,
        }
        for k in tot:
            tot[k] += b[k]
    out["overall"] = {
        "n_defectives": tot["n"],
        "ir_injected_rate": round(tot["ir_injected"] / tot["n"], 3) if tot["n"] else None,
        "n_template_pairs": tot["have_template"],
        "template_absorption_rate": round(tot["absorbed"] / tot["have_template"], 3) if tot["have_template"] else None,
        "note": ("template_absorption_rate = fraction of injected defectives whose "
                 "perturbation renders under freeform but is snapped away (clean) "
                 "under template = silent label-noise = the perturbation-fidelity hazard."),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
