from slide_examiner.adapters import MockAdapter
from slide_examiner.probe import ProbeRunConfig, ProbeRunner
from slide_examiner.schemas import DefectLabel, ManifestSample


def test_probe_runner_records_cross_product() -> None:
    runner = ProbeRunner(MockAdapter(), ProbeRunConfig(modalities=("A", "B"), tasks=("T1",)))
    records = runner.run(
        [
            ManifestSample(
                sample_id="s1",
                image_path="slide.png",
                oracle={"elements": []},
                labels=(DefectLabel("G2_ELEMENT_OVERLAP", 0.1, ("a", "b")),),
            )
        ]
    )
    assert len(records) == 2
    assert {record["modality"] for record in records} == {"A", "B"}
    assert records[0]["output"]["defects"][0]["type"] == "G2_ELEMENT_OVERLAP"


def test_probe_runner_writes_jsonl(tmp_path) -> None:
    path = tmp_path / "probe.jsonl"
    runner = ProbeRunner(MockAdapter(), ProbeRunConfig(modalities=("A",), tasks=("T1",)))
    records = runner.run_jsonl([{"sample_id": "s1", "labels": []}], path)
    assert len(records) == 1
    assert path.read_text(encoding="utf-8").strip()

