import json

import pytest

from slide_examiner.examiner_contract import (
    DeckExamResult,
    PageExamResult,
    PairwiseResult,
    parse_deck_result,
    parse_page_result,
)
from slide_examiner.schemas import BBox, Deck, DefectLabel, Element, ManifestSample, Slide
from slide_examiner.sft import (
    build_pairwise_record,
    build_pointwise_record,
    export_sft_jsonl,
    export_sft_jsonl_with_stats,
    parse_sft_assistant,
)


def sample() -> ManifestSample:
    return ManifestSample(
        sample_id="sft1",
        image_path="defective.png",
        labels=(DefectLabel("G6_MARGIN_VIOLATION", 12, ("logo",)),),
        pair={"clean_image_path": "clean.png", "defective_image_path": "defective.png"},
    )


def test_build_pointwise_record() -> None:
    record = build_pointwise_record(sample())
    assert record["modality"] == "B"
    assert record["metadata"]["modality"] == "B"
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
    assert answer["findings"][0]["type"] == "G6_MARGIN_VIOLATION"
    assert answer["findings"][0]["severity"] == "moderate"


def test_build_pairwise_record() -> None:
    record = build_pairwise_record(sample())
    assert record["exam_level"] == "PairwiseResult"
    assert record["metadata"]["modality"] == "A"
    content = record["messages"][0]["content"]
    assert content[0]["image_url"]["url"] == "clean.png"
    assert content[1]["image_url"]["url"] == "defective.png"
    assert "CANDIDATE_B_CONTRACT_VIEW" in content[2]["text"]
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
    assert answer["better"] == "A"


def test_export_sft_jsonl(tmp_path) -> None:
    path = tmp_path / "sft.jsonl"
    count = export_sft_jsonl([sample()], path, min_a_image_only_ratio=0)
    assert count == 1
    assert json.loads(path.read_text(encoding="utf-8"))["sample_id"] == "sft1"


def test_pointwise_export_assigns_at_least_30_percent_a_and_writes_parse_summary(tmp_path) -> None:
    image_paths = []
    for index in range(10):
        path = tmp_path / f"{index}.png"
        path.write_bytes(b"png")
        image_paths.append(path)
    samples = [
        ManifestSample(
            sample_id=f"s{index}",
            slide=Slide(f"p{index}", (Element("logo", "shape", BBox(0, 0, 100, 40)),)),
            image_path=str(image_paths[index]),
            labels=(DefectLabel("G6_MARGIN_VIOLATION", 32, ("logo",), {"bleed_px": 32, "side": "left"}),),
        )
        for index in range(10)
    ]

    out = tmp_path / "sft.jsonl"
    summary = tmp_path / "parse_summary.json"
    stats = export_sft_jsonl_with_stats(samples, out, parse_summary_path=summary)
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    assert stats.record_count == 10
    assert stats.parse_failures == 0
    assert stats.modality_counts["A"] >= 3
    assert sum(record["metadata"]["modality"] == "A" for record in records) >= 3
    assert json.loads(summary.read_text(encoding="utf-8"))["parse_failures"] == 0
    assert all(isinstance(parse_sft_assistant(record), PageExamResult) for record in records)


def test_pointwise_export_enforces_a_ratio_separately_for_page_and_deck(tmp_path) -> None:
    deck = Deck(
        deck_id="deck1",
        slides=(
            Slide("p1", (Element("t1", "title", BBox(0, 0, 100, 40), text="Problem"),)),
            Slide("p2", (Element("t2", "title", BBox(0, 0, 100, 40), text="Solution"),)),
        ),
    )
    samples = []
    for level in ("page", "deck"):
        for index in range(4):
            image = tmp_path / f"{level}-{index}.png"
            image.write_bytes(b"png")
            if level == "page":
                samples.append(
                    ManifestSample(
                        sample_id=f"page-{index}",
                        slide=Slide(f"page-{index}", (Element("logo", "shape", BBox(0, 0, 100, 40)),)),
                        image_path=str(image),
                        labels=(DefectLabel("G6_MARGIN_VIOLATION", 32, ("logo",), {"bleed_px": 32}),),
                    )
                )
            else:
                samples.append(
                    ManifestSample(
                        sample_id=f"deck-{index}",
                        deck=deck,
                        image_path=str(image),
                        labels=(DefectLabel("S2_NARRATIVE_ORDER_BREAK", 1, ("p2", "p1"), {"swapped_indices": [0, 1]}),),
                    )
                )

    out = tmp_path / "mixed.jsonl"
    export_sft_jsonl_with_stats(samples, out)
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    for level in ("page", "deck"):
        level_records = [record for record in records if record["metadata"]["level"] == level]
        assert len(level_records) == 4
        assert sum(record["metadata"]["modality"] == "A" for record in level_records) >= 2


def test_deck_and_pairwise_sft_assistant_roundtrip_parser() -> None:
    deck = Deck(
        deck_id="deck1",
        slides=(
            Slide("p1", (Element("t1", "title", BBox(0, 0, 100, 40), text="Problem"),)),
            Slide("p2", (Element("t2", "title", BBox(0, 0, 100, 40), text="Solution"),)),
        ),
    )
    sample = ManifestSample(
        sample_id="deck-s2",
        deck=deck,
        labels=(DefectLabel("S2_NARRATIVE_ORDER_BREAK", 1, ("p2", "p1"), {"swapped_indices": [0, 1]}),),
    )

    pointwise = build_pointwise_record(sample)
    pairwise = build_pairwise_record(sample)

    assert isinstance(parse_sft_assistant(pointwise), DeckExamResult)
    assert isinstance(parse_deck_result(pointwise["messages"][-1]["content"][0]["text"]), DeckExamResult)
    assert isinstance(parse_sft_assistant(pairwise), PairwiseResult)
    assert isinstance(PairwiseResult.model_validate_json(pairwise["messages"][-1]["content"][0]["text"]), PairwiseResult)


def test_pointwise_export_rejects_a_ratio_when_images_are_missing(tmp_path) -> None:
    with pytest.raises(ValueError, match="A_IMAGE_ONLY requires"):
        export_sft_jsonl_with_stats([sample()], tmp_path / "sft.jsonl")


def test_no_defect_sft_record_has_empty_defects() -> None:
    record = build_pointwise_record(
        ManifestSample(sample_id="neg", image_path="clean.png", labels=(DefectLabel("NO_DEFECT", 0, ()),))
    )
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
    assert isinstance(parse_page_result(record["messages"][-1]["content"][0]["text"]), PageExamResult)
    assert answer["findings"] == []
    assert answer["has_defect"] is False

    pairwise = build_pairwise_record(
        ManifestSample(sample_id="neg", image_path="clean.png", labels=(DefectLabel("NO_DEFECT", 0, ()),))
    )
    pairwise_answer = json.loads(pairwise["messages"][1]["content"][0]["text"])
    assert pairwise_answer["better"] == "tie"


def test_deck_sft_record_uses_deck_result() -> None:
    deck = Deck(
        deck_id="deck1",
        slides=(
            Slide("p1", (Element("t1", "title", BBox(0, 0, 100, 40), text="Problem"),)),
            Slide("p2", (Element("t2", "title", BBox(0, 0, 100, 40), text="Solution"),)),
        ),
    )
    record = build_pointwise_record(
        ManifestSample(
            sample_id="deck-s2",
            deck=deck,
            labels=(DefectLabel("S2_NARRATIVE_ORDER_BREAK", 1, ("p2", "p1"), {"swapped_indices": [0, 1]}),),
        )
    )
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
    assert record["exam_level"] == "DeckExamResult"
    assert answer["deck_id"] == "deck1"
    assert answer["findings"][0]["locator"]["level"] == "deck"
