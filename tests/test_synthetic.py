import json

from slide_examiner.schemas import BBox, Deck, Element, Slide
from slide_examiner.synthetic import SyntheticBuildConfig, build_synthetic_manifest


def slide() -> Slide:
    return Slide(
        slide_id="syn",
        elements=(
            Element("title", "title", BBox(100, 50, 400, 60), text="Product", style={"font_size_pt": 24, "color": "#000000"}, metadata={"role": "title"}),
            Element("body", "text", BBox(100, 150, 600, 100), text="Product body", style={"font_size_pt": 22}, metadata={"role": "body"}),
            Element("shape", "shape", BBox(900, 150, 120, 120)),
            Element("diagram", "diagram", BBox(900, 350, 120, 120), metadata={"role": "diagram", "diagram_claim": "three-layer architecture"}),
        ),
    )


def deck() -> Deck:
    return Deck(
        deck_id="deck",
        slides=(slide(), Slide("validation", (Element("v", "text", BBox(100, 100, 500, 80), text="Product validation"),), metadata={"section": "validation"})),
        metadata={"required_sections": ["intro", "validation"], "canonical_term": "Product", "variant_term": "Widget"},
    )


def test_build_synthetic_manifest(tmp_path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    samples = build_synthetic_manifest(
        [slide()],
        [deck()],
        output_dir=tmp_path / "out",
        manifest_path=manifest,
        config=SyntheticBuildConfig(
            examples_per_cell=1,
            heldout_severities=(64,),
            heldout_defect_types=("S6_IMAGE_TEXT_CONTRADICTION",),
            negative_ratio=0.1,
        ),
    )
    types = {sample.labels[0].type for sample in samples}
    assert "G1_TEXT_OVERFLOW" in types
    assert "S5_MISSING_LOGIC_SECTION" in types
    assert "NO_DEFECT" in types
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert any(row["metadata"]["split"] == "ood_severity" for row in rows)
    assert any(row["metadata"]["split"] == "ood_defect" for row in rows)

