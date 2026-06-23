"""Part 3 Protocol-2 — hybrid-critic coverage on the synthetic all-class set (A.5).

Compares five critic configurations on the SAME paired-clean synthetic slides,
per defect class, by **named attribution** (does the critic emit the correct
defect type on the defective image and not on its clean twin) at paired-clean
balanced accuracy + precision:

  * **linter-only**  — every class routed to the symbolic linter (lint_slide /
                       lint_deck), the deployed default operating point (~0 FP).
  * **VLM-only**     — every class routed to one served VLM under C0 whole-taxonomy
                       pointwise (the realistic "just ask a VLM" single-pass critic).
  * **VLM-C3 everywhere** — the same served VLM under one atomic C3 question for
                       every image-level class; no linter and no per-class routing.
  * **linter+VLM-C3** — the obvious minimal baseline: symbolic linter for declared
                       geometry, one C3 VLM for everything else.
  * **hybrid**       — each class routed by ``hybrid_critic.ROUTER`` to its engine:
                       linter (declared geometry / terminology), VLM-with-best-
                       elicitation (G1->C2, G7->C3, S6->C0), LLM (S1/S2/S4 text).

The headline is **coverage**: number of classes detected at bal_acc>=0.70 &
precision>=0.70, and the mean bal_acc, for each config — hybrid should strictly
dominate. The load-bearing cell is **G7**: linter blind (0.50), VLM-C0 cannot name
it (0.50), VLM-C3 catches it (~1.0) -> only the hybrid covers it.

Uses freeform renders only (the manifest interleaves __freeform/__template; the
template/snap renders absorb ~45% of injected geometry defects — Protocol-3c).

Usage (after serving a capable VLM):
  python scripts/part3_p2_eval.py --base-url http://127.0.0.1:8101/v1 \
     --model qwen35-27b --out data/part3/p2_synth.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from slide_examiner.hybrid_critic import (  # noqa: E402
    ROUTER, VLM_ELICIT, LINTER, VLM, LLM, linter_types, llm_engine)
from slide_examiner.ingest import load_slide_json  # noqa: E402
from part2_eval import clean_variant, defect_of  # noqa: E402
from part3_elicit import _blank_result, _cell, ENGINES  # noqa: E402

# page-level classes that have same-base clean image+IR pairs in the synth set.
PAGE_CLASSES = [
    "G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
    "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION",
    "G7_RENDER_CONTAINMENT_OVERFLOW",
    "S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION",
]


def freeform_only(recs):
    return [r for r in recs if "__template" not in (r.get("image_path") or "")]


def llm_clean_rec(rec):
    """Clean control for the LLM engine: swap in the CLEAN slide IR text."""
    cp = (rec.get("pair") or {}).get("clean_slide_path")
    if not cp:
        return None
    p = cp if Path(cp).is_absolute() else REPO / cp
    if not Path(p).exists():
        return None
    out = json.loads(json.dumps(rec))
    try:
        out["slide"] = load_slide_json(p).to_dict()
    except Exception:  # noqa: BLE001
        return None
    out["sample_id"] = rec["sample_id"] + "__CLEAN"
    return out


# --------------------------------------------------------------------------- #
# Per-engine paired-clean cell on NAMED attribution of `defect`.
# --------------------------------------------------------------------------- #
def linter_cell(pos):
    prows, nrows = [], []
    for r in pos:
        d = defect_of(r)
        prows.append({"x": d in linter_types(r)})
        # clean control = same record's CLEAN IR (declared-bbox negative)
        if (r.get("pair") or {}).get("clean_slide_path"):
            nrows.append({"x": d in linter_types(r, use_clean=True)})
    return _cell(prows, nrows, "x")


def vlm_llm_cell(client, model, pos, defect, engine, condition, modality, style, max_tokens, workers):
    """Run an engine over defective + clean controls; score NAMED attribution."""
    jobs = []  # (rec, is_clean)
    for r in pos:
        jobs.append((r, False))
        c = llm_clean_rec(r) if engine == LLM else clean_variant(r)
        if c is not None:
            jobs.append((c, True))

    # C2 snap-twins must be rendered in the MAIN thread (Playwright sync API) before
    # the pool starts; twins are keyed by slide_id so clean controls share them.
    if engine == VLM and condition == "C2":
        from slide_examiner.elicit_pairwise import prepare_twins
        prepare_twins([r for (r, _c) in jobs if r.get("slide")])

    def work(rec, is_clean):
        if engine == LLM:
            res = llm_engine(client, model, rec, target_defect=defect,
                             max_tokens=max_tokens, blank=_blank_result)
        else:
            res = ENGINES[condition](client, model, rec, modality, defect, style, max_tokens)
        res["is_clean"] = is_clean
        return res

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(work, r, c) for (r, c) in jobs]
        for f in as_completed(futs):
            rows.append(f.result())
    rows = [r for r in rows if not r.get("failure")]
    pos_rows = [r for r in rows if not r["is_clean"]]
    neg_rows = [r for r in rows if r["is_clean"]]
    if not pos_rows or not neg_rows:
        return None
    return _cell(pos_rows, neg_rows, "named_target")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8101/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--style", default="scoped")
    ap.add_argument("--manifest", default="data/part2/manifest_eval_test_rendered.jsonl")
    ap.add_argument("--g7", default="data/part3/manifest_g7_rendered.jsonl")
    ap.add_argument("--modality", default="A")
    ap.add_argument("--max-per-defect", type=int, default=40)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--classes", nargs="+", default=None,
                    help="subset of PAGE_CLASSES to run (for sharding across servers)")
    ap.add_argument("--reuse-existing", default=None,
                    help="existing p2_synth JSON whose per_class cells should be reused; "
                         "missing vlm_c3 cells are still computed")
    ap.add_argument("--force-c3", action="store_true",
                    help="recompute vlm_c3 even when it already exists or can be reused from vlm_best")
    ap.add_argument("--out", default="data/part3/p2_synth.json")
    args = ap.parse_args()
    classes = args.classes or PAGE_CLASSES

    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
                    base_url=args.base_url, timeout=120.0, max_retries=1)

    synth = freeform_only([json.loads(l) for l in Path(args.manifest).open() if l.strip()])
    g7 = [json.loads(l) for l in Path(args.g7).open() if l.strip()]
    bydef = {}
    for r in synth:
        bydef.setdefault(defect_of(r), []).append(r)
    bydef["G7_RENDER_CONTAINMENT_OVERFLOW"] = g7
    existing_per_class = {}
    if args.reuse_existing:
        existing = json.loads(Path(args.reuse_existing).read_text())
        existing_per_class = existing.get("per_class", {})

    per_class = {}
    t0 = time.time()
    for d in classes:
        pos = bydef.get(d, [])[: args.max_per_defect]
        if not pos:
            continue
        cell = json.loads(json.dumps(existing_per_class.get(d, {})))
        # linter engine (offline)
        if not cell.get("linter"):
            cell["linter"] = linter_cell(pos)
        # VLM-C0 (whole-taxonomy pointwise) — the VLM-only critic
        if not cell.get("vlm_c0"):
            cell["vlm_c0"] = vlm_llm_cell(client, args.model, pos, d, VLM, "C0",
                                          args.modality, args.style, args.max_tokens, args.workers)
        # VLM-best elicitation only for VLM-routed classes (G7->C3, S6->C0); other
        # classes are linter/LLM-routed so the special elicitation is not needed.
        if cell.get("vlm_best"):
            pass
        elif ROUTER.get(d) == VLM:
            best = VLM_ELICIT.get(d, "C0")
            cell["vlm_best"] = cell["vlm_c0"] if best == "C0" else vlm_llm_cell(
                client, args.model, pos, d, VLM, best,
                args.modality, args.style, args.max_tokens, args.workers)
        else:
            cell["vlm_best"] = cell["vlm_c0"]
        # VLM-C3 everywhere baseline: one atomic visual question for every
        # image-level class in this P2 set. Reuse the routed VLM cell when it is
        # already C3 (currently G7), otherwise run the extra C3 cell explicitly.
        if cell.get("vlm_c3") and not args.force_c3:
            pass
        elif ROUTER.get(d) == VLM and VLM_ELICIT.get(d, "C0") == "C3" and not args.force_c3:
            cell["vlm_c3"] = cell["vlm_best"]
        else:
            cell["vlm_c3"] = vlm_llm_cell(client, args.model, pos, d, VLM, "C3",
                                          args.modality, args.style, args.max_tokens,
                                          args.workers)
        # LLM engine for the LLM-routed semantic classes
        if ROUTER.get(d) == LLM and not cell.get("llm"):
            cell["llm"] = vlm_llm_cell(client, args.model, pos, d, LLM, None,
                                       args.modality, args.style, args.max_tokens, args.workers)
        per_class[d] = cell
        eng = ROUTER.get(d)
        print(f"  {d:32s} linter={cell['linter']['bal_acc']:.2f} "
              f"vlm_c0={cell['vlm_c0']['bal_acc'] if cell['vlm_c0'] else 'NA'} "
              f"vlm_c3={cell['vlm_c3']['bal_acc'] if cell['vlm_c3'] else 'NA'} "
              f"route={eng}  ({time.time()-t0:.0f}s)", flush=True)

    # ----- assemble the critic configs (named bal_acc + precision) ----- #
    def routed_cell(d):
        eng = ROUTER.get(d)
        if eng == LINTER:
            return per_class[d]["linter"]
        if eng == LLM:
            return per_class[d].get("llm")
        return per_class[d].get("vlm_best")  # VLM

    def linter_plus_vlmc3_cell(d):
        if ROUTER.get(d) == LINTER:
            return per_class[d]["linter"]
        return per_class[d].get("vlm_c3")

    configs = {
        "linter_only": {},
        "vlm_only": {},
        "vlm_c3_everywhere": {},
        "linter_plus_vlmc3": {},
        "hybrid": {},
    }
    for d, cell in per_class.items():
        configs["linter_only"][d] = cell["linter"]
        configs["vlm_only"][d] = cell["vlm_c0"]
        configs["vlm_c3_everywhere"][d] = cell.get("vlm_c3")
        configs["linter_plus_vlmc3"][d] = linter_plus_vlmc3_cell(d)
        configs["hybrid"][d] = routed_cell(d)

    def agg(cfg):
        cells = [c for c in cfg.values() if c]
        covered = [d for d, c in cfg.items() if c and c["bal_acc"] >= 0.70 and c["precision"] >= 0.70]
        return {
            "n_classes": len(cells),
            "mean_bal_acc": round(sum(c["bal_acc"] for c in cells) / len(cells), 3) if cells else None,
            "n_covered_0.70": len(covered),
            "covered_classes": covered,
        }

    out = {
        "model": args.model, "manifest": args.manifest, "modality": args.modality,
        "max_per_defect": args.max_per_defect,
        "metric": "paired-clean named-attribution balanced accuracy + precision",
        "router": {d: ROUTER.get(d) for d in PAGE_CLASSES},
        "vlm_elicit": VLM_ELICIT,
        "per_class": per_class,
        "config_per_class": configs,
        "coverage": {k: agg(v) for k, v in configs.items()},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nCOVERAGE:", json.dumps(out["coverage"], indent=2))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
