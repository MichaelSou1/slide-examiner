from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

from .geometry import lint_slide
from .schemas import ManifestSample, Slide


def summarize_manifest_distribution(samples: Iterable[ManifestSample | dict[str, Any]]) -> dict[str, Any]:
    parsed = [ManifestSample.from_mapping(sample) for sample in samples]
    defect_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    template_counts: Counter[str] = Counter()
    severities: dict[str, list[float]] = defaultdict(list)

    for sample in parsed:
        split_counts[str(sample.metadata.get("split", "unknown"))] += 1
        template_counts[str(sample.metadata.get("template_condition", "unknown"))] += 1
        active_labels = [label for label in sample.labels if label.type != "NO_DEFECT"]
        if not active_labels:
            defect_counts["NO_DEFECT"] += 1
        for label in active_labels:
            defect_counts[label.type] += 1
            severities[label.type].append(label.severity)

    return {
        "sample_count": len(parsed),
        "defect_counts": dict(sorted(defect_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "template_counts": dict(sorted(template_counts.items())),
        "severity": {
            defect_type: {
                "n": len(values),
                "mean": mean(values),
                "min": min(values),
                "max": max(values),
            }
            for defect_type, values in sorted(severities.items())
        },
    }


def summarize_linter_distribution(slides: Iterable[Slide | dict[str, Any]]) -> dict[str, Any]:
    parsed = [Slide.from_mapping(slide) for slide in slides]
    defect_counts: Counter[str] = Counter()
    severities: dict[str, list[float]] = defaultdict(list)
    for slide in parsed:
        labels = lint_slide(slide)
        if not labels:
            defect_counts["NO_DEFECT"] += 1
        for label in labels:
            defect_counts[label.type] += 1
            severities[label.type].append(label.severity)
    return {
        "slide_count": len(parsed),
        "defect_counts": dict(sorted(defect_counts.items())),
        "severity": {
            defect_type: {
                "n": len(values),
                "mean": mean(values),
                "min": min(values),
                "max": max(values),
            }
            for defect_type, values in sorted(severities.items())
        },
    }

