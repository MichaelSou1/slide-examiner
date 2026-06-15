from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Iterable


@dataclass(frozen=True)
class PanelRating:
    sample_id: str
    judge_id: str
    score: float
    source: str = "human"
    passed: bool | None = None
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "PanelRating":
        score = float(value["score"])
        return cls(
            sample_id=str(value["sample_id"]),
            judge_id=str(value["judge_id"]),
            score=score,
            source=str(value.get("source", "human")),
            passed=value.get("passed"),
            notes=str(value.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "judge_id": self.judge_id,
            "score": self.score,
            "source": self.source,
            "passed": self.passed,
            "notes": self.notes,
        }


def summarize_panel_ratings(ratings: Iterable[PanelRating | dict[str, Any]], *, pass_threshold: float = 0.7) -> dict[str, Any]:
    parsed = [rating if isinstance(rating, PanelRating) else PanelRating.from_mapping(rating) for rating in ratings]
    by_sample: dict[str, list[PanelRating]] = defaultdict(list)
    by_source: dict[str, list[PanelRating]] = defaultdict(list)
    for rating in parsed:
        by_sample[rating.sample_id].append(rating)
        by_source[rating.source].append(rating)

    samples = []
    for sample_id, group in sorted(by_sample.items()):
        scores = [rating.score for rating in group]
        pass_votes = [rating.passed if rating.passed is not None else rating.score >= pass_threshold for rating in group]
        samples.append(
            {
                "sample_id": sample_id,
                "n": len(group),
                "mean_score": mean(scores),
                "std_score": pstdev(scores) if len(scores) > 1 else 0.0,
                "pass_rate": sum(pass_votes) / len(pass_votes),
                "passed": sum(pass_votes) >= (len(pass_votes) / 2),
                "sources": sorted({rating.source for rating in group}),
            }
        )

    sources = []
    for source, group in sorted(by_source.items()):
        scores = [rating.score for rating in group]
        sources.append({"source": source, "n": len(group), "mean_score": mean(scores)})

    return {
        "rating_count": len(parsed),
        "sample_count": len(samples),
        "overall_mean_score": mean([rating.score for rating in parsed]) if parsed else 0.0,
        "samples": samples,
        "sources": sources,
    }

