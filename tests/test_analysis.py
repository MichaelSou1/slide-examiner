import json

from slide_examiner.analysis import (
    attribute_failures,
    classify_probe_record,
    modality_accuracy_gaps,
    psychometric_thresholds,
    summarize_probe_records,
    template_collapse,
    repair_pass_rates,
)
from slide_examiner.adapters import MockAdapter
from slide_examiner.probe import ProbeRunConfig, ProbeRunner
from slide_examiner.schemas import DefectLabel, ManifestSample


def record(sample_id: str, modality: str, predicted: list[str], expected: str = "G1_TEXT_OVERFLOW", severity: float = 16):
    return {
        "sample_id": sample_id,
        "model": "mock",
        "modality": modality,
        "task": "T1",
        "labels": [{"type": expected, "severity": severity, "target_element_ids": ["title"]}],
        "output": {
            "defects": [
                {
                    "type": item,
                    "present": True,
                    "element_ids": ["title"],
                    "severity": severity,
                }
                for item in predicted
            ],
            "overall_score": 0.5,
        },
        "metadata": {"template_condition": "template"},
    }


def test_classify_probe_record() -> None:
    row = classify_probe_record(record("s1", "A", ["G1_TEXT_OVERFLOW"]))
    assert row.correct is True
    assert row.severity == 16
    assert row.template_condition == "template"


def test_no_defect_label_is_treated_as_negative() -> None:
    row = classify_probe_record(
        {
            "sample_id": "neg",
            "modality": "A",
            "task": "T1",
            "labels": [{"type": "NO_DEFECT", "severity": 0, "target_element_ids": []}],
            "output": {"defects": [], "overall_score": 1.0},
        }
    )
    assert row.expected_types == ()
    assert row.correct is True
    metrics = summarize_probe_records([
        {
            "sample_id": "neg",
            "modality": "A",
            "task": "T1",
            "labels": [{"type": "NO_DEFECT", "severity": 0, "target_element_ids": []}],
            "output": {"defects": [], "overall_score": 1.0},
        }
    ])["metrics"]
    assert metrics[0]["defect_type"] == "NO_DEFECT"
    assert metrics[0]["accuracy"] == 1.0


def test_attribute_failures_marks_a_fail_b_success_as_perception() -> None:
    rows = [
        classify_probe_record(record("s1", "A", [])),
        classify_probe_record(record("s1", "B", ["G1_TEXT_OVERFLOW"])),
    ]
    summary = attribute_failures(rows)
    assert summary[0]["perception_bottleneck_rate"] == 1.0
    assert summary[0]["reasoning_bottleneck_rate"] == 0.0


def test_modality_accuracy_gaps() -> None:
    rows = [
        classify_probe_record(record("s1", "A", [])),
        classify_probe_record(record("s1", "B", ["G1_TEXT_OVERFLOW"])),
    ]
    gaps = modality_accuracy_gaps(rows, left_modality="A", right_modality="B")
    assert gaps[0]["gap"] == 1.0


def test_caption_oracle_gap_normalizes_legacy_bprime_name() -> None:
    rows = [
        classify_probe_record(record("s1", "Bprime", [])),
        classify_probe_record(record("s1", "B", ["G1_TEXT_OVERFLOW"])),
    ]
    gaps = modality_accuracy_gaps(rows, left_modality="Bprime", right_modality="B")
    assert gaps[0]["left_modality"] == "B_prime"
    assert gaps[0]["gap"] == 1.0


def test_template_collapse_summary() -> None:
    freeform = record("s1", "A", [])
    freeform["metadata"]["template_condition"] = "freeform"
    templated = record("s2", "A", ["G1_TEXT_OVERFLOW"])
    templated["metadata"]["template_condition"] = "template"
    rows = [classify_probe_record(freeform), classify_probe_record(templated)]
    collapse = template_collapse(rows)
    assert collapse[0]["absolute_error_reduction"] == 1.0


def test_psychometric_thresholds() -> None:
    rows = [
        classify_probe_record(record("s1", "A", [], severity=4)),
        classify_probe_record(record("s2", "A", ["G1_TEXT_OVERFLOW"], severity=8)),
        classify_probe_record(record("s3", "A", ["G1_TEXT_OVERFLOW"], severity=16)),
    ]
    thresholds = psychometric_thresholds(rows)
    assert thresholds[0]["threshold"] == 8


def test_repair_pass_rates() -> None:
    rates = repair_pass_rates([{**record("s1", "A", ["G1_TEXT_OVERFLOW"]), "task": "T3", "repair_passed": True}])
    assert rates[0]["repair_pass_rate"] == 1.0


def test_summarize_probe_records_from_runner() -> None:
    samples = [
        ManifestSample(
            sample_id="s1",
            image_path="slide.png",
            oracle={"elements": [], "defect_present": True},
            labels=(DefectLabel("G2_ELEMENT_OVERLAP", 0.1, ("a", "b")),),
            metadata={"template_condition": "freeform"},
        )
    ]
    runner = ProbeRunner(MockAdapter(miss_modalities={"A"}), ProbeRunConfig(modalities=("A", "B"), tasks=("T1",)))
    summary = summarize_probe_records(runner.run(samples))
    assert summary["record_count"] == 2
    assert summary["attribution"][0]["perception_bottleneck_rate"] == 1.0
    assert summary["oracle_gaps"][0]["gap"] == 1.0


def test_cli_analyze(tmp_path) -> None:
    from slide_examiner.cli import main

    probe_path = tmp_path / "probe.jsonl"
    output_path = tmp_path / "summary.json"
    probe_path.write_text(json.dumps(record("s1", "A", ["G1_TEXT_OVERFLOW"])) + "\n", encoding="utf-8")
    assert main(["analyze", str(probe_path), "-o", str(output_path)]) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["record_count"] == 1
