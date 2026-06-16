from __future__ import annotations

import base64
import json
import mimetypes
import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import (
    BBox,
    Deck,
    Element as IrElement,
    ManifestSample,
    Slide,
    oracle_view,
)
from .taxonomy import DefectType


class ElementType(str, Enum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    BODY = "body"
    IMAGE = "image"
    TABLE = "table"
    CHART = "chart"
    SHAPE = "shape"
    ICON = "icon"
    FOOTER = "footer"
    OTHER = "other"


class Scene(str, Enum):
    LAUNCH = "launch"
    CLIENT_INTRO = "client_intro"
    FULL_PROPOSAL = "full_proposal"


class Modality(str, Enum):
    A_IMAGE_ONLY = "A"
    B_STRUCT_ONLY = "B"
    C_BOTH = "C"
    B_CAPTION_ONLY = "B_prime"


class ExamMode(str, Enum):
    POINTWISE = "pointwise"
    PAIRWISE = "pairwise"


class ExamLevel(str, Enum):
    PAGE = "page"
    DECK = "deck"


class SeverityLevel(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class Dimension(str, Enum):
    TEXT_FIT = "text_fit"
    OVERLAP = "overlap"
    ALIGNMENT = "alignment"
    TYPOGRAPHY = "typography"
    BRAND_COLOR = "brand_color"
    MARGINS = "margins"
    TITLE_BODY = "title_body"
    NARRATIVE_ORDER = "narrative_order"
    TERMINOLOGY = "terminology"
    DENSITY = "density"
    MISSING_SECTION = "missing_section"
    FIGURE_TEXT = "figure_text"


class PairwiseChoice(str, Enum):
    A = "A"
    B = "B"
    TIE = "tie"


PAGE_SCOPED_DEFECTS = frozenset(
    {
        DefectType.G1_TEXT_OVERFLOW,
        DefectType.G2_ELEMENT_OVERLAP,
        DefectType.G3_ALIGNMENT_OFFSET,
        DefectType.G4_FONT_SIZE_INCONSISTENCY,
        DefectType.G5_BRAND_COLOR_VIOLATION,
        DefectType.G6_MARGIN_VIOLATION,
        DefectType.S1_TITLE_BODY_MISMATCH,
        DefectType.S4_DENSITY_RULE_VIOLATION,
        DefectType.S6_IMAGE_TEXT_CONTRADICTION,
    }
)
DECK_SCOPED_DEFECTS = frozenset(
    {
        DefectType.S2_NARRATIVE_ORDER_BREAK,
        DefectType.S3_TERMINOLOGY_INCONSISTENCY,
        DefectType.S5_MISSING_LOGIC_SECTION,
    }
)

DEFECT_DIMENSIONS = {
    DefectType.G1_TEXT_OVERFLOW: Dimension.TEXT_FIT,
    DefectType.G2_ELEMENT_OVERLAP: Dimension.OVERLAP,
    DefectType.G3_ALIGNMENT_OFFSET: Dimension.ALIGNMENT,
    DefectType.G4_FONT_SIZE_INCONSISTENCY: Dimension.TYPOGRAPHY,
    DefectType.G5_BRAND_COLOR_VIOLATION: Dimension.BRAND_COLOR,
    DefectType.G6_MARGIN_VIOLATION: Dimension.MARGINS,
    DefectType.S1_TITLE_BODY_MISMATCH: Dimension.TITLE_BODY,
    DefectType.S2_NARRATIVE_ORDER_BREAK: Dimension.NARRATIVE_ORDER,
    DefectType.S3_TERMINOLOGY_INCONSISTENCY: Dimension.TERMINOLOGY,
    DefectType.S4_DENSITY_RULE_VIOLATION: Dimension.DENSITY,
    DefectType.S5_MISSING_LOGIC_SECTION: Dimension.MISSING_SECTION,
    DefectType.S6_IMAGE_TEXT_CONTRADICTION: Dimension.FIGURE_TEXT,
}

FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "expected_bbox",
        "placeholder_bbox",
        "expected_font_size_pt",
        "expected_color",
        "expected_topic",
        "narrative_order_broken",
        "swapped_indices",
        "missing_section",
        "canonical_term",
        "variant_term",
        "defect",
        "defect_type",
        "labels",
        "label",
        "severity",
        "repair_hint",
    }
)

SEVERITY_RANK = {
    SeverityLevel.NONE: 0,
    SeverityLevel.MINOR: 1,
    SeverityLevel.MODERATE: 2,
    SeverityLevel.SEVERE: 3,
}


class ContractModel(BaseModel):
    model_config = ConfigDict(use_enum_values=False, extra="forbid")


class BBoxPx(ContractModel):
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class RenderSpec(ContractModel):
    image_width_px: int = Field(gt=0)
    image_height_px: int = Field(gt=0)
    scale_x: float = Field(gt=0)
    scale_y: float = Field(gt=0)
    dpi: float | None = None
    renderer: str | None = None


class Element(ContractModel):
    element_id: str
    type: ElementType
    bbox: BBoxPx
    text: str | None = None
    font_size_pt: float | None = None
    font_color_hex: str | None = None
    fill_color_hex: str | None = None
    font_family: str | None = None
    z_index: int | None = None
    placeholder_role: str | None = None
    content_summary: str | None = None


class PageContext(ContractModel):
    scene: Scene
    template_id: str | None = None
    deck_id: str | None = None
    page_index: int | None = None
    task_brief: str | None = None


class PageExamRequest(ContractModel):
    page_id: str
    render: RenderSpec
    image_png_base64: str | None = None
    elements: list[Element] | None = None
    caption: str | None = None  # natural-language description; modality B' oracle
    context: PageContext
    check_scope: list[DefectType] = Field(default_factory=lambda: _sorted_defects(PAGE_SCOPED_DEFECTS))
    mode: Literal[ExamMode.POINTWISE] = ExamMode.POINTWISE
    level: Literal[ExamLevel.PAGE] = ExamLevel.PAGE
    modality: Modality = Modality.C_BOTH

    @field_validator("modality", mode="before")
    @classmethod
    def _normalize_page_modality(cls, value: Modality | str) -> Modality | str:
        return normalize_modality(value)

    @field_validator("check_scope")
    @classmethod
    def _check_page_scope(cls, value: list[DefectType]) -> list[DefectType]:
        out = [DefectType(item) for item in value]
        invalid = [item.value for item in out if item not in PAGE_SCOPED_DEFECTS]
        if invalid:
            raise ValueError(f"page request cannot check deck-scoped defects: {invalid}")
        return out

    @model_validator(mode="after")
    def _check_modality_inputs(self) -> "PageExamRequest":
        _validate_modality_payload(self.modality, self.image_png_base64, self.elements)
        return self


class DeckPageInput(ContractModel):
    page_id: str
    page_index: int
    render: RenderSpec | None = None
    image_png_base64: str | None = None
    elements: list[Element] | None = None
    title_text: str | None = None
    visible_text: str | None = None
    key_terms: list[str] = Field(default_factory=list)
    figure_summaries: list[str] = Field(default_factory=list)


class DeckContext(ContractModel):
    scene: Scene
    template_id: str | None = None
    task_brief: str | None = None
    required_sections: list[str] = Field(default_factory=list)
    project_glossary: dict[str, list[str]] = Field(default_factory=dict)


class DeckExamRequest(ContractModel):
    deck_id: str
    pages: list[DeckPageInput]
    caption: str | None = None  # natural-language description; modality B' oracle
    context: DeckContext
    check_scope: list[DefectType] = Field(default_factory=lambda: _sorted_defects(DECK_SCOPED_DEFECTS))
    mode: Literal[ExamMode.POINTWISE] = ExamMode.POINTWISE
    level: Literal[ExamLevel.DECK] = ExamLevel.DECK
    modality: Modality = Modality.C_BOTH

    @field_validator("modality", mode="before")
    @classmethod
    def _normalize_deck_modality(cls, value: Modality | str) -> Modality | str:
        return normalize_modality(value)

    @field_validator("check_scope")
    @classmethod
    def _check_deck_scope(cls, value: list[DefectType]) -> list[DefectType]:
        out = [DefectType(item) for item in value]
        invalid = [item.value for item in out if item not in DECK_SCOPED_DEFECTS]
        if invalid:
            raise ValueError(f"deck request cannot check page-scoped defects: {invalid}")
        return out

    @model_validator(mode="after")
    def _check_deck_modality_inputs(self) -> "DeckExamRequest":
        if self.modality in {Modality.A_IMAGE_ONLY, Modality.C_BOTH} and not any(
            page.image_png_base64 for page in self.pages
        ):
            raise ValueError("modality A/C requires at least one page image")
        if self.modality in {Modality.B_STRUCT_ONLY, Modality.C_BOTH} and not any(
            page.elements or page.visible_text or page.title_text for page in self.pages
        ):
            raise ValueError("modality B/C requires deck text or structure")
        return self


class Locator(ContractModel):
    level: ExamLevel
    page_id: str | None = None
    element_id: str | None = None
    bbox: BBoxPx | None = None
    related_page_ids: list[str] = Field(default_factory=list)


class Finding(ContractModel):
    type: DefectType
    severity: SeverityLevel
    locator: Locator
    evidence: str = Field(min_length=1)
    fix_suggestion: str = Field(min_length=1)

    @field_validator("severity")
    @classmethod
    def _no_none_findings(cls, value: SeverityLevel) -> SeverityLevel:
        severity = SeverityLevel(value)
        if severity == SeverityLevel.NONE:
            raise ValueError("Finding severity cannot be 'none'")
        return severity

    @model_validator(mode="after")
    def _check_explanatory_fields(self) -> "Finding":
        _validate_evidence_text(self)
        _validate_fix_suggestion_text(self.fix_suggestion)
        return self


class PageExamResult(ContractModel):
    page_id: str
    has_defect: bool
    findings: list[Finding] = Field(default_factory=list)
    clean_dimensions: list[Dimension] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_page_result(self) -> "PageExamResult":
        _validate_has_defect(self.has_defect, self.findings)
        for finding in self.findings:
            if finding.type not in PAGE_SCOPED_DEFECTS:
                raise ValueError(f"page result contains deck-scoped defect {finding.type.value}")
            if finding.locator.level != ExamLevel.PAGE:
                raise ValueError("page finding locator.level must be page")
        return self


class DeckExamResult(ContractModel):
    deck_id: str
    has_defect: bool
    findings: list[Finding] = Field(default_factory=list)
    clean_dimensions: list[Dimension] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_deck_result(self) -> "DeckExamResult":
        _validate_has_defect(self.has_defect, self.findings)
        for finding in self.findings:
            if finding.type not in DECK_SCOPED_DEFECTS:
                raise ValueError(f"deck result contains page-scoped defect {finding.type.value}")
            if finding.locator.level != ExamLevel.DECK:
                raise ValueError("deck finding locator.level must be deck")
        return self


class PairwiseResult(ContractModel):
    level: ExamLevel
    subject_id: str
    better: PairwiseChoice
    reason: str = Field(min_length=1)
    per_dimension: dict[Dimension, PairwiseChoice] = Field(default_factory=dict)


SYSTEM_PROMPT_PAGE = (
    "You are a slide quality examiner. Inspect the given single slide page for "
    "the requested page-scoped defect types. Output ONLY one valid JSON object "
    "matching PageExamResult. No prose, no code fences."
)
SYSTEM_PROMPT_DECK = (
    "You are a slide deck quality examiner. Inspect the whole deck for the "
    "requested deck-scoped defect types. Output ONLY one valid JSON object "
    "matching DeckExamResult. No prose, no code fences."
)


def build_page_messages(req: PageExamRequest) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if req.modality in {Modality.A_IMAGE_ONLY, Modality.C_BOTH}:
        content.append({"type": "image_url", "image_url": {"url": _data_image_url(req.image_png_base64)}})

    struct_txt = ""
    if req.modality in {Modality.B_STRUCT_ONLY, Modality.C_BOTH}:
        struct_txt = "ELEMENTS:\n" + serialize_elements(req.elements or []) + "\n"

    caption_txt = ""
    if req.modality == Modality.B_CAPTION_ONLY:
        caption_txt = "CAPTION (natural-language description of the rendered slide):\n" + (req.caption or "") + "\n"

    instruction = (
        f"PAGE_ID: {req.page_id}\n"
        f"{serialize_render(req.render)}\n"
        f"{struct_txt}"
        f"{caption_txt}"
        f"SCENE: {req.context.scene.value}\n"
        f"TEMPLATE_ID: {req.context.template_id}\n"
        f"PAGE_INDEX: {req.context.page_index}\n"
        f"TASK_BRIEF: {req.context.task_brief}\n"
        f"CHECK_SCOPE: {[item.value for item in req.check_scope]}\n"
    )
    content.append({"type": "text", "text": instruction})
    return [{"role": "system", "content": SYSTEM_PROMPT_PAGE}, {"role": "user", "content": content}]


def build_deck_messages(req: DeckExamRequest) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    page_blocks: list[str] = []
    for page in sorted(req.pages, key=lambda item: item.page_index):
        if req.modality in {Modality.A_IMAGE_ONLY, Modality.C_BOTH} and page.image_png_base64:
            content.append({"type": "image_url", "image_url": {"url": _data_image_url(page.image_png_base64)}})

        elements_txt = ""
        if req.modality in {Modality.B_STRUCT_ONLY, Modality.C_BOTH} and page.elements:
            elements_txt = "\nELEMENTS:\n" + serialize_elements(page.elements)

        render_txt = f"\n{serialize_render(page.render)}" if page.render else ""
        if req.modality == Modality.A_IMAGE_ONLY:
            page_blocks.append(f"PAGE {page.page_index} id={page.page_id}{render_txt}")
        else:
            page_blocks.append(
                f"PAGE {page.page_index} id={page.page_id}{render_txt}\n"
                f"TITLE: {page.title_text}\n"
                f"VISIBLE_TEXT: {page.visible_text}\n"
                f"KEY_TERMS: {page.key_terms}\n"
                f"FIGURES: {page.figure_summaries}"
                f"{elements_txt}"
            )

    caption_txt = ""
    if req.modality == Modality.B_CAPTION_ONLY:
        caption_txt = "CAPTION (natural-language description of the rendered deck):\n" + (req.caption or "") + "\n\n"

    instruction = (
        f"DECK_ID: {req.deck_id}\n"
        f"SCENE: {req.context.scene.value}\n"
        f"TEMPLATE_ID: {req.context.template_id}\n"
        f"TASK_BRIEF: {req.context.task_brief}\n"
        f"REQUIRED_SECTIONS: {req.context.required_sections}\n"
        f"PROJECT_GLOSSARY: {req.context.project_glossary}\n"
        f"CHECK_SCOPE: {[item.value for item in req.check_scope]}\n\n"
        f"{caption_txt}"
        + "\n\n".join(page_blocks)
    )
    content.append({"type": "text", "text": instruction})
    return [{"role": "system", "content": SYSTEM_PROMPT_DECK}, {"role": "user", "content": content}]


def image_content_from_path(path: str | Path) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": image_url_from_path(path)}}


def parse_page_result(raw: str | bytes | dict[str, Any]) -> PageExamResult:
    return PageExamResult.model_validate(_load_json_object(raw))


def parse_deck_result(raw: str | bytes | dict[str, Any]) -> DeckExamResult:
    return DeckExamResult.model_validate(_load_json_object(raw))


def serialize_bbox(bbox: BBoxPx) -> str:
    return f"x={bbox.x:g} y={bbox.y:g} w={bbox.width:g} h={bbox.height:g}"


def serialize_render(render: RenderSpec) -> str:
    return (
        f"render={render.image_width_px}x{render.image_height_px} "
        f"scale=({render.scale_x:g},{render.scale_y:g}) dpi={render.dpi} renderer={render.renderer}"
    )


def serialize_elements(elements: list[Element]) -> str:
    lines: list[str] = []
    for element in sorted(elements, key=lambda item: item.element_id):
        lines.append(
            f"[{element.element_id}] type={element.type.value} bbox=({serialize_bbox(element.bbox)}) "
            f"font={element.font_size_pt}pt color={element.font_color_hex} fill={element.fill_color_hex} "
            f"role={element.placeholder_role} z={element.z_index} text={element.text!r} "
            f"summary={element.content_summary!r}"
        )
    return "\n".join(lines)


def page_request_from_sample(
    sample: ManifestSample | dict[str, Any],
    *,
    modality: Modality | str = Modality.C_BOTH,
    check_scope: list[DefectType | str] | None = None,
) -> PageExamRequest:
    manifest = ManifestSample.from_mapping(sample)
    slide = _sample_slide(manifest)
    page_id = slide.slide_id if slide is not None else manifest.sample_id
    mod = normalize_modality(modality)
    image = _sample_image_base64(manifest) if mod in {Modality.A_IMAGE_ONLY, Modality.C_BOTH} else None
    elements = _elements_from_slide(slide) if slide is not None and mod in {Modality.B_STRUCT_ONLY, Modality.C_BOTH} else None
    if slide is None and mod in {Modality.B_STRUCT_ONLY, Modality.C_BOTH}:
        elements = []
    caption = _optional_str(manifest.caption) if mod == Modality.B_CAPTION_ONLY else None
    return PageExamRequest(
        page_id=page_id,
        render=render_spec_from_slide(slide, manifest),
        image_png_base64=image,
        elements=elements,
        caption=caption,
        context=PageContext(
            scene=_scene_from_metadata(manifest.metadata),
            template_id=_optional_str(manifest.metadata.get("template_id")),
            deck_id=_optional_str(manifest.metadata.get("deck_id")),
            page_index=_optional_int(manifest.metadata.get("page_index")),
            task_brief=_optional_str(manifest.metadata.get("task_brief")),
        ),
        check_scope=_coerce_defects(check_scope, PAGE_SCOPED_DEFECTS),
        modality=mod,
    )


def deck_request_from_sample(
    sample: ManifestSample | dict[str, Any],
    *,
    modality: Modality | str = Modality.C_BOTH,
    check_scope: list[DefectType | str] | None = None,
) -> DeckExamRequest:
    manifest = ManifestSample.from_mapping(sample)
    deck = _sample_deck(manifest)
    if deck is None:
        raise ValueError("deck request requires a deck sample")
    mod = normalize_modality(modality)
    fallback_image = _sample_image_base64(manifest) if mod in {Modality.A_IMAGE_ONLY, Modality.C_BOTH} else None
    page_images = _page_image_base64s(manifest) if mod in {Modality.A_IMAGE_ONLY, Modality.C_BOTH} else []
    pages: list[DeckPageInput] = []
    for index, slide in enumerate(deck.slides):
        image = page_images[index] if index < len(page_images) else (fallback_image if index == 0 else None)
        elements = _elements_from_slide(slide) if mod in {Modality.B_STRUCT_ONLY, Modality.C_BOTH} else None
        pages.append(
            DeckPageInput(
                page_id=slide.slide_id,
                page_index=index,
                render=render_spec_from_slide(slide, manifest),
                image_png_base64=image,
                elements=elements,
                title_text=_title_text(slide),
                visible_text=_visible_text(slide),
                key_terms=_key_terms(slide),
                figure_summaries=_figure_summaries(slide),
            )
        )
    caption = _optional_str(manifest.caption) if mod == Modality.B_CAPTION_ONLY else None
    return DeckExamRequest(
        deck_id=deck.deck_id or manifest.sample_id,
        pages=pages,
        caption=caption,
        context=DeckContext(
            scene=_scene_from_metadata(manifest.metadata),
            template_id=_optional_str(manifest.metadata.get("template_id")),
            task_brief=_optional_str(manifest.metadata.get("task_brief")),
            required_sections=_list_str(deck.metadata.get("required_sections", manifest.metadata.get("required_sections", []))),
            project_glossary=_glossary(manifest.metadata.get("project_glossary")),
        ),
        check_scope=_coerce_defects(check_scope, DECK_SCOPED_DEFECTS),
        modality=mod,
    )


def request_from_sample(
    sample: ManifestSample | dict[str, Any],
    *,
    modality: Modality | str = Modality.C_BOTH,
) -> PageExamRequest | DeckExamRequest:
    manifest = ManifestSample.from_mapping(sample)
    if _sample_deck(manifest) is not None:
        return deck_request_from_sample(manifest, modality=modality)
    return page_request_from_sample(manifest, modality=modality)


def result_from_sample(sample: ManifestSample | dict[str, Any]) -> PageExamResult | DeckExamResult:
    manifest = ManifestSample.from_mapping(sample)
    if _sample_deck(manifest) is not None:
        return deck_result_from_labels(manifest)
    return page_result_from_labels(manifest)


def page_result_from_labels(sample: ManifestSample | dict[str, Any]) -> PageExamResult:
    manifest = ManifestSample.from_mapping(sample)
    slide = _sample_slide(manifest)
    page_id = slide.slide_id if slide else manifest.sample_id
    active = [label for label in manifest.labels if label.type != "NO_DEFECT"]
    findings = [_finding_from_label(label, ExamLevel.PAGE, page_id=page_id) for label in active]
    return PageExamResult(
        page_id=page_id,
        has_defect=bool(findings),
        findings=findings,
        clean_dimensions=_clean_dimensions(active, PAGE_SCOPED_DEFECTS),
    )


def deck_result_from_labels(sample: ManifestSample | dict[str, Any]) -> DeckExamResult:
    manifest = ManifestSample.from_mapping(sample)
    deck = _sample_deck(manifest)
    deck_id = deck.deck_id if deck else manifest.sample_id
    active = [label for label in manifest.labels if label.type != "NO_DEFECT"]
    findings = [_finding_from_label(label, ExamLevel.DECK) for label in active]
    return DeckExamResult(
        deck_id=deck_id,
        has_defect=bool(findings),
        findings=findings,
        clean_dimensions=_clean_dimensions(active, DECK_SCOPED_DEFECTS),
    )


def build_messages_from_sample(
    sample: ManifestSample | dict[str, Any],
    *,
    modality: Modality | str = Modality.C_BOTH,
) -> list[dict[str, Any]]:
    request = request_from_sample(sample, modality=modality)
    if isinstance(request, DeckExamRequest):
        return build_deck_messages(request)
    return build_page_messages(request)


def build_runtime_messages_from_sample(sample: ManifestSample | dict[str, Any]) -> list[dict[str, Any]]:
    """Build the runtime examiner request.

    Runtime calls always use modality C (image + structure). Attribution probes
    and training export may still pass A/B/B_prime explicitly through the lower
    level builders.
    """

    return build_messages_from_sample(sample, modality=Modality.C_BOTH)


def normalize_contract_output(value: dict[str, Any]) -> dict[str, Any] | None:
    if "findings" not in value:
        return None
    findings = value.get("findings", [])
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        locator = finding.get("locator") or {}
        element_ids = []
        if locator.get("element_id"):
            element_ids.append(locator["element_id"])
        element_ids.extend(locator.get("related_page_ids") or [])
        severity = SeverityLevel(finding.get("severity", SeverityLevel.MODERATE.value))
        normalized.append(
            {
                "type": finding.get("type", "UNKNOWN"),
                "present": True,
                "element_ids": element_ids,
                "severity": float(SEVERITY_RANK[severity]),
                "severity_level": severity.value,
                "confidence": 1.0,
                "evidence": finding.get("evidence", ""),
                "fix": finding.get("fix_suggestion", ""),
            }
        )
    return {
        "defects": normalized,
        "overall_score": max(0.0, 1.0 - 0.2 * sum(SEVERITY_RANK[SeverityLevel(item["severity_level"])] for item in normalized)),
        "pairwise_winner": value.get("better"),
        "raw": value,
    }


def render_spec_from_slide(slide: Slide | None, sample: ManifestSample | None = None) -> RenderSpec:
    metadata = sample.metadata if sample is not None else {}
    render_meta = metadata.get("render") if isinstance(metadata.get("render"), dict) else {}
    slide_width = slide.width if slide is not None else 1920
    slide_height = slide.height if slide is not None else 1080
    width = int(render_meta.get("image_width_px", render_meta.get("width", slide_width or 1920)))
    height = int(render_meta.get("image_height_px", render_meta.get("height", slide_height or 1080)))
    scale_x = float(render_meta.get("scale_x", width / float(slide_width or width)))
    scale_y = float(render_meta.get("scale_y", height / float(slide_height or height)))
    return RenderSpec(
        image_width_px=width,
        image_height_px=height,
        scale_x=scale_x,
        scale_y=scale_y,
        dpi=_optional_float(render_meta.get("dpi")),
        renderer=_optional_str(render_meta.get("renderer")),
    )


def _finding_from_label(label: Any, level: ExamLevel, *, page_id: str | None = None) -> Finding:
    defect = DefectType(label.type)
    targets = list(label.target_element_ids)
    locator = Locator(
        level=level,
        page_id=page_id if level == ExamLevel.PAGE else None,
        element_id=targets[0] if level == ExamLevel.PAGE and targets else None,
        related_page_ids=targets if level == ExamLevel.DECK else [],
    )
    return Finding(
        type=defect,
        severity=severity_level_for_label(defect, float(label.severity), label.metadata),
        locator=locator,
        evidence=_evidence_from_label(defect, targets, level, label.metadata),
        fix_suggestion=_fix_from_label(defect, targets, level, label.metadata),
    )


def severity_level_for_label(defect: DefectType | str, severity: float, metadata: dict[str, Any] | None = None) -> SeverityLevel:
    defect = DefectType(defect)
    metadata = metadata or {}
    explicit = metadata.get("severity_level")
    if explicit:
        return SeverityLevel(str(explicit))
    if defect == DefectType.G1_TEXT_OVERFLOW:
        return _grid_level(severity, minor_max=8, moderate_max=32)
    if defect == DefectType.G2_ELEMENT_OVERLAP:
        if severity <= 0.05:
            return SeverityLevel.MINOR
        if severity <= 0.2:
            return SeverityLevel.MODERATE
        return SeverityLevel.SEVERE
    if defect == DefectType.G3_ALIGNMENT_OFFSET:
        return _grid_level(severity, minor_max=4, moderate_max=16)
    if defect == DefectType.G4_FONT_SIZE_INCONSISTENCY:
        if severity <= 1:
            return SeverityLevel.MINOR
        if severity <= 4:
            return SeverityLevel.MODERATE
        return SeverityLevel.SEVERE
    if defect == DefectType.G5_BRAND_COLOR_VIOLATION:
        if severity <= 3:
            return SeverityLevel.MINOR
        if severity <= 12:
            return SeverityLevel.MODERATE
        return SeverityLevel.SEVERE
    if defect == DefectType.G6_MARGIN_VIOLATION:
        if severity <= 8:
            return SeverityLevel.MINOR
        if severity <= 16:
            return SeverityLevel.MODERATE
        return SeverityLevel.SEVERE
    if defect == DefectType.S4_DENSITY_RULE_VIOLATION:
        max_words = float(metadata.get("max_words", 60) or 60)
        over_ratio = max(0.0, (severity - max_words) / max_words)
        if over_ratio <= 0.2:
            return SeverityLevel.MINOR
        if over_ratio <= 0.5:
            return SeverityLevel.MODERATE
        return SeverityLevel.SEVERE
    # Current semantic injectors use a binary severity=1.0 label. Treat it as
    # moderate unless an injector metadata rubric says otherwise.
    return SeverityLevel.MODERATE


def _grid_level(value: float, *, minor_max: float, moderate_max: float) -> SeverityLevel:
    if value <= minor_max:
        return SeverityLevel.MINOR
    if value <= moderate_max:
        return SeverityLevel.MODERATE
    return SeverityLevel.SEVERE


def _evidence_from_label(defect: DefectType, targets: list[str], level: ExamLevel, metadata: dict[str, Any]) -> str:
    target_text = ", ".join(targets) if targets else ("deck" if level == ExamLevel.DECK else "slide")
    if defect == DefectType.S2_NARRATIVE_ORDER_BREAK:
        swapped = metadata.get("swapped_indices")
        return f"Page order is inconsistent around pages {swapped}; visible sequence includes {target_text}."
    if defect == DefectType.S3_TERMINOLOGY_INCONSISTENCY:
        canonical = metadata.get("canonical")
        variant = metadata.get("variant")
        page = metadata.get("slide_id")
        page_text = f" on page {page}" if page else ""
        return f"Terms {canonical!r} and {variant!r} both appear for the same entity{page_text}."
    if defect == DefectType.S5_MISSING_LOGIC_SECTION:
        section = metadata.get("missing_section") or (targets[0] if targets else "required section")
        return f"Required section {section!r} is absent from the visible deck outline."
    if defect == DefectType.S4_DENSITY_RULE_VIOLATION:
        words = metadata.get("target_words")
        limit = metadata.get("max_words")
        if words is not None and limit is not None:
            return f"Element {target_text} has {words} visible words, above the {limit}-word scene density limit."
        return f"Element {target_text} has visible text above the scene density limit."
    if defect == DefectType.S6_IMAGE_TEXT_CONTRADICTION:
        claim = metadata.get("diagram_claim")
        if claim:
            return f"Diagram/text elements {target_text} conflict: diagram claim {claim!r} and body text disagree."
        return f"Diagram/text elements {target_text} conflict in the visible slide content."
    if defect == DefectType.S1_TITLE_BODY_MISMATCH:
        return f"Title/body elements {target_text} describe different visible topics on the same slide."
    if defect == DefectType.G1_TEXT_OVERFLOW:
        amount = _format_measurement(metadata.get("overflow_px"), suffix=" px")
        return f"Element {target_text} text overflows its bounding box{amount} on the page."
    if defect == DefectType.G2_ELEMENT_OVERLAP:
        iou = _format_measurement(metadata.get("iou"), prefix=" with IoU ")
        return f"Elements {target_text} visibly overlap on the page{iou}."
    if defect == DefectType.G3_ALIGNMENT_OFFSET:
        amount = _format_measurement(metadata.get("offset_px"), suffix=" px")
        axis = metadata.get("axis")
        axis_text = f" on the {axis} axis" if axis else ""
        return f"Element {target_text} is offset from the visible alignment position{amount}{axis_text}."
    if defect == DefectType.G4_FONT_SIZE_INCONSISTENCY:
        amount = _format_measurement(metadata.get("delta_pt"), suffix=" pt")
        return f"Element {target_text} font size differs from peer text{amount}."
    if defect == DefectType.G5_BRAND_COLOR_VIOLATION:
        amount = _format_measurement(metadata.get("delta_e"), prefix=" by delta-E ")
        color = metadata.get("actual_color")
        color_text = f" {color}" if color else ""
        return f"Element {target_text} uses visible color{color_text} outside the brand palette{amount}."
    if defect == DefectType.G6_MARGIN_VIOLATION:
        amount = _format_measurement(metadata.get("bleed_px"), suffix=" px")
        side = metadata.get("side")
        side_text = f" {side}" if side else ""
        return f"Element {target_text} crosses the{side_text} safe margin{amount}."
    return f"Visible element {target_text} has a page-level layout problem in the rendered slide."


def _fix_from_label(defect: DefectType, targets: list[str], level: ExamLevel, metadata: dict[str, Any]) -> str:
    target_text = ", ".join(targets) if targets else ("deck" if level == ExamLevel.DECK else "slide")
    if defect == DefectType.G1_TEXT_OVERFLOW:
        return f"Shorten or resize text in {target_text} so it fits inside its bounding box."
    if defect == DefectType.G2_ELEMENT_OVERLAP:
        return f"Move or resize {target_text} so the elements no longer overlap."
    if defect == DefectType.G3_ALIGNMENT_OFFSET:
        return f"Realign {target_text} to the slide grid or placeholder position."
    if defect == DefectType.G4_FONT_SIZE_INCONSISTENCY:
        return f"Normalize font size for {target_text} against peer text elements."
    if defect == DefectType.G5_BRAND_COLOR_VIOLATION:
        return f"Restore {target_text} to the approved brand/theme color."
    if defect == DefectType.G6_MARGIN_VIOLATION:
        return f"Move {target_text} back inside the safe slide margin."
    if defect == DefectType.S2_NARRATIVE_ORDER_BREAK:
        return "Reorder the affected pages so the story follows the required background, problem, solution, and validation flow."
    if defect == DefectType.S3_TERMINOLOGY_INCONSISTENCY:
        return "Replace terminology variants with one canonical term across all affected pages."
    if defect == DefectType.S5_MISSING_LOGIC_SECTION:
        section = metadata.get("missing_section") or "missing required section"
        return f"Add a page or section covering {section!r}."
    return f"Revise {target_text} so the slide content matches the requested narrative and visible evidence."


def _validate_evidence_text(finding: Finding) -> None:
    text = finding.evidence.strip()
    if not text:
        raise ValueError("evidence must be non-empty")
    lowered = text.lower()
    for forbidden in _FORBIDDEN_EVIDENCE_PATTERNS:
        if forbidden.search(lowered):
            raise ValueError(f"evidence contains forbidden key {forbidden.pattern!r}")

    normalized = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    defect_words = re.sub(r"[^a-z0-9]+", " ", finding.type.value.lower()).strip()
    defect_tokens = set(defect_words.split())
    evidence_tokens = set(normalized.split())
    if normalized == defect_words or (evidence_tokens and evidence_tokens <= defect_tokens):
        raise ValueError("evidence cannot only restate the defect type")

    if _has_visible_fact(text, finding.locator):
        return
    raise ValueError("evidence must cite a visible fact such as a page, element, text, term, order, or conflict")


def _validate_fix_suggestion_text(value: str) -> None:
    text = value.strip()
    if not text:
        raise ValueError("fix_suggestion must be non-empty")
    if not re.search(
        r"\b(add|adjust|align|change|correct|move|normalize|realign|reduce|remove|replace|resize|restore|revise|reorder|shorten|split|update)\b",
        text,
        flags=re.IGNORECASE,
    ):
        raise ValueError("fix_suggestion must describe an executable action")


def _has_visible_fact(text: str, locator: Locator) -> bool:
    lowered = text.lower()
    candidates = [locator.page_id, locator.element_id, *locator.related_page_ids]
    if any(candidate and str(candidate).lower() in lowered for candidate in candidates):
        return True
    visible_patterns = (
        r"\bpage\s+\d+\b",
        r"\bpage order\b",
        r"\bsequence\b",
        r"\belement\s+[\w.-]+\b",
        r"\btitle/body\b",
        r"\bdiagram/text\b",
        r"\bvisible\s+(text|color|slide|deck|sequence)\b",
        r"\b(term|terms|terminology)\b",
        r"\b(conflict|contradict|overlap|margin|font|color|text|bounding box)\b",
        r"\b\d+(?:\.\d+)?\s*(px|pt|words?)\b",
        r"\biou\s+\d",
        r"'[^']+'",
        r"\"[^\"]+\"",
    )
    return any(re.search(pattern, lowered) for pattern in visible_patterns)


def _format_measurement(value: Any, *, prefix: str = " by ", suffix: str = "") -> str:
    if value is None:
        return ""
    try:
        text = f"{float(value):.3g}"
    except (TypeError, ValueError):
        text = str(value)
    return f"{prefix}{text}{suffix}"


_FORBIDDEN_EVIDENCE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bexpected_[a-z0-9_]*\b",
        r"\bdefect_type\b",
        r"\bseverity\b",
        r"\brepair_hint\b",
    )
)


def _clean_dimensions(active_labels: list[Any], scope: frozenset[DefectType]) -> list[Dimension]:
    active = {DefectType(label.type) for label in active_labels if label.type != "NO_DEFECT"}
    return [DEFECT_DIMENSIONS[item] for item in _sorted_defects(scope) if item not in active]


def _elements_from_slide(slide: Slide) -> list[Element]:
    return [_element_from_ir(element) for element in slide.elements]


def _element_from_ir(element: IrElement) -> Element:
    style = element.style or {}
    metadata = element.metadata or {}
    forbidden = FORBIDDEN_INPUT_KEYS.intersection(metadata)
    if forbidden:
        # Use oracle_view upstream; this guard keeps accidental raw IR out of B/C.
        safe_metadata = {key: value for key, value in metadata.items() if key not in FORBIDDEN_INPUT_KEYS}
    else:
        safe_metadata = metadata
    return Element(
        element_id=element.element_id,
        type=_element_type(element),
        bbox=_bbox_from_ir(element.bbox),
        text=element.text or None,
        font_size_pt=_optional_float(style.get("font_size_pt")),
        font_color_hex=_optional_str(style.get("color") or style.get("font_color_hex")),
        fill_color_hex=_optional_str(style.get("fill") or style.get("fill_color_hex")),
        font_family=_optional_str(style.get("font_family")),
        z_index=element.z,
        placeholder_role=_optional_str(element.placeholder_id or safe_metadata.get("role")),
        content_summary=_optional_str(safe_metadata.get("content_summary")),
    )


def _bbox_from_ir(bbox: BBox) -> BBoxPx:
    return BBoxPx(x=bbox.x, y=bbox.y, width=bbox.width, height=bbox.height)


def _element_type(element: IrElement) -> ElementType:
    value = (element.type or "").lower()
    try:
        return ElementType(value)
    except ValueError:
        role = str((element.metadata or {}).get("role", "")).lower()
        try:
            return ElementType(role)
        except ValueError:
            return ElementType.OTHER


def _sample_slide(manifest: ManifestSample) -> Slide | None:
    if manifest.slide is not None:
        return manifest.slide
    if manifest.oracle and "slide_id" in manifest.oracle:
        return Slide.from_mapping(oracle_view(manifest.oracle))
    return None


def _sample_deck(manifest: ManifestSample) -> Deck | None:
    if manifest.deck is not None:
        return manifest.deck
    if manifest.oracle and "deck_id" in manifest.oracle:
        return Deck.from_mapping(oracle_view(manifest.oracle))
    return None


def _title_text(slide: Slide) -> str | None:
    for element in slide.elements:
        role = str((element.metadata or {}).get("role", "")).lower()
        if element.type == "title" or role == "title":
            return element.text or None
    return None


def _visible_text(slide: Slide) -> str:
    return "\n".join(element.text for element in slide.elements if element.text)


def _key_terms(slide: Slide) -> list[str]:
    terms = slide.metadata.get("key_terms", [])
    if isinstance(terms, list):
        return [str(item) for item in terms]
    return []


def _figure_summaries(slide: Slide) -> list[str]:
    summaries = []
    for element in slide.elements:
        if element.type in {"image", "chart", "diagram"}:
            summary = element.metadata.get("content_summary") or element.metadata.get("diagram_claim") or element.text
            if summary:
                summaries.append(str(summary))
    return summaries


def _sample_image_base64(manifest: ManifestSample) -> str | None:
    path = manifest.image_path or manifest.metadata.get("defective_image_path")
    if not path:
        return None
    image_path = Path(path)
    if not image_path.exists():
        return None
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


def _page_image_base64s(manifest: ManifestSample) -> list[str]:
    paths = manifest.metadata.get("page_image_paths")
    if not isinstance(paths, list | tuple):
        return []
    images: list[str] = []
    for path in paths:
        image_path = Path(str(path))
        if image_path.exists():
            images.append(base64.b64encode(image_path.read_bytes()).decode("ascii"))
    return images


def _data_image_url(image_png_base64: str | None) -> str:
    if not image_png_base64:
        return "data:image/png;base64,"
    if image_png_base64.startswith("data:"):
        return image_png_base64
    return f"data:image/png;base64,{image_png_base64}"


def image_url_from_path(path: str | Path) -> str:
    value = str(path)
    if value.startswith(("http://", "https://", "data:")):
        return value
    file_path = Path(value)
    if not file_path.exists():
        return value
    mime = mimetypes.guess_type(file_path.name)[0] or "image/png"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _scene_from_metadata(metadata: dict[str, Any]) -> Scene:
    value = metadata.get("scene", Scene.FULL_PROPOSAL.value)
    try:
        return Scene(str(value))
    except ValueError:
        return Scene.FULL_PROPOSAL


def _load_json_object(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    text = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def normalize_modality(modality: Modality | str) -> Modality:
    if isinstance(modality, Modality):
        return modality
    value = str(modality)
    if value == "Bprime":
        value = Modality.B_CAPTION_ONLY.value
    return Modality(value)


def _validate_modality_payload(modality: Modality, image: str | None, elements: list[Element] | None) -> None:
    if modality in {Modality.A_IMAGE_ONLY, Modality.C_BOTH} and not image:
        raise ValueError("modality A/C requires image_png_base64")
    if modality in {Modality.B_STRUCT_ONLY, Modality.C_BOTH} and elements is None:
        raise ValueError("modality B/C requires elements")


def _validate_has_defect(has_defect: bool, findings: list[Finding]) -> None:
    if has_defect != bool(findings):
        raise ValueError("has_defect must equal bool(findings)")


def _coerce_defects(
    defects: list[DefectType | str] | None,
    default_scope: frozenset[DefectType],
) -> list[DefectType]:
    if defects is None:
        return _sorted_defects(default_scope)
    return [DefectType(item) for item in defects]


def _sorted_defects(defects: frozenset[DefectType] | set[DefectType]) -> list[DefectType]:
    return sorted(defects, key=lambda item: item.value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _list_str(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _glossary(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _list_str(item) for key, item in value.items()}
