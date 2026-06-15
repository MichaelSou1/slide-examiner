from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import normalize_examiner_output


@dataclass(frozen=True)
class HybridEvaluation:
    score: float
    feedback: str
    details: dict[str, Any]


def evaluate_hybrid_feedback(
    *,
    linter_score: float,
    examiner_output: dict[str, Any],
    linter_weight: float = 0.6,
) -> HybridEvaluation:
    examiner = normalize_examiner_output(examiner_output)
    examiner_score = float(examiner.get("overall_score", 1.0))
    weight = min(1.0, max(0.0, linter_weight))
    score = weight * float(linter_score) + (1.0 - weight) * examiner_score
    defects = [item for item in examiner["defects"] if item.get("present", True)]

    if defects:
        lines = ["Examiner ASI:"]
        for defect in defects:
            ids = ", ".join(defect.get("element_ids", [])) or "unknown element"
            fix = defect.get("fix") or "revise the affected slide region"
            lines.append(f"- {defect['type']} on {ids}: {fix}")
    else:
        lines = ["Examiner ASI: no visual or semantic defects reported."]

    lines.append(f"Linter score: {linter_score:.3f}; examiner score: {examiner_score:.3f}.")
    return HybridEvaluation(
        score=max(0.0, min(1.0, score)),
        feedback="\n".join(lines),
        details={"linter_score": linter_score, "examiner_score": examiner_score, "defect_count": len(defects)},
    )


def make_gepa_metric(linter_fn, examiner_fn):
    """Return a small callable compatible with GEPA-like evaluator hooks."""

    def metric(candidate) -> dict[str, Any]:
        evaluation = evaluate_hybrid_feedback(
            linter_score=float(linter_fn(candidate)),
            examiner_output=examiner_fn(candidate),
        )
        return {"score": evaluation.score, "feedback": evaluation.feedback, "details": evaluation.details}

    return metric

