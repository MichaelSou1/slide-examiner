import json

from slide_examiner.generator import (
    DEFAULT_PROMPT_MODULES,
    GeneratorConfig,
    build_generation_messages,
    deck_from_content_json,
    generate_deck,
)


def _fake_complete(content: dict):
    def complete(messages):
        return json.dumps(content)

    return complete


def test_generation_messages_include_skill_modules() -> None:
    msgs = build_generation_messages({"task_id": "t1", "brief": "make a launch deck"}, DEFAULT_PROMPT_MODULES)
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    assert "make a launch deck" in user
    # the editable surface is present in the prompt
    for header in ("scenario_classifier", "page_type_instructions", "component_library", "quality_checklist"):
        assert header in user


def test_deck_from_content_json_additive_figures_and_terms() -> None:
    deck = deck_from_content_json(
        {
            "deck_id": "d",
            "slides": [
                {
                    "title": "T",
                    "bullets": ["a", "b"],
                    "figures": [{"kind": "trend_up", "claim": "revenue rose 12%"}],
                    "key_terms": ["Kubernetes"],
                }
            ],
        }
    )
    slide = deck.slides[0]
    figs = [e for e in slide.elements if e.type == "figure"]
    assert len(figs) == 1 and figs[0].text == "revenue rose 12%"
    assert figs[0].metadata["kind"] == "trend_up"
    assert slide.metadata["key_terms"] == ["Kubernetes"]
    # title + bullets skeleton still intact
    assert any(e.type == "title" for e in slide.elements)
    assert sum(1 for e in slide.elements if e.type == "text") == 2


def test_generate_deck_happy_path_no_render() -> None:
    content = {"deck_id": "gd", "scenario": "launch", "slides": [{"title": "Hi", "bullets": ["x", "y"]}]}
    art = generate_deck(
        {"task_id": "gd", "brief": "b"},
        DEFAULT_PROMPT_MODULES,
        GeneratorConfig(),
        out_dir="/tmp/test_p3_gen",
        seed=1,
        complete=_fake_complete(content),
        render=False,
    )
    assert not art.degenerate
    assert len(art.deck.slides) == 1
    assert art.content_json["deck_id"] == "gd"


def test_generate_deck_degenerate_on_bad_json() -> None:
    art = generate_deck(
        {"task_id": "bad", "brief": "b"},
        DEFAULT_PROMPT_MODULES,
        GeneratorConfig(),
        out_dir="/tmp/test_p3_gen_bad",
        complete=lambda messages: "not json at all",
        render=False,
    )
    assert art.degenerate
    assert len(art.deck.slides) == 0


def test_generate_deck_respects_max_slides() -> None:
    content = {"deck_id": "gd", "slides": [{"title": f"S{i}", "bullets": ["x"]} for i in range(20)]}
    cfg = GeneratorConfig(max_slides=5)
    art = generate_deck(
        {"task_id": "gd"}, DEFAULT_PROMPT_MODULES, cfg, out_dir="/tmp/test_p3_gen_cap", complete=_fake_complete(content), render=False
    )
    assert len(art.deck.slides) == 5
