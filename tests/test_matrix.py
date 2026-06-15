import json

from slide_examiner.matrix import ExperimentMatrix, write_matrix_json


def test_experiment_matrix_count() -> None:
    matrix = ExperimentMatrix(models=("m",), modalities=("A", "B"), tasks=("T1",), resolutions=(768,), seeds=(0,))
    assert len(matrix.records()) == 4


def test_write_matrix_json(tmp_path) -> None:
    path = write_matrix_json(ExperimentMatrix(models=("m",), resolutions=(768,), seeds=(0,)), tmp_path / "matrix.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["matrix"]["planned_cells"] == len(data["records"])

