from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt
from statistics import median

from .schemas import BBox, DefectLabel, Element, Slide


TEXT_TYPES = {"text", "textbox", "placeholder", "title", "body"}
IGNORED_OVERLAP_TYPES = {"background", "canvas"}


def estimate_text_capacity(element: Element) -> int:
    """Estimate how many characters fit in a text box without a renderer."""

    explicit = element.style.get("text_box_capacity") or element.metadata.get("text_box_capacity")
    if explicit is not None:
        return max(0, int(explicit))

    font_size = float(element.style.get("font_size", element.style.get("font_size_pt", 24)))
    avg_char_width = float(element.style.get("avg_char_width_px", font_size * 0.55))
    line_height = float(element.style.get("line_height_px", font_size * 1.25))
    chars_per_line = max(1, int(element.bbox.width // max(1.0, avg_char_width)))
    line_count = max(1, int(element.bbox.height // max(1.0, line_height)))
    return chars_per_line * line_count


def rendered_text_overflow_px(element: Element) -> float:
    rendered_width = element.metadata.get("rendered_text_width_px")
    rendered_height = element.metadata.get("rendered_text_height_px")
    width_overflow = max(0.0, float(rendered_width) - element.bbox.width) if rendered_width else 0.0
    height_overflow = max(0.0, float(rendered_height) - element.bbox.height) if rendered_height else 0.0
    if rendered_width or rendered_height:
        return max(width_overflow, height_overflow)

    capacity = estimate_text_capacity(element)
    extra_chars = max(0, len(element.text) - capacity)
    if extra_chars == 0:
        return 0.0
    font_size = float(element.style.get("font_size", element.style.get("font_size_pt", 24)))
    return extra_chars * font_size * 0.55


def detect_text_overflow(slide: Slide, min_overflow_px: float = 1.0) -> list[DefectLabel]:
    labels: list[DefectLabel] = []
    for element in slide.elements:
        if element.type not in TEXT_TYPES and not element.text:
            continue
        overflow = rendered_text_overflow_px(element)
        if overflow >= min_overflow_px:
            labels.append(
                DefectLabel(
                    type="G1_TEXT_OVERFLOW",
                    severity=overflow,
                    target_element_ids=(element.element_id,),
                    metadata={"overflow_px": overflow},
                )
            )
    return labels


def detect_overlaps(slide: Slide, min_iou: float = 0.05) -> list[DefectLabel]:
    elements = [item for item in slide.elements if item.type not in IGNORED_OVERLAP_TYPES]
    labels: list[DefectLabel] = []
    for left_index, left in enumerate(elements):
        for right in elements[left_index + 1 :]:
            iou = left.bbox.iou(right.bbox)
            if iou >= min_iou:
                labels.append(
                    DefectLabel(
                        type="G2_ELEMENT_OVERLAP",
                        severity=iou,
                        target_element_ids=(left.element_id, right.element_id),
                        metadata={"iou": iou},
                    )
                )
    return labels


def _expected_bbox(element: Element) -> BBox | None:
    value = element.metadata.get("expected_bbox") or element.metadata.get("placeholder_bbox")
    if not value:
        return None
    return BBox.from_mapping(value)


def detect_alignment_offsets(slide: Slide, min_offset_px: float = 4.0) -> list[DefectLabel]:
    labels: list[DefectLabel] = []
    already_labeled: set[str] = set()

    for element in slide.elements:
        expected = _expected_bbox(element)
        if not expected:
            continue
        offset = max(abs(element.bbox.x - expected.x), abs(element.bbox.y - expected.y))
        if offset >= min_offset_px:
            labels.append(
                DefectLabel(
                    type="G3_ALIGNMENT_OFFSET",
                    severity=offset,
                    target_element_ids=(element.element_id,),
                    metadata={"offset_px": offset, "expected_bbox": expected.to_dict()},
                )
            )
            already_labeled.add(element.element_id)

    groups: dict[str, list[Element]] = defaultdict(list)
    for element in slide.elements:
        group = element.metadata.get("alignment_group")
        if group and element.element_id not in already_labeled:
            groups[str(group)].append(element)

    for group, elements in groups.items():
        if len(elements) < 3:
            continue
        median_x = median(item.bbox.x for item in elements)
        for element in elements:
            offset = abs(element.bbox.x - median_x)
            if offset >= min_offset_px:
                labels.append(
                    DefectLabel(
                        type="G3_ALIGNMENT_OFFSET",
                        severity=offset,
                        target_element_ids=(element.element_id,),
                        metadata={"offset_px": offset, "alignment_group": group},
                    )
                )
    return labels


def detect_margin_violations(slide: Slide, margin_px: float = 32.0) -> list[DefectLabel]:
    labels: list[DefectLabel] = []
    for element in slide.elements:
        left = max(0.0, margin_px - element.bbox.x)
        top = max(0.0, margin_px - element.bbox.y)
        right = max(0.0, element.bbox.right - (slide.width - margin_px))
        bottom = max(0.0, element.bbox.bottom - (slide.height - margin_px))
        violation = max(left, top, right, bottom)
        if violation > 0:
            labels.append(
                DefectLabel(
                    type="G6_MARGIN_VIOLATION",
                    severity=violation,
                    target_element_ids=(element.element_id,),
                    metadata={
                        "violation_px": violation,
                        "left": left,
                        "top": top,
                        "right": right,
                        "bottom": bottom,
                    },
                )
            )
    return labels


def detect_font_size_inconsistencies(slide: Slide, min_delta_pt: float = 1.0) -> list[DefectLabel]:
    labels: list[DefectLabel] = []
    already_labeled: set[str] = set()

    for element in slide.elements:
        expected = element.metadata.get("expected_font_size_pt")
        current = _font_size(element)
        if expected is None or current is None:
            continue
        delta = abs(current - float(expected))
        if delta >= min_delta_pt:
            labels.append(
                DefectLabel(
                    type="G4_FONT_SIZE_INCONSISTENCY",
                    severity=delta,
                    target_element_ids=(element.element_id,),
                    metadata={"delta_pt": delta, "expected_font_size_pt": float(expected)},
                )
            )
            already_labeled.add(element.element_id)

    groups: dict[str, list[Element]] = defaultdict(list)
    for element in slide.elements:
        if element.element_id in already_labeled:
            continue
        level = element.metadata.get("text_level") or element.metadata.get("font_group")
        if level is not None and _font_size(element) is not None:
            groups[str(level)].append(element)

    for group, elements in groups.items():
        if len(elements) < 2:
            continue
        baseline = median(_font_size(element) or 0.0 for element in elements)
        for element in elements:
            current = _font_size(element)
            if current is None:
                continue
            delta = abs(current - baseline)
            if delta >= min_delta_pt:
                labels.append(
                    DefectLabel(
                        type="G4_FONT_SIZE_INCONSISTENCY",
                        severity=delta,
                        target_element_ids=(element.element_id,),
                        metadata={"delta_pt": delta, "font_group": group, "baseline_pt": baseline},
                    )
                )
    return labels


def detect_brand_color_violations(slide: Slide, min_delta_e: float = 1.5) -> list[DefectLabel]:
    labels: list[DefectLabel] = []
    palette = [_parse_rgb(item) for item in slide.metadata.get("brand_palette", [])]
    palette = [item for item in palette if item is not None]

    for element in slide.elements:
        current = _element_color(element)
        if current is None:
            continue
        expected = _parse_rgb(element.metadata.get("expected_color") or element.style.get("expected_color"))
        if expected is not None:
            delta = color_delta_e(current, expected)
            reference = expected
        elif palette:
            distances = [(color_delta_e(current, color), color) for color in palette]
            delta, reference = min(distances, key=lambda item: item[0])
        else:
            continue
        if delta >= min_delta_e:
            labels.append(
                DefectLabel(
                    type="G5_BRAND_COLOR_VIOLATION",
                    severity=delta,
                    target_element_ids=(element.element_id,),
                    metadata={"delta_e": delta, "actual_rgb": current, "reference_rgb": reference},
                )
            )
    return labels


def detect_color_inconsistency(slide: Slide, min_delta_e: float = 1.5) -> list[DefectLabel]:
    """INTERNAL colour-consistency rule (E8): within a ``color_group`` of >=3 elements,
    flag any member whose text colour differs from the group majority by >= min_delta_e.
    Decidable from the slide alone — no external brand palette (cf. the expected/palette
    path in ``detect_brand_color_violations``)."""
    labels: list[DefectLabel] = []
    groups: dict[str, list[Element]] = defaultdict(list)
    for element in slide.elements:
        group = element.metadata.get("color_group")
        if group and _element_color(element) is not None:
            groups[str(group)].append(element)
    for group, members in groups.items():
        if len(members) < 3:
            continue
        colors = [_element_color(m) for m in members]
        majority = Counter(colors).most_common(1)[0][0]  # the consensus colour
        for member, current in zip(members, colors):
            delta = color_delta_e(current, majority)
            if delta >= min_delta_e:
                labels.append(DefectLabel(
                    type="G5_BRAND_COLOR_VIOLATION", severity=delta,
                    target_element_ids=(member.element_id,),
                    metadata={"delta_e": delta, "actual_rgb": current, "majority_rgb": majority,
                              "color_group": group}))
    return labels


def lint_slide(
    slide: Slide,
    *,
    min_overflow_px: float = 1.0,
    min_iou: float = 0.05,
    min_alignment_offset_px: float = 4.0,
    min_font_delta_pt: float = 1.0,
    min_color_delta_e: float = 1.5,
    margin_px: float = 32.0,
) -> list[DefectLabel]:
    return [
        *detect_text_overflow(slide, min_overflow_px=min_overflow_px),
        *detect_overlaps(slide, min_iou=min_iou),
        *detect_alignment_offsets(slide, min_offset_px=min_alignment_offset_px),
        *detect_font_size_inconsistencies(slide, min_delta_pt=min_font_delta_pt),
        *detect_brand_color_violations(slide, min_delta_e=min_color_delta_e),
        *detect_color_inconsistency(slide, min_delta_e=min_color_delta_e),
        *detect_margin_violations(slide, margin_px=margin_px),
    ]


def linter_score(slide: Slide) -> float:
    """A simple bounded quality score for GEPA smoke tests."""

    defect_count = len(lint_slide(slide))
    return max(0.0, 1.0 - defect_count * 0.15)


def _font_size(element: Element) -> float | None:
    value = element.style.get("font_size_pt", element.style.get("font_size"))
    if value is None:
        return None
    return float(value)


def _element_color(element: Element) -> tuple[int, int, int] | None:
    for key in ("color", "font_color", "fill_color", "rgb"):
        parsed = _parse_rgb(element.style.get(key))
        if parsed is not None:
            return parsed
    return _parse_rgb(element.metadata.get("color"))


def _parse_rgb(value) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#"):
            text = text[1:]
        if len(text) == 6:
            return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))
        parts = [part.strip() for part in text.replace("rgb(", "").replace(")", "").split(",")]
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            return tuple(int(part) for part in parts)
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(max(0, min(255, item))) for item in value)
    return None


def _srgb_channel_to_linear(value: float) -> float:
    """Convert a single sRGB channel in [0, 1] to linear-light."""

    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _srgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert an sRGB (0-255) colour to CIELAB (D65)."""

    r, g, b = (_srgb_channel_to_linear(float(channel) / 255.0) for channel in rgb)
    # Linear sRGB -> XYZ (D65).
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    # Normalise by the D65 reference white.
    x /= 0.95047
    z /= 1.08883

    def _f(t: float) -> float:
        if t > 216.0 / 24389.0:
            return t ** (1.0 / 3.0)
        return (24389.0 / 27.0 * t + 16.0) / 116.0

    fx, fy, fz = _f(x), _f(y), _f(z)
    lightness = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_axis = 200.0 * (fy - fz)
    return lightness, a, b_axis


def color_delta_e(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    """CIE76 Delta-E: Euclidean distance between the two colours in CIELAB."""

    left_lab = _srgb_to_lab(left)
    right_lab = _srgb_to_lab(right)
    return sqrt(sum((a - b) ** 2 for a, b in zip(left_lab, right_lab, strict=True)))
