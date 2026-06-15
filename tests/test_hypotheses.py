from slide_examiner.hypotheses import evaluate_hypotheses


def test_evaluate_hypotheses_passes_h1() -> None:
    result = evaluate_hypotheses(
        {
            "oracle_gaps": [{"defect_type": "G1_TEXT_OVERFLOW", "gap": 0.25}],
            "template_collapse": [
                {"defect_type": "G3_ALIGNMENT_OFFSET", "relative_error_reduction": 0.6}
            ],
        }
    )
    assert result["H1"]["decision"] == "pass"
    assert result["H1_tpl"]["decision"] == "pass"


def test_evaluate_hypotheses_inconclusive_without_data() -> None:
    result = evaluate_hypotheses({})
    assert result["H1"]["decision"] == "inconclusive"
    assert result["H1_tpl"]["decision"] == "inconclusive"

