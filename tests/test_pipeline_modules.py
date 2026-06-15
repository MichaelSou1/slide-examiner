import json

from slide_examiner.cli import main
from slide_examiner.experiment import inject_artifact_to_manifest
from slide_examiner.gepa_runner import GEPARunConfig, write_gepa_plan
from slide_examiner.generator import PromptModules, deck_from_content_json, write_deck_html
from slide_examiner.ingest import deck_caption, extract_pptx_geometry, parse_annotated_html, save_slide_json, slide_caption
from slide_examiner.render import slide_to_html
from slide_examiner.reports import write_analysis_report
from slide_examiner.schemas import BBox, Element, Slide
from slide_examiner.training import TrainingConfig, build_training_command, write_training_config


def slide() -> Slide:
    return Slide(
        slide_id="pipe",
        elements=(
            Element("title", "title", BBox(100, 50, 300, 60), text="Title", style={"font_size_pt": 24}),
            Element("body", "text", BBox(100, 140, 500, 120), text="Body", metadata={"role": "body"}),
            Element("shape", "shape", BBox(800, 140, 120, 120)),
        ),
    )


def test_annotated_html_ingest() -> None:
    html = (
        '<div data-element-id="e1" data-x="10" data-y="20" data-width="30" '
        'data-height="40" data-type="text" data-font-size="18">Hello</div>'
    )
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "slide.html"
        path.write_text(html, encoding="utf-8")
        parsed = parse_annotated_html(path)
    assert parsed.elements[0].text == "Hello"
    assert parsed.elements[0].bbox.x == 10


def test_pptx_geometry_falls_back(monkeypatch, tmp_path) -> None:
    import builtins
    import zipfile

    pptx = tmp_path / "tiny.pptx"
    with zipfile.ZipFile(pptx, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", "<a:t>Hello</a:t>")

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pptx":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    deck = extract_pptx_geometry(pptx)
    assert deck.slides[0].elements[0].text == "Hello"


def test_caption_helpers() -> None:
    assert "title" in slide_caption(slide())
    assert "Slide 1" in deck_caption(deck_from_content_json({"slides": [{"title": "T"}]}))


def test_slide_to_html_contains_elements() -> None:
    html = slide_to_html(slide())
    assert 'data-element-id="title"' in html


def test_inject_artifact_to_manifest(tmp_path) -> None:
    slide_path = tmp_path / "slide.json"
    save_slide_json(slide(), slide_path)
    manifest_path = tmp_path / "manifest.jsonl"
    sample = inject_artifact_to_manifest(
        slide_path,
        defect_type="G1_TEXT_OVERFLOW",
        output_dir=tmp_path / "out",
        manifest_path=manifest_path,
    )
    assert sample.labels[0].type == "G1_TEXT_OVERFLOW"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["sample_id"]


def test_training_config_and_command(tmp_path) -> None:
    config = TrainingConfig(train_jsonl="train.jsonl", output_dir="out")
    command = build_training_command(config)
    assert "--model_name_or_path" in command
    path = write_training_config(config, tmp_path / "train.json")
    assert json.loads(path.read_text(encoding="utf-8"))["train_jsonl"] == "train.jsonl"


def test_gepa_plan_and_report(tmp_path) -> None:
    plan_path = write_gepa_plan(GEPARunConfig("train.jsonl", "val.jsonl", "test.jsonl"), tmp_path / "gepa.json")
    assert json.loads(plan_path.read_text(encoding="utf-8"))["dry_run"] is True
    report = write_analysis_report({"record_count": 0, "metrics": [], "attribution": []}, tmp_path / "report.md")
    assert report.read_text(encoding="utf-8").startswith("# SlideProbe Report")


def test_generator_from_content_json(tmp_path) -> None:
    deck = deck_from_content_json(
        {
            "deck_id": "demo",
            "scenario": "launch",
            "required_sections": ["intro"],
            "slides": [{"title": "Launch", "bullets": ["One", "Two"], "section": "intro"}],
        },
        prompt_modules=PromptModules(quality_checklist="Check overflow"),
    )
    assert deck.deck_id == "demo"
    assert deck.slides[0].elements[0].text == "Launch"
    paths = write_deck_html(deck, tmp_path / "html")
    assert paths[0].exists()


def test_new_cli_commands_smoke(tmp_path) -> None:
    slide_path = tmp_path / "slide.json"
    save_slide_json(slide(), slide_path)
    html_path = tmp_path / "slide.html"
    assert main(["render-html", str(slide_path), str(html_path)]) == 0
    assert main(["render", str(slide_path), str(tmp_path / "slide_alias.html")]) == 0
    assert main(["data-sources"]) == 0
    assert main(["power", "0.5", "0.7"]) == 0
    assert main(["hacking-audit", str(slide_path), "-o", str(tmp_path / "hack.json")]) == 0
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text('{"sample_id":"s","judge_id":"h1","score":0.8,"source":"human"}\n', encoding="utf-8")
    assert main(["panel", str(ratings), "-o", str(tmp_path / "panel.json")]) == 0
    manifest = tmp_path / "manifest.jsonl"
    assert main(["inject", str(slide_path), "G1_TEXT_OVERFLOW", str(tmp_path / "out"), str(manifest)]) == 0
    assert main([
        "build-synthetic",
        str(tmp_path / "synthetic"),
        str(tmp_path / "synthetic_manifest.jsonl"),
        str(slide_path),
        "--examples-per-cell",
        "1",
        "--negative-ratio",
        "0",
    ]) == 0
    summary_path = tmp_path / "summary.json"
    probe_path = tmp_path / "probe.jsonl"
    assert main(["probe", str(manifest), str(probe_path)]) == 0
    assert main(["eval-examiner", str(manifest), str(tmp_path / "eval.jsonl"), str(tmp_path / "eval_summary.json")]) == 0
    assert main(["analyze", str(probe_path), "-o", str(summary_path)]) == 0
    assert main(["distribution", str(manifest), "-o", str(tmp_path / "distribution.json")]) == 0
    assert main(["hypotheses", str(summary_path), "-o", str(tmp_path / "hypotheses.json")]) == 0
    assert main(["report", str(summary_path), str(tmp_path / "report.md")]) == 0
    assert main(["train-plan", str(tmp_path / "sft.jsonl"), str(tmp_path / "model")]) == 0
    assert main(["train-examiner", str(tmp_path / "sft.jsonl"), str(tmp_path / "model2")]) == 0
    assert main(["gepa-plan", "train.jsonl", "val.jsonl", "test.jsonl", str(tmp_path / "gepa.json")]) == 0
    assert main(["run-gepa", "train.jsonl", "val.jsonl", "test.jsonl", str(tmp_path / "gepa2.json")]) == 0
    assert main(["gepa-conditions", "train.jsonl", "val.jsonl", "test.jsonl", str(tmp_path / "gepa_conditions.json")]) == 0
    assert main(["matrix", str(tmp_path / "matrix.json")]) == 0
    assert main(["run-matrix", str(manifest), str(tmp_path / "matrix.json"), str(tmp_path / "matrix_probe.jsonl"), "--limit", "2"]) == 0
    content = tmp_path / "content.json"
    content.write_text(json.dumps({"deck_id": "demo", "slides": [{"title": "T", "bullets": ["B"]}]}), encoding="utf-8")
    assert main(["generate", str(content), str(tmp_path / "generated")]) == 0
