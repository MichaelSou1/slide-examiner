"""Snap-to-master template manipulation.

A real template condition (as opposed to a metadata tag) lays content into a
fixed master: every element is snapped to its canonical slot. This *absorbs*
geometric defects — an injected alignment offset (G3), element overlap (G2),
margin bleed (G6) or text-overflow box (G1) gets snapped back to the master
position/size, so the rendered slide is clean again — while leaving semantic
defects (S1 title/body mismatch, S2 narrative order) untouched. Comparing
freeform vs template detection is the H1-tpl (template-collapse) experiment.

The master here matches the generator layout (`generator.deck_from_content_json`):
a title band and evenly-spaced body rows. Non title/body elements snap to a
coarse grid and clamp inside the page margins.
"""

from __future__ import annotations

from .schemas import BBox, Deck, Element, Slide

# Canonical master slots (px, 1920x1080 master).
_TITLE_SLOT = (96.0, 72.0, 1728.0, 72.0)
_BODY_X, _BODY_W, _BODY_H = 144.0, 1512.0, 72.0
_BODY_Y0, _BODY_DY = 180.0, 92.0
_GRID = 24.0
_MARGIN = 96.0


def _role(element: Element) -> str | None:
    return element.metadata.get("role") or element.metadata.get("text_level")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def snap_slide_to_master(slide: Slide) -> Slide:
    """Return a copy of ``slide`` with every element snapped to a master slot."""
    body_order = sorted(
        (e for e in slide.elements if _role(e) == "body"),
        key=lambda e: (e.bbox.y, e.element_id),
    )
    body_slot = {e.element_id: i for i, e in enumerate(body_order)}

    snapped: list[Element] = []
    for element in slide.elements:
        role = _role(element)
        if role == "title":
            x, y, w, h = _TITLE_SLOT
        elif role == "body":
            k = body_slot.get(element.element_id, 0)
            x, y, w, h = _BODY_X, _BODY_Y0 + k * _BODY_DY, _BODY_W, _BODY_H
        else:
            # Snap to a coarse grid and keep the element inside the page margins.
            x = _clamp(round(element.bbox.x / _GRID) * _GRID, _MARGIN, slide.width - _MARGIN - element.bbox.width)
            y = _clamp(round(element.bbox.y / _GRID) * _GRID, _MARGIN, slide.height - _MARGIN - element.bbox.height)
            w, h = element.bbox.width, element.bbox.height
        updated = element.with_bbox(BBox(x, y, w, h))
        # Drop the overflow marker the box now fits the master width again.
        if "rendered_text_width_px" in updated.metadata:
            updated = updated.with_metadata(rendered_text_width_px=min(updated.metadata["rendered_text_width_px"], w))
        snapped.append(updated)
    return slide.replace_elements(snapped) if hasattr(slide, "replace_elements") else _rebuilt(slide, snapped)


def snap_deck_to_master(deck: Deck) -> Deck:
    from dataclasses import replace

    return replace(deck, slides=tuple(snap_slide_to_master(s) for s in deck.slides))


def _rebuilt(slide: Slide, elements: list[Element]) -> Slide:
    from dataclasses import replace

    return replace(slide, elements=tuple(elements))
