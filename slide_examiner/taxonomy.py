from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefectSpec:
    id: str
    name: str
    group: str
    severities: tuple[float, ...]
    template_coverage: str
    description: str


DEFECTS: dict[str, DefectSpec] = {
    "G1_TEXT_OVERFLOW": DefectSpec(
        "G1_TEXT_OVERFLOW",
        "text overflow",
        "geometry",
        (4, 8, 16, 32, 64),
        "none",
        "Text content exceeds the text container.",
    ),
    "G2_ELEMENT_OVERLAP": DefectSpec(
        "G2_ELEMENT_OVERLAP",
        "element overlap",
        "geometry",
        (0.05, 0.1, 0.2, 0.4),
        "partial",
        "Two non-background elements overlap.",
    ),
    "G3_ALIGNMENT_OFFSET": DefectSpec(
        "G3_ALIGNMENT_OFFSET",
        "alignment offset",
        "geometry",
        (2, 4, 8, 16, 32),
        "strong",
        "An element is displaced from its placeholder or alignment group.",
    ),
    "G4_FONT_SIZE_INCONSISTENCY": DefectSpec(
        "G4_FONT_SIZE_INCONSISTENCY",
        "font size inconsistency",
        "geometry",
        (1, 2, 4, 8),
        "strong",
        "Same-level text uses inconsistent font sizes.",
    ),
    "G5_BRAND_COLOR_VIOLATION": DefectSpec(
        "G5_BRAND_COLOR_VIOLATION",
        "brand color violation",
        "geometry",
        (3, 6, 12, 24),
        "strong",
        "Element color deviates from expected theme or brand palette.",
    ),
    "G6_MARGIN_VIOLATION": DefectSpec(
        "G6_MARGIN_VIOLATION",
        "margin violation",
        "geometry",
        (4, 8, 16, 32),
        "strong",
        "An element bleeds into or beyond the safe margin.",
    ),
    "S1_TITLE_BODY_MISMATCH": DefectSpec(
        "S1_TITLE_BODY_MISMATCH",
        "title-body mismatch",
        "semantic",
        (1,),
        "none",
        "Slide title no longer matches body content.",
    ),
    "S2_NARRATIVE_ORDER_BREAK": DefectSpec(
        "S2_NARRATIVE_ORDER_BREAK",
        "narrative order break",
        "semantic",
        (1,),
        "none",
        "Deck page order breaks the expected story chain.",
    ),
    "S3_TERMINOLOGY_INCONSISTENCY": DefectSpec(
        "S3_TERMINOLOGY_INCONSISTENCY",
        "terminology inconsistency",
        "semantic",
        (1,),
        "none",
        "The same entity is named inconsistently across slides.",
    ),
    "S4_DENSITY_RULE_VIOLATION": DefectSpec(
        "S4_DENSITY_RULE_VIOLATION",
        "density rule violation",
        "semantic",
        (60, 90, 120),
        "none",
        "Text density exceeds a scenario-specific rule.",
    ),
    "S5_MISSING_LOGIC_SECTION": DefectSpec(
        "S5_MISSING_LOGIC_SECTION",
        "missing logic section",
        "semantic",
        (1,),
        "none",
        "A required narrative section is missing.",
    ),
    "S6_IMAGE_TEXT_CONTRADICTION": DefectSpec(
        "S6_IMAGE_TEXT_CONTRADICTION",
        "image-text contradiction",
        "semantic",
        (1,),
        "none",
        "Diagram metadata contradicts nearby text.",
    ),
}


GEOMETRY_DEFECTS = tuple(key for key, value in DEFECTS.items() if value.group == "geometry")
SEMANTIC_DEFECTS = tuple(key for key, value in DEFECTS.items() if value.group == "semantic")

