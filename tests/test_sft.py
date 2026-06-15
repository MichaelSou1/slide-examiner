import json

from slide_examiner.schemas import DefectLabel, ManifestSample
from slide_examiner.sft import build_pairwise_record, build_pointwise_record, export_sft_jsonl


def sample() -> ManifestSample:
    return ManifestSample(
        sample_id="sft1",
        image_path="defective.png",
        labels=(DefectLabel("G6_MARGIN_VIOLATION", 12, ("logo",)),),
        pair={"clean_image_path": "clean.png", "defective_image_path": "defective.png"},
    )


def test_build_pointwise_record() -> None:
    record = build_pointwise_record(sample())
    assert record["messages"][0]["content"][0]["image"] == "defective.png"
    answer = json.loads(record["messages"][1]["content"][0]["text"])
    assert answer["defects"][0]["type"] == "G6_MARGIN_VIOLATION"


def test_build_pairwise_record() -> None:
    record = build_pairwise_record(sample())
    content = record["messages"][0]["content"]
    assert content[0]["image"] == "clean.png"
    assert content[1]["image"] == "defective.png"
    answer = json.loads(record["messages"][1]["content"][0]["text"])
    assert answer["pairwise_winner"] == "clean"


def test_export_sft_jsonl(tmp_path) -> None:
    path = tmp_path / "sft.jsonl"
    count = export_sft_jsonl([sample()], path)
    assert count == 1
    assert json.loads(path.read_text(encoding="utf-8"))["sample_id"] == "sft1"


def test_no_defect_sft_record_has_empty_defects() -> None:
    record = build_pointwise_record(
        ManifestSample(sample_id="neg", image_path="clean.png", labels=(DefectLabel("NO_DEFECT", 0, ()),))
    )
    answer = json.loads(record["messages"][1]["content"][0]["text"])
    assert answer["defects"] == []
    assert answer["overall_score"] == 1.0

    pairwise = build_pairwise_record(
        ManifestSample(sample_id="neg", image_path="clean.png", labels=(DefectLabel("NO_DEFECT", 0, ()),))
    )
    pairwise_answer = json.loads(pairwise["messages"][1]["content"][0]["text"])
    assert pairwise_answer["pairwise_winner"] == "tie"
