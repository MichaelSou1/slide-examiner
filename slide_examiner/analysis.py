from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .adapters import normalize_examiner_output
from .examiner_contract import Modality, normalize_modality
from .statistics import variance_gated_effect


@dataclass(frozen=True)
class Classification:
    sample_id: str
    model: str | None
    modality: str
    task: str
    expected_types: tuple[str, ...]
    predicted_types: tuple[str, ...]
    correct: bool
    severity: float | None = None
    severity_grid_value: float | None = None
    template_condition: str | None = None
    resolution: int | None = None


def summarize_probe_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [classify_probe_record(record) for record in records]
    return {
        "record_count": len(rows),
        "metrics": aggregate_metrics(rows),
        "attribution": attribute_failures(rows, repair_outcomes=_repair_outcomes(records)),
        "oracle_gaps": modality_accuracy_gaps(rows, left_modality="A", right_modality="B"),
        "caption_oracle_gaps": modality_accuracy_gaps(
            rows,
            left_modality=Modality.B_CAPTION_ONLY.value,
            right_modality=Modality.B_STRUCT_ONLY.value,
        ),
        "template_collapse": template_collapse(rows),
        "variance_gates": variance_gates(rows),
        "psychometric_thresholds": psychometric_thresholds(rows),
        "repair_pass_rates": repair_pass_rates(records),
    }


def classify_probe_record(record: dict[str, Any]) -> Classification:
    labels = _record_labels(record)
    expected_types = tuple(label["type"] for label in labels if label.get("type") and label.get("type") != "NO_DEFECT")
    predicted_types = _predicted_types(record)
    correct = _is_correct(expected_types, predicted_types)
    return Classification(
        sample_id=str(record.get("sample_id", record.get("payload", {}).get("sample_id", ""))),
        model=_record_model(record),
        modality=_record_modality(record),
        task=str(record.get("task", record.get("payload", {}).get("task", ""))),
        expected_types=expected_types,
        predicted_types=predicted_types,
        correct=correct,
        severity=_record_severity(record, labels),
        severity_grid_value=_record_severity_grid_value(record, labels),
        template_condition=_record_template_condition(record),
        resolution=_record_resolution(record),
    )


def aggregate_metrics(rows: Iterable[Classification]) -> list[dict[str, Any]]:
    groups: dict[tuple[str | None, str, str, str, str | None, int | None], list[Classification]] = defaultdict(list)
    # All rows in a (model, modality, task) slice, used to find off-target
    # (false-positive) predictions for any given defect type, including rows
    # that truly carry a different defect or no defect at all.
    slices: dict[tuple[str | None, str, str], list[Classification]] = defaultdict(list)
    for row in rows:
        slices[(row.model, row.modality, row.task)].append(row)
        defect_types = row.expected_types or ("NO_DEFECT",)
        for defect_type in defect_types:
            groups[(row.model, row.modality, row.task, defect_type, row.template_condition, row.resolution)].append(row)

    metrics = []
    for (model, modality, task, defect_type, template_condition, resolution), group in sorted(
        groups.items(), key=lambda item: _sort_key(item[0])
    ):
        correct = sum(row.correct for row in group)
        if defect_type == "NO_DEFECT":
            # Keep the historical negative-class bookkeeping for NO_DEFECT cells.
            true_positive = 0
            false_negative = 0
            false_positive = sum(bool(row.predicted_types) for row in group)
            precision = _safe_div(true_positive, true_positive + false_positive)
            recall = _safe_div(true_positive, true_positive + false_negative)
        else:
            # TP/FN come from rows that truly carry this defect (the group).
            true_positive = sum(defect_type in row.predicted_types for row in group)
            false_negative = sum(defect_type not in row.predicted_types for row in group)
            # FP = predictions of this defect on rows whose GROUND TRUTH does not
            # include it, drawn from the whole (model, modality, task) slice so
            # that clean and differently-defective slides both penalize precision.
            false_positive = sum(
                defect_type in row.predicted_types and defect_type not in row.expected_types
                for row in slices[(model, modality, task)]
            )
            precision = _safe_div(true_positive, true_positive + false_positive)
            recall = _safe_div(true_positive, true_positive + false_negative)
        metrics.append(
            {
                "model": model,
                "modality": modality,
                "task": task,
                "defect_type": defect_type,
                "template_condition": template_condition,
                "resolution": resolution,
                # "n" counts rows truly having this defect (NO_DEFECT rows for the
                # NO_DEFECT cell); FP is sourced from the wider slice, not "n".
                "n": len(group),
                "accuracy": correct / len(group),
                "precision": precision,
                "recall": recall,
                "f1": _safe_div(2 * precision * recall, precision + recall),
            }
        )
    return metrics


def attribute_failures(
    rows: Iterable[Classification],
    *,
    task: str = "T1",
    repair_outcomes: dict[tuple[str | None, str, str], bool] | None = None,
) -> list[dict[str, Any]]:
    by_sample: dict[tuple[str | None, str], dict[str, Classification]] = defaultdict(dict)
    for row in rows:
        if row.task == task and row.modality in {"A", "B"}:
            by_sample[(row.model, row.sample_id)][row.modality] = row

    repair_outcomes = repair_outcomes or {}
    counts: dict[tuple[str | None, str, str | None], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for sample_rows in by_sample.values():
        if "A" not in sample_rows or "B" not in sample_rows:
            continue
        a_row = sample_rows["A"]
        b_row = sample_rows["B"]
        defect_type = a_row.expected_types[0] if a_row.expected_types else "NO_DEFECT"
        key = (a_row.model, defect_type, a_row.template_condition)
        if not a_row.correct and b_row.correct:
            counts[key]["perception_bottleneck"] += 1
        elif not a_row.correct and not b_row.correct:
            counts[key]["reasoning_bottleneck"] += 1
        elif a_row.correct:
            counts[key]["image_success"] += 1
        # Execution bottleneck: the model sees the defect on the image (T1/A
        # correct) but the corresponding modality-A T3 repair failed. Only
        # counted when a T3 repair_passed outcome is available for this sample.
        if a_row.correct:
            repair_passed = repair_outcomes.get((a_row.model, a_row.sample_id, "A"))
            if repair_passed is False:
                counts[key]["execution_bottleneck"] += 1
        counts[key]["n"] += 1

    summaries = []
    for (model, defect_type, template_condition), values in sorted(counts.items(), key=lambda item: _sort_key(item[0])):
        n = values["n"]
        summaries.append(
            {
                "task": task,
                "model": model,
                "defect_type": defect_type,
                "template_condition": template_condition,
                "n": n,
                "perception_bottleneck_rate": _safe_div(values["perception_bottleneck"], n),
                "reasoning_bottleneck_rate": _safe_div(values["reasoning_bottleneck"], n),
                "execution_bottleneck_rate": _safe_div(values["execution_bottleneck"], n),
                "image_success_rate": _safe_div(values["image_success"], n),
                "counts": dict(values),
            }
        )
    return summaries


def _repair_outcomes(records: Iterable[dict[str, Any]]) -> dict[tuple[str | None, str, str], bool]:
    """Map (model, sample_id, modality) -> T3 repair_passed for repair records."""
    outcomes: dict[tuple[str | None, str, str], bool] = {}
    for record in records:
        task = str(record.get("task", record.get("payload", {}).get("task", "")))
        if task != "T3" or "repair_passed" not in record:
            continue
        sample = str(record.get("sample_id", record.get("payload", {}).get("sample_id", "")))
        modality = str(record.get("modality", record.get("payload", {}).get("modality", "")))
        outcomes[(_record_model(record), sample, modality)] = bool(record["repair_passed"])
    return outcomes


def modality_accuracy_gaps(
    rows: Iterable[Classification],
    *,
    left_modality: str,
    right_modality: str,
    task: str = "T1",
) -> list[dict[str, Any]]:
    left_modality = _normalize_modality_name(left_modality)
    right_modality = _normalize_modality_name(right_modality)
    grouped: dict[tuple[str | None, str, str | None], dict[str, list[Classification]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.task != task or row.modality not in {left_modality, right_modality}:
            continue
        defect_type = row.expected_types[0] if row.expected_types else "NO_DEFECT"
        grouped[(row.model, defect_type, row.template_condition)][row.modality].append(row)

    gaps = []
    for (model, defect_type, template_condition), modalities in sorted(grouped.items(), key=lambda item: _sort_key(item[0])):
        left_rows = modalities.get(left_modality, [])
        right_rows = modalities.get(right_modality, [])
        if not left_rows or not right_rows:
            continue
        left_accuracy = sum(row.correct for row in left_rows) / len(left_rows)
        right_accuracy = sum(row.correct for row in right_rows) / len(right_rows)
        gaps.append(
            {
                "task": task,
                "model": model,
                "defect_type": defect_type,
                "template_condition": template_condition,
                "left_modality": left_modality,
                "right_modality": right_modality,
                "left_accuracy": left_accuracy,
                "right_accuracy": right_accuracy,
                "gap": right_accuracy - left_accuracy,
                "left_n": len(left_rows),
                "right_n": len(right_rows),
            }
        )
    return gaps


def template_collapse(rows: Iterable[Classification], *, template_name: str = "template", freeform_name: str = "freeform") -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str, str, str], dict[str, list[Classification]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        defect_type = row.expected_types[0] if row.expected_types else "NO_DEFECT"
        condition = row.template_condition
        if condition in {template_name, freeform_name}:
            grouped[(row.model, row.modality, row.task, defect_type)][condition].append(row)

    summaries = []
    for (model, modality, task, defect_type), conditions in sorted(grouped.items(), key=lambda item: _sort_key(item[0])):
        freeform_rows = conditions.get(freeform_name, [])
        template_rows = conditions.get(template_name, [])
        if not freeform_rows or not template_rows:
            continue
        freeform_error = 1.0 - sum(row.correct for row in freeform_rows) / len(freeform_rows)
        template_error = 1.0 - sum(row.correct for row in template_rows) / len(template_rows)
        summaries.append(
            {
                "model": model,
                "modality": modality,
                "task": task,
                "defect_type": defect_type,
                "freeform_error": freeform_error,
                "template_error": template_error,
                "absolute_error_reduction": freeform_error - template_error,
                "relative_error_reduction": _safe_div(freeform_error - template_error, freeform_error),
                "freeform_n": len(freeform_rows),
                "template_n": len(template_rows),
            }
        )
    return summaries


def variance_gates(rows: Iterable[Classification]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str, str, str | None], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.modality not in {"A", "B"}:
            continue
        defect_type = row.expected_types[0] if row.expected_types else "NO_DEFECT"
        grouped[(row.model, row.task, defect_type, row.template_condition)][row.modality].append(float(row.correct))

    gates = []
    for (model, task, defect_type, template_condition), values in sorted(grouped.items(), key=lambda item: _sort_key(item[0])):
        if not values.get("A") or not values.get("B"):
            continue
        gate = variance_gated_effect(values["A"], values["B"])
        gates.append(
            {
                "model": model,
                "task": task,
                "defect_type": defect_type,
                "template_condition": template_condition,
                "comparison": "B_minus_A_accuracy",
                "effect": gate.effect,
                "sigma": gate.sigma,
                "threshold": gate.threshold,
                "decision": gate.decision,
            }
        )
    return gates


def psychometric_thresholds(rows: Iterable[Classification], *, target_rate: float = 0.5) -> list[dict[str, Any]]:
    groups: dict[tuple[str | None, str, str, str | None], dict[float, list[Classification]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        # Bin by the nominal severity-grid value so that defects whose realized
        # label is a near-unique float (e.g. G2 IoU) collapse into shared buckets.
        bin_value = row.severity_grid_value if row.severity_grid_value is not None else row.severity
        if bin_value is None or not row.expected_types:
            continue
        for defect_type in row.expected_types:
            groups[(row.model, row.modality, row.task, defect_type)][bin_value].append(row)

    thresholds = []
    for (model, modality, task, defect_type), by_severity in sorted(groups.items(), key=lambda item: _sort_key(item[0])):
        threshold = None
        points = []
        for severity in sorted(by_severity):
            group = by_severity[severity]
            detection_rate = sum(defect_type in row.predicted_types for row in group) / len(group)
            realized = [row.severity for row in group if row.severity is not None]
            mean_realized = sum(realized) / len(realized) if realized else None
            points.append(
                {
                    "severity": severity,
                    "realized_severity": mean_realized,
                    "n": len(group),
                    "detection_rate": detection_rate,
                }
            )
            if threshold is None and detection_rate >= target_rate:
                threshold = severity
        thresholds.append(
            {
                "model": model,
                "modality": modality,
                "task": task,
                "defect_type": defect_type,
                "target_rate": target_rate,
                "threshold": threshold,
                "points": points,
            }
        )
    return thresholds


def repair_pass_rates(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str, str | None], list[bool]] = defaultdict(list)
    for record in records:
        task = str(record.get("task", record.get("payload", {}).get("task", "")))
        if task != "T3" or "repair_passed" not in record:
            continue
        labels = _record_labels(record)
        active_labels = [label for label in labels if label.get("type") != "NO_DEFECT"]
        defect_type = active_labels[0]["type"] if active_labels else "NO_DEFECT"
        model = _record_model(record)
        template_condition = _record_template_condition(record)
        grouped[(model, defect_type, template_condition)].append(bool(record["repair_passed"]))
    return [
        {
            "model": model,
            "defect_type": defect_type,
            "template_condition": template_condition,
            "n": len(values),
            "repair_pass_rate": sum(values) / len(values),
        }
        for (model, defect_type, template_condition), values in sorted(grouped.items(), key=lambda item: _sort_key(item[0]))
    ]


def _record_labels(record: dict[str, Any]) -> list[dict[str, Any]]:
    labels = record.get("labels")
    if labels is None:
        labels = record.get("payload", {}).get("expected_labels")
    if labels is None and "label_types" in record:
        labels = [{"type": label_type} for label_type in record["label_types"]]
    return list(labels or [])


def _record_model(record: dict[str, Any]) -> str | None:
    for key in ("model", "adapter"):
        if record.get(key) is not None:
            return str(record[key])
    payload = record.get("payload", {})
    if isinstance(payload, dict) and payload.get("model") is not None:
        return str(payload["model"])
    return None


def _record_modality(record: dict[str, Any]) -> str:
    value = record.get("modality", record.get("payload", {}).get("modality", ""))
    return _normalize_modality_name(str(value))


def _normalize_modality_name(value: str) -> str:
    try:
        return normalize_modality(value).value
    except ValueError:
        return value


def _predicted_types(record: dict[str, Any]) -> tuple[str, ...]:
    output = record.get("output")
    if output is None:
        output = record.get("parsed")
    if output is None:
        return ()
    normalized = normalize_examiner_output(output)
    return tuple(
        defect["type"]
        for defect in normalized["defects"]
        if defect.get("present", True) and defect.get("type") != "UNKNOWN"
    )


def _record_severity(record: dict[str, Any], labels: list[dict[str, Any]]) -> float | None:
    if "severity" in record and record["severity"] is not None:
        return float(record["severity"])
    for label in labels:
        if "severity" in label:
            return float(label["severity"])
    return None


def _record_severity_grid_value(record: dict[str, Any], labels: list[dict[str, Any]]) -> float | None:
    """Nominal severity-grid value used for psychometric binning.

    Prefer the nominal grid value stored on sample metadata; fall back to the
    realized/label severity when the grid value is absent so behavior is
    unchanged for records that lack the metadata.
    """
    for container in (record, record.get("metadata", {}), record.get("payload", {}).get("metadata", {})):
        if isinstance(container, dict):
            value = container.get("severity_grid_value")
            if value is not None:
                return float(value)
    return _record_severity(record, labels)


def _record_template_condition(record: dict[str, Any]) -> str | None:
    for container in (record, record.get("metadata", {}), record.get("payload", {}).get("metadata", {})):
        if isinstance(container, dict):
            value = container.get("template_condition")
            if value is not None:
                return str(value)
    return None


def _record_resolution(record: dict[str, Any]) -> int | None:
    for container in (record, record.get("metadata", {}), record.get("payload", {}).get("metadata", {})):
        if isinstance(container, dict):
            value = container.get("resolution")
            if value is not None:
                return int(value)
    return None


def _is_correct(expected_types: tuple[str, ...], predicted_types: tuple[str, ...]) -> bool:
    expected = set(expected_types)
    predicted = set(predicted_types)
    if not expected:
        return not predicted
    return expected.issubset(predicted)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _sort_key(value: tuple) -> tuple:
    return tuple("" if item is None else str(item) for item in value)
