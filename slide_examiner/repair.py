from __future__ import annotations

from dataclasses import replace

from .geometry import estimate_text_capacity, lint_slide
from .schemas import BBox, DefectLabel, Element, Slide


def repair_slide(slide: Slide, labels: list[DefectLabel] | tuple[DefectLabel, ...] | None = None) -> Slide:
    """Apply deterministic repairs for symbolically verifiable geometry defects."""

    repaired = slide
    active_labels = list(labels or lint_slide(slide))
    for label in active_labels:
        if label.type == "G1_TEXT_OVERFLOW":
            repaired = _repair_text_overflow(repaired, label)
        elif label.type == "G2_ELEMENT_OVERLAP":
            repaired = _repair_overlap(repaired, label)
        elif label.type == "G3_ALIGNMENT_OFFSET":
            repaired = _repair_alignment(repaired, label)
        elif label.type == "G4_FONT_SIZE_INCONSISTENCY":
            repaired = _repair_font_size(repaired, label)
        elif label.type == "G5_BRAND_COLOR_VIOLATION":
            repaired = _repair_color(repaired, label)
        elif label.type == "G6_MARGIN_VIOLATION":
            repaired = _repair_margin(repaired, label)
    return repaired


def repair_passes_linter(slide: Slide, labels: list[DefectLabel] | tuple[DefectLabel, ...] | None = None) -> bool:
    repaired = repair_slide(slide, labels)
    repaired_types = {label.type for label in lint_slide(repaired)}
    target_types = {label.type for label in (labels or lint_slide(slide))}
    geometry_targets = {item for item in target_types if item.startswith("G")}
    return not (repaired_types & geometry_targets)


def _repair_text_overflow(slide: Slide, label: DefectLabel) -> Slide:
    element = slide.get(label.target_element_ids[0])
    capacity = estimate_text_capacity(element)
    text = element.text[:capacity] if capacity > 0 else ""
    metadata = {**element.metadata}
    metadata.pop("rendered_text_width_px", None)
    metadata.pop("rendered_text_height_px", None)
    return slide.replace_element(replace(element, text=text, metadata=metadata))


def _repair_overlap(slide: Slide, label: DefectLabel) -> Slide:
    if len(label.target_element_ids) < 2:
        return slide
    first = slide.get(label.target_element_ids[0])
    second = slide.get(label.target_element_ids[1])
    gap = 16
    new_x = min(max(gap, second.bbox.right + gap), max(gap, slide.width - first.bbox.width - gap))
    new_y = first.bbox.y
    if BBox(new_x, new_y, first.bbox.width, first.bbox.height).iou(second.bbox) > 0:
        new_y = min(max(gap, second.bbox.bottom + gap), max(gap, slide.height - first.bbox.height - gap))
    return slide.replace_element(first.with_bbox(BBox(new_x, new_y, first.bbox.width, first.bbox.height)))


def _repair_alignment(slide: Slide, label: DefectLabel) -> Slide:
    element = slide.get(label.target_element_ids[0])
    expected = element.metadata.get("expected_bbox") or label.metadata.get("expected_bbox")
    if not expected:
        return slide
    return slide.replace_element(element.with_bbox(BBox.from_mapping(expected)))


def _repair_font_size(slide: Slide, label: DefectLabel) -> Slide:
    element = slide.get(label.target_element_ids[0])
    expected = element.metadata.get("expected_font_size_pt") or label.metadata.get("expected_font_size_pt")
    if expected is None:
        return slide
    style = {**element.style, "font_size_pt": float(expected)}
    metadata = {**element.metadata}
    metadata.pop("expected_font_size_pt", None)
    return slide.replace_element(replace(element, style=style, metadata=metadata))


def _repair_color(slide: Slide, label: DefectLabel) -> Slide:
    element = slide.get(label.target_element_ids[0])
    expected = element.metadata.get("expected_color") or label.metadata.get("expected_color")
    if expected is None:
        rgb = label.metadata.get("reference_rgb")
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            expected = "#{:02x}{:02x}{:02x}".format(*[int(value) for value in rgb])
    if expected is None:
        return slide
    style = {**element.style, "color": expected}
    metadata = {**element.metadata}
    metadata.pop("expected_color", None)
    return slide.replace_element(replace(element, style=style, metadata=metadata))


def _repair_margin(slide: Slide, label: DefectLabel) -> Slide:
    element = slide.get(label.target_element_ids[0])
    margin = float(label.metadata.get("margin_px", 32))
    x = min(max(element.bbox.x, margin), slide.width - margin - element.bbox.width)
    y = min(max(element.bbox.y, margin), slide.height - margin - element.bbox.height)
    return slide.replace_element(element.with_bbox(BBox(x, y, element.bbox.width, element.bbox.height)))

