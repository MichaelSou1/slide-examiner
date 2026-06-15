from slide_examiner.panel import PanelRating, summarize_panel_ratings


def test_summarize_panel_ratings() -> None:
    summary = summarize_panel_ratings(
        [
            PanelRating("s1", "h1", 0.9, "human"),
            PanelRating("s1", "h2", 0.7, "human"),
            {"sample_id": "s1", "judge_id": "api", "score": 0.8, "source": "api"},
            {"sample_id": "s2", "judge_id": "h1", "score": 0.4, "source": "human"},
        ]
    )
    assert summary["rating_count"] == 4
    assert summary["sample_count"] == 2
    assert summary["samples"][0]["passed"] is True
    assert summary["samples"][1]["passed"] is False

