from __future__ import annotations

from typing import Any


def evaluate_hypotheses(
    summary: dict[str, Any],
    *,
    h1_gap_threshold: float = 0.20,
    h1_semantic_gap_max: float = 0.10,
    h1_tpl_reduction_threshold: float = 0.50,
) -> dict[str, Any]:
    return {
        "H1": _evaluate_h1(summary, h1_gap_threshold, h1_semantic_gap_max),
        "H1_tpl": _evaluate_h1_tpl(summary, h1_tpl_reduction_threshold),
        "notes": [
            "H2 requires examiner comparison metrics with finetuned and zero-shot model names.",
            "H3 requires GEPA rollout result records.",
        ],
    }


def _evaluate_h1(summary: dict[str, Any], geometry_threshold: float, semantic_max: float) -> dict[str, Any]:
    gaps = summary.get("oracle_gaps", [])
    geometry = [item for item in gaps if str(item.get("defect_type", "")).startswith("G")]
    semantic = [item for item in gaps if str(item.get("defect_type", "")).startswith("S")]
    if not geometry:
        return {"decision": "inconclusive", "reason": "no geometry oracle gaps"}
    geometry_pass = all(item.get("gap", 0.0) >= geometry_threshold for item in geometry)
    semantic_pass = not semantic or all(abs(item.get("gap", 0.0)) <= semantic_max for item in semantic)
    return {
        "decision": "pass" if geometry_pass and semantic_pass else "fail",
        "geometry_gap_min": min(item.get("gap", 0.0) for item in geometry),
        "semantic_gap_max_abs": max((abs(item.get("gap", 0.0)) for item in semantic), default=0.0),
        "geometry_threshold": geometry_threshold,
        "semantic_gap_max": semantic_max,
    }


def _evaluate_h1_tpl(summary: dict[str, Any], reduction_threshold: float) -> dict[str, Any]:
    collapse = summary.get("template_collapse", [])
    targeted = [
        item
        for item in collapse
        if item.get("defect_type") in {"G3_ALIGNMENT_OFFSET", "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"}
    ]
    if not targeted:
        return {"decision": "inconclusive", "reason": "no G3-G6 template collapse comparisons"}
    reduction_min = min(item.get("relative_error_reduction", 0.0) for item in targeted)
    return {
        "decision": "pass" if reduction_min >= reduction_threshold else "fail",
        "relative_error_reduction_min": reduction_min,
        "threshold": reduction_threshold,
    }

