"""Part 3 extension defect types — **additive**.

This module does NOT touch the frozen Part 2 taxonomy
(:mod:`slide_examiner.taxonomy`) or the :mod:`slide_examiner.examiner_contract`
validators / Part 2 weights. It defines the one Part 3 extension class and a
small registry the elicitation harness uses so the new code never has to widen
the frozen ``DefectType`` enum.

``G7_RENDER_CONTAINMENT_OVERFLOW`` — *render-level containment overflow*: an
element whose **declared bbox is legal** (inside the page safe-margin, no bbox
IoU overlap with siblings) but whose **rendered content spills out of its
container / card / page boundary**. By construction the geometry linter — which
reasons over declared bboxes — is blind to it. That blindness is the *defining
property* and is asserted by the Phase-1 self-check
(``scripts/part3_build_g7.py`` requires ``lint_slide`` to return no finding on
>=90% of G7 defectives, otherwise the sample is dropped).

Relation to SlideAudit (UIST'25, arXiv 2508.03630): G7 is an OUR-EXTENSION
refinement of SlideAudit's holistic ``Content Overflow/Cut-off`` dim — same
phenomenon visually, but G7 adds the structural criterion (declared bbox legal
=> linter-blind) that makes it the canonical witness for "structurally valid but
renders broken". See ``data/part3/taxonomy_map.json``.
"""
from __future__ import annotations

from dataclasses import dataclass

# The frozen Part 1/2 taxonomy (12 types). Imported only to expose a single
# combined view; never mutated.
from .taxonomy import DefectType

#: The Part 3 extension type. A plain string (NOT a member of the frozen
#: ``DefectType`` enum) so it flows through the string-keyed eval/score paths
#: (``part2_eval.score_pointwise`` matches on label strings) without widening
#: the contract enum.
G7_RENDER_CONTAINMENT_OVERFLOW = "G7_RENDER_CONTAINMENT_OVERFLOW"


@dataclass(frozen=True)
class ExtensionSpec:
    id: str
    name: str
    group: str
    description: str
    #: Human-facing one-liner used verbatim in C3 per-type binary prompts.
    elicit_question: str
    #: Closest SlideAudit canonical dim (for taxonomy_map / cross-comparability).
    nearest_slideaudit: str
    our_extension: bool


G7_SPEC = ExtensionSpec(
    id=G7_RENDER_CONTAINMENT_OVERFLOW,
    name="render containment overflow",
    group="render",  # the bottleneck dichotomy bucket (A.2): VLM-rescuable render class
    description=(
        "An element whose declared bbox is legal (inside page margins, no bbox "
        "overlap) but whose rendered content overflows its container/card/page "
        "boundary. The declared-bbox geometry linter cannot see it."
    ),
    elicit_question=(
        "Does any element's visible content spill outside the box, card, or "
        "container that is supposed to hold it (e.g. text running past a card's "
        "edge, a list item rendered below its card, an image bleeding out of its "
        "frame)?"
    ),
    nearest_slideaudit="Content Overflow/Cut-off",
    our_extension=True,
)

#: The three render-overflow synthesis variants the G7 builder produces (A.3).
G7_VARIANTS = ("card_height", "unbreakable_text", "image_objectfit")

EXTENSION_SPECS: dict[str, ExtensionSpec] = {G7_RENDER_CONTAINMENT_OVERFLOW: G7_SPEC}

#: The "rescuable" classes Protocol 1 probes (A.2 / A.4): render/calibration-
#: bottlenecked types the elicitation conditions try to recover.
RESCUABLE_DEFECTS: tuple[str, ...] = (
    DefectType.G1_TEXT_OVERFLOW.value,
    DefectType.S6_IMAGE_TEXT_CONTRADICTION.value,
    G7_RENDER_CONTAINMENT_OVERFLOW,
)

#: All defect-type *strings* the Part 3 harness may reference: the 12 frozen +
#: the extension. Order is stable for deterministic prompt/scope construction.
ALL_DEFECT_STRINGS: tuple[str, ...] = (
    *(d.value for d in DefectType),
    G7_RENDER_CONTAINMENT_OVERFLOW,
)


def is_extension(defect: str) -> bool:
    """True for Part 3 extension types (currently only G7)."""
    return defect in EXTENSION_SPECS


def spec_for(defect: str) -> ExtensionSpec | None:
    return EXTENSION_SPECS.get(defect)
