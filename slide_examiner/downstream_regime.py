"""E6 (todo_0623) — floored vs unfloored downstream-regime comparison.

The strong-generator self-refine study (Part 3 §1) found the hypothesised
examiner-quality -> refinement-gain *direction* (+0.66) but a sub-1 % *magnitude*,
because a mainstream generator floors most briefs at the first draft. E6 re-runs
the identical gradient with a WEAK local generator (Qwen3-VL-4B) so first drafts
are no longer floored, and asks whether the effect becomes *material*.

This module is pure analysis over the already-aggregated summaries produced by
``scripts/part3_self_refine.py`` (one per regime). No model calls, no I/O beyond
parsed dicts handed in by the caller, so it unit-tests deterministically.

Vocabulary:

* **headroom**   — ``1 − mean_initial`` (room a first draft leaves to improve).
* **gain spread**— ``max − min`` of ``mean_best_gain`` across the examiner gradient
  (how much swapping examiners moves the achievable lift).
* **addressable / unaddressable** — geometry/terms/conciseness are critiqued by the
  linter and/or the injected-defect examiner; *coverage* (deck completeness) is
  critiqued by neither, so coverage headroom cannot transfer no matter the regime.
"""
from __future__ import annotations

from typing import Any

from .feedback_sources import FEEDBACK_SOURCE_ORDER

#: Dimensions the feedback channels can act on vs. cannot (coverage = deck
#: completeness, outside both the geometry linter and the injected-defect examiner).
ADDRESSABLE_DIMS: tuple[str, ...] = ("geometry", "terms", "conciseness")
UNADDRESSABLE_DIMS: tuple[str, ...] = ("coverage",)

#: A best-over-iters gain at or above this (absolute, on the 0–1 model-free DV) is
#: reported as a *material* downstream effect rather than the sub-1 % floored one.
MATERIAL_GAIN: float = 0.03


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson r; 0.0 when undefined (n<2 or a zero-variance axis)."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(num / (dx * dy), 4) if dx > 0 and dy > 0 else 0.0


def ordered_conditions(summary: dict[str, Any]) -> list[str]:
    """Conditions present in ``per_condition`` with a quality_scalar, gradient order."""
    pc = summary.get("per_condition") or {}
    return [c for c in FEEDBACK_SOURCE_ORDER if c in pc and pc[c].get("quality_scalar") is not None]


def regime_stats(summary: dict[str, Any]) -> dict[str, Any]:
    """Headline scalars for one self-refine regime summary."""
    pc = summary.get("per_condition") or {}
    conds = ordered_conditions(summary)
    qs = [pc[c]["quality_scalar"] for c in conds]
    best_gains = [pc[c].get("mean_best_gain", 0.0) for c in conds]
    gains = [pc[c].get("mean_gain", 0.0) for c in conds]
    initials = [pc[c]["mean_initial"] for c in conds if pc[c].get("mean_initial") is not None]

    # best examiner (top quality_scalar; ties -> later in the gradient, i.e. hybrid)
    best_key, best_key_gain = None, 0.0
    if conds:
        best_key = max(conds, key=lambda c: (pc[c]["quality_scalar"], FEEDBACK_SOURCE_ORDER.index(c)))
        best_key_gain = round(pc[best_key].get("mean_best_gain", 0.0), 4)

    # per-dimension Δ aggregated across the gradient (mean over conditions that have it)
    dim_delta_mean: dict[str, float] = {}
    for d in (*ADDRESSABLE_DIMS, *UNADDRESSABLE_DIMS):
        vals = [pc[c]["dim_delta"][d] for c in conds if (pc[c].get("dim_delta") or {}).get(d) is not None]
        if vals:
            dim_delta_mean[d] = round(sum(vals) / len(vals), 4)

    mean_initial = (
        summary.get("regime_mean_initial")
        if summary.get("regime_mean_initial") is not None
        else (round(sum(initials) / len(initials), 4) if initials else None)
    )
    return {
        "n_conditions": len(conds),
        "conditions": conds,
        "mean_initial": mean_initial,
        "mean_headroom": round(1.0 - mean_initial, 4) if mean_initial is not None else None,
        "corr_quality_vs_gain": pearson(qs, gains),
        "corr_quality_vs_best_gain": pearson(qs, best_gains),
        "gain_spread": round(max(best_gains) - min(best_gains), 4) if best_gains else 0.0,
        "max_best_gain": round(max(best_gains), 4) if best_gains else 0.0,
        "best_examiner": best_key,
        "best_examiner_best_gain": best_key_gain,
        "dim_delta_mean": dim_delta_mean,
    }


def compare_regimes(
    strong: dict[str, Any],
    weak: dict[str, Any],
    *,
    material_gain: float = MATERIAL_GAIN,
) -> dict[str, Any]:
    """Compare a flooring (strong) and an unfloored (weak) regime.

    Returns both regimes' stats plus the headroom ratio, the gain-spread
    amplification, and a verdict: ``bounded_positive`` if the best examiner buys a
    material gain in the unfloored regime, else ``stronger_negative``. ``mechanism``
    flags when the unfloored headroom is concentrated in the *unaddressable*
    coverage dimension (the structural reason a tiny gain persists).
    """
    s, w = regime_stats(strong), regime_stats(weak)

    def ratio(a: float | None, b: float | None) -> float | None:
        if a is None or b is None or b == 0:
            return None
        return round(a / b, 3)

    addressable_delta = sum(w["dim_delta_mean"].get(d, 0.0) for d in ADDRESSABLE_DIMS)
    coverage_init_dominates = None
    pcw = weak.get("per_condition") or {}
    if pcw:
        # is the weak regime's headroom mostly coverage? (mean over conditions)
        covs, geos = [], []
        for c, cell in pcw.items():
            di = cell.get("dim_initial") or {}
            if "coverage" in di:
                covs.append(1.0 - di["coverage"])  # coverage headroom
                geos.append(sum(1.0 - di.get(d, 1.0) for d in ADDRESSABLE_DIMS))
        if covs:
            coverage_init_dominates = bool(sum(covs) > sum(geos))

    material = (w["best_examiner_best_gain"] >= material_gain) or (w["max_best_gain"] >= material_gain)
    return {
        "strong": s,
        "weak": w,
        "headroom_ratio_weak_over_strong": ratio(w["mean_headroom"], s["mean_headroom"]),
        "gain_spread_amplification": ratio(w["gain_spread"], s["gain_spread"]),
        "material_gain_threshold": material_gain,
        "weak_addressable_delta_sum": round(addressable_delta, 4),
        "weak_headroom_is_coverage_dominated": coverage_init_dominates,
        "verdict": "bounded_positive" if material else "stronger_negative",
    }
