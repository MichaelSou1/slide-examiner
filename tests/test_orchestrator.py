import json

from slide_examiner.io import write_jsonl
from slide_examiner.matrix import ExperimentMatrix, write_matrix_json
from slide_examiner.orchestrator import MatrixRunConfig, run_matrix
from slide_examiner.schemas import DefectLabel


def test_run_matrix_mock(tmp_path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    write_jsonl(
        [
            {
                "sample_id": "s1",
                "labels": [DefectLabel("G1_TEXT_OVERFLOW", 8, ("title",)).to_dict()],
                "metadata": {"template_condition": "freeform"},
            }
        ],
        manifest,
    )
    matrix = tmp_path / "matrix.json"
    write_matrix_json(
        ExperimentMatrix(models=("m1",), modalities=("A", "B"), tasks=("T1",), template_conditions=("freeform",), resolutions=(768,), seeds=(0,)),
        matrix,
    )
    output = tmp_path / "records.jsonl"
    records = run_matrix(manifest, matrix, output, config=MatrixRunConfig(adapter="mock"))
    assert len(records) == 2
    assert records[0]["model"] == "m1"
    assert output.read_text(encoding="utf-8").count("\n") == 2

