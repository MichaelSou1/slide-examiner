from __future__ import annotations

import json
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


def _launch_chromium(playwright):
    """Launch Chromium, falling back to a system Chrome/Chromium when Playwright's
    bundled browser is not installed (e.g. its CDN is blocked behind a firewall)."""

    import os

    attempts: list[dict] = [{}, {"channel": "chrome"}, {"channel": "chromium"}]
    executable = (
        os.environ.get("SLIDE_EXAMINER_CHROME")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if executable:
        attempts.append({"executable_path": executable})

    last_exc: Exception | None = None
    for kwargs in attempts:
        try:
            return playwright.chromium.launch(**kwargs), (kwargs or {"bundled": True})
        except Exception as exc:  # noqa: BLE001 - probe each launch strategy
            last_exc = exc
    raise RuntimeError(
        "Could not launch a Chromium/Chrome browser for rendering. Install Playwright's "
        "chromium (`playwright install chromium`) or a system Chrome, or set "
        f"SLIDE_EXAMINER_CHROME to its path. Last error: {last_exc}"
    )


def render_html_to_png(html_path: str | Path, output_path: str | Path, *, width: int = 1920, height: int = 1080) -> RenderResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for HTML raster rendering. Install playwright and browsers.") from exc

    html = Path(html_path).resolve()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser, launch = _launch_chromium(playwright)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(html.as_uri())
        page.screenshot(path=str(output), full_page=True)
        browser.close()
    return RenderResult(image_path=output, metadata={"renderer": "playwright", "launch": launch, "width": width, "height": height})


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


def render_slides_to_png(jobs, *, default_width: int = 1920, default_height: int = 1080) -> list[Path]:
    """Render many slides to PNG reusing a single browser.

    ``jobs`` is an iterable of ``(Slide, output_png_path)``. Launching one browser
    for the whole batch avoids paying the per-slide browser startup cost.
    """

    job_list = [(slide, Path(out)) for slide, out in jobs]
    if not job_list:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for raster rendering. Install playwright.") from exc

    rendered: list[Path] = []
    with sync_playwright() as playwright:
        browser, _ = _launch_chromium(playwright)
        try:
            for slide, out in job_list:
                out.parent.mkdir(parents=True, exist_ok=True)
                html_path = out.with_suffix(".html")
                html_path.write_text(slide_to_html(slide), encoding="utf-8")
                width = int(slide.width or default_width)
                height = int(slide.height or default_height)
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(html_path.resolve().as_uri())
                page.screenshot(path=str(out), full_page=True)
                page.close()
                rendered.append(out)
        finally:
            browser.close()
    return rendered


def plan_manifest_render_jobs(records: list[dict], output_dir: str | Path, *, render_clean: bool = True) -> list[tuple]:
    """Collect (slide, png_path, record_index, kind) jobs for a manifest.

    Slide-level samples render the defective slide (and the clean slide when its
    saved IR is available); deck-level samples render the deck's first slide as a
    representative image. Pure/no-IO except reading the saved clean slide JSON.
    """

    from .schemas import Deck

    out = Path(output_dir)
    jobs: list[tuple] = []
    for index, record in enumerate(records):
        sample_id = str(record.get("sample_id", index))
        base = out / sample_id
        if record.get("slide"):
            slide = Slide.from_mapping(record["slide"])
            jobs.append((slide, base / "defective.png", index, "defective"))
            if render_clean:
                clean_path = (record.get("metadata") or {}).get("clean_slide_path") or (record.get("pair") or {}).get("clean_slide_path")
                if clean_path and Path(clean_path).exists():
                    clean = Slide.from_mapping(json.loads(Path(clean_path).read_text(encoding="utf-8")))
                    jobs.append((clean, base / "clean.png", index, "clean"))
        elif record.get("deck"):
            deck = Deck.from_mapping(record["deck"])
            if deck.slides:
                jobs.append((deck.slides[0], base / "defective.png", index, "defective"))
    return jobs


def render_manifest(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    output_manifest: str | Path | None = None,
    render_clean: bool = True,
) -> Path:
    """Render images for every sample in a manifest and rewrite it with image paths.

    Sets ``image_path`` and ``metadata/pair.defective_image_path`` (and the clean
    counterparts) so SFT export and modality-A probing have real rendered images.
    """

    from .io import read_jsonl, write_jsonl

    records = list(read_jsonl(manifest_path))
    jobs = plan_manifest_render_jobs(records, output_dir, render_clean=render_clean)
    render_slides_to_png([(slide, png) for slide, png, _, _ in jobs])

    for _slide, png, index, kind in jobs:
        record = records[index]
        metadata = dict(record.get("metadata") or {})
        pair = dict(record.get("pair") or {})
        if kind == "defective":
            record["image_path"] = str(png)
            metadata["defective_image_path"] = str(png)
            pair["defective_image_path"] = str(png)
        else:
            metadata["clean_image_path"] = str(png)
            pair["clean_image_path"] = str(png)
        record["metadata"] = metadata
        record["pair"] = pair

    target = Path(output_manifest) if output_manifest else Path(manifest_path)
    write_jsonl(records, target)
    return target

