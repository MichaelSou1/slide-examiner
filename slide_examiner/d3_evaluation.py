"""Unified row-level scoring for the frozen D3 evaluation protocol."""
from __future__ import annotations

from collections import defaultdict
import json
from math import ceil, comb
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

from .examiner_contract import (
    DECK_SCOPED_DEFECTS,
    PAGE_SCOPED_DEFECTS,
    Dimension,
    ExaminerAction,
    EvidenceSource,
    parse_deck_result,
    parse_page_result,
)
from .statistics import balanced_accuracy_ci, holm_bonferroni, wilson_interval


def _extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    return json.loads(text[start:end + 1])


def _repair_contract(payload: dict[str, Any], row: dict[str, Any] | None = None
                    ) -> dict[str, Any] | None:
    """Apply conservative, content-preserving repairs to generated JSON."""
    repaired = json.loads(json.dumps(payload))
    if repaired.get("action") not in {action.value for action in ExaminerAction}:
        repaired["action"] = ExaminerAction.ANSWER.value
    defect_class = str((row or {}).get("defect", "")).split("_", 1)[0]
    is_deck = "deck_id" in repaired or defect_class in {"S2", "S3", "S5"}
    id_key = "deck_id" if is_deck else "page_id"
    repaired.pop("page_id" if is_deck else "deck_id", None)
    repaired[id_key] = str(repaired.get(id_key)
                           or (row or {}).get("sample_id")
                           or (row or {}).get("record_id") or "unknown")
    findings = repaired.get("findings", [])
    if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
        return None
    if repaired.get("has_defect") is None:
        repaired["has_defect"] = bool(findings)
    requested = repaired.get("requested_context")
    if requested is None or requested == "":
        requested = []
    elif isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list):
        return None
    valid_sources = {source.value for source in EvidenceSource}
    repaired["requested_context"] = [str(item) for item in requested
                                     if str(item) in valid_sources]
    source = str(repaired.get("evidence_source") or "")
    if source == "image_only":
        source = EvidenceSource.PIXELS.value
    repaired["evidence_source"] = (source if source in valid_sources
                                    else EvidenceSource.PIXELS.value)
    dimensions = repaired.get("clean_dimensions")
    if not isinstance(dimensions, list):
        dimensions = []
    dimension_aliases = {
        "visible_text": "text_fit", "title_fit": "text_fit",
        "body_fit": "text_fit", "figure_fit": "text_fit",
    }
    valid_dimensions = {dimension.value for dimension in Dimension}
    normalized_dimensions = []
    for dimension in dimensions:
        normalized = dimension_aliases.get(str(dimension), str(dimension))
        if normalized in valid_dimensions and normalized not in normalized_dimensions:
            normalized_dimensions.append(normalized)
    repaired["clean_dimensions"] = normalized_dimensions
    allowed = DECK_SCOPED_DEFECTS if is_deck else PAGE_SCOPED_DEFECTS
    allowed_by_prefix = {item.value.split("_", 1)[0]: item.value for item in allowed}
    subject_id = str(repaired.get("deck_id" if is_deck else "page_id") or "unknown")
    for finding in findings:
        raw_type = str(finding.get("type", ""))
        if raw_type not in {item.value for item in allowed}:
            replacement = allowed_by_prefix.get(raw_type.split("_", 1)[0])
            if replacement is None:
                return None
            finding["type"] = replacement
        if str(finding.get("severity", "")).lower() in {"critical", "blocker"}:
            finding["severity"] = "severe"
        locator = finding.setdefault("locator", {})
        locator.setdefault("level", "deck" if is_deck else "page")
        if not is_deck:
            locator.setdefault("page_id", subject_id)
        locator.setdefault("related_page_ids", [])
        evidence = str(finding.get("evidence", "")).strip()
        visible_id = locator.get("element_id") or locator.get("page_id")
        if visible_id and str(visible_id).lower() not in evidence.lower():
            finding["evidence"] = f"Visible element {visible_id}: {evidence}"
    return repaired


def _repair_non_answer(payload: dict[str, Any], row: dict[str, Any] | None
                       ) -> dict[str, Any] | None:
    """Normalize a generated routing envelope without inventing findings."""
    action = str(payload.get("action") or "")
    if action not in {"CALL_LINTER", "REQUEST_REFERENCE", "REQUEST_DECK", "DEFER"}:
        return None
    repaired = json.loads(json.dumps(payload))
    defect_class = str((row or {}).get("defect", "")).split("_", 1)[0]
    is_deck = "deck_id" in repaired or defect_class in {"S2", "S3", "S5"}
    id_key = "deck_id" if is_deck else "page_id"
    repaired.pop("page_id" if is_deck else "deck_id", None)
    repaired[id_key] = str(repaired.get(id_key)
                           or (row or {}).get("sample_id")
                           or (row or {}).get("record_id") or "unknown")
    repaired["has_defect"] = False
    repaired["findings"] = []
    repaired["clean_dimensions"] = []
    repaired["requested_context"] = {
        "CALL_LINTER": ["structure"],
        "REQUEST_REFERENCE": ["reference"],
        "REQUEST_DECK": ["deck_context"],
    }.get(action, [])
    repaired["evidence_source"] = "none"
    return repaired


def parse_generated_contract(text: str, row: dict[str, Any] | None = None
                             ) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Parse generated examiner JSON, including legal route-only envelopes."""
    try:
        parsed = _extract_json(text)
        parser = parse_deck_result if "deck_id" in parsed else parse_page_result
        try:
            return parser(json.dumps(parsed)).model_dump(mode="json"), None, False
        except Exception as original:  # noqa: BLE001 - attempt bounded schema repair
            repaired = _repair_non_answer(parsed, row) or _repair_contract(parsed, row)
            if repaired is not None:
                parser = parse_deck_result if "deck_id" in repaired else parse_page_result
                try:
                    return parser(json.dumps(repaired)).model_dump(mode="json"), None, True
                except Exception:  # noqa: BLE001 - preserve the original useful error
                    pass
            return None, f"{type(original).__name__}: {original}", False
    except Exception as exc:  # noqa: BLE001 - parser failures are measured artifacts
        return None, f"{type(exc).__name__}: {exc}", False


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


def generated_route_action(raw_action: str, *, terminal: bool = False) -> str:
    """Preserve an LM route on pass one; stop repeated requests on a follow-up."""
    external_actions = {"CALL_LINTER", "REQUEST_REFERENCE", "REQUEST_DECK"}
    return ExaminerAction.DEFER.value if terminal and raw_action in external_actions else raw_action


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


def selective_risk_at_coverages(
    rows: Sequence[dict[str, Any]], coverages: Sequence[float] = (0.5, 0.75, 0.9),
) -> list[dict[str, Any]]:
    """Evaluate selective risk at a predeclared coverage grid without interpolation."""
    eligible = [row for row in rows if not row.get("failure")]
    ranked = sorted(
        (row for row in eligible if not row.get("deferred")),
        key=lambda row: float(row.get("confidence") or 0.0),
        reverse=True,
    )
    output = []
    for target in coverages:
        if not 0 < float(target) <= 1:
            raise ValueError(f"coverage must be in (0, 1], got {target}")
        required = ceil(float(target) * len(eligible))
        if not eligible or required > len(ranked):
            output.append({"target_coverage": float(target), "available": False,
                           "covered": len(ranked),
                           "achieved_coverage": _ratio(len(ranked), len(eligible)),
                           "risk": None, "confidence_threshold": None})
            continue
        selected = ranked[:required]
        errors = sum(not bool(row.get(
            "correct", finding_present(row) != bool(row.get("is_clean"))))
                     for row in selected)
        output.append({"target_coverage": float(target), "available": True,
                       "covered": required,
                       "achieved_coverage": required / len(eligible),
                       "risk": errors / required,
                       "confidence_threshold": float(
                           selected[-1].get("confidence") or 0.0)})
    return output


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
        "fixed_coverage_risk": selective_risk_at_coverages(valid),
    }


def score_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("arm", "unknown"))].append(row)
    return {"schema_version": 1, "arms": {arm: score_arm(group)
                                           for arm, group in sorted(grouped.items())}}


def exact_mcnemar(left: Sequence[dict[str, Any]], right: Sequence[dict[str, Any]],
                  *, key: str = "record_id") -> dict[str, Any]:
    """Two-sided exact McNemar test on aligned correctness rows."""
    def keyed(rows: Sequence[dict[str, Any]], side: str) -> dict[str, bool]:
        aligned: dict[str, bool] = {}
        for row in rows:
            if row.get("failure") or "correct" not in row:
                continue
            value = row.get(key)
            if value is None:
                raise ValueError(f"{side} row is missing McNemar key {key!r}")
            identity = str(value)
            if identity in aligned:
                raise ValueError(f"duplicate McNemar key in {side}: {identity!r}")
            aligned[identity] = bool(row["correct"])
        return aligned

    a, b = keyed(left, "left"), keyed(right, "right")
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
