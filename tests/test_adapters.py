import pytest

from slide_examiner.adapters import MockAdapter, build_probe_payload, parse_examiner_json
from slide_examiner.schemas import DefectLabel, ManifestSample


def sample() -> ManifestSample:
    return ManifestSample(
        sample_id="m1",
        image_path="render.png",
        oracle={"elements": []},
        caption="A rendered title slide.",
        labels=(DefectLabel("G1_TEXT_OVERFLOW", 16, ("title",)),),
    )


def test_parse_examiner_json_from_fenced_block() -> None:
    parsed = parse_examiner_json(
        """```json
        {"defects":[{"type":"G1_TEXT_OVERFLOW","element_ids":["title"],"severity":16}],"overall_score":0.2}
        ```"""
    )
    assert parsed["defects"][0]["element_ids"] == ["title"]
    assert parsed["overall_score"] == 0.2


def test_parse_examiner_json_rejects_missing_json() -> None:
    with pytest.raises(ValueError):
        parse_examiner_json("no structured answer here")


def test_build_probe_payload_modalities() -> None:
    payload_a = build_probe_payload(sample(), modality="A", task="T1")
    payload_b = build_probe_payload(sample(), modality="B", task="T2")
    payload_bp = build_probe_payload(sample(), modality="Bprime", task="T3")
    assert payload_a["image_path"] == "render.png"
    assert "oracle" in payload_b
    assert payload_bp["caption"] == "A rendered title slide."


def test_mock_adapter_echoes_labels() -> None:
    payload = build_probe_payload(sample(), modality="A", task="T1")
    output = MockAdapter().examine(payload)
    assert output["defects"][0]["type"] == "G1_TEXT_OVERFLOW"


def test_mock_adapter_can_simulate_missed_modality() -> None:
    payload = build_probe_payload(sample(), modality="A", task="T1")
    output = MockAdapter(miss_modalities={"A"}).examine(payload)
    assert output["defects"] == []


def test_mock_adapter_treats_no_defect_as_negative() -> None:
    payload = build_probe_payload(
        ManifestSample(sample_id="neg", labels=(DefectLabel("NO_DEFECT", 0, ()),)),
        modality="A",
        task="T1",
    )
    output = MockAdapter().examine(payload)
    assert output["defects"] == []
    assert output["overall_score"] == 1.0
