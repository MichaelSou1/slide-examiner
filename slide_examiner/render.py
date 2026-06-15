from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .schemas import Slide


@dataclass(frozen=True)
class RenderResult:
    image_path: Path
    metadata: dict


def slide_to_html(slide: Slide) -> str:
    elements = []
    for element in sorted(slide.elements, key=lambda item: item.z):
        style = (
            f"position:absolute;left:{element.bbox.x}px;top:{element.bbox.y}px;"
            f"width:{element.bbox.width}px;height:{element.bbox.height}px;"
            "box-sizing:border-box;overflow:visible;"
        )
        if "font_size_pt" in element.style:
            style += f"font-size:{element.style['font_size_pt']}pt;"
        if "color" in element.style:
            style += f"color:{element.style['color']};"
        text = _escape_html(element.text)
        elements.append(
            f'<div data-element-id="{element.element_id}" data-type="{element.type}" style="{style}">{text}</div>'
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        f'<body style="margin:0;width:{slide.width}px;height:{slide.height}px;position:relative;">'
        + "".join(elements)
        + "</body></html>"
    )


def render_slide_html_file(slide: Slide, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(slide_to_html(slide), encoding="utf-8")
    return path


def render_html_to_png(html_path: str | Path, output_path: str | Path, *, width: int = 1920, height: int = 1080) -> RenderResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for HTML raster rendering. Install playwright and browsers.") from exc

    html = Path(html_path).resolve()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(html.as_uri())
        page.screenshot(path=str(output), full_page=True)
        browser.close()
    return RenderResult(image_path=output, metadata={"renderer": "playwright", "width": width, "height": height})


def render_pptx_to_pdf(pptx_path: str | Path, output_dir: str | Path) -> Path:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise RuntimeError("LibreOffice/soffice is required for PPTX rendering.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output), str(pptx_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pdf_path = output / (Path(pptx_path).stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not produce expected PDF: {pdf_path}")
    return pdf_path


def _escape_html(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

