from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any


JSONDict = dict[str, Any]


# Ground-truth / injection-bookkeeping keys that must NOT leak into the oracle
# perception input shown to a model. See SHARED CONTRACT in the repo docs.
ORACLE_HIDDEN_ELEMENT_KEYS = frozenset(
    {
        "expected_bbox",
        "placeholder_bbox",
        "expected_font_size_pt",
        "expected_color",
        "expected_topic",
        "max_words",
        "diagram_claim",
        "diagram_false_claim",
        "diagram_trend",
    }
)
ORACLE_HIDDEN_CONTAINER_KEYS = frozenset(
    {
        "narrative_order_broken",
        "required_sections",
        "swapped_indices",
        "missing_section",
        "expected_topic",
        "canonical_term",
        "variant_term",
    }
)


def _strip_metadata(metadata: Any, hidden_keys: frozenset[str]) -> None:
    if isinstance(metadata, dict):
        for key in hidden_keys:
            metadata.pop(key, None)


def oracle_view(data: JSONDict) -> JSONDict:
    """Return a deep copy of a Slide/Deck ``to_dict()`` mapping with the
    ground-truth bookkeeping keys removed so it is safe to show to a model.

    Handles both a slide dict (``{"elements": [...], "metadata": {...}}``) and a
    deck dict (``{"slides": [...], "metadata": {...}}``) recursively. The input
    is never mutated.
    """

    view = copy.deepcopy(data)
    if not isinstance(view, dict):
        return view

    _strip_metadata(view.get("metadata"), ORACLE_HIDDEN_CONTAINER_KEYS)

    for element in view.get("elements", []) or []:
        if isinstance(element, dict):
            _strip_metadata(element.get("metadata"), ORACLE_HIDDEN_ELEMENT_KEYS)

    for slide in view.get("slides", []) or []:
        if isinstance(slide, dict):
            _strip_metadata(slide.get("metadata"), ORACLE_HIDDEN_CONTAINER_KEYS)
            for element in slide.get("elements", []) or []:
                if isinstance(element, dict):
                    _strip_metadata(element.get("metadata"), ORACLE_HIDDEN_ELEMENT_KEYS)

    return view


@dataclass(frozen=True)
class BBox:
    """Canonical pixel-space bounding box."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def moved(self, dx: float = 0.0, dy: float = 0.0) -> "BBox":
        return replace(self, x=self.x + dx, y=self.y + dy)

    def resized(self, width: float | None = None, height: float | None = None) -> "BBox":
        return replace(
            self,
            width=self.width if width is None else width,
            height=self.height if height is None else height,
        )

    def intersection_area(self, other: "BBox") -> float:
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        return max(0.0, right - left) * max(0.0, bottom - top)

    def iou(self, other: "BBox") -> float:
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        if union <= 0:
            return 0.0
        return intersection / union

    def to_dict(self) -> JSONDict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_mapping(cls, value: JSONDict | "BBox") -> "BBox":
        if isinstance(value, BBox):
            return value
        return cls(
            x=float(value["x"]),
            y=float(value["y"]),
            width=float(value["width"]),
            height=float(value["height"]),
        )


@dataclass(frozen=True)
class Element:
    element_id: str
    type: str
    bbox: BBox
    text: str = ""
    style: JSONDict = field(default_factory=dict)
    z: int = 0
    placeholder_id: str | None = None
    metadata: JSONDict = field(default_factory=dict)

    def with_bbox(self, bbox: BBox) -> "Element":
        return replace(self, bbox=bbox)

    def with_text(self, text: str) -> "Element":
        return replace(self, text=text)

    def with_metadata(self, **metadata: Any) -> "Element":
        merged = {**self.metadata, **metadata}
        return replace(self, metadata=merged)

    def to_dict(self) -> JSONDict:
        return {
            "element_id": self.element_id,
            "type": self.type,
            "bbox": self.bbox.to_dict(),
            "text": self.text,
            "style": self.style,
            "z": self.z,
            "placeholder_id": self.placeholder_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_mapping(cls, value: JSONDict | "Element") -> "Element":
        if isinstance(value, Element):
            return value
        return cls(
            element_id=str(value["element_id"]),
            type=str(value.get("type", "shape")),
            bbox=BBox.from_mapping(value["bbox"]),
            text=str(value.get("text", "")),
            style=dict(value.get("style", {})),
            z=int(value.get("z", 0)),
            placeholder_id=value.get("placeholder_id"),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class Slide:
    slide_id: str
    elements: tuple[Element, ...]
    width: int = 1920
    height: int = 1080
    metadata: JSONDict = field(default_factory=dict)

    def get(self, element_id: str) -> Element:
        for element in self.elements:
            if element.element_id == element_id:
                return element
        raise KeyError(element_id)

    def replace_element(self, updated: Element) -> "Slide":
        elements = tuple(updated if item.element_id == updated.element_id else item for item in self.elements)
        return replace(self, elements=elements)

    def to_dict(self) -> JSONDict:
        return {
            "slide_id": self.slide_id,
            "width": self.width,
            "height": self.height,
            "elements": [element.to_dict() for element in self.elements],
            "metadata": self.metadata,
        }

    @classmethod
    def from_mapping(cls, value: JSONDict | "Slide") -> "Slide":
        if isinstance(value, Slide):
            return value
        return cls(
            slide_id=str(value["slide_id"]),
            width=int(value.get("width", 1920)),
            height=int(value.get("height", 1080)),
            elements=tuple(Element.from_mapping(item) for item in value.get("elements", [])),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class Deck:
    deck_id: str
    slides: tuple[Slide, ...]
    metadata: JSONDict = field(default_factory=dict)

    def replace_slide(self, updated: Slide) -> "Deck":
        slides = tuple(updated if item.slide_id == updated.slide_id else item for item in self.slides)
        return replace(self, slides=slides)

    def without_slide(self, slide_id: str) -> "Deck":
        return replace(self, slides=tuple(item for item in self.slides if item.slide_id != slide_id))

    def to_dict(self) -> JSONDict:
        return {
            "deck_id": self.deck_id,
            "slides": [slide.to_dict() for slide in self.slides],
            "metadata": self.metadata,
        }

    @classmethod
    def from_mapping(cls, value: JSONDict | "Deck") -> "Deck":
        if isinstance(value, Deck):
            return value
        return cls(
            deck_id=str(value["deck_id"]),
            slides=tuple(Slide.from_mapping(item) for item in value.get("slides", [])),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class DefectLabel:
    type: str
    severity: float
    target_element_ids: tuple[str, ...]
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "type": self.type,
            "severity": self.severity,
            "target_element_ids": list(self.target_element_ids),
            "metadata": self.metadata,
        }

    @classmethod
    def from_mapping(cls, value: JSONDict | "DefectLabel") -> "DefectLabel":
        if isinstance(value, DefectLabel):
            return value
        return cls(
            type=str(value["type"]),
            severity=float(value.get("severity", 0.0)),
            target_element_ids=tuple(str(item) for item in value.get("target_element_ids", [])),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class ManifestSample:
    sample_id: str
    slide: Slide | None = None
    deck: Deck | None = None
    image_path: str | None = None
    oracle: JSONDict | None = None
    caption: str | None = None
    labels: tuple[DefectLabel, ...] = ()
    pair: JSONDict | None = None
    metadata: JSONDict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: JSONDict | "ManifestSample") -> "ManifestSample":
        if isinstance(value, ManifestSample):
            return value
        slide_value = value.get("slide")
        deck_value = value.get("deck")
        labels = value.get("labels", value.get("defects", []))
        return cls(
            sample_id=str(value.get("sample_id", value.get("id", ""))),
            slide=Slide.from_mapping(slide_value) if slide_value else None,
            deck=Deck.from_mapping(deck_value) if deck_value else None,
            image_path=value.get("image_path"),
            oracle=value.get("oracle"),
            caption=value.get("caption"),
            labels=tuple(DefectLabel.from_mapping(item) for item in labels),
            pair=value.get("pair"),
            metadata=dict(value.get("metadata", {})),
        )
