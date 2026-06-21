"""Part 3 — independent, fully-verifiable deck quality (the convergence DV + gold).

The optimizer carriers maximize their *feedback source's* ``selection_score`` (a
condition-specific proxy — geometry-only for the linter, semantic for the
examiners). To compare conditions fairly, convergence is measured against a
SINGLE quality function that is identical across conditions and never used as the
optimization signal — exactly the ``达到固定质量阈值`` DV of SPEC §5.2 and the
``gold`` of the Gao 2210.10760 gold-vs-proxy audit (here gold = deterministic).

``deck_quality`` is symbolic (no model), so a condition cannot "game" it the way
it can game a learned examiner — making it the right reference both for the
convergence threshold and for detecting reward-hacking (proxy↑ while gold↛).

The five dimensions span what the four skill modules can actually move:

* **coverage**   — every required section appears (scenario_classifier / page_type)
* **count**      — slide count near the task target (page_type_instructions)
* **geometry**   — overflow/overlap clean, reusing the Part 1 linter (component_library)
* **terms**      — terminology consistent across slides (quality_checklist)
* **conciseness**— bullets/title within limits (component_library / quality_checklist)

A linter-only proxy moves geometry+terms but is blind to coverage/count/
conciseness, so it plateaus below threshold on full quality; a semantic examiner
critiques the missing dimensions — the mechanism H3 predicts (better feedback →
fewer rollouts to the same fixed quality).
"""
from __future__ import annotations

from statistics import mean
from typing import Any, TYPE_CHECKING

from .geometry import linter_score
from .term_consistency import lint_deck

if TYPE_CHECKING:  # avoid importing generator (render) at module load
    from .generator import GeneratedArtifact

#: Dimension weights (sum to 1.0). Coverage/conciseness/terms are exactly what a
#: pure geometry linter is BLIND to — that asymmetry is the H3 lever: a semantic
#: examiner can reveal them, the linter cannot. ``count`` is reported but weighted
#: 0 (the exact per-task slide target is not fairly learnable from a vague brief).
QUALITY_WEIGHTS: dict[str, float] = {
    "coverage": 0.40,
    "geometry": 0.20,
    "terms": 0.15,
    "conciseness": 0.25,
}

#: Stricter held-out variant for the gold-vs-proxy audit (weights coverage even
#: harder, so proxy-gaming that polishes geometry while ignoring structure shows
#: up as a proxy↑/gold↛ gap).
GOLD_QUALITY_WEIGHTS: dict[str, float] = {
    "coverage": 0.45,
    "geometry": 0.15,
    "terms": 0.15,
    "conciseness": 0.25,
}


def _required_sections(task: dict[str, Any]) -> list[str]:
    rubric = task.get("rubric") or {}
    req = task.get("required_sections") or rubric.get("required_sections") or []
    return [str(s).strip().lower() for s in req if str(s).strip()]


def _target_slides(task: dict[str, Any]) -> int | None:
    rubric = task.get("rubric") or {}
    t = task.get("target_slides") or rubric.get("target_slides")
    try:
        return int(t) if t else None
    except (TypeError, ValueError):
        return None


def _slide_bodies(slide) -> list:
    return [e for e in slide.elements if (e.metadata or {}).get("role") == "body"]


def _slide_title(slide):
    return next((e for e in slide.elements if (e.metadata or {}).get("role") == "title"), None)


def quality_components(artifact: "GeneratedArtifact", task: dict[str, Any], *, max_bullets: int = 6, title_max_words: int = 12) -> dict[str, float]:
    """Per-dimension scores in [0,1]; deterministic, model-free."""
    deck = artifact.deck
    if artifact.degenerate or not deck.slides:
        return {"coverage": 0.0, "count": 0.0, "geometry": 0.0, "terms": 0.0, "conciseness": 0.0, "degenerate": 1.0}

    # coverage: a required section is "present" if it appears as a slide section
    # tag OR as a substring of any title/section text (the generator may name the
    # section in the title rather than the metadata tag).
    required = _required_sections(task)
    haystacks: list[str] = []
    for s in deck.slides:
        sec = (s.metadata or {}).get("section")
        if sec:
            haystacks.append(str(sec).lower())
        title = _slide_title(s)
        if title and title.text:
            haystacks.append(title.text.lower())
    if required:
        hit = sum(1 for r in required if any(r.replace("_", " ") in h or r in h for h in haystacks))
        coverage = hit / len(required)
    else:
        coverage = 1.0

    # count: slide count near the task target
    target = _target_slides(task)
    n = len(deck.slides)
    count = 1.0 if not target else max(0.0, 1.0 - abs(n - target) / max(1, target))

    # geometry: reuse the Part 1 linter (overflow/overlap/...)
    geometry = mean(linter_score(s) for s in deck.slides)

    # terms: terminology consistency across the deck
    n_term = len(list(lint_deck(deck)))
    terms = max(0.0, 1.0 - 0.25 * n_term)

    # conciseness: bullets <= max_bullets and title <= title_max_words, per slide
    flags = []
    for s in deck.slides:
        bullets = _slide_bodies(s)
        title = _slide_title(s)
        title_ok = title is None or len((title.text or "").split()) <= title_max_words
        flags.append(1.0 if (len(bullets) <= max_bullets and title_ok) else 0.0)
    conciseness = mean(flags) if flags else 1.0

    return {
        "coverage": round(coverage, 4),
        "count": round(count, 4),
        "geometry": round(geometry, 4),
        "terms": round(terms, 4),
        "conciseness": round(conciseness, 4),
    }


def deck_quality(artifact: "GeneratedArtifact", task: dict[str, Any], *, weights: dict[str, float] | None = None) -> tuple[float, dict[str, float]]:
    """Composite verifiable quality in [0,1] + its per-dimension components."""
    comps = quality_components(artifact, task)
    if comps.get("degenerate"):
        return 0.0, comps
    w = weights or QUALITY_WEIGHTS
    score = sum(comps[k] * w[k] for k in w)
    return round(score, 4), comps


def gold_quality(artifact: "GeneratedArtifact", task: dict[str, Any]) -> tuple[float, dict[str, float]]:
    """Stricter held-out 'gold' quality for the gold-vs-proxy reward-hacking audit."""
    return deck_quality(artifact, task, weights=GOLD_QUALITY_WEIGHTS)
