import json

from slide_examiner.cli import main
from slide_examiner.data_prep import (
    CleanCorpusConfig,
    convert_pptbench_arrow_to_benchmark_input,
    ensure_data_layout,
    prepare_benchmark_tasks,
    prepare_clean_deck_corpus,
    write_benchmark_subset_plan,
)
from slide_examiner.io import read_jsonl
from slide_examiner.schemas import BBox, Deck, Element, Slide


def _clean_deck(deck_id: str = "deck") -> Deck:
    return Deck(
        deck_id=deck_id,
        slides=(
            Slide(
                slide_id=f"{deck_id}_s1",
                elements=(
                    Element(
                        element_id="title",
                        type="title",
                        bbox=BBox(80, 80, 800, 80),
                        text="Market launch",
                    ),
                ),
            ),
        ),
    )


def _bad_deck() -> Deck:
    return Deck(
        deck_id="bad",
        slides=(
            Slide(
                slide_id="bad_s1",
                elements=(
                    Element(
                        element_id="off",
                        type="body",
                        bbox=BBox(-80, 80, 300, 60),
                        text="Too close to the edge",
                    ),
                ),
            ),
        ),
    )


def _write_arrow(path, rows) -> None:
    import pyarrow as pa
    import pyarrow.ipc as ipc

    table = pa.Table.from_pylist(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        with ipc.new_stream(handle, table.schema) as writer:
            writer.write_table(table)


def test_ensure_data_layout(tmp_path) -> None:
    layout = ensure_data_layout(tmp_path)
    assert (tmp_path / "data/raw").is_dir()
    assert (tmp_path / "runs/probe").is_dir()
    assert layout["manifests"].endswith("data/manifests")


def test_prepare_clean_deck_corpus_filters_and_writes_manifest(tmp_path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "clean.json").write_text(json.dumps(_clean_deck("clean").to_dict()), encoding="utf-8")
    (raw / "bad.json").write_text(json.dumps(_bad_deck().to_dict()), encoding="utf-8")
    (raw / "empty.json").write_text(
        json.dumps(Deck(deck_id="empty", slides=()).to_dict()),
        encoding="utf-8",
    )

    summary = prepare_clean_deck_corpus(
        CleanCorpusConfig(
            source_name="pptagent_zenodo10k",
            raw_path=raw,
            ir_dir=tmp_path / "ir",
            manifest_path=tmp_path / "manifest.jsonl",
            summary_path=tmp_path / "summary.json",
            source_version="fixture",
            include_slide_samples=True,
        )
    )

    assert summary["scanned_files"] == 3
    assert summary["accepted_decks"] == 1
    assert summary["accepted_slide_samples"] == 1
    assert summary["rejected"]["empty_deck"] == 1
    assert summary["rejected"]["linter_defect"] == 1
    records = read_jsonl(tmp_path / "manifest.jsonl")
    assert [record["labels"][0]["type"] for record in records] == ["NO_DEFECT", "NO_DEFECT"]
    assert records[0]["metadata"]["source_name"] == "pptagent_zenodo10k"
    assert (tmp_path / "ir" / "clean.json").exists()


def test_benchmark_plan_and_adapter(tmp_path) -> None:
    plan = write_benchmark_subset_plan("pptbench", tmp_path / "plan.json", source_version="v1")
    assert any(item["subset"] == "detection" for item in plan["usable_subsets"])

    tasks = [
        {
            "id": "t1",
            "task_subset": "detection",
            "prompt": "Find slide defects",
            "deck": _clean_deck("bench").to_dict(),
        }
    ]
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps(tasks), encoding="utf-8")
    summary = prepare_benchmark_tasks(
        "pptbench",
        tasks_path,
        tmp_path / "tasks.jsonl",
        ir_dir=tmp_path / "ir",
        summary_path=tmp_path / "tasks_summary.json",
        source_version="v1",
    )

    assert summary["record_count"] == 1
    assert summary["converted_ir_count"] == 1
    record = read_jsonl(tmp_path / "tasks.jsonl")[0]
    assert record["task_subset"] == "detection"
    assert record["deck_ir_path"].endswith("_deck.json")


def test_convert_pptbench_arrow_to_benchmark_input(tmp_path) -> None:
    arrow = tmp_path / "raw" / "train" / "data-00000-of-00001.arrow"
    _write_arrow(
        arrow,
        [
            {
                "hash": "abc",
                "category": "detection",
                "subcategory": "style detection",
                "task": "font_size_difference",
                "description": "Identify font size difference",
                "ground_truth": "12",
                "file_hash": "deckhash",
                "slide_number": 3,
                "image_path": "dataset/png/deckhash/deckhash-page-3.png",
                "json_data": json.dumps({"slide_width": 100, "slide": {"shapes": []}}),
                "image": {"bytes": b"png-bytes", "path": "deckhash-page-3.png"},
            }
        ],
    )

    summary = convert_pptbench_arrow_to_benchmark_input(
        tmp_path / "raw",
        tmp_path / "adapter_input.jsonl",
        image_dir=tmp_path / "images",
        summary_path=tmp_path / "summary.json",
        source_version="rev",
        task_subset="detection",
    )

    assert summary["record_count"] == 1
    assert summary["image_records"] == 1
    assert summary["structure_records"] == 1
    record = read_jsonl(tmp_path / "adapter_input.jsonl")[0]
    assert record["id"] == "pptbench_detection_abc"
    assert record["task_subset"] == "detection"
    assert record["pptbench_task"] == "font_size_difference"
    assert record["structure"]["slide_width"] == 100
    assert (tmp_path / "images" / "pptbench_detection_abc.png").read_bytes() == b"png-bytes"


def test_data_prep_cli_smoke(tmp_path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "clean.json").write_text(json.dumps(_clean_deck("cli").to_dict()), encoding="utf-8")
    assert main(["init-data-layout", "--root", str(tmp_path / "workspace")]) == 0
    assert (
        main(
            [
                "prepare-clean-corpus",
                "pptagent_zenodo10k",
                str(raw),
                str(tmp_path / "ir"),
                str(tmp_path / "manifest.jsonl"),
                "--summary",
                str(tmp_path / "summary.json"),
                "--source-version",
                "fixture",
            ]
        )
        == 0
    )
    assert main(["benchmark-plan", "pptbench", str(tmp_path / "pptbench_plan.json")]) == 0
    arrow = tmp_path / "pptbench" / "train" / "data-00000-of-00001.arrow"
    _write_arrow(
        arrow,
        [
            {
                "hash": "cli",
                "category": "understanding",
                "task": "chart understanding",
                "description": "Answer a chart question",
                "question": "Which option is correct?",
                "options": json.dumps({"A": "One", "B": "Two"}),
                "ground_truth": "A",
                "file_hash": "deckhash",
                "slide_number": 1,
                "json_content": "{'slide_width': 100, 'slide': {'shapes': []}}",
                "image": {"bytes": b"png-bytes", "path": "deckhash-page-1.png"},
            }
        ],
    )
    assert (
        main(
            [
                "convert-pptbench-arrow",
                str(tmp_path / "pptbench"),
                str(tmp_path / "pptbench_input.jsonl"),
                "--image-dir",
                str(tmp_path / "pptbench_images"),
                "--summary",
                str(tmp_path / "pptbench_convert_summary.json"),
                "--task-subset",
                "understanding",
            ]
        )
        == 0
    )
