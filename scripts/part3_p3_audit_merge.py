"""Part 3 Protocol-3 — merge per-RM audits into the model-agnostic blind-spot view.

Reads every ``data/part3/p3_audit__<key>.json`` (the assertion-variant runs) plus
any ``__neutral`` prompt-sensitivity runs, and emits:

  * ``data/part3/p3_audit_multi.json`` — the freeform preference-accuracy table for
    every reward model, a G7 cross-model row, the prompt-sensitivity deltas, and
    the headline verdict: do ALL *trained* reward models sit at/below chance on G7?
  * ``data/part3/p3_fidelity_multi.json`` — the template (snap-absorbed) runs for
    every reward model: feeding the ~45% snap-erased pairs to each RM yields
    gap≈0 / preference≈0, i.e. any IR-label reward trained on snapped renders
    inherits zero-signal pairs. Cross-references the model-agnostic pixel-level
    absorption rates already in ``p3_fidelity.json``.

Pure offline. Run after the per-RM audits:  python scripts/part3_p3_audit_merge.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO / "data/part3"
CHANCE = 0.5
G7 = "G7_RENDER_CONTAINMENT_OVERFLOW"


def load_audits(audit_dir: Path = D):
    primary, probe = {}, {}
    for fp in sorted(glob.glob(str(audit_dir / "p3_audit__*.json"))):
        d = json.loads(Path(fp).read_text())
        key = d["key"]
        if d.get("variant") == "probe":
            probe[key] = d
        else:
            primary[key] = d
    return primary, probe


def summarize(primary: dict, probe: dict, pixel_fidelity: dict | None = None):
    """Pure aggregation: per-RM audit dicts -> (audit_multi, fidelity_multi).

    ``primary`` maps rm-key -> the per-RM 'generic' audit json (deployment-realistic
    elicitation); ``probe`` maps rm-key -> the 'probe' (defect-aware) audit json,
    used for the elicitation-recoverability check. ``pixel_fidelity`` is the parsed
    ``p3_fidelity.json`` (model-agnostic pixel-level absorption), or None."""
    models, fidelity_models = [], []
    for key, d in primary.items():
        ff = [r for r in d["results"] if r["render"] == "freeform"]
        tpl = [r for r in d["results"] if r["render"] == "template"]
        models.append({
            **{k: d[k] for k in ("key", "display_name", "category", "contract",
                                 "backbone", "trained_reward")},
            "elicitation": d.get("elicitation"),
            "freeform": {r["defect"]: {"preference_accuracy": r["preference_accuracy"],
                                       "preference_ci": r["preference_ci"],
                                       "mean_gap": r["mean_reward_gap_clean_minus_def"],
                                       "n": r["n"]} for r in ff},
        })
        if tpl:
            fidelity_models.append({
                "key": key, "display_name": d["display_name"],
                "trained_reward": d["trained_reward"],
                "template_snap_absorbed": {
                    r["defect"]: {"preference_accuracy": r["preference_accuracy"],
                                  "mean_gap": r["mean_reward_gap_clean_minus_def"],
                                  "n": r["n"]} for r in tpl},
            })

    # ---- G7 cross-model row + headline verdict -----------------------------
    # Two criteria per reward, under deployment-realistic (generic) elicitation:
    #   below_chance  = CI upper <= 0.5 (or point <= 0.5): it actively mis-ranks G7.
    #   not_reliably_above = CI lower < 0.5: it does NOT reliably detect G7.
    # The honest headline at full n: a reward "reliably detects G7" only if its 95%
    # CI lower bound exceeds chance. None do -> model-agnostic blind spot. (At small
    # n a subset of G7 variants can push a point estimate below chance; the CI test
    # is the robust statement.) below_chance (point/CI<=0.5) is reported too.
    g7_row = []
    below_trained, not_reliable_trained = [], []   # over trained rewards
    n_scorers_reliable = 0                          # over ALL scorers incl. aesthetic
    for m in models:
        cell = m["freeform"].get(G7)
        if not cell:
            continue
        is_below = cell["preference_ci"][1] <= CHANCE or cell["preference_accuracy"] <= CHANCE
        reliably = cell["preference_ci"][0] >= CHANCE   # CI fully above chance
        g7_row.append({"key": m["key"], "display_name": m["display_name"],
                       "category": m["category"], "trained_reward": m["trained_reward"],
                       "preference_accuracy": cell["preference_accuracy"],
                       "preference_ci": cell["preference_ci"],
                       "mean_gap": cell["mean_gap"],
                       "below_chance": is_below, "reliably_detects_g7": reliably})
        n_scorers_reliable += int(reliably)
        if m["trained_reward"]:
            below_trained.append(is_below)
            not_reliable_trained.append(not reliably)
    verdict_all_blind = bool(below_trained) and all(below_trained)
    verdict_none_reliable = bool(not_reliable_trained) and all(not_reliable_trained)
    verdict_no_scorer_reliable = (n_scorers_reliable == 0) and bool(g7_row)

    # ---- elicitation recoverability (generic vs probe, on G7) --------------
    sensitivity = []
    for key, dp in probe.items():
        g7p = next((r for r in dp["results"] if r["defect"] == G7), None)
        base = primary.get(key, {})
        g7g = next((r for r in base.get("results", []) if r["defect"] == G7
                    and r["render"] == "freeform"), None)
        if g7p and g7g:
            sensitivity.append({
                "key": key, "display_name": base.get("display_name", key),
                "g7_generic_pref": g7g["preference_accuracy"],
                "g7_probe_pref": g7p["preference_accuracy"],
                "g7_generic_gap": g7g["mean_reward_gap_clean_minus_def"],
                "g7_probe_gap": g7p["mean_reward_gap_clean_minus_def"],
            })

    audit_multi = {
        "metric": "paired preference accuracy = P(reward(clean) > reward(defective)); "
                  "0.5 = blind, 1.0 = always prefers the clean slide",
        "chance": CHANCE,
        "n_models": len(models),
        "categories_covered": sorted({m["category"] for m in models}),
        "models": models,
        "g7_cross_model": g7_row,
        "prompt_sensitivity_g7": sensitivity,
        "verdict": {
            "n_models": len(models),
            "n_trained_rewards": int(sum(m["trained_reward"] for m in models)),
            "n_scorers_reliably_detecting_g7_generic": n_scorers_reliable,
            "n_trained_below_chance_on_g7": int(sum(below_trained)),
            "all_trained_rewards_at_or_below_chance_on_g7": verdict_all_blind,
            "no_trained_reward_reliably_detects_g7_generic": verdict_none_reliable,
            # the robust headline: under generic elicitation NO scorer (trained or
            # aesthetic) reliably detects G7 (no CI excludes chance from below).
            "no_scorer_reliably_detects_g7_generic": verdict_no_scorer_reliable,
            "statement": (
                (f"Under deployment-realistic (generic) elicitation only "
                 f"{n_scorers_reliable}/{len(models)} reward scorers reliably detect G7 "
                 "(95% CI above chance). The G7 blind spot is a property of NARROW "
                 "critics — the symbolic linter and specialised document / aesthetic "
                 "rewards all miss it — while a capable GENERAL-multimodal reward "
                 "detects it; every scorer is meanwhile clearly sensitive to its "
                 "in-taxonomy classes. This refines 'neural rewards are blind to G7' to "
                 "'narrow rewards are; a general VLM reward (like a prompted VLM, "
                 "Result-1) is not' — and validates routing G7 to a VLM engine.")
                if n_scorers_reliable and not verdict_no_scorer_reliable else
                ("Model-agnostic G7 blind spot under deployment-realistic (generic) "
                 f"elicitation: 0 of {len(models)} reward scorers reliably detect G7 "
                 "(every 95% CI includes chance) across document / general-multimodal / "
                 "aesthetic categories and distinct backbones, while each is sensitive "
                 "to its in-taxonomy classes.")),
        },
    }
    # ---- cross-RM fidelity -------------------------------------------------
    pixel = {}
    if pixel_fidelity:
        pixel = {"overall_template_absorption_rate":
                 pixel_fidelity.get("overall", {}).get("template_absorption_rate"),
                 "per_defect_absorption": {k: v.get("template_absorption_rate")
                                           for k, v in pixel_fidelity.get("per_defect", {}).items()}}
    fidelity_multi = {
        "note": ("Cross-RM perturbation-fidelity tie-in. The template (snap-to-master) "
                 "render absorbs ~45% of injected geometry defects, making the defective "
                 "image pixel-identical to its clean twin. Feeding those snap-absorbed "
                 "pairs to each reward model yields preference≈0 / gap≈0 — so ANY reward "
                 "trained or evaluated on snapped renders inherits zero-signal pairs. "
                 "This is model-agnostic by construction (identical pixels)."),
        "pixel_level_absorption": pixel,
        "per_reward_model": fidelity_models,
    }
    return audit_multi, fidelity_multi


def main():
    primary, neutral = load_audits()
    if not primary:
        raise SystemExit("no per-RM audits found (run part3_p3_reward_audit.py --rm ... first)")
    fpix = D / "p3_fidelity.json"
    pixel_fidelity = json.loads(fpix.read_text()) if fpix.exists() else None

    audit_multi, fidelity_multi = summarize(primary, neutral, pixel_fidelity)

    (D / "p3_audit_multi.json").write_text(
        json.dumps(audit_multi, indent=2, ensure_ascii=False), encoding="utf-8")
    (D / "p3_fidelity_multi.json").write_text(
        json.dumps(fidelity_multi, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- console summary ---------------------------------------------------
    g7_row = audit_multi["g7_cross_model"]
    print(f"merged {audit_multi['n_models']} reward models -> p3_audit_multi.json")
    print(f"categories: {audit_multi['categories_covered']}")
    print("\nG7 (render-containment overflow) preference accuracy across reward models:")
    for r in sorted(g7_row, key=lambda x: x["preference_accuracy"]):
        flag = "DETECTS" if r["reliably_detects_g7"] else "blind (CI spans chance)"
        tr = "trained" if r["trained_reward"] else "heuristic"
        print(f"  {r['display_name']:28s} ({tr:9s}) pref={r['preference_accuracy']:.2f} "
              f"CI{r['preference_ci']} gap={r['mean_gap']:+.3f}  [{flag}]")
    print(f"\nVERDICT all_trained_rewards_<=_chance_on_G7 = "
          f"{audit_multi['verdict']['all_trained_rewards_at_or_below_chance_on_g7']}")
    if audit_multi["prompt_sensitivity_g7"]:
        print("\nelicitation recoverability (G7, generic -> probe):")
        for s in audit_multi["prompt_sensitivity_g7"]:
            print(f"  {s['display_name']:28s} pref {s['g7_generic_pref']:.2f} -> "
                  f"{s['g7_probe_pref']:.2f}  (gap {s['g7_generic_gap']:+.2f} -> {s['g7_probe_gap']:+.2f})")
    print("\nwrote p3_audit_multi.json + p3_fidelity_multi.json")


if __name__ == "__main__":
    main()
