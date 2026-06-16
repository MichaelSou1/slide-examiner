from slide_examiner.adapters import ExaminerAdapter, MockAdapter, complete_and_parse_with_retries
from slide_examiner.probe import ProbeRunConfig, ProbeRunner
from slide_examiner.schemas import DefectLabel, ManifestSample


class BrokenAdapter(ExaminerAdapter):
    name = "broken"

    def examine(self, payload, *args, **kwargs):
        return complete_and_parse_with_retries(payload, lambda _: "not json")


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


def test_probe_runner_records_examiner_parse_failure() -> None:
    runner = ProbeRunner(BrokenAdapter(), ProbeRunConfig(modalities=("B_prime",), tasks=("T1",)))
    records = runner.run([ManifestSample(sample_id="s1", caption="Caption", labels=())])
    assert records[0]["modality"] == "B_prime"
    assert records[0]["examiner_failure"] is True
    assert records[0]["failure_type"] == "parse_error"
    assert len(records[0]["parse_attempts"]) == 2
