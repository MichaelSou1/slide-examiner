from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .render import render_slide_html_file
from .schemas import BBox, Deck, Element, Slide


@dataclass(frozen=True)
class PromptModules:
    scenario_classifier: str = ""
    page_type_instructions: str = ""
    component_library: str = ""
    quality_checklist: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "scenario_classifier": self.scenario_classifier,
            "page_type_instructions": self.page_type_instructions,
            "component_library": self.component_library,
            "quality_checklist": self.quality_checklist,
        }


def deck_from_content_json(content: dict[str, Any], *, prompt_modules: PromptModules | None = None) -> Deck:
    modules = prompt_modules or PromptModules()
    deck_id = str(content.get("deck_id", "generated_deck"))
    slides: list[Slide] = []
    for index, page in enumerate(content.get("slides", []), start=1):
        title = str(page.get("title", f"Slide {index}"))
        bullets = [str(item) for item in page.get("bullets", [])]
        section = page.get("section")
        elements = [
            Element(
                element_id=f"s{index}_title",
                type="title",
                bbox=BBox(96, 72, 1728, 72),
                text=title,
                style={"font_size_pt": 34, "color": "#111111"},
                metadata={"role": "title", "text_level": "title"},
            )
        ]
        for bullet_index, bullet in enumerate(bullets):
            elements.append(
                Element(
                    element_id=f"s{index}_body{bullet_index}",
                    type="text",
                    bbox=BBox(144, 180 + bullet_index * 92, 1512, 72),
                    text=bullet,
                    style={"font_size_pt": 22, "color": "#222222"},
                    metadata={"role": "body", "text_level": "body"},
                )
            )
        slides.append(
            Slide(
                slide_id=f"{deck_id}_{index}",
                elements=tuple(elements),
                metadata={"section": section, "page_type": page.get("page_type"), "prompt_modules": modules.to_dict()},
            )
        )
    return Deck(
        deck_id=deck_id,
        slides=tuple(slides),
        metadata={
            "scenario": content.get("scenario"),
            "required_sections": content.get("required_sections", []),
            "prompt_modules": modules.to_dict(),
        },
    )


def load_content_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_deck_html(deck: Deck, output_dir: str | Path) -> list[Path]:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, slide in enumerate(deck.slides, start=1):
        paths.append(render_slide_html_file(slide, base / f"{index:03d}_{slide.slide_id}.html"))
    return paths


def export_deck_pptx(deck: Deck, output_path: str | Path) -> Path:
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
    except ImportError as exc:
        raise RuntimeError("python-pptx is required for PPTX export.") from exc

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    for slide_ir in deck.slides:
        ppt_slide = prs.slides.add_slide(blank)
        for element in slide_ir.elements:
            left = Inches(element.bbox.x / slide_ir.width * 13.333)
            top = Inches(element.bbox.y / slide_ir.height * 7.5)
            width = Inches(element.bbox.width / slide_ir.width * 13.333)
            height = Inches(element.bbox.height / slide_ir.height * 7.5)
            box = ppt_slide.shapes.add_textbox(left, top, width, height)
            box.text = element.text
            for paragraph in box.text_frame.paragraphs:
                for run in paragraph.runs:
                    if "font_size_pt" in element.style:
                        run.font.size = Pt(float(element.style["font_size_pt"]))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    return output

