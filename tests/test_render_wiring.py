import json

import pytest

from slide_examiner.schemas import BBox, DefectLabel, Element, ManifestSample, Slide
from slide_examiner.render import (
    RESOLUTION_LONG_EDGES,
    _natural_page_key,
    bbox_to_pixels,
    build_render_spec,
    check_render_artifact,
    plan_manifest_render_jobs,
    summarize_render_quality,
    target_dimensions,
)
from slide_examiner.sft import (
    build_llamafactory_record,
    export_llamafactory_jsonl,
    write_llamafactory_dataset_info,
)


def _slide() -> Slide:
    return Slide("s1", (Element("t", "text", BBox(0, 0, 100, 40), text="hi"),))


def _png(path, size, boxes=()):  # white canvas with optional black filled boxes
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle(box, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def test_plan_render_jobs_slide_with_clean(tmp_path):
    clean_path = tmp_path / "clean.json"
    clean_path.write_text(json.dumps(_slide().to_dict()), encoding="utf-8")
    record = {
        "sample_id": "x",
        "slide": _slide().to_dict(),
        "metadata": {"clean_slide_path": str(clean_path)},
    }
    jobs = plan_manifest_render_jobs([record], tmp_path / "imgs")
    assert sorted(kind for _s, _p, _i, kind in jobs) == ["clean", "defective"]
    assert all(index == 0 for _s, _p, index, _k in jobs)


def test_plan_render_jobs_skips_missing_clean(tmp_path):
    record = {"sample_id": "x", "slide": _slide().to_dict(), "metadata": {}}
    jobs = plan_manifest_render_jobs([record], tmp_path / "imgs")
    assert [kind for *_x, kind in jobs] == ["defective"]


def test_plan_render_jobs_deck_all_pages(tmp_path):
    record = {"sample_id": "y", "deck": {"deck_id": "d", "slides": [_slide().to_dict(), _slide().to_dict()], "metadata": {}}}
    jobs = plan_manifest_render_jobs([record], tmp_path / "imgs", render_clean=False)
    # Every deck page is rendered so deck modality A/C can send the full sequence.
    assert [job[3] for job in jobs] == ["page:0", "page:1"]
    assert all(rec_index == 0 for *_x, rec_index, _kind in jobs)


def test_llamafactory_record_requires_image(tmp_path):
    label = DefectLabel("G1_TEXT_OVERFLOW", 16.0, ("t",))
    assert build_llamafactory_record(ManifestSample(sample_id="z", labels=(label,))) is None

    image = tmp_path / "x.png"
    image.write_bytes(b"png")
    sample = ManifestSample(sample_id="z", image_path=str(image), labels=(label,))
    record = build_llamafactory_record(sample)
    assert record["images"] == [str(image)]
    assert "<image>" in record["messages"][0]["content"]
    assert record["messages"][0]["role"] == "user"
    assert record["messages"][1]["role"] == "assistant"
    answer = json.loads(record["messages"][1]["content"])
    assert answer["findings"][0]["type"] == "G1_TEXT_OVERFLOW"
    assert answer["findings"][0]["severity"] == "moderate"


def test_export_llamafactory_jsonl_skips_imageless_and_writes_info(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"png")
    samples = [
        {
            "sample_id": "a",
            "image_path": str(image),
            "labels": [{"type": "G1_TEXT_OVERFLOW", "severity": 16, "target_element_ids": ["t"]}],
        },
        {  # no image -> skipped
            "sample_id": "b",
            "labels": [{"type": "G2_ELEMENT_OVERLAP", "severity": 0.2, "target_element_ids": ["x", "y"]}],
        },
    ]
    out = tmp_path / "sft_lf.jsonl"
    count = export_llamafactory_jsonl(samples, out)
    assert count == 1
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 1
    info = json.loads((tmp_path / "dataset_info.json").read_text(encoding="utf-8"))
    assert info["slide_examiner"]["formatting"] == "sharegpt"
    assert info["slide_examiner"]["columns"]["images"] == "images"


# --------------------------------------------------------------------------- #
# Resolution math + render spec
# --------------------------------------------------------------------------- #
def test_target_dimensions_long_edge_16x9():
    assert target_dimensions(1920, 1080, 768) == (768, 432)
    assert target_dimensions(1920, 1080, 1024) == (1024, 576)
    assert target_dimensions(1920, 1080, 1536) == (1536, 864)
    assert target_dimensions(1920, 1080, 2048) == (2048, 1152)


def test_target_dimensions_uses_long_side_for_portrait():
    # long edge is the height here, so height should equal the requested size
    assert target_dimensions(1080, 1920, 768) == (432, 768)


def test_resolution_long_edges_constant():
    assert RESOLUTION_LONG_EDGES == (768, 1024, 1536, 2048)


def test_build_render_spec_scale_and_dims():
    spec = build_render_spec(
        slide_width=1920, slide_height=1080, image_width=1024, image_height=576, renderer="playwright-chromium"
    )
    assert spec["image_width_px"] == 1024
    assert spec["image_height_px"] == 576
    assert spec["scale_x"] == pytest.approx(1024 / 1920)
    assert spec["scale_y"] == pytest.approx(576 / 1080)
    assert spec["renderer"] == "playwright-chromium"


def test_bbox_to_pixels_uses_same_scale():
    spec = build_render_spec(slide_width=1920, slide_height=1080, image_width=960, image_height=540)
    px = bbox_to_pixels(BBox(100, 200, 400, 80), spec)
    assert px == pytest.approx((50.0, 100.0, 200.0, 40.0))


def test_natural_page_key_orders_numerically(tmp_path):
    from pathlib import Path

    names = [Path(f"deck-{n:02d}.png") for n in (1, 2, 10, 11)]
    assert [_natural_page_key(p) for p in names] == [1, 2, 10, 11]
    # lexical order would already match here; ensure double-digit beats single
    assert _natural_page_key(Path("deck-3.png")) < _natural_page_key(Path("deck-12.png"))


# --------------------------------------------------------------------------- #
# Quality checks
# --------------------------------------------------------------------------- #
def test_check_render_artifact_passes_when_text_has_ink(tmp_path):
    slide = Slide("s1", (Element("t", "text", BBox(10, 10, 100, 40), text="hi"),), width=200, height=100)
    spec = build_render_spec(slide_width=200, slide_height=100, image_width=200, image_height=100)
    image = _png(tmp_path / "ok.png", (200, 100), boxes=[(12, 12, 90, 45)])
    quality = check_render_artifact(image, slide, spec)
    assert quality.ok, quality.issues
    assert quality.checks["dims_match_spec"] is True
    assert quality.checks["n_text_with_ink"] == 1


def test_check_render_artifact_flags_dims_mismatch(tmp_path):
    slide = Slide("s1", (Element("t", "text", BBox(10, 10, 100, 40), text="hi"),), width=200, height=100)
    spec = build_render_spec(slide_width=200, slide_height=100, image_width=200, image_height=100)
    image = _png(tmp_path / "small.png", (100, 50), boxes=[(5, 5, 40, 20)])
    quality = check_render_artifact(image, slide, spec)
    assert not quality.ok
    assert any("render spec" in issue for issue in quality.issues)


def test_check_render_artifact_flags_missing_ink(tmp_path):
    slide = Slide("s1", (Element("t", "text", BBox(10, 10, 100, 40), text="hi"),), width=200, height=100)
    spec = build_render_spec(slide_width=200, slide_height=100, image_width=200, image_height=100)
    image = _png(tmp_path / "blank.png", (200, 100))  # all white, no ink
    quality = check_render_artifact(image, slide, spec)
    assert not quality.ok
    assert any("ink" in issue for issue in quality.issues)
    assert quality.checks["n_text_with_ink"] == 0


def test_check_render_artifact_flags_out_of_bounds(tmp_path):
    slide = Slide("s1", (Element("t", "text", BBox(500, 500, 50, 50), text="x"),), width=200, height=100)
    spec = build_render_spec(slide_width=200, slide_height=100, image_width=200, image_height=100)
    image = _png(tmp_path / "oob.png", (200, 100), boxes=[(5, 5, 40, 20)])
    quality = check_render_artifact(image, slide, spec)
    assert not quality.ok
    assert any("outside" in issue for issue in quality.issues)
    assert quality.checks["n_out_of_bounds"] == 1


def test_summarize_render_quality_counts(tmp_path):
    slide = Slide("s1", (Element("t", "text", BBox(10, 10, 100, 40), text="hi"),), width=200, height=100)
    spec = build_render_spec(slide_width=200, slide_height=100, image_width=200, image_height=100)
    good = check_render_artifact(_png(tmp_path / "g.png", (200, 100), boxes=[(12, 12, 90, 45)]), slide, spec)
    bad = check_render_artifact(_png(tmp_path / "b.png", (200, 100)), slide, spec)
    summary = summarize_render_quality([good, bad])
    assert summary["total"] == 2
    assert summary["ok"] == 1
    assert summary["failed"] == 1
