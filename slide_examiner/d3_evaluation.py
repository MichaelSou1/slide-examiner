"""Unified row-level scoring for the frozen D3 evaluation protocol."""
from __future__ import annotations

from collections import defaultdict
import json
from math import comb
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

from .statistics import balanced_accuracy_ci, holm_bonferroni, wilson_interval


def prompt_row(row: dict[str, Any], prompt_mode: str) -> dict[str, Any]:
    """Return a detached prompt and optionally append the atomic C3 query."""
    prompted = json.loads(json.dumps(row))
    if prompt_mode == "generic":
        return prompted
    suffix = (
        "\nATOMIC_CHECK: Decide specifically whether the visible artifact exhibits "
        f"{row['defect']}. Localize concrete visible evidence if present, but still return the "
        "exact examiner JSON contract and request context or defer when evidence is insufficient."
    )
    for item in reversed(prompted["messages"][0]["content"]):
        if item.get("type") == "text":
            item["text"] = str(item.get("text", "")) + suffix
            break
    return prompted


def validate_deployment(run: Path | None, merged_model: Path | None,
                        lm_adapter: Path | None, route_mode: str) -> str | None:
    """Return a CLI validation error without loading any model assets."""
    if route_mode != "answer" and run is None:
        return "--run is required unless --route-mode=answer"
    if merged_model is not None and run is None:
        return "--merged-model requires --run because it only replaces the D3 language model"
    if lm_adapter is not None and run is not None:
        return "--lm-adapter is only valid for LM-only --route-mode=answer runs without --run"
    return None


def route_requires_heads(route_mode: str) -> bool:
    """Only learned sample-level routing needs a D3-head forward pass."""
    return route_mode == "sample"


def _ratio(k: int, n: int) -> float | None:
    return k / n if n else None


def _mean(values: Iterable[float | int | None]) -> float | None:
    kept = [float(value) for value in values if value is not None]
    return mean(kept) if kept else None


def finding_present(row: dict[str, Any], defect: str | None = None) -> bool:
    """Return the named prediction when available, otherwise any-finding detection."""
    predicted = set(row.get("predicted_types") or [])
    if defect is not None and predicted:
        return defect in predicted
    return bool(row.get("has_defect", bool(predicted)))


def normalize_runtime_row(row: dict[str, Any], *, arm: str | None = None) -> dict[str, Any]:
    """Convert a D3 runtime trace into the frozen row-level scoring contract."""
    escalation = row.get("escalation") or {}
    performed = bool(escalation.get("performed"))
    parsed = escalation.get("final_parsed") if performed else row.get("parsed")
    parsed = parsed or {}
    action = escalation.get("final_action") if performed else row.get("predicted_action")
    findings = parsed.get("findings") or []
    predicted_types = sorted({str(item.get("type")) for item in findings
                              if isinstance(item, dict) and item.get("type")})
    defect = str(row.get("defect") or "")
    is_clean = bool(row.get("is_clean", defect == "NO_DEFECT"))
    named = [item for item in findings if isinstance(item, dict)
             and item.get("type") == defect]
    localization_valid = any(bool((item.get("locator") or {}).get("page_id")
                                  or (item.get("locator") or {}).get("element_id")
                                  or (item.get("locator") or {}).get("related_page_ids"))
                             for item in named)
    failure = bool(row.get("failure") or row.get("consistency_error")
                   or row.get("parse_error")
                   or (((escalation.get("result") or {}).get("parse_error")) if performed else False)
                   or (escalation and not escalation.get("performed")))
    has_defect = bool(parsed.get("has_defect", predicted_types))
    correct = (not has_defect) if is_clean else defect in predicted_types
    return {
        **row,
        "arm": arm or str(row.get("arm") or "unknown"),
        "pair_id": str(row.get("pair_id") or row.get("sample_id") or row.get("record_id")),
        "is_clean": is_clean,
        "predicted_action": action,
        "deferred": action == "DEFER",
        "confidence": float(row.get("route_confidence", parsed.get("confidence", 0.0)) or 0.0),
        "predicted_types": predicted_types,
        "has_defect": has_defect,
        "localization_valid": localization_valid,
        "correct": correct,
        "failure": failure,
    }


def _class_metrics(rows: Sequence[dict[str, Any]], defect: str) -> dict[str, Any]:
    valid = [row for row in rows if not row.get("failure")]
    positives = [row for row in valid if not row.get("is_clean") and row.get("defect") == defect]
    negatives = [row for row in valid if row.get("is_clean") and row.get("defect") == defect]
    tp = sum(finding_present(row, defect) for row in positives)
    fp = sum(finding_present(row, defect) for row in negatives)
    fn, tn = len(positives) - tp, len(negatives) - fp
    recall = wilson_interval(tp, len(positives))
    specificity = wilson_interval(tn, len(negatives))
    precision = wilson_interval(tp, tp + fp)
    balanced = balanced_accuracy_ci(tp, len(positives), tn, len(negatives))
    localized = [row for row in positives if finding_present(row, defect)]
    localization_hits = sum(bool(row.get("localization_valid", row.get("named_target", False)))
                            for row in localized)
    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "n_pos": len(positives), "n_neg": len(negatives),
        "balanced_accuracy": balanced.to_dict(),
        "precision": precision.to_dict(), "recall": recall.to_dict(),
        "specificity": specificity.to_dict(),
        "paired_clean_fpr": _ratio(fp, len(negatives)),
        "named_localization": wilson_interval(localization_hits, len(localized)).to_dict(),
        "failures": sum(bool(row.get("failure")) for row in rows
                        if row.get("defect") == defect),
    }


def selective_curve(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Risk-coverage points ordered by frozen confidence, with defer as uncovered."""
    eligible = [row for row in rows if not row.get("failure")]
    ranked = sorted((row for row in eligible if not row.get("deferred")),
                    key=lambda row: float(row.get("confidence") or 0.0), reverse=True)
    points: list[dict[str, Any]] = [{"covered": 0, "coverage": 0.0, "risk": 0.0}]
    errors = 0
    for index, row in enumerate(ranked, 1):
        correct = bool(row.get("correct", finding_present(row) != bool(row.get("is_clean"))))
        errors += int(not correct)
        points.append({"covered": index, "coverage": index / len(eligible) if eligible else 0.0,
                       "risk": errors / index,
                       "confidence_threshold": float(row.get("confidence") or 0.0)})
    return points


def score_arm(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    defects = sorted({str(row["defect"]) for row in rows
                      if row.get("defect") and row.get("defect") != "NO_DEFECT"})
    per_class = {defect: _class_metrics(rows, defect) for defect in defects}
    complete = [metrics for metrics in per_class.values()
                if metrics["n_pos"] and metrics["n_neg"]]
    valid = [row for row in rows if not row.get("failure")]
    action_rows = [row for row in valid if row.get("target_action") is not None]
    deferred = sum(bool(row.get("deferred", row.get("predicted_action") == "DEFER"))
                   for row in valid)
    return {
        "records": len(rows), "valid_records": len(valid),
        "failure_rate": _ratio(len(rows) - len(valid), len(rows)),
        "per_class": per_class,
        "macro": {
            "balanced_accuracy": _mean(m["balanced_accuracy"]["estimate"] for m in complete),
            "precision": _mean(m["precision"]["estimate"] for m in complete),
            "recall": _mean(m["recall"]["estimate"] for m in complete),
            "specificity": _mean(m["specificity"]["estimate"] for m in complete),
            "paired_clean_fpr": _mean(m["paired_clean_fpr"] for m in complete),
            "named_localization": _mean(m["named_localization"]["estimate"] for m in complete),
            "classes": len(complete),
        },
        "routing_and_cost": {
            "action_accuracy": _ratio(sum(row.get("predicted_action") == row.get("target_action")
                                           for row in action_rows), len(action_rows)),
            "defer_rate": _ratio(deferred, len(valid)),
            "coverage": _ratio(len(valid) - deferred, len(valid)),
            "mean_model_calls": _mean(row.get("model_calls") for row in valid),
            "mean_external_calls": _mean(row.get("external_calls") for row in valid),
            "mean_prompt_tokens": _mean(row.get("prompt_tokens") for row in valid),
            "mean_completion_tokens": _mean(row.get("completion_tokens") for row in valid),
            "mean_total_tokens": _mean(row.get("total_tokens") for row in valid),
            "mean_latency_seconds": _mean(row.get("latency_seconds") for row in valid),
        },
        "risk_coverage": selective_curve(valid),
    }


def score_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("arm", "unknown"))].append(row)
    return {"schema_version": 1, "arms": {arm: score_arm(group)
                                           for arm, group in sorted(grouped.items())}}


def exact_mcnemar(left: Sequence[dict[str, Any]], right: Sequence[dict[str, Any]],
                  *, key: str = "pair_id") -> dict[str, Any]:
    """Two-sided exact McNemar test on aligned correctness rows."""
    a = {str(row.get(key) or row.get("sample_id")): bool(row["correct"]) for row in left
         if not row.get("failure") and "correct" in row}
    b = {str(row.get(key) or row.get("sample_id")): bool(row["correct"]) for row in right
         if not row.get("failure") and "correct" in row}
    common = sorted(a.keys() & b.keys())
    left_only = sum(a[item] and not b[item] for item in common)
    right_only = sum(not a[item] and b[item] for item in common)
    discordant = left_only + right_only
    tail = min(left_only, right_only)
    p_value = (min(1.0, 2 * sum(comb(discordant, i) for i in range(tail + 1))
                   / (2 ** discordant)) if discordant else 1.0)
    return {"pairs": len(common), "left_wins": left_only, "right_wins": right_only,
            "discordant": discordant, "p_value": p_value}


def holm_family(tests: Sequence[dict[str, Any]], alpha: float = 0.05) -> dict[str, Any]:
    correction = holm_bonferroni([float(test["p_value"]) for test in tests], alpha)
    return {"method": "Holm", "alpha": alpha, "tests": [
        {**test, "adjusted_p": correction.adjusted[index], "reject": correction.reject[index]}
        for index, test in enumerate(tests)
    ]}


def pareto_frontier(points: Sequence[dict[str, Any]], *, accuracy: str = "accuracy",
                    cost: str = "cost") -> list[dict[str, Any]]:
    """Keep points not dominated by another point with >= accuracy and <= cost."""
    return [point for point in points if not any(
        other is not point
        and float(other[accuracy]) >= float(point[accuracy])
        and float(other[cost]) <= float(point[cost])
        and (float(other[accuracy]) > float(point[accuracy])
             or float(other[cost]) < float(point[cost]))
        for other in points)]
