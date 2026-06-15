from slide_examiner.distribution import summarize_linter_distribution, summarize_manifest_distribution
from slide_examiner.schemas import BBox, DefectLabel, Element, ManifestSample, Slide


def test_summarize_manifest_distribution() -> None:
    summary = summarize_manifest_distribution(
        [
            ManifestSample(
                sample_id="s1",
                labels=(DefectLabel("G1_TEXT_OVERFLOW", 8, ("title",)),),
                metadata={"split": "train", "template_condition": "freeform"},
            ),
            ManifestSample(
                sample_id="s2",
                labels=(DefectLabel("NO_DEFECT", 0, ()),),
                metadata={"split": "train", "template_condition": "template"},
            ),
        ]
    )
    assert summary["defect_counts"]["G1_TEXT_OVERFLOW"] == 1
    assert summary["defect_counts"]["NO_DEFECT"] == 1
    assert summary["severity"]["G1_TEXT_OVERFLOW"]["mean"] == 8


def test_summarize_linter_distribution() -> None:
    slide = Slide(
        "s",
        (Element("title", "text", BBox(100, 100, 100, 20), text="long text", style={"text_box_capacity": 1}),),
    )
    summary = summarize_linter_distribution([slide])
    assert summary["defect_counts"]["G1_TEXT_OVERFLOW"] == 1

