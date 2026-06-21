"""Part 3 feedback sources — the single controlled independent variable.

A ``FeedbackSource`` maps a rendered deck artifact to
``(selection_score in [0,1], reflection_text)``:

* **selection_score** drives the optimizer's validation gate (SkillOpt
  ``gate_metric="soft"`` / GEPA candidate score).
* **reflection_text** is the ASI the frozen optimizer model reads to propose
  skill edits.

The five sources span an examiner-quality gradient whose *intrinsic* quality was
already measured in Parts 1/2 (recorded here, not recomputed). Everything else in
the optimization loop is held constant, so swapping the ``FeedbackSource`` is the
only manipulation. ``LinterOnlyFeedback`` is fully offline and is the CI anchor;
examiner sources need a served VLM but accept an injected ``complete`` callable
for tests.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Callable, TYPE_CHECKING

from .adapters import normalize_examiner_output, parse_examiner_json
from .examiner_contract import build_messages_from_sample
from .geometry import lint_slide, linter_score
from .term_consistency import lint_deck

if TYPE_CHECKING:  # avoid importing render (playwright) at module load for type hints
    from .generator import GeneratedArtifact

#: Canonical condition keys (also used by gepa_runner + synthesis); ordered by
#: increasing examiner quality. "hybrid" is the decoupled architecture.
FEEDBACK_SOURCE_ORDER: tuple[str, ...] = (
    "linter",
    "zero_shot_8b",
    "zero_shot_30b",
    "finetuned_8b",
    "hybrid",
)

#: Intrinsic feedback quality from frozen Part 1/2 metrics (the H3 x-axis).
#: ``part3_feedback_iv.py`` refines these from the summary JSONs when present.
DEFAULT_INTRINSIC_QUALITY: dict[str, dict[str, float]] = {
    "linter": {"geometry_bal_acc": 1.0},  # verifiable, ~1.0 recall / 0 FP (Part 1 linter track)
    "zero_shot_8b": {"semantic_bal_acc": 0.64},  # Part 2 Table 1
    "zero_shot_30b": {"semantic_bal_acc": 0.785},
    "finetuned_8b": {"semantic_bal_acc": 0.99},
    "hybrid": {"gate_bal_acc": 1.0, "reflection_bal_acc": 0.99},
}

_SCOPE_SUFFIX = (
    'Return ONLY a JSON object: {"page_id": str, "has_defect": bool, "findings": '
    '[{"type": str, "severity": "minor"|"moderate"|"severe", "locator": '
    '{"element_id": str}, "evidence": str, "fix_suggestion": str}]}. '
    "Report a defect only if clearly visible."
)


@dataclass(frozen=True)
class FeedbackResult:
    selection_score: float
    reflection_text: str
    details: dict[str, Any] = field(default_factory=dict)


class FeedbackSource(ABC):
    name: str
    intrinsic_quality: dict[str, float]

    @abstractmethod
    def score(self, artifact: "GeneratedArtifact", task: dict[str, Any]) -> FeedbackResult: ...


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _slide_record(slide, image_path: str | None, render_spec: dict | None) -> dict[str, Any]:
    rec: dict[str, Any] = {"sample_id": slide.slide_id, "slide": slide.to_dict(), "labels": [], "metadata": {}}
    if image_path:
        rec["image_path"] = str(image_path)
    if render_spec:
        rec["metadata"]["render"] = render_spec
    return rec


def _modality_for(image_path: str | None) -> str:
    return "C" if image_path else "B"


def _linter_reflection(geo_defects: list, term_defects: list) -> str:
    items = list(geo_defects) + list(term_defects)
    if not items:
        return "Linter: no verifiable geometry or terminology violations."
    lines = ["Linter verifiable violations:"]
    for d in items[:20]:
        meta = d.metadata or {}
        metric = next((f"{k}={v:.1f}" for k, v in meta.items() if isinstance(v, (int, float))), "")
        ids = ", ".join(d.target_element_ids) or "?"
        lines.append(f"- {d.type} @ {ids} {metric}".rstrip())
    return "\n".join(lines)


def _examiner_reflection(defects: list[dict[str, Any]]) -> str:
    present = [d for d in defects if d.get("present", True)]
    if not present:
        return "Examiner: no visual or semantic defects detected; deck reads clean."
    lines = ["Examiner critique:"]
    for d in present[:12]:
        ids = ", ".join(d.get("element_ids") or []) or "unknown element"
        ev = (d.get("evidence") or "").strip()
        fix = (d.get("fix") or "revise the affected region").strip()
        lines.append(f"- {d['type']} @ {ids}: {ev} -> {fix}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 1. linter-only (offline anchor; verifiable selection, minimal reflection)
# --------------------------------------------------------------------------- #
class LinterOnlyFeedback(FeedbackSource):
    name = "linter"

    def __init__(self, *, intrinsic_quality: dict[str, float] | None = None) -> None:
        self.intrinsic_quality = intrinsic_quality or DEFAULT_INTRINSIC_QUALITY["linter"]

    def score(self, artifact: "GeneratedArtifact", task: dict[str, Any]) -> FeedbackResult:
        deck = artifact.deck
        if artifact.degenerate or not deck.slides:
            return FeedbackResult(0.0, "Linter: generation failed (empty deck).", {"degenerate": True})
        slide_scores = [linter_score(s) for s in deck.slides]
        geo_defects = [d for s in deck.slides for d in lint_slide(s)]
        term_defects = list(lint_deck(deck))
        geo = mean(slide_scores) if slide_scores else 0.0
        deck_penalty = min(0.5, 0.1 * len(term_defects))
        selection = max(0.0, min(1.0, geo - deck_penalty))
        return FeedbackResult(
            selection_score=selection,
            reflection_text=_linter_reflection(geo_defects, term_defects),
            details={
                "n_geometry_defects": len(geo_defects),
                "n_term_defects": len(term_defects),
                "mean_slide_linter_score": geo,
                "linter_score": selection,
            },
        )


# --------------------------------------------------------------------------- #
# 2-4. examiner sources (zero-shot 8B / 30B, finetuned 8B)
# --------------------------------------------------------------------------- #
class ExaminerFeedback(FeedbackSource):
    """Page-level VLM examiner over the rendered deck.

    ``complete`` is ``Callable[[list[message]], str]`` returning the model's raw
    JSON text (mirrors the Part 2 eval ``call`` helper). ``prompt_style`` follows
    Part 2 Table 6: ``trained`` (bare contract) for the finetuned model, ``scoped``
    (schema suffix) for zero-shot models.
    """

    def __init__(
        self,
        name: str,
        complete: Callable[[list[dict[str, Any]]], str],
        *,
        intrinsic_quality: dict[str, float] | None = None,
        prompt_style: str = "trained",
        retries: int = 1,
    ) -> None:
        self.name = name
        self._complete = complete
        self.intrinsic_quality = intrinsic_quality or DEFAULT_INTRINSIC_QUALITY.get(name, {})
        self.prompt_style = prompt_style
        self.retries = retries

    def _probe_slide(self, slide, image_path, render_spec) -> dict[str, Any]:
        rec = _slide_record(slide, image_path, render_spec)
        messages = build_messages_from_sample(rec, modality=_modality_for(image_path))
        if self.prompt_style == "scoped":
            messages = [*messages, {"role": "user", "content": _SCOPE_SUFFIX}]
        raw = "{}"
        for attempt in range(self.retries + 1):
            try:
                raw = self._complete(messages)
                return normalize_examiner_output(parse_examiner_json(raw))
            except Exception:
                messages = [*messages, {"role": "user", "content": "OUTPUT VALID JSON ONLY."}]
        return normalize_examiner_output(parse_examiner_json(raw)) if raw else {"defects": [], "overall_score": 1.0}

    def score(self, artifact: "GeneratedArtifact", task: dict[str, Any]) -> FeedbackResult:
        deck = artifact.deck
        if artifact.degenerate or not deck.slides:
            return FeedbackResult(0.0, "Examiner: generation failed (empty deck).", {"degenerate": True})
        images = artifact.page_image_paths or [None] * len(deck.slides)
        specs = artifact.render_specs or [None] * len(deck.slides)
        per_slide_scores: list[float] = []
        defects_all: list[dict[str, Any]] = []
        for slide, img, spec in zip(deck.slides, images, specs):
            norm = self._probe_slide(slide, str(img) if img else None, spec)
            per_slide_scores.append(float(norm.get("overall_score", 1.0)))
            defects_all.extend(norm.get("defects", []))
        selection = mean(per_slide_scores) if per_slide_scores else 0.0
        return FeedbackResult(
            selection_score=max(0.0, min(1.0, selection)),
            reflection_text=_examiner_reflection(defects_all),
            details={"n_defects": len([d for d in defects_all if d.get("present", True)]), "examiner_score": selection},
        )


# --------------------------------------------------------------------------- #
# 5. hybrid decoupled (linter = selection gate, examiner = reflection ASI)
# --------------------------------------------------------------------------- #
class HybridDecoupledFeedback(FeedbackSource):
    name = "hybrid"

    def __init__(
        self,
        linter: LinterOnlyFeedback,
        examiner: ExaminerFeedback,
        *,
        intrinsic_quality: dict[str, float] | None = None,
    ) -> None:
        self.linter = linter
        self.examiner = examiner
        self.intrinsic_quality = intrinsic_quality or DEFAULT_INTRINSIC_QUALITY["hybrid"]

    def score(self, artifact: "GeneratedArtifact", task: dict[str, Any]) -> FeedbackResult:
        gate = self.linter.score(artifact, task)  # verifiable selection gate
        critique = self.examiner.score(artifact, task)  # learned reflection ASI
        # Equivalent to evaluate_hybrid_feedback(linter_weight=1.0): selection is
        # the verifiable linter; the ASI is the learned examiner's critique.
        return FeedbackResult(
            selection_score=gate.selection_score,
            reflection_text=critique.reflection_text,
            details={
                "linter": gate.details,
                "examiner_score": critique.details.get("examiner_score"),
                "gate_score": gate.selection_score,
            },
        )


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def build_feedback_source(
    condition: str,
    *,
    examiner_complete: Callable[[list[dict[str, Any]]], str] | None = None,
    intrinsic_quality: dict[str, dict[str, float]] | None = None,
) -> FeedbackSource:
    """Construct a feedback source by condition key.

    ``examiner_complete`` is required for every condition except ``linter``; it is
    the raw text-completion callable for the served examiner VLM (built from a
    vLLM endpoint in production, or a fake in tests).
    """

    iq = intrinsic_quality or DEFAULT_INTRINSIC_QUALITY
    if condition == "linter":
        return LinterOnlyFeedback(intrinsic_quality=iq.get("linter"))
    if condition in {"zero_shot_8b", "zero_shot_30b"}:
        if examiner_complete is None:
            raise ValueError(f"{condition} requires examiner_complete")
        return ExaminerFeedback(condition, examiner_complete, intrinsic_quality=iq.get(condition), prompt_style="scoped")
    if condition == "finetuned_8b":
        if examiner_complete is None:
            raise ValueError("finetuned_8b requires examiner_complete")
        return ExaminerFeedback("finetuned_8b", examiner_complete, intrinsic_quality=iq.get("finetuned_8b"), prompt_style="trained")
    if condition == "hybrid":
        if examiner_complete is None:
            raise ValueError("hybrid requires examiner_complete (for the ft-8B reflection arm)")
        linter = LinterOnlyFeedback(intrinsic_quality=iq.get("linter"))
        examiner = ExaminerFeedback("finetuned_8b", examiner_complete, intrinsic_quality=iq.get("finetuned_8b"), prompt_style="trained")
        return HybridDecoupledFeedback(linter, examiner, intrinsic_quality=iq.get("hybrid"))
    raise ValueError(f"unknown feedback condition: {condition!r}")
