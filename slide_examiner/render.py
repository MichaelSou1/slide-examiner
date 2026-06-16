from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import Slide


# Long-edge pixel sizes used for the Part 1 resolution ablation (SPEC §3.4).
RESOLUTION_LONG_EDGES: tuple[int, ...] = (768, 1024, 1536, 2048)


@dataclass(frozen=True)
class RenderResult:
    image_path: Path
    metadata: dict


@dataclass(frozen=True)
class RenderArtifact:
    """A single rendered image together with the render spec that produced it.

    The image, the render spec and the bbox scale all come from the *same*
    render so that bbox -> pixel conversion is exact (SPEC §3.4 / IO contract §3).
    """

    image_path: Path
    render_spec: dict
    long_edge: int
    slide_id: str


@dataclass(frozen=True)
class RenderQuality:
    image_path: str
    ok: bool
    checks: dict
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "ok": self.ok,
            "checks": self.checks,
            "issues": list(self.issues),
        }


# --------------------------------------------------------------------------- #
# HTML serialization
# --------------------------------------------------------------------------- #
_CONTAINER_TYPES = {"text", "textbox", "placeholder", "title", "body", "subtitle", "footer", "shape", "table", "chart"}


def slide_to_html(slide: Slide, *, scale: float = 1.0) -> str:
    """Serialize a slide to absolutely-positioned HTML.

    ``scale`` multiplies every geometric quantity (position, size and font
    size) so the same layout can be rasterized crisply at any resolution: the
    browser re-rasterizes vector text at the target pixel size instead of
    up/down-sampling a fixed bitmap.
    """

    elements = []
    for element in sorted(slide.elements, key=lambda item: item.z):
        style = (
            f"position:absolute;left:{element.bbox.x * scale}px;top:{element.bbox.y * scale}px;"
            f"width:{element.bbox.width * scale}px;height:{element.bbox.height * scale}px;"
            # nowrap so text wider than its box visibly spills past the edge
            # (a real G1 overflow) instead of silently wrapping inside it.
            "box-sizing:border-box;overflow:visible;white-space:nowrap;"
        )
        if "font_size_pt" in element.style:
            style += f"font-size:{float(element.style['font_size_pt']) * scale}pt;"
        if "color" in element.style:
            style += f"color:{element.style['color']};"
        # Give content blocks a visible container (honoring an explicit fill, else
        # a faint card). Without a drawn boundary, geometry defects are invisible:
        # text overflowing its box (G1) or two boxes colliding (G2) only read as
        # defects when the box edge is actually on screen, as on real slides.
        fill = element.style.get("fill_color") or element.style.get("background_color")
        if fill:
            style += f"background:{fill};"
        if element.type in _CONTAINER_TYPES or element.text:
            style += "border:1px solid #cdd3dc;"
            if not fill:
                # Translucent so two overlapping boxes (G2) blend into a visibly
                # darker intersection instead of one opaque card hiding another.
                style += "background:rgba(150,170,200,0.18);"
        text = _escape_html(element.text)
        elements.append(
            f'<div data-element-id="{element.element_id}" data-type="{element.type}" style="{style}">{text}</div>'
        )
    body_width = round(slide.width * scale)
    body_height = round(slide.height * scale)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        f'<body style="margin:0;width:{body_width}px;height:{body_height}px;position:relative;background:#ffffff;">'
        + "".join(elements)
        + "</body></html>"
    )


def render_slide_html_file(slide: Slide, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(slide_to_html(slide), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Render spec / geometry helpers (pure, no IO)
# --------------------------------------------------------------------------- #
def target_dimensions(width: int, height: int, long_edge: int) -> tuple[int, int]:
    """Scale (width, height) so the longer side equals ``long_edge`` px."""

    long_side = max(int(width), int(height))
    if long_side <= 0:
        raise ValueError("slide dimensions must be positive")
    if long_edge <= 0:
        raise ValueError("long_edge must be positive")
    scale = long_edge / long_side
    return max(1, round(width * scale)), max(1, round(height * scale))


def build_render_spec(
    *,
    slide_width: int,
    slide_height: int,
    image_width: int,
    image_height: int,
    renderer: str | None = None,
    dpi: float | None = None,
) -> dict:
    """Build a RenderSpec dict (IO contract §3) from the *actual* image size.

    ``scale_x``/``scale_y`` map a source slide unit to a rendered pixel, so a
    bbox is converted to pixel space by ``bbox * scale``. Computed from the real
    rendered dimensions, the spec can never silently disagree with the image.
    """

    if slide_width <= 0 or slide_height <= 0:
        raise ValueError("slide dimensions must be positive")
    return {
        "image_width_px": int(image_width),
        "image_height_px": int(image_height),
        "scale_x": image_width / float(slide_width),
        "scale_y": image_height / float(slide_height),
        "dpi": dpi,
        "renderer": renderer,
    }


def bbox_to_pixels(bbox, render_spec: dict) -> tuple[float, float, float, float]:
    """Convert an IR bbox to render-pixel (x, y, w, h) using the render spec."""

    sx = float(render_spec["scale_x"])
    sy = float(render_spec["scale_y"])
    return bbox.x * sx, bbox.y * sy, bbox.width * sx, bbox.height * sy


def image_size(path: str | Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size  # (width, height)


# --------------------------------------------------------------------------- #
# Browser rasterization
# --------------------------------------------------------------------------- #
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


@dataclass(frozen=True)
class _RasterJob:
    html: str
    output: Path
    width: int
    height: int


def _rasterize_jobs(jobs: list[_RasterJob]) -> list[Path]:
    if not jobs:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for raster rendering. Install playwright.") from exc

    rendered: list[Path] = []
    with sync_playwright() as playwright:
        browser, _ = _launch_chromium(playwright)
        try:
            for job in jobs:
                job.output.parent.mkdir(parents=True, exist_ok=True)
                html_path = job.output.with_suffix(".html")
                html_path.write_text(job.html, encoding="utf-8")
                page = browser.new_page(viewport={"width": job.width, "height": job.height})
                page.goto(html_path.resolve().as_uri())
                # full_page=False keeps the screenshot pinned to the viewport so its
                # dimensions exactly equal (width, height) and match the render spec.
                page.screenshot(path=str(job.output), full_page=False)
                page.close()
                rendered.append(job.output)
        finally:
            browser.close()
    return rendered


def render_slides_to_png(jobs, *, default_width: int = 1920, default_height: int = 1080) -> list[Path]:
    """Render many slides to PNG reusing a single browser.

    ``jobs`` is an iterable of ``(Slide, output_png_path)``. Launching one browser
    for the whole batch avoids paying the per-slide browser startup cost.
    """

    raster_jobs: list[_RasterJob] = []
    for slide, out in jobs:
        out_path = Path(out)
        width = int(slide.width or default_width)
        height = int(slide.height or default_height)
        raster_jobs.append(_RasterJob(html=slide_to_html(slide), output=out_path, width=width, height=height))
    return _rasterize_jobs(raster_jobs)


def render_slide_multi_resolution(
    slide: Slide,
    base_dir: str | Path,
    *,
    long_edges: tuple[int, ...] = RESOLUTION_LONG_EDGES,
    renderer: str = "playwright-chromium",
    filename: str = "image",
) -> list[RenderArtifact]:
    """Render a single slide at each long-edge resolution.

    Each resolution is a *true* render (coordinate-scaled HTML) rather than a
    resample of one bitmap, so up-scaled targets (e.g. 2048 from a 1920 slide)
    stay crisp. Returns one :class:`RenderArtifact` per resolution, each with a
    render spec read back from the bytes actually written.
    """

    base = Path(base_dir)
    jobs: list[_RasterJob] = []
    planned: list[tuple[int, Path]] = []
    for long_edge in long_edges:
        target_w, target_h = target_dimensions(slide.width, slide.height, long_edge)
        scale = long_edge / max(slide.width, slide.height)
        out = base / str(long_edge) / f"{filename}.png"
        jobs.append(_RasterJob(html=slide_to_html(slide, scale=scale), output=out, width=target_w, height=target_h))
        planned.append((long_edge, out))

    _rasterize_jobs(jobs)

    artifacts: list[RenderArtifact] = []
    for long_edge, out in planned:
        img_w, img_h = image_size(out)
        spec = build_render_spec(
            slide_width=slide.width,
            slide_height=slide.height,
            image_width=img_w,
            image_height=img_h,
            renderer=renderer,
        )
        artifacts.append(RenderArtifact(image_path=out, render_spec=spec, long_edge=long_edge, slide_id=slide.slide_id))
    return artifacts


# --------------------------------------------------------------------------- #
# Quality checks
# --------------------------------------------------------------------------- #
def _region_has_ink(image, box_px: tuple[int, int, int, int], *, background: int = 255, tol: int = 8) -> bool:
    """Whether a pixel region contains non-background content (rendered ink)."""

    left, top, right, bottom = box_px
    left = max(0, left)
    top = max(0, top)
    right = min(image.width, right)
    bottom = min(image.height, bottom)
    if right <= left or bottom <= top:
        return False
    crop = image.crop((left, top, right, bottom)).convert("L")
    extrema = crop.getextrema()  # (min, max)
    return (background - extrema[0]) > tol


def check_render_artifact(
    image_path: str | Path,
    slide: Slide,
    render_spec: dict,
    *,
    min_bytes: int = 256,
) -> RenderQuality:
    """Validate one rendered image against its slide + render spec.

    Covers SPEC §5 quality checks: image opens, has reasonable size, bbox not
    degenerate/out of bounds, and text elements actually have ink where their
    (scaled) bbox says they should be.
    """

    from PIL import Image

    issues: list[str] = []
    checks: dict = {}
    path = Path(image_path)

    checks["exists"] = path.exists()
    if not path.exists():
        return RenderQuality(str(path), False, checks, ("image does not exist",))

    size_bytes = path.stat().st_size
    checks["bytes"] = size_bytes
    if size_bytes < min_bytes:
        issues.append(f"file too small: {size_bytes} bytes < {min_bytes}")

    img_w = img_h = 0
    image = None
    try:
        with Image.open(path) as probe:
            probe.verify()
        image = Image.open(path)
        img_w, img_h = image.size
        checks["openable"] = True
    except Exception as exc:  # noqa: BLE001 - report any decode failure
        checks["openable"] = False
        issues.append(f"cannot open image: {exc}")
        return RenderQuality(str(path), False, checks, tuple(issues))

    checks["image_width_px"] = img_w
    checks["image_height_px"] = img_h
    dims_match = img_w == int(render_spec["image_width_px"]) and img_h == int(render_spec["image_height_px"])
    checks["dims_match_spec"] = dims_match
    if not dims_match:
        issues.append(
            f"image {img_w}x{img_h} != render spec "
            f"{render_spec['image_width_px']}x{render_spec['image_height_px']}"
        )

    text_elements = [el for el in slide.elements if (el.text or "").strip()]
    n_zero = 0
    n_oob = 0
    n_in_bounds = 0
    n_text_with_ink = 0
    for element in slide.elements:
        px_x, px_y, px_w, px_h = bbox_to_pixels(element.bbox, render_spec)
        if px_w <= 0 and px_h <= 0:
            n_zero += 1
        outside = px_x >= img_w or px_y >= img_h or (px_x + px_w) <= 0 or (px_y + px_h) <= 0
        if outside:
            n_oob += 1
        else:
            n_in_bounds += 1
        if (element.text or "").strip() and not outside:
            box = (int(px_x), int(px_y), int(px_x + max(1.0, px_w)), int(px_y + max(1.0, px_h)))
            if _region_has_ink(image, box):
                n_text_with_ink += 1

    image.close()

    checks["n_elements"] = len(slide.elements)
    checks["n_text_elements"] = len(text_elements)
    checks["n_zero_area"] = n_zero
    checks["n_out_of_bounds"] = n_oob
    checks["n_in_bounds"] = n_in_bounds
    checks["n_text_with_ink"] = n_text_with_ink

    if slide.elements and n_zero == len(slide.elements):
        issues.append("all element bboxes have zero area")
    if slide.elements and n_oob == len(slide.elements):
        issues.append("all element bboxes fall outside the image")
    if text_elements and n_text_with_ink == 0:
        issues.append("no text element has ink at its bbox (image/bbox misaligned?)")

    return RenderQuality(str(path), not issues, checks, tuple(issues))


def summarize_render_quality(qualities: list[RenderQuality]) -> dict:
    total = len(qualities)
    ok = sum(1 for q in qualities if q.ok)
    issue_counts: dict[str, int] = {}
    for quality in qualities:
        for issue in quality.issues:
            key = issue.split(":")[0]
            issue_counts[key] = issue_counts.get(key, 0) + 1
    return {
        "total": total,
        "ok": ok,
        "failed": total - ok,
        "issue_counts": issue_counts,
        "items": [q.to_dict() for q in qualities],
    }


# --------------------------------------------------------------------------- #
# PPTX / PDF rendering (LibreOffice + poppler)
# --------------------------------------------------------------------------- #
def _find_soffice() -> str | None:
    """Locate a LibreOffice launcher.

    Honors ``SLIDE_EXAMINER_SOFFICE`` so an extracted AppImage launcher (the
    self-contained ``.../program/soffice`` script, which needs no FUSE mount)
    can be used in environments where the bare AppImage cannot mount.
    """

    import os

    override = os.environ.get("SLIDE_EXAMINER_SOFFICE")
    if override and Path(override).exists():
        return override
    return shutil.which("libreoffice") or shutil.which("soffice")


def render_pptx_to_pdf(pptx_path: str | Path, output_dir: str | Path) -> Path:
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice/soffice is required for PPTX rendering.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    # --nolockcheck / --nodefault / --invisible keep headless conversion robust:
    # without them a stale profile lock surfaces as "source file could not be
    # loaded" or a bare exit 81 on some LibreOffice builds (notably AppImages).
    # start_new_session isolates the soffice.bin tree in its own process group.
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--invisible",
            "--nodefault",
            "--nolockcheck",
            "--nologo",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output),
            str(Path(pptx_path).resolve()),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    pdf_path = output / (Path(pptx_path).stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(
            f"LibreOffice did not produce expected PDF: {pdf_path}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return pdf_path


def _natural_page_key(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


def render_pdf_to_pngs(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = 150,
    prefix: str | None = None,
) -> list[Path]:
    """Rasterize each PDF page to a PNG with poppler ``pdftoppm``.

    ``pdftoppm`` zero-pads page numbers by total page count, so pages are
    returned in document order (verified numerically, not lexically).
    """

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("poppler 'pdftoppm' is required for PDF -> PNG rendering.")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = prefix or Path(pdf_path).stem
    base = out / stem
    subprocess.run(
        [pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(base)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pages = sorted(out.glob(f"{stem}-*.png"), key=_natural_page_key)
    return pages


def pdf_page_count(pdf_path: str | Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return None
    result = subprocess.run(
        [pdfinfo, str(pdf_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class PptxRenderResult:
    pptx_path: str
    pdf_path: str
    page_images: tuple[str, ...]
    page_count: int
    order_ok: bool

    def to_dict(self) -> dict:
        return {
            "pptx_path": self.pptx_path,
            "pdf_path": self.pdf_path,
            "page_images": list(self.page_images),
            "page_count": self.page_count,
            "order_ok": self.order_ok,
        }


def render_pptx_to_pngs(pptx_path: str | Path, output_dir: str | Path, *, dpi: int = 150) -> PptxRenderResult:
    """PPTX -> PDF (LibreOffice) -> ordered page PNGs (poppler).

    Verifies the number of rendered pages matches the PDF's reported page count
    so a multi-page deck cannot silently lose or reorder slides.
    """

    out = Path(output_dir)
    pdf = render_pptx_to_pdf(pptx_path, out)
    pages = render_pdf_to_pngs(pdf, out, dpi=dpi, prefix=Path(pptx_path).stem)
    expected = pdf_page_count(pdf)
    order_ok = bool(pages) and (expected is None or expected == len(pages))
    return PptxRenderResult(
        pptx_path=str(pptx_path),
        pdf_path=str(pdf),
        page_images=tuple(str(p) for p in pages),
        page_count=len(pages),
        order_ok=order_ok,
    )


# --------------------------------------------------------------------------- #
# Manifest rendering
# --------------------------------------------------------------------------- #
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
            # Render every page so deck-level modality A/C can send the full
            # ordered page sequence (not just the first slide).
            for page_index, slide in enumerate(deck.slides):
                jobs.append((slide, base / f"page_{page_index:03d}.png", index, f"page:{page_index}"))
    return jobs


def _slide_for_record(record: dict):
    from .schemas import Deck

    if record.get("slide"):
        return Slide.from_mapping(record["slide"])
    if record.get("deck"):
        deck = Deck.from_mapping(record["deck"])
        if deck.slides:
            return deck.slides[0]
    return None


def render_manifest(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    output_manifest: str | Path | None = None,
    render_clean: bool = True,
    long_edge: int | None = None,
    renderer: str = "playwright-chromium",
) -> Path:
    """Render images for every sample in a manifest and rewrite it with image
    paths and a ``RenderSpec``.

    Sets ``image_path`` and ``metadata/pair`` image paths (so modality A/C find
    the image), writes ``metadata['render']`` (so bbox -> pixel conversion is
    exact for modality B/C), and leaves ``slide``/``deck`` (structure) and
    ``caption`` (modality B') untouched. When ``long_edge`` is given, slides are
    rendered at that long-edge resolution; otherwise at native slide size.
    """

    from .io import read_jsonl, write_jsonl

    records = list(read_jsonl(manifest_path))
    jobs = plan_manifest_render_jobs(records, output_dir, render_clean=render_clean)

    raster_jobs: list[_RasterJob] = []
    job_outputs: list[tuple[Slide, Path, int, str]] = []
    for slide, png, index, kind in jobs:
        png = Path(png)
        if long_edge is not None:
            target_w, target_h = target_dimensions(slide.width, slide.height, long_edge)
            scale = long_edge / max(slide.width, slide.height)
        else:
            target_w, target_h = int(slide.width), int(slide.height)
            scale = 1.0
        raster_jobs.append(_RasterJob(html=slide_to_html(slide, scale=scale), output=png, width=target_w, height=target_h))
        job_outputs.append((slide, png, index, kind))

    _rasterize_jobs(raster_jobs)

    deck_pages: dict[int, dict[int, str]] = {}
    for slide, png, index, kind in job_outputs:
        record = records[index]
        metadata = dict(record.get("metadata") or {})
        pair = dict(record.get("pair") or {})
        img_w, img_h = image_size(png)
        spec = build_render_spec(
            slide_width=slide.width,
            slide_height=slide.height,
            image_width=img_w,
            image_height=img_h,
            renderer=renderer,
        )
        if kind.startswith("page:"):
            page_index = int(kind.split(":", 1)[1])
            deck_pages.setdefault(index, {})[page_index] = str(png)
            if page_index == 0:
                record["image_path"] = str(png)
                metadata["defective_image_path"] = str(png)
                metadata["render"] = spec
        elif kind == "defective":
            record["image_path"] = str(png)
            metadata["defective_image_path"] = str(png)
            metadata["render"] = spec
            pair["defective_image_path"] = str(png)
        else:
            metadata["clean_image_path"] = str(png)
            metadata["render_clean"] = spec
            pair["clean_image_path"] = str(png)
        record["metadata"] = metadata
        record["pair"] = pair

    # Write the ordered per-page image paths for deck samples so the contract
    # deck serializer can attach one image per page.
    for index, pages in deck_pages.items():
        metadata = dict(records[index].get("metadata") or {})
        metadata["page_image_paths"] = [pages[i] for i in sorted(pages)]
        records[index]["metadata"] = metadata

    target = Path(output_manifest) if output_manifest else Path(manifest_path)
    write_jsonl(records, target)
    return target


def render_manifest_resolutions(
    manifest_path: str | Path,
    output_root: str | Path,
    *,
    long_edges: tuple[int, ...] = RESOLUTION_LONG_EDGES,
    render_clean: bool = False,
    renderer: str = "playwright-chromium",
    quality_report: str | Path | None = None,
) -> dict:
    """Render a manifest at every resolution, emitting one manifest per
    resolution plus a quality report.

    Returns ``{"manifests": {long_edge: path}, "quality": {long_edge: summary}}``.
    Each per-resolution manifest carries ``image_path`` + ``metadata['render']``
    for that exact resolution, while structure/caption are preserved verbatim.
    """

    from .io import read_jsonl

    root = Path(output_root)
    manifests: dict[int, str] = {}
    quality: dict[int, dict] = {}
    base_records = list(read_jsonl(manifest_path))

    for long_edge in long_edges:
        res_dir = root / str(long_edge)
        res_manifest = res_dir / "manifest.jsonl"
        render_manifest(
            manifest_path,
            res_dir / "images",
            output_manifest=res_manifest,
            render_clean=render_clean,
            long_edge=long_edge,
            renderer=renderer,
        )
        manifests[long_edge] = str(res_manifest)

        qualities: list[RenderQuality] = []
        for record in read_jsonl(res_manifest):
            slide = _slide_for_record(record)
            image_path = record.get("image_path") or (record.get("metadata") or {}).get("defective_image_path")
            spec = (record.get("metadata") or {}).get("render")
            if slide is None or not image_path or not spec:
                continue
            qualities.append(check_render_artifact(image_path, slide, spec))
        quality[long_edge] = summarize_render_quality(qualities)

    result = {
        "source_manifest": str(manifest_path),
        "long_edges": list(long_edges),
        "records": len(base_records),
        "manifests": manifests,
        "quality": quality,
    }
    if quality_report is not None:
        report_path = Path(quality_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _escape_html(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
