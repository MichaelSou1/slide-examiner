from __future__ import annotations

from pathlib import Path
from typing import Callable

from .dataset import deck_sample_from_injection, slide_sample_from_injection, write_manifest
from .ingest import load_deck_json, load_slide_json
from .injection import (
    InjectedDeck,
    InjectedSlide,
    inject_alignment_offset,
    inject_brand_color_violation,
    inject_density_rule_violation,
    inject_font_size_inconsistency,
    inject_image_text_contradiction,
    inject_margin_violation,
    inject_missing_logic_section,
    inject_narrative_order_break,
    inject_overlap,
    inject_terminology_inconsistency,
    inject_text_overflow,
    inject_title_body_mismatch,
)
from .schemas import Deck, ManifestSample, Slide


def inject_slide_defect(slide: Slide, defect_type: str, *, severity: float | None = None) -> InjectedSlide:
    if defect_type == "G1_TEXT_OVERFLOW":
        return inject_text_overflow(slide, overflow_px=float(severity or 32))
    if defect_type == "G2_ELEMENT_OVERLAP":
        return inject_overlap(slide, severity_iou=float(severity or 0.1))
    if defect_type == "G3_ALIGNMENT_OFFSET":
        return inject_alignment_offset(slide, offset_px=float(severity or 16))
    if defect_type == "G4_FONT_SIZE_INCONSISTENCY":
        return inject_font_size_inconsistency(slide, delta_pt=float(severity or 4))
    if defect_type == "G5_BRAND_COLOR_VIOLATION":
        return inject_brand_color_violation(slide, delta_e=float(severity or 24))
    if defect_type == "G6_MARGIN_VIOLATION":
        return inject_margin_violation(slide, bleed_px=float(severity or 16))
    if defect_type == "S1_TITLE_BODY_MISMATCH":
        return inject_title_body_mismatch(slide)
    if defect_type == "S4_DENSITY_RULE_VIOLATION":
        target_words = int(severity or 90)
        return inject_density_rule_violation(slide, target_words=target_words)
    if defect_type == "S6_IMAGE_TEXT_CONTRADICTION":
        return inject_image_text_contradiction(slide)
    raise ValueError(f"Unsupported slide-level defect type: {defect_type}")


def inject_deck_defect(deck: Deck, defect_type: str, *, severity: float | None = None) -> InjectedDeck:
    if defect_type == "S2_NARRATIVE_ORDER_BREAK":
        return inject_narrative_order_break(deck)
    if defect_type == "S3_TERMINOLOGY_INCONSISTENCY":
        return inject_terminology_inconsistency(
            deck,
            canonical=str(deck.metadata.get("canonical_term", "Product")),
            variant=str(deck.metadata.get("variant_term", "ProductX")),
        )
    if defect_type == "S5_MISSING_LOGIC_SECTION":
        return inject_missing_logic_section(
            deck,
            section=str(deck.metadata.get("required_sections", ["validation"])[-1]),
        )
    raise ValueError(f"Unsupported deck-level defect type: {defect_type}")


SLIDE_INJECTORS: dict[str, Callable[[Slide], InjectedSlide]] = {
    defect_type: (lambda slide, defect_type=defect_type: inject_slide_defect(slide, defect_type))
    for defect_type in (
        "G1_TEXT_OVERFLOW",
        "G2_ELEMENT_OVERLAP",
        "G3_ALIGNMENT_OFFSET",
        "G4_FONT_SIZE_INCONSISTENCY",
        "G5_BRAND_COLOR_VIOLATION",
        "G6_MARGIN_VIOLATION",
        "S1_TITLE_BODY_MISMATCH",
        "S4_DENSITY_RULE_VIOLATION",
        "S6_IMAGE_TEXT_CONTRADICTION",
    )
}

DECK_INJECTORS: dict[str, Callable[[Deck], InjectedDeck]] = {
    defect_type: (lambda deck, defect_type=defect_type: inject_deck_defect(deck, defect_type))
    for defect_type in (
        "S2_NARRATIVE_ORDER_BREAK",
        "S3_TERMINOLOGY_INCONSISTENCY",
        "S5_MISSING_LOGIC_SECTION",
    )
}


def inject_artifact_to_manifest(
    input_path: str | Path,
    *,
    defect_type: str,
    output_dir: str | Path,
    manifest_path: str | Path,
    template_condition: str = "freeform",
    severity: float | None = None,
) -> ManifestSample:
    if defect_type in SLIDE_INJECTORS:
        slide = load_slide_json(input_path)
        injected = inject_slide_defect(slide, defect_type, severity=severity)
        sample = slide_sample_from_injection(
            injected,
            sample_id=f"{slide.slide_id}_{defect_type}",
            output_dir=output_dir,
            template_condition=template_condition,
        )
    elif defect_type in DECK_INJECTORS:
        deck = load_deck_json(input_path)
        injected = inject_deck_defect(deck, defect_type, severity=severity)
        sample = deck_sample_from_injection(
            injected,
            sample_id=f"{deck.deck_id}_{defect_type}",
            output_dir=output_dir,
            template_condition=template_condition,
        )
    else:
        raise ValueError(f"Unsupported defect type: {defect_type}")
    write_manifest([sample], manifest_path)
    return sample
