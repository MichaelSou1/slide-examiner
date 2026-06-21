import json

from slide_examiner.generator import DEFAULT_PROMPT_MODULES, GeneratorConfig, generate_deck
from slide_examiner.feedback_sources import (
    DEFAULT_INTRINSIC_QUALITY,
    FEEDBACK_SOURCE_ORDER,
    build_feedback_source,
)


def _artifact(content: dict, out: str):
    return generate_deck(
        {"task_id": content.get("deck_id", "gd"), "brief": "b"},
        DEFAULT_PROMPT_MODULES,
        GeneratorConfig(),
        out_dir=out,
        complete=lambda messages: json.dumps(content),
        render=False,
    )


_CLEAN = {"deck_id": "clean", "slides": [{"title": "Intro", "bullets": ["short point", "second point"]}]}


def _fake_examiner(findings):
    def complete(messages):
        return json.dumps({"page_id": "p", "has_defect": bool(findings), "findings": findings})

    return complete


def test_linter_source_offline_legal_range() -> None:
    art = _artifact(_CLEAN, "/tmp/fb_lint")
    res = build_feedback_source("linter").score(art, {})
    assert 0.0 <= res.selection_score <= 1.0
    assert res.reflection_text
    assert "n_geometry_defects" in res.details


def test_examiner_source_returns_legal_tuple() -> None:
    art = _artifact(_CLEAN, "/tmp/fb_exm")
    findings = [{"type": "S1_TITLE_BODY_MISMATCH", "severity": "moderate", "locator": {"element_id": "s1_title"}, "evidence": "x", "fix_suggestion": "y"}]
    res = build_feedback_source("finetuned_8b", examiner_complete=_fake_examiner(findings)).score(art, {})
    assert 0.0 <= res.selection_score <= 1.0
    assert res.reflection_text.startswith("Examiner")


def test_hybrid_selection_is_linter_reflection_is_examiner() -> None:
    art = _artifact(_CLEAN, "/tmp/fb_hyb")
    findings = [{"type": "G1_TEXT_OVERFLOW", "severity": "severe", "locator": {"element_id": "s1_body0"}, "evidence": "overflow", "fix_suggestion": "shorten"}]
    examiner = _fake_examiner(findings)
    linter_score = build_feedback_source("linter").score(art, {}).selection_score
    hybrid = build_feedback_source("hybrid", examiner_complete=examiner).score(art, {})
    assert abs(hybrid.selection_score - linter_score) < 1e-9  # gate is the verifiable linter
    assert hybrid.reflection_text.startswith("Examiner")  # ASI is the learned examiner


def test_degenerate_deck_scores_zero() -> None:
    bad = generate_deck(
        {"task_id": "bad"}, DEFAULT_PROMPT_MODULES, GeneratorConfig(), out_dir="/tmp/fb_bad", complete=lambda m: "nope", render=False
    )
    assert build_feedback_source("linter").score(bad, {}).selection_score == 0.0


def test_registry_covers_all_conditions_and_requires_examiner() -> None:
    assert set(FEEDBACK_SOURCE_ORDER) == set(DEFAULT_INTRINSIC_QUALITY)
    # examiner-backed conditions require a completion callable
    for cond in ("zero_shot_8b", "zero_shot_30b", "finetuned_8b", "hybrid"):
        try:
            build_feedback_source(cond)
            raised = False
        except ValueError:
            raised = True
        assert raised, f"{cond} should require examiner_complete"
    # linter needs nothing
    assert build_feedback_source("linter").name == "linter"
