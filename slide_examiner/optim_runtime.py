"""Shared rollout/scoring runtime for the Part 3 optimizer carriers.

Both SkillOpt and GEPA drive the SAME pipeline:

    task + skill modules -> generate_deck -> FeedbackSource.score
                         -> (selection_score, reflection_text)

so the ONLY thing that varies across the experiment is the ``FeedbackSource``
(the IV). The generator and the frozen reflection/optimizer LLM are identical
across all conditions and both carriers — enforced by ``OptimizerRunConfig``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api_config import Completion, build_completion
from .feedback_sources import FeedbackSource, build_feedback_source
from .generator import GeneratorConfig, generate_deck
from .io import read_jsonl
from .skill_doc import PromptModules


def load_tasks(path: str | Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def openai_text_complete(
    model: str,
    base_url: str | None,
    *,
    api_key_env: str = "OPENAI_API_KEY",
    api_style: str = "chat",
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> Completion:
    """Back-compat alias for build_completion (chat | responses selectable)."""

    return build_completion(
        model, base_url, api_key_env=api_key_env, api_style=api_style, max_tokens=max_tokens, temperature=temperature
    )


@dataclass(frozen=True)
class OptimizerRunConfig:
    condition: str  # feedback-source key (the IV)
    carrier: str  # "skillopt" | "gepa"
    train_tasks: str
    val_tasks: str
    test_tasks: str = ""
    out_root: str = "runs/part3/run"
    rollout_budget: int = 200
    seed: int = 0
    q_threshold: float = 0.8  # fixed quality threshold for convergence (pre-registered)
    level: str = "deck"  # "deck" | "page"
    # generator (frozen; only the skill doc changes) — its own API service
    gen_model: str = "qwen3.6-27b"
    gen_base_url: str | None = "http://127.0.0.1:8200/v1"
    gen_api_key_env: str = "OPENAI_API_KEY"
    gen_api_style: str = "chat"
    gen_max_tokens: int = 1024  # cap content-JSON length (throughput is the bottleneck)
    long_edge: int = 1024
    max_slides: int = 15
    render: bool = True
    # examiner feedback endpoint (the IV source VLM/LLM); None for linter condition
    examiner_model: str | None = None
    examiner_base_url: str | None = None
    examiner_max_tokens: int = 768
    # examiner may use a DIFFERENT key/style than the generator (e.g. a VLM API);
    # default to the shared api_key_env/api_style below.
    examiner_api_key_env: str | None = None
    examiner_api_style: str | None = None
    # FROZEN reflection / optimizer LLM (identical across all conditions/carriers).
    # DECOUPLED from the generator: it may be a different model/endpoint/key — the
    # experiment only requires it be frozen and identical across conditions.
    optimizer_model: str = "qwen3.6-27b"
    optimizer_base_url: str | None = "http://127.0.0.1:8200/v1"
    optimizer_api_key_env: str = "OPENAI_API_KEY"
    optimizer_api_style: str = "chat"
    optimizer_max_tokens: int = 2048
    # shared default endpoint style + key env (fallback for any role left unset)
    api_style: str = "chat"  # "chat" | "responses"
    api_key_env: str = "OPENAI_API_KEY"

    def generator_config(self) -> GeneratorConfig:
        return GeneratorConfig(
            model=self.gen_model,
            base_url=self.gen_base_url,
            api_key_env=self.gen_api_key_env,  # generator's OWN service key
            api_style=self.gen_api_style,
            max_tokens=self.gen_max_tokens,
            long_edge=self.long_edge,
            max_slides=self.max_slides,
        )

    def control_signature(self) -> dict[str, Any]:
        """Everything that MUST be identical across conditions (the controls).

        Excludes ``condition`` (the IV) and ``carrier``/``seed``. Two configs with
        equal signatures isolate the feedback source as the only manipulation.
        """
        return {
            "train_tasks": self.train_tasks,
            "val_tasks": self.val_tasks,
            "test_tasks": self.test_tasks,
            "rollout_budget": self.rollout_budget,
            "q_threshold": self.q_threshold,
            "level": self.level,
            "gen_model": self.gen_model,
            "gen_base_url": self.gen_base_url,
            "long_edge": self.long_edge,
            "max_slides": self.max_slides,
            "optimizer_model": self.optimizer_model,
            "optimizer_base_url": self.optimizer_base_url,
        }


class RolloutEngine:
    """One generation+scoring rollout; shared by both optimizer carriers."""

    def __init__(
        self,
        config: OptimizerRunConfig,
        *,
        gen_complete: Completion | None = None,
        examiner_complete: Completion | None = None,
        feedback: FeedbackSource | None = None,
        quality_fn: "Callable[[Any, dict[str, Any]], tuple[float, dict[str, Any]]] | None" = None,
    ) -> None:
        self.config = config
        self._gen_config = config.generator_config()
        self._gen_complete = gen_complete  # injected -> offline; None -> live vLLM
        if examiner_complete is None and config.examiner_model and config.condition != "linter":
            examiner_complete = build_completion(
                config.examiner_model,
                config.examiner_base_url,
                api_key_env=config.examiner_api_key_env or config.api_key_env,
                api_style=config.examiner_api_style or config.api_style,
                max_tokens=config.examiner_max_tokens,
            )
        self.feedback = feedback or build_feedback_source(config.condition, examiner_complete=examiner_complete)
        # Optional INDEPENDENT, model-free quality (SPEC §5.2 "fixed quality
        # threshold" DV + gold-vs-proxy gold). When set, convergence is measured
        # against this common gold instead of the condition-specific proxy, so the
        # five conditions are compared on the SAME yardstick. None -> fall back to
        # the proxy selection_score (keeps the offline smoke calibration intact).
        self.quality_fn = quality_fn
        self.n_rollouts = 0
        self.history: list[dict[str, Any]] = []  # per-rollout (n, score, hard, quality?) for convergence curves
        # per-CANDIDATE evaluation: (cumulative n, mean batch quality). A candidate's
        # mean val-quality is the fair convergence target — unlike running-best over
        # rollouts, it can't be satisfied by one lucky easy-task deck.
        self.batch_history: list[dict[str, Any]] = []

    def record_candidate_eval(self, qualities: "list[float | None]") -> None:
        """Record one candidate's batch (val/minibatch) eval: cumulative rollout
        count + mean common-quality. Called once per candidate by the carriers."""
        vals = [float(q) for q in qualities if q is not None]
        if vals:
            self.batch_history.append({"n": self.n_rollouts, "mean_quality": sum(vals) / len(vals)})

    def rollouts_to_threshold(self, q: float | None = None) -> int | None:
        """Rollouts until convergence — the carrier-agnostic efficiency DV.

        Prefers the **best-candidate mean common-quality** (``batch_history``): the
        first candidate eval whose running-best mean-quality >= q, as a cumulative
        rollout count. This avoids a single lucky easy-task rollout crossing the bar.
        Falls back to running-best over individual rollouts (common ``quality`` if a
        ``quality_fn`` is set, else proxy ``selection_score``) when no candidate-level
        evals were recorded. ``None`` (censored) if never reached."""
        q = self.config.q_threshold if q is None else q
        if self.batch_history:
            best = 0.0
            for b in self.batch_history:
                best = max(best, b["mean_quality"])
                if best >= q:
                    return b["n"]
            return None
        use_quality = self.quality_fn is not None and any("quality" in row for row in self.history)
        best = 0.0
        for row in self.history:
            best = max(best, row["quality"] if use_quality else row["score"])
            if best >= q:
                return row["n"]
        return None

    def best_score(self) -> float:
        """Best proxy (selection_score) reached — what the optimizer maximizes."""
        return max((row["score"] for row in self.history), default=0.0)

    def best_quality(self) -> float | None:
        """Best single-rollout common (gold) quality; None when no ``quality_fn`` set."""
        vals = [row["quality"] for row in self.history if "quality" in row]
        return max(vals) if vals else None

    def best_candidate_quality(self) -> float | None:
        """Best CANDIDATE mean common-quality reached (the convergence target)."""
        return max((b["mean_quality"] for b in self.batch_history), default=None)

    def rollout(self, modules: PromptModules, task: dict[str, Any], out_dir: str | Path, *, seed: int = 0) -> dict[str, Any]:
        artifact = generate_deck(
            task, modules, self._gen_config, out_dir=out_dir, seed=seed, complete=self._gen_complete, render=self.config.render
        )
        result = self.feedback.score(artifact, task)
        self.n_rollouts += 1
        hard = 1 if result.selection_score >= self.config.q_threshold else 0
        row: dict[str, Any] = {"n": self.n_rollouts, "score": float(result.selection_score), "hard": hard}
        quality: float | None = None
        quality_components: dict[str, Any] | None = None
        if self.quality_fn is not None:
            quality, quality_components = self.quality_fn(artifact, task)
            quality = float(quality)
            row["quality"] = quality
        self.history.append(row)
        out: dict[str, Any] = {
            "id": str(task.get("task_id") or task.get("id") or self.n_rollouts),
            "hard": hard,
            "soft": float(result.selection_score),
            "fail_reason": result.reflection_text,  # -> optimizer reflection (the ASI)
            "selection_score": float(result.selection_score),
            "reflection": result.reflection_text,
            "degenerate": artifact.degenerate,
            "n_slides": len(artifact.deck.slides),
            "details": result.details,
        }
        if quality is not None:
            out["quality"] = quality
            out["quality_components"] = quality_components
        return out
