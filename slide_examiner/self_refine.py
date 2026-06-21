"""P10 — self-refine downstream vehicle (Part 3's downgraded PRIMARY evidence).

The simplest, dependency-free way to ask "does a better examiner help the agent
improve its output more?": plug each ``FeedbackSource`` (the IV) into a
generate→critique→revise loop and watch the deck's INDEPENDENT common-quality
(``part3_quality``) over refinement iterations.

    deck_0 = generate(brief, skill)
    for it in 1..N:
        critique = examiner.score(deck_{it-1})        # the IV
        deck_it  = generate(brief, skill, revise=critique)
    measure: quality vs iteration, gain, iters-to-threshold

No GEPA/SkillOpt — only ``generator.generate_deck`` + ``feedback_sources`` +
``part3_quality``. This is the EvoPresent-style self-refine loop, used here as a
controlled MEASUREMENT (examiner-quality gradient), reported as a baseline-style
vehicle (not a headline). The model edits THIS deck (no proxy saturation, no
running-best-over-rollouts artifact), so it is the cleanest test of whether
examiner critique quality transfers to refinement gain.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .feedback_sources import FeedbackSource
from .generator import GeneratorConfig, generate_deck
from .part3_quality import deck_quality


def _revision_prompt(prev_raw: str, critique: str) -> str:
    return (
        "## Your previous deck (JSON)\n"
        f"{(prev_raw or '')[:4000]}\n\n"
        "## Critique of that deck\n"
        f"{(critique or '').strip()}\n\n"
        "Revise into an improved, COMPLETE deck JSON that fixes the critique while "
        "keeping what already worked. Output ONLY the JSON object."
    )


def run_self_refine(
    task: dict[str, Any],
    modules,
    gen_config: GeneratorConfig,
    feedback: FeedbackSource,
    *,
    n_iters: int = 4,
    complete: Callable[[list[dict[str, str]]], str] | None = None,
    render: bool = False,
    quality_fn: Callable[[Any, dict[str, Any]], tuple[float, dict[str, Any]]] = deck_quality,
    out_dir: str | Path = "runs/part3/self_refine",
    seed: int = 0,
) -> list[dict[str, Any]]:
    """One self-refine trajectory for a single task. Returns per-iteration records
    ``{iter, quality, selection_score, degenerate, n_slides}`` (iter 0 = the
    initial deck before any critique)."""
    out = Path(out_dir)
    history: list[dict[str, Any]] = []
    prev_raw: str | None = None
    critique: str | None = None
    for it in range(n_iters):
        revise = _revision_prompt(prev_raw, critique) if (critique and prev_raw) else None
        art = generate_deck(
            task, modules, gen_config, out_dir=out / f"iter{it}", seed=seed,
            complete=complete, render=render, revise=revise,
        )
        fb = feedback.score(art, task)
        quality, _ = quality_fn(art, task)
        history.append({
            "iter": it,
            "quality": float(quality),
            "selection_score": float(fb.selection_score),
            "degenerate": bool(art.degenerate),
            "n_slides": len(art.deck.slides),
        })
        prev_raw = art.raw_completion
        critique = fb.reflection_text
    return history


def refinement_summary(history: list[dict[str, Any]], q_threshold: float = 0.85) -> dict[str, Any]:
    """Per-trajectory DV: initial/final/best quality, gain, and iters-to-threshold."""
    qs = [h["quality"] for h in history]
    if not qs:
        return {"initial": None, "final": None, "best": None, "gain": None, "iters_to_threshold": None}
    iters_to_threshold = next((h["iter"] for h in history if h["quality"] >= q_threshold), None)
    return {
        "initial": round(qs[0], 4),
        "final": round(qs[-1], 4),
        "best": round(max(qs), 4),
        "gain": round(qs[-1] - qs[0], 4),          # refinement gain (what the examiner bought)
        "best_gain": round(max(qs) - qs[0], 4),
        "iters_to_threshold": iters_to_threshold,   # None = never reached
        "n_iters": len(qs),
        "quality_curve": [round(q, 4) for q in qs],
    }
