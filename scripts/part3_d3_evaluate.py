#!/usr/bin/env python3
"""Normalize, score, compare, and plot frozen D3 evaluation traces."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.d3_evaluation import (  # noqa: E402
    exact_mcnemar,
    holm_family,
    normalize_runtime_row,
    pareto_frontier,
    score_rows,
)
from slide_examiner.d3_training import GENERIC_INSPECTION_INSTRUCTION  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_final_test_unlocked(repo: Path, registry: Path) -> dict[str, Any]:
    """Require a clean, committed freeze artifact before any final-test operation."""
    payload = json.loads(registry.read_text())
    required = {"checkpoint", "policy", "primary_comparisons", "table_schema",
                "one_shot_command", "final_test_protocol_sha256", "freeze_commit"}
    missing = sorted(required - payload.keys())
    if missing:
        raise RuntimeError(f"final-test registry is incomplete: {missing}")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    frozen = str(payload["freeze_commit"])
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", frozen, head], cwd=repo)
    if ancestor.returncode:
        raise RuntimeError("freeze_commit is not an ancestor of current HEAD")
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    if status.strip():
        raise RuntimeError("working tree must be clean before final-test execution")
    relative = str(registry.relative_to(repo))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", relative],
                             cwd=repo, capture_output=True, text=True)
    if tracked.returncode:
        raise RuntimeError("freeze registry is not Git-tracked")
    first_commit = subprocess.check_output(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", relative],
        cwd=repo, text=True).splitlines()
    if not first_commit:
        raise RuntimeError("freeze registry has no committed provenance")
    registry_after_freeze = subprocess.run(
        ["git", "merge-base", "--is-ancestor", frozen, first_commit[-1]], cwd=repo)
    if registry_after_freeze.returncode:
        raise RuntimeError("unlock registry was committed before freeze_commit")
    return payload


def _relocatable(value: str, repo: Path) -> str:
    """Normalize historical absolute paths to checkout-relative runtime paths."""
    for marker in ("/runs/", "/data/", "/release/"):
        if marker in value:
            return str(Path(marker.strip("/")) / value.split(marker, 1)[1])
    path = Path(value)
    return str(path.relative_to(repo)) if path.is_absolute() and path.is_relative_to(repo) else value


def _message(images: list[str], availability: str, structure: dict[str, Any] | None = None
             ) -> list[dict[str, Any]]:
    context: dict[str, Any] = {"availability": availability}
    if structure is not None:
        context["structure"] = structure
    if availability == "reference_available":
        context["reference_note"] = (
            "The first image is the clean/reference candidate when two images are supplied.")
    content = [{"type": "image", "image": path} for path in images]
    content.append({"type": "text", "text": GENERIC_INSPECTION_INSTRUCTION
                    + "\nINPUT_CONTEXT=" + json.dumps(context, ensure_ascii=False,
                                                         separators=(",", ":"))})
    return [{"role": "user", "content": content}]


def materialize_paired_images(rows: list[dict[str, Any]], repo: Path, per_class: int,
                              split: str = "validation"
                              ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create frozen positive/clean initial rows followed by hidden escalation counterparts."""
    by_defect: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("labels"):
            by_defect[str(row["labels"][0]["type"])].append(row)
    selected = [row for defect in sorted(by_defect)
                for row in sorted(by_defect[defect], key=lambda item: str(item["sample_id"]))[:per_class]]
    initial, counterparts = [], []
    for source in selected:
        defect = str(source["labels"][0]["type"])
        pair_id = str(source["sample_id"])
        severity = float(source["labels"][0].get("severity", 0.0))
        pair = source.get("pair") or source.get("metadata") or {}
        clean_image = _relocatable(str(pair["clean_image_path"]), repo)
        defective_image = _relocatable(str(pair["defective_image_path"]), repo)
        clean_slide = (json.loads((repo / _relocatable(str(pair["clean_slide_path"]), repo)).read_text())
                       if pair.get("clean_slide_path") else None)
        defective_slide = (json.loads(
            (repo / _relocatable(str(pair["defective_slide_path"]), repo)).read_text())
                            if pair.get("defective_slide_path") else source.get("slide"))
        route = ("CALL_LINTER" if defect.split("_", 1)[0] in {"G2", "G3", "G4", "G5", "G6"}
                 else "REQUEST_REFERENCE" if defect.split("_", 1)[0] in {"G1", "S6"}
                 else "ANSWER")
        for clean, image, structure in ((False, defective_image, defective_slide),
                                        (True, clean_image, clean_slide)):
            sample_id = pair_id + ("__clean" if clean else "__positive")
            common = {"sample_id": sample_id, "pair_id": pair_id, "defect": defect,
                      "is_clean": clean, "is_clean_deck": False, "severity": severity,
                      "severity_chain": f"{sample_id}|{defect}", "split": split}
            initial.append({**common, "record_id": sample_id + "__image_only",
                            "availability": "image_only", "target_action": route,
                            "images": [image], "messages": _message([image], "image_only")})
            if route == "CALL_LINTER":
                counterparts.append({**common, "record_id": sample_id + "__image_structure",
                                     "availability": "image_structure", "target_action": "ANSWER",
                                     "images": [image],
                                     "messages": _message([image], "image_structure", structure)})
            elif route == "REQUEST_REFERENCE":
                images = [clean_image, image]
                counterparts.append({**common, "record_id": sample_id + "__reference",
                                     "availability": "reference_available", "target_action": "ANSWER",
                                     "images": images,
                                     "messages": _message(images, "reference_available")})
    summary = {"source_rows": len(rows), "selected_pairs": len(selected),
               "initial_records": len(initial), "counterpart_records": len(counterparts),
               "initial_limit": len(initial),
               "per_class_pairs": {defect: sum(row["defect"] == defect for row in initial) // 2
                                   for defect in sorted(by_defect)}}
    return initial + counterparts, summary


def materialize(args: argparse.Namespace) -> None:
    if args.split == "final_test":
        if not args.freeze_registry:
            raise RuntimeError("--freeze-registry is mandatory before reading final_test")
        assert_final_test_unlocked(args.repo.resolve(), args.freeze_registry.resolve())
    source_rows = [row for manifest in args.manifest for row in read_jsonl(manifest)]
    rows, summary = materialize_paired_images(
        source_rows, args.repo.resolve(), args.per_class, split=args.split)
    write_jsonl(args.output, rows)
    summary.update({"split": args.split,
                    "manifests": [{"path": str(path), "sha256": sha256(path)}
                                  for path in args.manifest], "output": str(args.output),
                    "output_sha256": sha256(args.output)})
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def normalize(args: argparse.Namespace) -> None:
    if args.split == "final_test":
        if not args.freeze_registry:
            raise RuntimeError("--freeze-registry is mandatory for final_test")
        assert_final_test_unlocked(args.repo.resolve(), args.freeze_registry.resolve())
    rows = [normalize_runtime_row(row, arm=args.arm) for row in read_jsonl(args.input)]
    for row in rows:
        row["split"] = args.split
    write_jsonl(args.output, rows)
    print(json.dumps({"output": str(args.output), "rows": len(rows), "sha256": sha256(args.output)},
                     indent=2))


def score(args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    inputs = []
    for path in args.input:
        arm_rows = read_jsonl(path)
        rows.extend(arm_rows)
        inputs.append({"path": str(path), "rows": len(arm_rows), "sha256": sha256(path)})
    result = score_rows(rows)
    result["inputs"] = inputs
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"output": str(args.output), "arms": sorted(result["arms"])}, indent=2))


def compare(args: argparse.Namespace) -> None:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for path in args.input:
        for row in read_jsonl(path):
            by_arm.setdefault(str(row["arm"]), []).append(row)
    specs = json.loads(args.comparisons.read_text())
    tests = []
    for spec in specs["tests"]:
        left = by_arm[spec["left"]]
        right = by_arm[spec["right"]]
        allowed = set(spec.get("defects", []))
        if allowed:
            left = [row for row in left if row.get("defect") in allowed]
            right = [row for row in right if row.get("defect") in allowed]
        test = exact_mcnemar(left, right, key=spec.get("key", "pair_id"))
        tests.append({**spec, **test})
    result = holm_family(tests, float(specs.get("alpha", 0.05)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"output": str(args.output), "tests": len(tests)}, indent=2))


def plot(args: argparse.Namespace) -> None:
    import matplotlib.pyplot as plt

    scored = json.loads(args.scores.read_text())["arms"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(6.4, 4.2))
    for arm, metrics in scored.items():
        curve = metrics["risk_coverage"]
        axis.plot([point["coverage"] for point in curve], [point["risk"] for point in curve],
                  label=arm)
    axis.set(xlabel="Coverage", ylabel="Selective risk", xlim=(0, 1), ylim=(0, 1))
    axis.grid(alpha=.25)
    axis.legend(fontsize=7)
    fig.tight_layout()
    risk_path = args.output_dir / "risk_coverage.png"
    fig.savefig(risk_path, dpi=200)
    plt.close(fig)

    points = []
    for arm, metrics in scored.items():
        accuracy = metrics["macro"]["balanced_accuracy"]
        cost = metrics["routing_and_cost"]["mean_total_tokens"]
        if accuracy is not None and cost is not None:
            points.append({"arm": arm, "accuracy": accuracy, "cost": cost})
    frontier = pareto_frontier(points)
    fig, axis = plt.subplots(figsize=(6.4, 4.2))
    for point in points:
        axis.scatter(point["cost"], point["accuracy"], marker="o" if point in frontier else "x")
        axis.annotate(point["arm"], (point["cost"], point["accuracy"]), fontsize=7)
    axis.set(xlabel="Mean total tokens", ylabel="Macro balanced accuracy")
    axis.grid(alpha=.25)
    fig.tight_layout()
    pareto_path = args.output_dir / "accuracy_cost_pareto.png"
    fig.savefig(pareto_path, dpi=200)
    plt.close(fig)
    print(json.dumps({"risk_coverage": str(risk_path), "pareto": str(pareto_path),
                      "frontier": [point["arm"] for point in frontier]}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    materializer = sub.add_parser("materialize")
    materializer.add_argument("--repo", type=Path, default=Path.cwd())
    materializer.add_argument("--manifest", type=Path, nargs="+", required=True)
    materializer.add_argument("--output", type=Path, required=True)
    materializer.add_argument("--split", choices=("validation", "final_test"), required=True)
    materializer.add_argument("--per-class", type=int, default=12)
    materializer.add_argument("--freeze-registry", type=Path)
    materializer.set_defaults(function=materialize)
    normalizer = sub.add_parser("normalize")
    normalizer.add_argument("--repo", type=Path, default=Path.cwd())
    normalizer.add_argument("--input", type=Path, required=True)
    normalizer.add_argument("--output", type=Path, required=True)
    normalizer.add_argument("--arm", required=True)
    normalizer.add_argument("--split", choices=("dev", "validation", "final_test"), required=True)
    normalizer.add_argument("--freeze-registry", type=Path)
    normalizer.set_defaults(function=normalize)

    scorer = sub.add_parser("score")
    scorer.add_argument("--input", type=Path, nargs="+", required=True)
    scorer.add_argument("--output", type=Path, required=True)
    scorer.set_defaults(function=score)

    comparator = sub.add_parser("compare")
    comparator.add_argument("--input", type=Path, nargs="+", required=True)
    comparator.add_argument("--comparisons", type=Path, required=True)
    comparator.add_argument("--output", type=Path, required=True)
    comparator.set_defaults(function=compare)

    plotter = sub.add_parser("plot")
    plotter.add_argument("--scores", type=Path, required=True)
    plotter.add_argument("--output-dir", type=Path, required=True)
    plotter.set_defaults(function=plot)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
