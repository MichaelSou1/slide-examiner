from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from .geometry import _parse_rgb, color_delta_e
from .schemas import BBox, Deck, DefectLabel, Element, Slide


@dataclass(frozen=True)
class InjectedSlide:
    clean: Slide
    defective: Slide
    label: DefectLabel


@dataclass(frozen=True)
class InjectedDeck:
    clean: Deck
    defective: Deck
    label: DefectLabel


def _choose_element(slide: Slide, element_id: str | None, *, require_text: bool = False) -> Element:
    candidates = [item for item in slide.elements if not require_text or item.text or item.type in {"text", "textbox", "placeholder"}]
    if element_id is not None:
        return slide.get(element_id)
    if not candidates:
        raise ValueError("No suitable element found for injection")
    return candidates[0]


# Saturated off-brand hues for the internal G5 colour swap (a real brand violation is a
# hue change, not a gray-axis lightness step).
_HUE_PALETTE = [(203, 36, 41), (26, 95, 180), (38, 162, 105), (224, 120, 20), (129, 61, 156)]


def _chromatic_at_delta_e(base_rgb: tuple[int, int, int], delta_e: float,
                          hue_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Point on the segment base->hue whose CIEDE2000 to base is closest to delta_e —
    a clearly-hued colour calibrated in perceptual magnitude."""
    best, best_err = base_rgb, abs(color_delta_e(base_rgb, base_rgb) - delta_e)
    for i in range(1, 201):
        t = i / 200.0
        cand = tuple(int(round(b + (h - b) * t)) for b, h in zip(base_rgb, hue_rgb))
        err = abs(color_delta_e(base_rgb, cand) - delta_e)
        if err < best_err:
            best, best_err = cand, err
    return best


def inject_text_overflow(
    slide: Slide,
    *,
    element_id: str | None = None,
    overflow_px: float = 32.0,
    seed: int | None = None,
) -> InjectedSlide:
    rng = Random(seed)
    element = _choose_element(slide, element_id, require_text=True)
    font_size = float(element.style.get("font_size", element.style.get("font_size_pt", 24)))
    avg_char_width = float(element.style.get("avg_char_width_px", font_size * 0.55))
    original_text = element.text or ""
    extra_chars = max(1, int(overflow_px // max(1.0, avg_char_width)) + 2)
    filler = "X" * extra_chars
    if rng.random() < 0.5:
        text = f"{original_text} {filler}"
    else:
        text = f"{filler} {original_text}"
    # Shrink the box to fit only the original text on one line, so the appended
    # filler genuinely spills past the (now snug) box in the render — not just in
    # a metadata field. Width of the original text on one line at this font:
    original_text_width = max(avg_char_width, len(original_text) * avg_char_width)
    snug_width = min(element.bbox.width, original_text_width)
    rendered_text_width = len(text) * avg_char_width
    updated = (
        element.with_text(text)
        .with_bbox(BBox(element.bbox.x, element.bbox.y, snug_width, element.bbox.height))
        .with_metadata(rendered_text_width_px=rendered_text_width)
    )
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="G1_TEXT_OVERFLOW",
        severity=overflow_px,
        target_element_ids=(element.element_id,),
        metadata={"overflow_px": overflow_px},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def inject_overlap(
    slide: Slide,
    *,
    source_element_id: str | None = None,
    target_element_id: str | None = None,
    dx: float | None = None,
    dy: float | None = None,
    severity_iou: float = 0.1,
) -> InjectedSlide:
    if len(slide.elements) < 2:
        raise ValueError("Need at least two elements for overlap injection")
    source = slide.get(source_element_id) if source_element_id else slide.elements[0]
    target = slide.get(target_element_id) if target_element_id else slide.elements[1]
    if dx is None:
        overlap_width = min(source.bbox.width, target.bbox.width) * max(0.1, min(0.8, severity_iou * 2))
        dx = target.bbox.x - source.bbox.x + target.bbox.width - overlap_width
    if dy is None:
        dy = target.bbox.y - source.bbox.y
    updated = source.with_bbox(source.bbox.moved(dx=dx, dy=dy))
    defective = slide.replace_element(updated)
    actual_iou = updated.bbox.iou(target.bbox)
    label = DefectLabel(
        type="G2_ELEMENT_OVERLAP",
        severity=actual_iou,
        target_element_ids=(source.element_id, target.element_id),
        metadata={"iou": actual_iou},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def _aligned_sibling_group(slide: Slide) -> tuple[str, list[Element]] | None:
    """Largest set of >=3 same-type elements sharing a (rounded) left edge — a visible
    alignment column (e.g. body bullets). The basis for an INTERNAL-contrast defect:
    one member out of line with the rest is decidable from the slide alone, no external
    expected-position needed (E8 re-operationalisation)."""
    buckets: dict[tuple[str, int], list[Element]] = {}
    for el in slide.elements:
        if el.type in {"text", "body", "textbox", "placeholder"} and el.text:
            buckets.setdefault((el.type, round(el.bbox.x)), []).append(el)
    groups = [(f"{t}@{x}", members) for (t, x), members in buckets.items() if len(members) >= 3]
    if not groups:
        return None
    return max(groups, key=lambda g: len(g[1]))


def inject_alignment_offset(
    slide: Slide,
    *,
    element_id: str | None = None,
    offset_px: float = 16.0,
    axis: str = "x",
) -> InjectedSlide:
    """G3 as an INTERNAL alignment inconsistency: shift ONE member of an aligned sibling
    column out of line and tag the column with ``alignment_group`` so the linter's
    internal rule (median-x deviation) detects it. Falls back to the legacy absolute
    offset only when the slide has no >=3-member column."""
    group = _aligned_sibling_group(slide)
    dx = offset_px if axis == "x" else 0.0
    dy = offset_px if axis == "y" else 0.0
    if group is not None and element_id is None:
        key, members = group
        members.sort(key=lambda e: e.bbox.y)
        target = members[len(members) // 2]  # the middle one — clearly out of the column
        elements = list(slide.elements)
        for i, el in enumerate(elements):
            if any(el.element_id == m.element_id for m in members):
                el = el.with_metadata(alignment_group=key)
                if el.element_id == target.element_id:
                    el = el.with_bbox(el.bbox.moved(dx=dx, dy=dy))
                elements[i] = el
        clean = replace(slide, elements=tuple(
            e.with_metadata(alignment_group=key) if any(e.element_id == m.element_id for m in members) else e
            for e in slide.elements))
        defective = replace(slide, elements=tuple(elements))
        label = DefectLabel(
            type="G3_ALIGNMENT_OFFSET", severity=offset_px,
            target_element_ids=(target.element_id,),
            metadata={"offset_px": offset_px, "axis": axis, "alignment_group": key, "mode": "internal"})
        return InjectedSlide(clean=clean, defective=defective, label=label)
    # legacy fallback (no sibling column): absolute offset vs expected_bbox
    element = _choose_element(slide, element_id)
    expected = element.metadata.get("expected_bbox") or element.bbox.to_dict()
    updated = element.with_bbox(element.bbox.moved(dx=dx, dy=dy)).with_metadata(expected_bbox=expected)
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="G3_ALIGNMENT_OFFSET", severity=offset_px,
        target_element_ids=(element.element_id,),
        metadata={"offset_px": offset_px, "axis": axis, "expected_bbox": expected, "mode": "absolute_fallback"})
    return InjectedSlide(clean=slide, defective=defective, label=label)


def inject_margin_violation(
    slide: Slide,
    *,
    element_id: str | None = None,
    bleed_px: float = 16.0,
    side: str = "left",
    margin_px: float = 32.0,
) -> InjectedSlide:
    element = _choose_element(slide, element_id)
    bbox = element.bbox
    if side == "left":
        updated_bbox = bbox.moved(dx=(margin_px - bleed_px) - bbox.x)
    elif side == "top":
        updated_bbox = bbox.moved(dy=(margin_px - bleed_px) - bbox.y)
    elif side == "right":
        updated_bbox = bbox.moved(dx=(slide.width - margin_px + bleed_px) - bbox.right)
    elif side == "bottom":
        updated_bbox = bbox.moved(dy=(slide.height - margin_px + bleed_px) - bbox.bottom)
    else:
        raise ValueError(f"Unsupported margin side: {side}")
    updated = element.with_bbox(updated_bbox)
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="G6_MARGIN_VIOLATION",
        severity=bleed_px,
        target_element_ids=(element.element_id,),
        metadata={"bleed_px": bleed_px, "side": side, "margin_px": margin_px},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def inject_font_size_inconsistency(
    slide: Slide,
    *,
    element_id: str | None = None,
    delta_pt: float = 4.0,
) -> InjectedSlide:
    element = _choose_element(slide, element_id, require_text=True)
    current = float(element.style.get("font_size_pt", element.style.get("font_size", 24)))
    style = {**element.style, "font_size_pt": current + delta_pt}
    updated = replace(element, style=style).with_metadata(expected_font_size_pt=current)
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="G4_FONT_SIZE_INCONSISTENCY",
        severity=abs(delta_pt),
        target_element_ids=(element.element_id,),
        metadata={"delta_pt": abs(delta_pt), "expected_font_size_pt": current},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{int(channel):02x}" for channel in rgb)


def _color_at_delta_e(expected_rgb: tuple[int, int, int], target_delta_e: float) -> tuple[int, int, int]:
    """Build an sRGB colour whose CIELAB Delta-E to ``expected_rgb`` ~= ``target_delta_e``.

    Moves along a fixed deterministic direction in RGB space, scaling the step so the
    realized perceptual distance is as close as possible to the requested target. The
    direction is chosen per-channel to head toward the middle of the gamut so we can
    realize large distances without immediately saturating against [0, 255].
    """

    if target_delta_e <= 0:
        return expected_rgb

    # Deterministic unit-ish direction: each channel steps toward the gamut interior so
    # that bright sources darken and dark sources brighten, avoiding early clamping.
    direction = tuple(-1.0 if channel >= 128 else 1.0 for channel in expected_rgb)

    best = expected_rgb
    best_error = abs(color_delta_e(expected_rgb, expected_rgb) - target_delta_e)
    # Scan step magnitudes in RGB units; clamp channels and keep the closest realized
    # distance to the target. 442 ~= max possible RGB-space radius (sqrt(3)*255).
    for step in range(1, 443):
        candidate = tuple(
            int(max(0, min(255, round(channel + axis * step))))
            for channel, axis in zip(expected_rgb, direction, strict=True)
        )
        realized = color_delta_e(expected_rgb, candidate)
        error = abs(realized - target_delta_e)
        if error < best_error:
            best_error = error
            best = candidate
        if realized >= target_delta_e:
            # Distance is monotonically non-decreasing along the ray; no point overshooting.
            break
    return best


def inject_brand_color_violation(
    slide: Slide,
    *,
    element_id: str | None = None,
    delta_e: float = 24.0,
    color: str | None = None,
) -> InjectedSlide:
    """G5 as an INTERNAL colour inconsistency: recolour ONE member of an aligned sibling
    column so its text colour differs from the rest, and tag the column with
    ``color_group`` so the linter's internal rule detects "which element is off". The
    contrast is among the bullets themselves — decidable from the slide alone, no
    external brand palette needed (E8 re-operationalisation). Falls back to the legacy
    expected-colour shift only when there is no >=3-member column."""
    group = _aligned_sibling_group(slide)
    if group is not None and element_id is None:
        key, members = group
        members.sort(key=lambda e: e.bbox.y)
        target = members[len(members) // 2]
        sibling_hex = target.style.get("color") or target.style.get("fill_color") or "#111111"
        if color is None:
            sib_rgb = _parse_rgb(sibling_hex) or (17, 17, 17)
            # A real off-brand colour is a HUE swap, not a gray-axis lightness step
            # (`_color_at_delta_e` walks the gray axis -> perceptually weak even when
            # internal). Pick a saturated hue deterministically from the target id.
            hue = _HUE_PALETTE[sum(ord(c) for c in target.element_id) % len(_HUE_PALETTE)]
            new_rgb = _chromatic_at_delta_e(sib_rgb, float(delta_e), hue)
            color = _rgb_to_hex(new_rgb)
            realized = color_delta_e(sib_rgb, new_rgb)
        else:
            realized = color_delta_e(_parse_rgb(sibling_hex) or (17, 17, 17), _parse_rgb(color) or (0, 0, 0))
        elements = []
        for el in slide.elements:
            if any(el.element_id == m.element_id for m in members):
                el = el.with_metadata(color_group=key)
                if el.element_id == target.element_id:
                    el = replace(el, style={**el.style, "color": color})
            elements.append(el)
        clean = replace(slide, elements=tuple(
            e.with_metadata(color_group=key) if any(e.element_id == m.element_id for m in members) else e
            for e in slide.elements))
        defective = replace(slide, elements=tuple(elements))
        label = DefectLabel(
            type="G5_BRAND_COLOR_VIOLATION", severity=realized,
            target_element_ids=(target.element_id,),
            metadata={"delta_e": realized, "sibling_color": sibling_hex, "odd_color": color,
                      "color_group": key, "mode": "internal"})
        return InjectedSlide(clean=clean, defective=defective, label=label)
    # legacy fallback (no sibling column): shift one element vs its own expected colour
    element = _choose_element(slide, element_id)
    expected = element.style.get("color") or element.style.get("fill_color") or "#000000"
    if color is None:
        expected_rgb = _parse_rgb(expected) or (0, 0, 0)
        new_rgb = _color_at_delta_e(expected_rgb, float(delta_e))
        color = _rgb_to_hex(new_rgb)
        realized = color_delta_e(expected_rgb, new_rgb)
    else:
        expected_rgb, actual_rgb = _parse_rgb(expected), _parse_rgb(color)
        realized = color_delta_e(expected_rgb, actual_rgb) if expected_rgb and actual_rgb else float(delta_e)
    updated = replace(element, style={**element.style, "color": color}).with_metadata(expected_color=expected)
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="G5_BRAND_COLOR_VIOLATION", severity=realized,
        target_element_ids=(element.element_id,),
        metadata={"delta_e": realized, "expected_color": expected, "actual_color": color, "mode": "absolute_fallback"})
    return InjectedSlide(clean=slide, defective=defective, label=label)


def inject_title_body_mismatch(
    slide: Slide,
    *,
    title_element_id: str | None = None,
    body_element_id: str | None = None,
) -> InjectedSlide:
    title = slide.get(title_element_id) if title_element_id else _first_by_role(slide, "title")
    body = slide.get(body_element_id) if body_element_id else _first_by_role(slide, "body")
    replacement = body.text or "Unrelated implementation details"
    updated = title.with_text(f"Unrelated: {replacement[:80]}").with_metadata(expected_topic=slide.metadata.get("topic"))
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="S1_TITLE_BODY_MISMATCH",
        severity=1.0,
        target_element_ids=(title.element_id, body.element_id),
        metadata={"title_element_id": title.element_id, "body_element_id": body.element_id},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def inject_narrative_order_break(deck: Deck, *, first_index: int = 0, second_index: int = 1) -> InjectedDeck:
    if len(deck.slides) < 2:
        raise ValueError("Need at least two slides for narrative order injection")
    slides = list(deck.slides)
    slides[first_index], slides[second_index] = slides[second_index], slides[first_index]
    defective = replace(deck, slides=tuple(slides), metadata={**deck.metadata, "narrative_order_broken": True})
    label = DefectLabel(
        type="S2_NARRATIVE_ORDER_BREAK",
        severity=1.0,
        target_element_ids=tuple(slide.slide_id for slide in defective.slides),
        metadata={"swapped_indices": [first_index, second_index]},
    )
    return InjectedDeck(clean=deck, defective=defective, label=label)


def inject_terminology_inconsistency(
    deck: Deck,
    *,
    canonical: str,
    variant: str,
    slide_index: int = -1,
) -> InjectedDeck:
    if not deck.slides:
        raise ValueError("Need at least one slide for terminology injection")
    target_slide = deck.slides[slide_index]
    updated_elements = []
    touched: list[str] = []
    for element in target_slide.elements:
        if canonical in element.text:
            updated_elements.append(element.with_text(element.text.replace(canonical, variant)))
            touched.append(element.element_id)
        else:
            updated_elements.append(element)
    if not touched:
        element = _choose_element(target_slide, None, require_text=True)
        updated_elements = [item.with_text(f"{item.text} {variant}") if item.element_id == element.element_id else item for item in target_slide.elements]
        touched.append(element.element_id)
    updated_slide = replace(target_slide, elements=tuple(updated_elements))
    defective = deck.replace_slide(updated_slide)
    label = DefectLabel(
        type="S3_TERMINOLOGY_INCONSISTENCY",
        severity=1.0,
        target_element_ids=tuple(touched),
        metadata={"canonical": canonical, "variant": variant, "slide_id": target_slide.slide_id},
    )
    return InjectedDeck(clean=deck, defective=defective, label=label)


def inject_density_rule_violation(
    slide: Slide,
    *,
    element_id: str | None = None,
    max_words: int = 50,
    target_words: int = 90,
) -> InjectedSlide:
    element = _choose_element(slide, element_id, require_text=True)
    words = element.text.split()
    filler = [f"detail{i}" for i in range(max(0, target_words - len(words)))]
    updated = element.with_text(" ".join([*words, *filler])).with_metadata(max_words=max_words)
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="S4_DENSITY_RULE_VIOLATION",
        severity=float(target_words),
        target_element_ids=(element.element_id,),
        metadata={"max_words": max_words, "target_words": target_words},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def inject_missing_logic_section(deck: Deck, *, section: str) -> InjectedDeck:
    target = None
    for slide in deck.slides:
        if slide.metadata.get("section") == section:
            target = slide
            break
    if target is None:
        raise ValueError(f"No slide with section {section!r}")
    defective = deck.without_slide(target.slide_id)
    required = list(deck.metadata.get("required_sections", []))
    if section not in required:
        required.append(section)
    defective = replace(defective, metadata={**defective.metadata, "required_sections": required})
    label = DefectLabel(
        type="S5_MISSING_LOGIC_SECTION",
        severity=1.0,
        target_element_ids=(target.slide_id,),
        metadata={"missing_section": section},
    )
    return InjectedDeck(clean=deck, defective=defective, label=label)


def inject_image_text_contradiction(
    slide: Slide,
    *,
    diagram_element_id: str | None = None,
    text_element_id: str | None = None,
) -> InjectedSlide:
    diagram = slide.get(diagram_element_id) if diagram_element_id else _first_by_role(slide, "diagram")
    text = slide.get(text_element_id) if text_element_id else _first_by_role(slide, "body")
    claim = diagram.metadata.get("diagram_claim", "three-layer architecture")
    # Prefer an authored contradiction so the body asserts the opposite of what the
    # figure visibly depicts (a real image-text contradiction the model can see).
    false_claim = diagram.metadata.get("diagram_false_claim")
    new_text = str(false_claim) if false_claim else f"This slide describes a contradictory single-layer architecture, not {claim}."
    updated = text.with_text(new_text)
    defective = slide.replace_element(updated)
    label = DefectLabel(
        type="S6_IMAGE_TEXT_CONTRADICTION",
        severity=1.0,
        target_element_ids=(diagram.element_id, text.element_id),
        metadata={"diagram_claim": claim},
    )
    return InjectedSlide(clean=slide, defective=defective, label=label)


def _first_by_role(slide: Slide, role: str) -> Element:
    for element in slide.elements:
        if element.metadata.get("role") == role or element.type == role:
            return element
    return _choose_element(slide, None, require_text=role in {"title", "body"})
