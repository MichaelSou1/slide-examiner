from slide_examiner.skill_doc import (
    DEFAULT_PROMPT_MODULES,
    MODULE_FIELDS,
    PromptModules,
    components_to_modules,
    modules_to_components,
    parse_skill_doc,
    render_skill_doc,
)


def test_skill_doc_round_trip() -> None:
    md = render_skill_doc(DEFAULT_PROMPT_MODULES)
    assert parse_skill_doc(md) == DEFAULT_PROMPT_MODULES
    # all four headers present
    for name in MODULE_FIELDS:
        assert f"## {name}" in md


def test_component_dict_round_trip() -> None:
    comps = modules_to_components(DEFAULT_PROMPT_MODULES)
    assert set(comps) == set(MODULE_FIELDS)
    assert components_to_modules(comps) == DEFAULT_PROMPT_MODULES


def test_missing_section_falls_back_to_default() -> None:
    partial = parse_skill_doc("# h\n## quality_checklist\nbe terse\n")
    assert partial.quality_checklist == "be terse"
    # untouched sections fall back to the default, not empty string
    assert partial.scenario_classifier == DEFAULT_PROMPT_MODULES.scenario_classifier


def test_edited_section_is_parsed() -> None:
    modules = PromptModules(
        scenario_classifier="classify X",
        page_type_instructions="pages Y",
        component_library="components Z",
        quality_checklist="check W",
    )
    assert parse_skill_doc(render_skill_doc(modules)) == modules


def test_write_and_load(tmp_path) -> None:
    from slide_examiner.skill_doc import load_skill_doc, write_skill_doc

    path = write_skill_doc(DEFAULT_PROMPT_MODULES, tmp_path / "skill.md")
    assert load_skill_doc(path) == DEFAULT_PROMPT_MODULES
