"""Training-data contracts and joint objectives for the D3 critic."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .d3_data import read_jsonl, sha256_file, write_jsonl
from .examiner_contract import (
    EvidenceSource,
    ExaminerAction,
    ExamLevel,
    Locator,
    Modality,
    PageExamResult,
    DeckExamResult,
    page_result_from_labels,
    deck_result_from_labels,
    severity_level_for_label,
    parse_deck_result,
    parse_page_result,
)
from .geometry import lint_slide
from .schemas import Slide

GENERIC_INSPECTION_INSTRUCTION = (
    "Inspect the supplied slide artifact for presentation-quality defects. First decide whether "
    "the available evidence is sufficient. Return exactly one JSON object with action, confidence, "
    "requested_context, evidence_source, has_defect, findings, and clean_dimensions. Choose ANSWER "
    "only when the evidence supports a finding or a clean decision; otherwise choose CALL_LINTER, "
    "REQUEST_REFERENCE, REQUEST_DECK, or DEFER. A non-ANSWER action must not contain a finding."
)

ACTIONS = tuple(action.value for action in ExaminerAction)
ACTION_TO_ID = {name: index for index, name in enumerate(ACTIONS)}
LOSS_NAMES = ("detect", "distill", "pair", "severity", "route", "select")


def mixed_objective_batches(rows: list[dict[str, Any]], seed: int, batches: int,
                            start_batch: int = 0) -> Iterable[list[int]]:
    """Yield a deterministic mixed-objective stream, optionally from a resume offset."""
    chains: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        chains.setdefault(row["severity_chain"], []).append(index)
    pairs = []
    for indices in chains.values():
        ordered = sorted(
            indices,
            key=lambda i: float(rows[i].get("severity_target", rows[i]["severity"])),
        )
        if (len(ordered) > 1
                and rows[ordered[0]].get("severity_target", rows[ordered[0]]["severity"])
                != rows[ordered[-1]].get("severity_target", rows[ordered[-1]]["severity"])):
            pairs.append((ordered[0], ordered[-1]))
    if not pairs:
        raise ValueError("no non-tied severity chains available for monotonic batches")
    task_counts = Counter(row["task"] for row in rows)
    action_counts = Counter(int(row["action_id"]) for row in rows)
    sample_weights = [
        0.5 / task_counts[row["task"]] + 0.5 / action_counts[int(row["action_id"])]
        for row in rows
    ]
    generator = random.Random(seed)
    population = list(range(len(rows)))
    for batch_index in range(batches):
        batch = (list(generator.choice(pairs)) if batch_index % 4 == 0 else
                 generator.choices(population, weights=sample_weights, k=2))
        if batch_index >= start_batch:
            yield batch


def resume_config_mismatches(saved: dict[str, Any], expected: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Return checkpoint/current values for fields that make exact resume unsafe."""
    return {key: (saved.get(key), value) for key, value in expected.items()
            if saved.get(key) != value}


def is_optimizer_boundary(micro_step: int, gradient_accumulation: int) -> bool:
    """An optimizer step is due only after a complete accumulation window."""
    if gradient_accumulation < 1:
        raise ValueError("gradient_accumulation must be positive")
    return micro_step % gradient_accumulation == 0


def balanced_smoke_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Reserve every available W7.4 semantic cell before adding diverse repeats."""
    selected: list[dict[str, Any]] = []
    remaining = list(rows)
    available = {(row["sample_id"], row["availability"]) for row in rows}
    chain_available = {(row.get("severity_chain"), row["availability"]) for row in rows}

    def has_counterpart(row: dict[str, Any], availability: str) -> bool:
        return ((row["sample_id"], availability) in available
                or (row.get("severity_chain"), availability) in chain_available)

    required_cells = [
        lambda row: row["defect"].startswith("G7_") and row["availability"] == "image_only",
        *[(lambda row, prefix=prefix: row["defect"].split("_", 1)[0] == prefix
           and row["availability"] == "image_only") for prefix in ("G2", "G3", "G4", "G5", "G6")],
        lambda row: row["target_action"] == "CALL_LINTER",
        lambda row: row["defect"].split("_", 1)[0] in {"G1", "S6"}
        and row["target_action"] == "REQUEST_REFERENCE"
        and has_counterpart(row, "reference_available"),
        lambda row: row["defect"].split("_", 1)[0] == "S2"
        and row["target_action"] == "REQUEST_DECK"
        and has_counterpart(row, "deck_context_available"),
        # The frozen dev artifact has no is_clean_deck=true rows. Use its
        # executable deck-context NO_DEFECT arm as the clean control instead
        # of silently leaving W7.4 without an eligible negative deck case.
        lambda row: bool(row.get("is_clean_deck")) or (
            row["defect"] == "NO_DEFECT"
            and row["availability"] == "deck_context_available"
        ),
        lambda row: row["defect"] == "NO_DEFECT" and not row.get("is_clean_deck"),
    ]
    for predicate in required_cells:
        if len(selected) >= limit:
            break
        candidate = next((row for row in remaining if predicate(row)), None)
        if candidate is not None:
            selected.append(candidate)
            remaining.remove(candidate)
    # Do not turn an intentionally incomplete availability arm into a runtime
    # escalation failure. Such rows remain valid route-training examples, but
    # they are not executable end-to-end smoke cases.
    required_availability = {"REQUEST_REFERENCE": "reference_available",
                             "REQUEST_DECK": "deck_context_available"}
    remaining = [row for row in remaining
                 if row["target_action"] not in required_availability
                 or has_counterpart(row, required_availability[row["target_action"]])]
    seen = {key: Counter() for key in ("target_action", "task", "defect", "availability")}
    for row in selected:
        for key in seen:
            seen[key][str(row[key])] += 1
    while remaining and len(selected) < limit:
        def score(row: dict[str, Any]) -> tuple[float, str]:
            novelty = sum(1.0 / (1.0 + seen[key][str(row[key])]) for key in seen)
            return novelty, row["record_id"]
        best = max(remaining, key=score)
        remaining.remove(best)
        selected.append(best)
        for key in seen:
            seen[key][str(best[key])] += 1
    return selected


def evaluate_semantic_gate(results: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, Any]:
    """Evaluate implementation semantics only; this is not a quality threshold."""
    geometry = {"G2", "G3", "G4", "G5", "G6"}
    checks: dict[str, dict[str, Any]] = {}

    def add(name: str, eligible: list[dict[str, Any]], passed: int) -> None:
        checks[name] = {"eligible": len(eligible), "passed_records": passed,
                        "passed": bool(eligible) and passed == len(eligible)}

    g7 = [x for x in results if x["defect"].startswith("G7_") and x["availability"] == "image_only"]
    add("g7_image_only_legal_finding", g7, sum(
        x["predicted_action"] == "ANSWER" and bool((x["parsed"] or {}).get("findings")) for x in g7))
    geo = [x for x in results if x["defect"].split("_", 1)[0] in geometry
           and x["availability"] == "image_only"]
    add("g2_g6_image_only_safe_route", geo, sum(
        x["predicted_action"] in {"CALL_LINTER", "DEFER"}
        and not (x["parsed"] or {}).get("findings") for x in geo))
    # This gate tests executor semantics conditional on the learned policy
    # requesting the relevant context; route recall is reported separately as
    # a model-quality metric rather than being smuggled into a smoke invariant.
    reference = [x for x in results if x["defect"].split("_", 1)[0] in {"G1", "S6"}
                 and x["target_action"] == "REQUEST_REFERENCE"
                 and x["predicted_action"] == "REQUEST_REFERENCE"]
    add("reference_escalation_completes", reference, sum(
        x["predicted_action"] == "REQUEST_REFERENCE" and bool(x["escalation"])
        and x["escalation"].get("final_action") in {"ANSWER", "DEFER"} for x in reference))
    deck = [x for x in results if x["defect"].split("_", 1)[0] == "S2"
            and x["target_action"] == "REQUEST_DECK"
            and x["predicted_action"] == "REQUEST_DECK"]
    add("deck_escalation_completes", deck, sum(
        x["predicted_action"] == "REQUEST_DECK" and bool(x["escalation"])
        and x["escalation"].get("final_action") in {"ANSWER", "DEFER"} for x in deck))
    clean_deck = [x for x in results if x.get("is_clean_deck") or (
        x["defect"] == "NO_DEFECT"
        and x["availability"] == "deck_context_available"
    )]
    add("clean_deck_not_forced_positive", clean_deck, sum(
        not (x["parsed"] or {}).get("findings") for x in clean_deck))
    runtime_ok = all(counts[name] == 0 for name in (
        "parser_failure", "action_loop", "teacher_failure", "consistency_failure", "escalation_failure"))
    checks["runtime_failures_zero"] = {"eligible": len(results),
                                        "passed_records": len(results) if runtime_ok else 0,
                                        "passed": runtime_ok}
    failures = [name for name, check in checks.items() if not check["passed"]]
    return {"passed": not failures, "checks": checks, "failure_reasons": failures}


def fit_class_router(train: list[dict[str, Any]], dev: list[dict[str, Any]], *,
                     steps: int = 400, learning_rate: float = 0.2,
                     l2: float = 1e-3) -> dict[str, Any]:
    """Fit a train-only multinomial class router and report held-out dev accuracy."""
    classes = sorted({row["defect"].split("_", 1)[0] for row in train})
    class_to_id = {name: index for index, name in enumerate(classes)}
    weights = [[0.0 for _ in classes] for _ in ACTIONS]
    bias = [0.0 for _ in ACTIONS]
    for _ in range(steps):
        grad_w = [[l2 * value for value in row] for row in weights]
        grad_b = [0.0 for _ in ACTIONS]
        for record in train:
            feature = class_to_id[record["defect"].split("_", 1)[0]]
            logits = [bias[action] + weights[action][feature] for action in range(len(ACTIONS))]
            peak = max(logits)
            exp = [math.exp(value - peak) for value in logits]
            total = sum(exp)
            truth = int(record["action_id"])
            for action in range(len(ACTIONS)):
                error = exp[action] / total - float(action == truth)
                grad_w[action][feature] += error / len(train)
                grad_b[action] += error / len(train)
        for action in range(len(ACTIONS)):
            bias[action] -= learning_rate * grad_b[action]
            for feature in range(len(classes)):
                weights[action][feature] -= learning_rate * grad_w[action][feature]

    confusion = [[0 for _ in ACTIONS] for _ in ACTIONS]
    predictions: dict[str, dict[str, Any]] = {}
    for name, feature in class_to_id.items():
        logits = [bias[action] + weights[action][feature] for action in range(len(ACTIONS))]
        peak = max(logits)
        exp = [math.exp(value - peak) for value in logits]
        probs = [value / sum(exp) for value in exp]
        predictions[name] = {"prediction": ACTIONS[max(range(len(ACTIONS)), key=probs.__getitem__)],
                             "probabilities": dict(zip(ACTIONS, probs, strict=True))}
    evaluated = 0
    for record in dev:
        defect = record["defect"].split("_", 1)[0]
        if defect not in predictions:
            continue
        truth = int(record["action_id"])
        pred = ACTION_TO_ID[predictions[defect]["prediction"]]
        confusion[truth][pred] += 1
        evaluated += 1
    correct = sum(confusion[index][index] for index in range(len(ACTIONS)))
    return {"fit_split": "train", "eval_split": "dev",
            "estimator": "multinomial logistic regression on defect class",
            "manual_route_used": False, "feature_classes": classes,
            "training": {"steps": steps, "learning_rate": learning_rate, "l2": l2},
            "weights": {action: dict(zip(classes, weights[index], strict=True))
                        for index, action in enumerate(ACTIONS)},
            "bias": dict(zip(ACTIONS, bias, strict=True)), "routes": predictions,
            "dev_records": evaluated, "dev_accuracy": correct / evaluated if evaluated else None,
            "action_labels": list(ACTIONS), "dev_confusion": confusion}


def input_context(row: dict[str, Any]) -> dict[str, Any]:
    """Recover the non-oracle runtime payload embedded by the frozen serializer."""
    for item in row["messages"][0]["content"]:
        text = item.get("text", "")
        marker = "INPUT_CONTEXT="
        if marker in text:
            return json.loads(text.split(marker, 1)[1])
    return {}


def authoritative_result(parsed: dict[str, Any] | None, predicted_action: str
                         ) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Project the authoritative route-head action onto a legal public result."""
    generated_action = str((parsed or {}).get("action")) if parsed else None
    mismatch = generated_action is not None and generated_action != predicted_action
    if predicted_action == ExaminerAction.ANSWER.value:
        if parsed is None:
            return None, mismatch, "ANSWER route has no parseable generated result"
        if generated_action != ExaminerAction.ANSWER.value:
            return None, True, f"ANSWER route conflicts with generated {generated_action}"
        return parsed, mismatch, None
    deck_id = (parsed or {}).get("deck_id")
    payload = {
        ("deck_id" if deck_id else "page_id"): str(deck_id or (parsed or {}).get("page_id") or "unknown"),
        "has_defect": False, "findings": [], "clean_dimensions": [],
        "action": predicted_action, "confidence": float((parsed or {}).get("confidence", 0.0)),
        "requested_context": {
            "CALL_LINTER": [EvidenceSource.STRUCTURE.value],
            "REQUEST_REFERENCE": [EvidenceSource.REFERENCE.value],
            "REQUEST_DECK": [EvidenceSource.DECK_CONTEXT.value],
        }.get(predicted_action, []),
        "evidence_source": EvidenceSource.NONE.value,
    }
    parser = parse_deck_result if deck_id else parse_page_result
    return parser(json.dumps(payload)).model_dump(mode="json"), mismatch, None


def run_linter(row: dict[str, Any]) -> dict[str, Any]:
    """Execute the deterministic geometry linter after a CALL_LINTER action."""
    structure = input_context(row).get("structure")
    if not structure:
        raise ValueError("CALL_LINTER counterpart has no structure")
    slide = Slide.from_mapping(structure)
    labels = lint_slide(slide)
    sample = {"sample_id": row["sample_id"], "slide": slide.to_dict(),
              "labels": [label.to_dict() for label in labels], "metadata": {}}
    result = page_result_from_labels(sample).model_dump(mode="json")
    result.update({"action": ExaminerAction.ANSWER.value, "confidence": 1.0,
                   "requested_context": [], "evidence_source": EvidenceSource.LINTER.value})
    return PageExamResult.model_validate(result).model_dump(mode="json")


def relocate_path(value: str | None, repo: Path) -> Path | None:
    """Resolve frozen paths from the Mac/old GPU checkout into this checkout."""
    if not value:
        return None
    path = Path(value)
    if path.exists():
        return path.resolve()
    for marker in ("/runs/", "/data/", "/release/"):
        if marker in value:
            candidate = repo / marker.strip("/") / value.split(marker, 1)[1]
            if candidate.exists():
                return candidate.resolve()
    candidate = repo / value
    return candidate.resolve() if candidate.exists() else None


def image_paths_for_sample(sample: dict[str, Any], repo: Path, availability: str) -> list[str]:
    pair = sample.get("pair") or {}
    metadata = sample.get("metadata") or {}
    defective = (sample.get("image_path") or pair.get("defective_image_path")
                 or metadata.get("defective_image_path"))
    if not defective and sample.get("slide"):
        defective = str(repo / "runs/part2/rendered" / sample["sample_id"] / "defective.png")
    paths: list[Path] = []
    resolved = relocate_path(defective, repo)
    if not resolved:
        rendered = repo / "runs/part2/rendered" / sample["sample_id"] / "defective.png"
        resolved = rendered.resolve() if rendered.exists() else None
    if resolved:
        paths.append(resolved)
    if availability == "reference_available":
        clean = pair.get("clean_image_path") or metadata.get("clean_image_path")
        if not clean and sample.get("slide"):
            clean = str(repo / "runs/part2/rendered" / sample["sample_id"] / "clean.png")
        clean_path = relocate_path(clean, repo)
        if not clean_path:
            rendered = repo / "runs/part2/rendered" / sample["sample_id"] / "clean.png"
            clean_path = rendered.resolve() if rendered.exists() else None
        if clean_path:
            paths.insert(0, clean_path)
    if availability == "deck_context_available":
        for value in metadata.get("page_image_paths", []):
            page = relocate_path(value, repo)
            if page and page not in paths:
                paths.append(page)
    return [str(path) for path in paths]


def _evidence_source(availability: str, is_deck: bool) -> EvidenceSource:
    return {
        "image_structure": EvidenceSource.STRUCTURE,
        "reference_available": EvidenceSource.REFERENCE,
        "deck_context_available": EvidenceSource.DECK_CONTEXT,
    }.get(availability, EvidenceSource.DECK_CONTEXT if is_deck else EvidenceSource.PIXELS)


def _requested_context(action: str) -> list[EvidenceSource]:
    return {
        "CALL_LINTER": [EvidenceSource.STRUCTURE],
        "REQUEST_REFERENCE": [EvidenceSource.REFERENCE],
        "REQUEST_DECK": [EvidenceSource.DECK_CONTEXT],
    }.get(action, [])


def _answer_for(sample: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    is_deck = bool(sample.get("deck"))
    result = deck_result_from_labels(sample) if is_deck else page_result_from_labels(sample)
    action = target["target_action"]
    data = result.model_dump(mode="json")
    availability = target["availability"]
    data.update({
        "action": action,
        "confidence": round(float(target.get("distillation_weight", 1.0)), 3),
        "requested_context": [item.value for item in _requested_context(action)],
        "evidence_source": (EvidenceSource.NONE.value if action != "ANSWER" else
                            _evidence_source(availability, is_deck).value),
    })
    teacher = target.get("target_finding") or {}
    teacher_locator = teacher.get("locator") or {}
    if action == "ANSWER" and target.get("target_kind") == "distill" and teacher.get("has_defect"):
        base = data["findings"][0]
        base["locator"] = Locator(
            level=ExamLevel.PAGE,
            page_id=data["page_id"],
            element_id=teacher_locator.get("element") or base["locator"].get("element_id"),
        ).model_dump(mode="json")
        region = teacher_locator.get("region", "unspecified region")
        base["evidence"] = (
            f"Teacher-localized rendered overflow at {region}: "
            f"{teacher_locator.get('element', 'named content element')}."
        )
    if action != "ANSWER":
        data.update(has_defect=False, findings=[], clean_dimensions=[])
    model = DeckExamResult if is_deck else PageExamResult
    return model.model_validate(data).model_dump(mode="json")


def _structure_text(sample: dict[str, Any], availability: str) -> str:
    payload: dict[str, Any] = {"availability": availability}
    if availability == "image_structure":
        payload["structure"] = sample.get("slide") or sample.get("deck") or sample.get("oracle")
    elif availability == "deck_context_available":
        payload["deck_context"] = sample.get("deck") or sample.get("oracle")
    elif availability == "reference_available":
        payload["reference_note"] = "The first image is the clean/reference candidate when two images are supplied."
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _task_for(target: dict[str, Any]) -> str:
    kind = target["target_kind"]
    if kind in {"pairwise", "clean_clean_pairwise"}:
        return "pair"
    if kind == "distill":
        return "distill"
    if kind == "route" or target["target_action"] != "ANSWER":
        return "route"
    return "detect"


def build_d3_training_records(repo: Path, *, include_splits: set[str] | None = None,
                              max_per_cell: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialise multimodal records without reading either final-test manifest."""
    include_splits = include_splits or {"train", "dev"}
    samples: dict[str, dict[str, Any]] = {}
    for source in (repo / "data/part2/manifest.jsonl",
                   repo / "release/part3/manifests/manifest_g7_rendered.jsonl"):
        for row in read_jsonl(source):
            samples[row["sample_id"]] = row
    # Clean-deck controls exist first as split records rather than Part-2 manifest rows.
    # Materialise contract-shaped samples from their immutable clean deck IR.
    for row in read_jsonl(repo / "data/part3/d3/split_manifest.jsonl"):
        if row["sample_id"] in samples or row.get("record_kind") != "clean_deck_negative":
            continue
        deck_path = relocate_path((row.get("pair") or {}).get("clean_deck_path"), repo)
        if not deck_path:
            continue
        deck = json.loads(deck_path.read_text())
        samples[row["sample_id"]] = {
            "sample_id": row["sample_id"], "slide": None, "deck": deck,
            "image_path": None, "labels": [], "oracle": deck,
            "pair": row.get("pair") or {},
            "metadata": {"split": row["split"], "clean_deck_path": str(deck_path)},
        }
    targets = read_jsonl(repo / "release/part3/d3/training_targets.jsonl")
    pair_orders: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for order in read_jsonl(repo / "data/part3/d3/pairwise_orders.jsonl"):
        pair_orders[order["sample_id"]].append(order)
    cell_counts: Counter[tuple[str, str, str, str]] = Counter()
    records: list[dict[str, Any]] = []
    skipped = Counter()
    for target in targets:
        if target["split"] not in include_splits or not target.get("included", True):
            continue
        sample = samples.get(target["sample_id"])
        if not sample:
            skipped["missing_sample"] += 1
            continue
        prefix = target["defect"].split("_", 1)[0]
        cell = (target["split"], prefix, target["availability"], target["target_action"])
        if max_per_cell is not None and cell_counts[cell] >= max_per_cell:
            continue
        images = image_paths_for_sample(sample, repo, target["availability"])
        if not images and target["availability"] in {"image_only", "reference_available"}:
            skipped["missing_image"] += 1
            continue
        output = _answer_for(sample, target)
        task = _task_for(target)
        raw_severity = float(next(iter(sample.get("labels") or [{}]), {}).get("severity", 0.0))
        if target["defect"] == "NO_DEFECT":
            severity_target = 0.0
        else:
            severity_target = {"none": 0.0, "minor": 1 / 3, "moderate": 2 / 3, "severe": 1.0}[
                severity_level_for_label(target["defect"], raw_severity).value]
        variants: list[tuple[str, list[str], float | None]] = [("single", images, None)]
        if target["target_kind"] == "clean_clean_pairwise" and len(images) == 2:
            variants = [("clean_clean_tie", images, 0.5)]
        elif (target["target_kind"] == "pairwise" and target["availability"] == "reference_available"
              and len(images) == 2 and pair_orders.get(target["sample_id"])):
            variants = []
            # Learn both candidate orders explicitly: the pair head predicts
            # whether the first candidate is better, rather than memorising a
            # canonical clean-first convention.
            for order in sorted(pair_orders[target["sample_id"]], key=lambda row: row["order_index"]):
                ordered_images = images if order["order"] == "clean_defective" else list(reversed(images))
                variants.append((order["order"], ordered_images,
                                 1.0 if order["better"] == "A" else 0.0))
        elif target["target_kind"] == "pairwise" and target["availability"] == "reference_available":
            variants = [("canonical_clean_first", images, 1.0)]
        for pair_order, variant_images, pair_target in variants:
            content: list[dict[str, str]] = [
                {"type": "image", "image": path} for path in variant_images]
            content.append({"type": "text", "text": GENERIC_INSPECTION_INSTRUCTION
                            + "\nINPUT_CONTEXT=" + _structure_text(sample, target["availability"])})
            records.append({
                "record_id": hashlib.sha256(
                    f"{target['sample_id']}|{target['availability']}|{task}|{pair_order}".encode()
                ).hexdigest()[:20],
                "sample_id": target["sample_id"], "split": target["split"], "defect": target["defect"],
                "availability": target["availability"], "task": task,
                "is_clean_deck": bool(sample.get("deck") and not sample.get("slide") and not sample.get("labels")),
                "target_kind": target["target_kind"], "pair_order": pair_order,
                "target_action": target["target_action"], "action_id": ACTION_TO_ID[target["target_action"]],
                "target_confidence": float(target.get("distillation_weight", 1.0)),
                "severity": raw_severity, "severity_target": severity_target,
                "severity_chain": f"{(sample.get('slide') or {}).get('slide_id', target['sample_id'])}|{target['defect']}",
                "pair_target": pair_target,
                "weight": float(target.get("distillation_weight", 1.0)),
                "messages": [{"role": "user", "content": content},
                             {"role": "assistant", "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}]}],
                "images": variant_images,
            })
        cell_counts[cell] += 1
    summary = {
        "records": len(records), "splits": dict(Counter(r["split"] for r in records)),
        "tasks": dict(Counter(r["task"] for r in records)),
        "actions": dict(Counter(r["target_action"] for r in records)),
        "defects": dict(Counter(r["defect"].split("_", 1)[0] for r in records)),
        "skipped": dict(skipped), "generic_instruction_sha256": hashlib.sha256(
            GENERIC_INSPECTION_INSTRUCTION.encode()).hexdigest(),
        "final_test_read": False,
    }
    return records, summary


def export_d3_training(repo: Path, out_dir: Path, *, max_per_cell: int | None = None) -> dict[str, Any]:
    records, summary = build_d3_training_records(repo, max_per_cell=max_per_cell)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "dev"):
        write_jsonl(out_dir / f"d3_{split}.jsonl", (r for r in records if r["split"] == split))
    class_router = fit_class_router([row for row in records if row["split"] == "train"],
                                    [row for row in records if row["split"] == "dev"])
    (out_dir / "class_router.json").write_text(json.dumps(
        class_router, ensure_ascii=False, indent=2))
    summary.update({"train_sha256": sha256_file(out_dir / "d3_train.jsonl"),
                    "dev_sha256": sha256_file(out_dir / "d3_dev.jsonl"),
                    "class_router": "class_router.json", "losses": list(LOSS_NAMES)})
    (out_dir / "export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


@dataclass
class LossWeights:
    detect: float = 1.0
    distill: float = 1.0
    pair: float = 1.0
    severity: float = 0.2
    route: float = 0.5
    select: float = 0.2

    def enabled(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in LOSS_NAMES}


def action_class_weights(rows: list[dict[str, Any]], mode: str = "sqrt-inverse") -> list[float]:
    """Return mean-normalised train-only weights for the route objective."""
    counts = Counter(int(row["action_id"]) for row in rows)
    if mode == "none":
        return [1.0] * len(ACTIONS)
    missing = [ACTIONS[index] for index in range(len(ACTIONS)) if not counts[index]]
    if missing:
        raise ValueError(f"training split is missing route actions: {missing}")
    exponent = 1.0 if mode == "inverse" else 0.5
    raw = [1.0 / (counts[index] ** exponent) for index in range(len(ACTIONS))]
    mean = sum(raw) / len(raw)
    return [value / mean for value in raw]


def action_sample_weights(rows: list[dict[str, Any]]) -> list[float]:
    """Inverse-frequency weights yielding a uniform expected action mixture."""
    counts = Counter(int(row["action_id"]) for row in rows)
    missing = [ACTIONS[index] for index in range(len(ACTIONS)) if not counts[index]]
    if missing:
        raise ValueError(f"training split is missing route actions: {missing}")
    return [1.0 / counts[int(row["action_id"])] for row in rows]
