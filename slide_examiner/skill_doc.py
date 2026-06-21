"""Skill-document artifact shared by the Part 3 optimizer carriers.

The slide-generator agent (``generator.generate_deck``) is steered by four
*editable* skill modules (``PromptModules``). Both optimizer carriers operate on
exactly these four texts, but represent them differently:

* **SkillOpt (ReflACT)** edits a single markdown document with four stable
  ``## <field>`` sections (add/insert/replace/delete edits land inside a section).
* **GEPA** evolves a ``dict[str, str]`` candidate whose keys are the four field
  names (one component per module).

This module is the single reconciliation point: ``PromptModules`` <-> markdown
(``parse_skill_doc`` / ``render_skill_doc``) <-> component dict
(``modules_to_components`` / ``components_to_modules``). It deliberately has no
heavy dependencies so optimizer adapters and ``generator`` can both import it
without cycles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path

#: Ordered names of the four editable skill modules. The order is stable and is
#: relied on by the markdown round-trip and by the optimizer candidate dicts.
MODULE_FIELDS: tuple[str, ...] = (
    "scenario_classifier",
    "page_type_instructions",
    "component_library",
    "quality_checklist",
)

_DOC_TITLE = "# Slide Generator Skill"
_SECTION_RE = re.compile(r"^##[ \t]+(?P<name>[A-Za-z0-9_]+)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class PromptModules:
    """The four editable prompt/skill modules consumed by the generator.

    These four strings are the *entire* surface the optimizer may rewrite; the
    generator's structural layout is fixed so that skill quality — not code —
    drives changes in the generated deck.
    """

    scenario_classifier: str = ""
    page_type_instructions: str = ""
    component_library: str = ""
    quality_checklist: str = ""

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in MODULE_FIELDS}

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> "PromptModules":
        return cls(**{name: str(value.get(name, "")) for name in MODULE_FIELDS})


#: Terse, non-empty baseline for every module — the "no learned skill"
#: (condition-0) starting point the optimizers improve upon.
DEFAULT_PROMPT_MODULES = PromptModules(
    scenario_classifier=(
        "Read the task brief and classify the deck scenario as one of "
        "`launch`, `client_intro`, or `full_proposal`. Choose required_sections "
        "to match: a launch deck needs background/problem/solution; a full "
        "proposal also needs validation and next-steps."
    ),
    page_type_instructions=(
        "Assign each slide a page_type from {title, agenda, content, comparison, "
        "closing}. The first slide is always `title` and the last is `closing`. "
        "Map every required section to at least one `content` slide."
    ),
    component_library=(
        "Each slide has one title (<= 8 words) and 3-5 bullets (<= 14 words "
        "each). Use a `figures` entry with kind in {trend_up, trend_down, arch} "
        "and a short claim only when the slide makes a quantitative or "
        "architectural point. Carry recurring product names in `key_terms`."
    ),
    quality_checklist=(
        "Before finalizing: no slide exceeds 6 bullets; each required section "
        "appears exactly once; terminology is identical across slides (do not "
        "mix variants of the same product name); titles and bullets are concise."
    ),
)


#: Near-empty seed skill — the genuine "no learned skill" starting point for the
#: optimizers. Under a vague brief a strong generator scores ~0.73 common-quality
#: from this seed (coverage is the weak point), leaving real headroom for the
#: optimizer to climb; DEFAULT_PROMPT_MODULES already encodes the conventions and
#: is therefore NOT a fair optimization seed for the H3 measurement.
WEAK_PROMPT_MODULES = PromptModules(
    scenario_classifier="Read the brief and decide what the deck is about.",
    page_type_instructions="Produce a sequence of slides for the brief.",
    component_library="Each slide has a title and some bullet points.",
    quality_checklist="Make the deck reasonable.",
)


def parse_skill_doc(markdown: str) -> PromptModules:
    """Parse a skill markdown document into ``PromptModules``.

    Missing or malformed sections fall back to ``DEFAULT_PROMPT_MODULES`` for
    that field so a bad optimizer edit degrades gracefully instead of crashing
    the rollout. Unknown ``## headers`` are ignored.
    """

    text = markdown or ""
    matches = list(_SECTION_RE.finditer(text))
    captured: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group("name")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        captured[name] = text[start:end].strip()

    values: dict[str, str] = {}
    for name in MODULE_FIELDS:
        body = captured.get(name, "").strip()
        values[name] = body if body else getattr(DEFAULT_PROMPT_MODULES, name)
    return PromptModules(**values)


def render_skill_doc(modules: PromptModules) -> str:
    """Serialize ``PromptModules`` to the canonical markdown document."""

    parts = [_DOC_TITLE, ""]
    for name in MODULE_FIELDS:
        parts.append(f"## {name}")
        parts.append(getattr(modules, name).strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def load_skill_doc(path: str | Path) -> PromptModules:
    return parse_skill_doc(Path(path).read_text(encoding="utf-8"))


def write_skill_doc(modules: PromptModules, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_skill_doc(modules), encoding="utf-8")
    return out


def modules_to_components(modules: PromptModules) -> dict[str, str]:
    """GEPA seed-candidate form: one component per module."""

    return modules.to_dict()


def components_to_modules(components: dict[str, str]) -> PromptModules:
    """Inverse of :func:`modules_to_components` (tolerates partial dicts)."""

    return PromptModules.from_dict(components)


# Sanity: the dataclass fields and MODULE_FIELDS must not drift apart.
assert tuple(f.name for f in fields(PromptModules)) == MODULE_FIELDS
