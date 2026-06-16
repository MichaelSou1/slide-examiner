import json

from slide_examiner.schemas import BBox, DefectLabel, Element, ManifestSample, Slide
from slide_examiner.render import plan_manifest_render_jobs
from slide_examiner.sft import (
    build_llamafactory_record,
    export_llamafactory_jsonl,
    write_llamafactory_dataset_info,
)


def _slide() -> Slide:
    return Slide("s1", (Element("t", "text", BBox(0, 0, 100, 40), text="hi"),))


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


def test_plan_render_jobs_deck_first_slide(tmp_path):
    record = {"sample_id": "y", "deck": {"deck_id": "d", "slides": [_slide().to_dict()], "metadata": {}}}
    jobs = plan_manifest_render_jobs([record], tmp_path / "imgs", render_clean=False)
    assert len(jobs) == 1 and jobs[0][3] == "defective"


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
