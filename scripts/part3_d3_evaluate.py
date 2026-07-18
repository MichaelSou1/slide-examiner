#!/usr/bin/env python3
"""Normalize, score, compare, and plot frozen D3 evaluation traces."""
from __future__ import annotations

import argparse
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
