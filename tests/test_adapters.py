import pytest

from slide_examiner.adapters import (
    JSON_RETRY_INSTRUCTION,
    MODALITIES,
    MockAdapter,
    build_probe_payload,
    complete_and_parse_with_retries,
    parse_examiner_json,
    payload_with_json_retry_instruction,
    validate_modality,
)
from slide_examiner.examiner_contract import Modality
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
    payload_bp = build_probe_payload(sample(), modality="B_prime", task="T3")
    assert payload_a["image_path"] == "render.png"
    assert "oracle" in payload_b
    assert payload_bp["caption"] == "A rendered title slide."


def test_modality_names_use_contract_values_with_legacy_alias() -> None:
    assert MODALITIES == ("A", "B", "B_prime", "C")
    assert Modality.B_CAPTION_ONLY.value == "B_prime"
    assert validate_modality("Bprime") == "B_prime"
    assert build_probe_payload(sample(), modality="Bprime", task="T1")["modality"] == "B_prime"


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


def test_retry_instruction_is_added_to_prompt_payload() -> None:
    retried = payload_with_json_retry_instruction({"prompt": "Inspect."})
    assert retried["prompt"].endswith(JSON_RETRY_INSTRUCTION)


def test_complete_and_parse_retries_once() -> None:
    seen_prompts = []

    def complete(payload):
        seen_prompts.append(payload.get("prompt", ""))
        if len(seen_prompts) == 1:
            return "not json"
        return '{"defects": [], "overall_score": 1.0}'

    parsed = complete_and_parse_with_retries({"prompt": "Inspect."}, complete)
    assert parsed["defects"] == []
    assert JSON_RETRY_INSTRUCTION in seen_prompts[1]
