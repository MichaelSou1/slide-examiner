from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .geometry import color_delta_e, detect_overlaps
from .schemas import Deck, DefectLabel, Element, Slide


@dataclass(frozen=True)
class HackingFinding:
    type: str
    severity: float
    target_element_ids: tuple[str, ...]
    evidence: str

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "target_element_ids": list(self.target_element_ids),
            "evidence": self.evidence,
        }


def audit_slide_hacking(slide: Slide) -> list[HackingFinding]:
    findings: list[HackingFinding] = []
    findings.extend(_overflow_hidden(slide))
    findings.extend(_tiny_or_invisible_text(slide))
    findings.extend(_off_canvas(slide))
    findings.extend(_texture_background(slide))
    findings.extend(_covering_overlays(slide))
    return findings


def audit_deck_hacking(deck: Deck) -> list[dict]:
    records = []
    for slide in deck.slides:
        for finding in audit_slide_hacking(slide):
            record = finding.to_dict()
            record["slide_id"] = slide.slide_id
            records.append(record)
    return records


def hacking_score(findings: Iterable[HackingFinding | dict]) -> float:
    count = len(list(findings))
    return max(0.0, 1.0 - 0.2 * count)


def _overflow_hidden(slide: Slide) -> list[HackingFinding]:
    findings = []
    for element in slide.elements:
        overflow = str(element.style.get("overflow", element.metadata.get("overflow", ""))).lower()
        if overflow == "hidden" and element.text:
            findings.append(
                HackingFinding(
                    "HACK_OVERFLOW_HIDDEN",
                    1.0,
                    (element.element_id,),
                    "Text element uses overflow:hidden, which can hide clipping rather than fix it.",
                )
            )
    return findings


def _tiny_or_invisible_text(slide: Slide) -> list[HackingFinding]:
    findings = []
    for element in slide.elements:
        if not element.text:
            continue
        font_size = element.style.get("font_size_pt", element.style.get("font_size"))
        if font_size is not None and float(font_size) < 6:
            findings.append(
                HackingFinding(
                    "HACK_TINY_TEXT",
                    6 - float(font_size),
                    (element.element_id,),
                    "Text is too small to be a legitimate readable fix.",
                )
            )
        opacity = float(element.style.get("opacity", element.metadata.get("opacity", 1.0)))
        if opacity < 0.2:
            findings.append(
                HackingFinding(
                    "HACK_INVISIBLE_TEXT",
                    1.0 - opacity,
                    (element.element_id,),
                    "Text opacity is near invisible.",
                )
            )
        color = _parse_rgb(element.style.get("color"))
        background = _parse_rgb(element.style.get("background_color") or slide.metadata.get("background_color"))
        if color and background and color_delta_e(color, background) < 8:
            findings.append(
                HackingFinding(
                    "HACK_LOW_CONTRAST_TEXT",
                    8 - color_delta_e(color, background),
                    (element.element_id,),
                    "Text color nearly matches background.",
                )
            )
    return findings


def _off_canvas(slide: Slide) -> list[HackingFinding]:
    findings = []
    for element in slide.elements:
        outside_width = element.bbox.right < 0 or element.bbox.x > slide.width
        outside_height = element.bbox.bottom < 0 or element.bbox.y > slide.height
        if outside_width or outside_height:
            findings.append(
                HackingFinding(
                    "HACK_OFF_CANVAS_ELEMENT",
                    1.0,
                    (element.element_id,),
                    "Element is placed completely outside the visible canvas.",
                )
            )
    return findings


def _texture_background(slide: Slide) -> list[HackingFinding]:
    texture = slide.metadata.get("texture_background") or slide.metadata.get("background_texture")
    if texture:
        return [
            HackingFinding(
                "HACK_TEXTURE_BACKGROUND",
                1.0,
                (),
                "Texture background may mask layout or visual defects.",
            )
        ]
    return []


def _covering_overlays(slide: Slide) -> list[HackingFinding]:
    findings = []
    overlaps = detect_overlaps(slide, min_iou=0.85)
    for label in overlaps:
        left, right = (slide.get(element_id) for element_id in label.target_element_ids)
        if _is_plain_overlay(left) or _is_plain_overlay(right):
            findings.append(
                HackingFinding(
                    "HACK_COVERING_OVERLAY",
                    label.severity,
                    label.target_element_ids,
                    "Large plain overlay covers another element.",
                )
            )
    return findings


def _is_plain_overlay(element: Element) -> bool:
    return not element.text and bool(element.style.get("fill_color") or element.style.get("background_color"))


def _parse_rgb(value) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#"):
            text = text[1:]
        if len(text) == 6:
            return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(item) for item in value)
    return None

