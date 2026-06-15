import json

from slide_examiner.schemas import BBox, Deck, DefectLabel, Element, ManifestSample, Slide
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
    assert record["modality"] == "B"
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
    assert answer["findings"][0]["type"] == "G6_MARGIN_VIOLATION"
    assert answer["findings"][0]["severity"] == "moderate"


def test_build_pairwise_record() -> None:
    record = build_pairwise_record(sample())
    content = record["messages"][0]["content"]
    assert content[0]["image"] == "clean.png"
    assert content[1]["image"] == "defective.png"
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
    assert answer["better"] == "A"


def test_export_sft_jsonl(tmp_path) -> None:
    path = tmp_path / "sft.jsonl"
    count = export_sft_jsonl([sample()], path)
    assert count == 1
    assert json.loads(path.read_text(encoding="utf-8"))["sample_id"] == "sft1"


def test_no_defect_sft_record_has_empty_defects() -> None:
    record = build_pointwise_record(
        ManifestSample(sample_id="neg", image_path="clean.png", labels=(DefectLabel("NO_DEFECT", 0, ()),))
    )
    answer = json.loads(record["messages"][-1]["content"][0]["text"])
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
