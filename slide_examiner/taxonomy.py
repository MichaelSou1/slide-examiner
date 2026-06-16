from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DefectType(str, Enum):
    G1_TEXT_OVERFLOW = "G1_TEXT_OVERFLOW"
    G2_ELEMENT_OVERLAP = "G2_ELEMENT_OVERLAP"
    G3_ALIGNMENT_OFFSET = "G3_ALIGNMENT_OFFSET"
    G4_FONT_SIZE_INCONSISTENCY = "G4_FONT_SIZE_INCONSISTENCY"
    G5_BRAND_COLOR_VIOLATION = "G5_BRAND_COLOR_VIOLATION"
    G6_MARGIN_VIOLATION = "G6_MARGIN_VIOLATION"
    S1_TITLE_BODY_MISMATCH = "S1_TITLE_BODY_MISMATCH"
    S2_NARRATIVE_ORDER_BREAK = "S2_NARRATIVE_ORDER_BREAK"
    S3_TERMINOLOGY_INCONSISTENCY = "S3_TERMINOLOGY_INCONSISTENCY"
    S4_DENSITY_RULE_VIOLATION = "S4_DENSITY_RULE_VIOLATION"
    S5_MISSING_LOGIC_SECTION = "S5_MISSING_LOGIC_SECTION"
    S6_IMAGE_TEXT_CONTRADICTION = "S6_IMAGE_TEXT_CONTRADICTION"


@dataclass(frozen=True)
class DefectSpec:
    id: str
    name: str
    group: str
    severities: tuple[float, ...]
    template_coverage: str
    description: str


DEFECTS: dict[str, DefectSpec] = {
    DefectType.G1_TEXT_OVERFLOW.value: DefectSpec(
        DefectType.G1_TEXT_OVERFLOW.value,
        "text overflow",
        "geometry",
        (4, 8, 16, 32, 64),
        "none",
        "Text content exceeds the text container.",
    ),
    DefectType.G2_ELEMENT_OVERLAP.value: DefectSpec(
        DefectType.G2_ELEMENT_OVERLAP.value,
        "element overlap",
        "geometry",
        (0.05, 0.1, 0.2, 0.4),
        "partial",
        "Two non-background elements overlap.",
    ),
    DefectType.G3_ALIGNMENT_OFFSET.value: DefectSpec(
        DefectType.G3_ALIGNMENT_OFFSET.value,
        "alignment offset",
        "geometry",
        (2, 4, 8, 16, 32),
        "strong",
        "An element is displaced from its placeholder or alignment group.",
    ),
    DefectType.G4_FONT_SIZE_INCONSISTENCY.value: DefectSpec(
        DefectType.G4_FONT_SIZE_INCONSISTENCY.value,
        "font size inconsistency",
        "geometry",
        (1, 2, 4, 8),
        "strong",
        "Same-level text uses inconsistent font sizes.",
    ),
    DefectType.G5_BRAND_COLOR_VIOLATION.value: DefectSpec(
        DefectType.G5_BRAND_COLOR_VIOLATION.value,
        "brand color violation",
        "geometry",
        (3, 6, 12, 24),
        "strong",
        "Element color deviates from expected theme or brand palette.",
    ),
    DefectType.G6_MARGIN_VIOLATION.value: DefectSpec(
        DefectType.G6_MARGIN_VIOLATION.value,
        "margin violation",
        "geometry",
        (4, 8, 16, 32),
        "strong",
        "An element bleeds into or beyond the safe margin.",
    ),
    DefectType.S1_TITLE_BODY_MISMATCH.value: DefectSpec(
        DefectType.S1_TITLE_BODY_MISMATCH.value,
        "title-body mismatch",
        "semantic",
        (1,),
        "none",
        "Slide title no longer matches body content.",
    ),
    DefectType.S2_NARRATIVE_ORDER_BREAK.value: DefectSpec(
        DefectType.S2_NARRATIVE_ORDER_BREAK.value,
        "narrative order break",
        "semantic",
        (1,),
        "none",
        "Deck page order breaks the expected story chain.",
    ),
    DefectType.S3_TERMINOLOGY_INCONSISTENCY.value: DefectSpec(
        DefectType.S3_TERMINOLOGY_INCONSISTENCY.value,
        "terminology inconsistency",
        "semantic",
        (1,),
        "none",
        "The same entity is named inconsistently across slides.",
    ),
    DefectType.S4_DENSITY_RULE_VIOLATION.value: DefectSpec(
        DefectType.S4_DENSITY_RULE_VIOLATION.value,
        "density rule violation",
        "semantic",
        (60, 90, 120),
        "none",
        "Text density exceeds a scenario-specific rule.",
    ),
    DefectType.S5_MISSING_LOGIC_SECTION.value: DefectSpec(
        DefectType.S5_MISSING_LOGIC_SECTION.value,
        "missing logic section",
        "semantic",
        (1,),
        "none",
        "A required narrative section is missing.",
    ),
    DefectType.S6_IMAGE_TEXT_CONTRADICTION.value: DefectSpec(
        DefectType.S6_IMAGE_TEXT_CONTRADICTION.value,
        "image-text contradiction",
        "semantic",
        (1,),
        "none",
        "Diagram metadata contradicts nearby text.",
    ),
}


GEOMETRY_DEFECTS = tuple(key for key, value in DEFECTS.items() if value.group == "geometry")
SEMANTIC_DEFECTS = tuple(key for key, value in DEFECTS.items() if value.group == "semantic")
