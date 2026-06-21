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


def _binary_vote(rating: "PanelRating", threshold: float) -> bool:
    return rating.passed if rating.passed is not None else rating.score >= threshold


def inter_annotator_agreement(
    by_sample: dict[str, list["PanelRating"]], *, pass_threshold: float = 0.7
) -> dict[str, Any]:
    """Percent agreement over all rater pairs on the binary present/absent vote,
    plus Cohen's kappa for the common exactly-two-human-raters case. Samples with
    a single rating are ignored (no pair to compare)."""

    agree_pairs = total_pairs = 0
    # 2x2 confusion over rater-A vs rater-B for samples rated by exactly two humans
    both_pos = both_neg = a_only = b_only = 0
    for ratings in by_sample.values():
        humans = [r for r in ratings if r.source == "human"]
        votes = [_binary_vote(r, pass_threshold) for r in humans]
        for i in range(len(votes)):
            for j in range(i + 1, len(votes)):
                total_pairs += 1
                if votes[i] == votes[j]:
                    agree_pairs += 1
        if len(votes) == 2:
            a, b = votes
            both_pos += int(a and b)
            both_neg += int((not a) and (not b))
            a_only += int(a and not b)
            b_only += int((not a) and b)
    percent = agree_pairs / total_pairs if total_pairs else None
    kappa = None
    n2 = both_pos + both_neg + a_only + b_only
    if n2:
        po = (both_pos + both_neg) / n2
        pa = (both_pos + a_only) / n2
        pb = (both_pos + b_only) / n2
        pe = pa * pb + (1 - pa) * (1 - pb)
        kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0
    return {"percent_agreement": percent, "cohen_kappa": kappa,
            "n_rater_pairs": total_pairs, "n_two_rater_samples": n2}


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
        "agreement": inter_annotator_agreement(by_sample, pass_threshold=pass_threshold),
        "samples": samples,
        "sources": sources,
    }

