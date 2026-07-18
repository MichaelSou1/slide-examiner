#!/usr/bin/env python3
"""Normalize, score, compare, and plot frozen D3 evaluation traces."""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.d3_evaluation import (  # noqa: E402
    endpoint_rows,
    exact_mcnemar,
    holm_family,
    normalize_runtime_row,
    pareto_frontier,
    parse_generated_contract,
    prompt_row,
    score_rows,
)
from slide_examiner.api_config import (  # noqa: E402
    build_completion_with_metadata,
    load_dotenv,
    resolve_role,
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
    for checkout_root in ("/data/slide-examiner/", "/home/gpus/slide-examiner/"):
        if checkout_root in value:
            return value.split(checkout_root, 1)[1]
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
                              split: str = "validation", offset_per_class: int = 0
                              ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create frozen positive/clean initial rows followed by hidden escalation counterparts."""
    by_defect: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("labels"):
            by_defect[str(row["labels"][0]["type"])].append(row)
    selected = [row for defect in sorted(by_defect)
                for row in sorted(by_defect[defect], key=lambda item: str(item["sample_id"]))[
                    offset_per_class:offset_per_class + per_class]]
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
               "initial_limit": len(initial), "offset_per_class": offset_per_class,
               "per_class_pairs": {defect: sum(row["defect"] == defect for row in initial) // 2
                                   for defect in sorted(by_defect)}}
    return initial + counterparts, summary


def drop_availability(rows: list[dict[str, Any]], unavailable: str
                      ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Remove unavailable escalation evidence while preserving the frozen initial cohort."""
    if unavailable not in {"image_structure", "reference_available"}:
        raise ValueError(f"unsupported unavailable evidence: {unavailable}")
    kept = [row for row in rows if row.get("availability") != unavailable]
    return kept, {
        "unavailable": unavailable,
        "source_records": len(rows),
        "kept_records": len(kept),
        "removed_counterparts": len(rows) - len(kept),
        "initial_records": sum(row.get("availability") == "image_only" for row in kept),
    }


def _deck_message(images: list[str], sample_id: str) -> list[dict[str, Any]]:
    context = {"availability": "deck_context_available", "deck_id": sample_id,
               "page_order": list(range(len(images)))}
    instruction = (
        "Inspect the complete ordered slide deck for narrative-order breaks or missing logic "
        "sections. Return the strict DeckExamResult JSON contract and ground any finding in "
        "specific related_page_ids.\nINPUT_CONTEXT="
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )
    content = [{"type": "image", "image": image} for image in images]
    content.append({"type": "text", "text": instruction})
    return [{"role": "user", "content": content}]


def materialize_deck_pairs(positive_rows: list[dict[str, Any]], clean_rows: list[dict[str, Any]],
                           repo: Path, per_class: int = 12
                           ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build S2/S5 first-page requests plus complete paired positive/clean deck contexts."""
    clean_by_source = {str(row["sample_id"]).removesuffix("__CLEAN"): row for row in clean_rows}
    by_defect: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in positive_rows:
        for label in row.get("labels", []):
            defect = str(label.get("type", ""))
            if defect in {"S2_NARRATIVE_ORDER_BREAK", "S5_MISSING_LOGIC_SECTION"}:
                by_defect[defect].append(row)
    initial, counterparts = [], []
    selected_counts: dict[str, int] = {}
    for defect in sorted(by_defect):
        selected = [row for row in sorted(by_defect[defect], key=lambda item: str(item["sample_id"]))
                    if str(row["sample_id"]) in clean_by_source][:per_class]
        selected_counts[defect] = len(selected)
        for positive in selected:
            pair_id = str(positive["sample_id"])
            clean = clean_by_source[pair_id]
            for is_clean, source in ((False, positive), (True, clean)):
                sample_id = pair_id + ("__clean" if is_clean else "__positive")
                paths = [_relocatable(str(path), repo)
                         for path in source.get("metadata", {}).get("page_image_paths", [])]
                if not paths:
                    raise ValueError(f"deck has no page images: {source['sample_id']}")
                common = {"sample_id": sample_id, "pair_id": pair_id, "defect": defect,
                          "is_clean": is_clean, "is_clean_deck": is_clean,
                          "severity": 0.0 if is_clean else 1.0,
                          "severity_chain": f"{sample_id}|{defect}", "split": "validation"}
                initial.append({**common, "record_id": sample_id + "__image_only",
                                "availability": "image_only", "target_action": "REQUEST_DECK",
                                "images": paths[:1],
                                "messages": _message(paths[:1], "image_only")})
                counterparts.append({
                    **common, "record_id": sample_id + "__deck_context",
                    "availability": "deck_context_available", "target_action": "ANSWER",
                    "images": paths, "messages": _deck_message(paths, sample_id),
                })
    summary = {"positive_source_rows": len(positive_rows), "clean_source_rows": len(clean_rows),
               "selected_pairs_per_class": selected_counts, "initial_records": len(initial),
               "counterpart_records": len(counterparts), "initial_limit": len(initial)}
    return initial + counterparts, summary


def materialize_slideaudit(rows: list[dict[str, Any]], repo: Path, per_class: int = 20
                           ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build real image-only present/confident-absent cells without inventing IR/reference."""
    defects = sorted({str(label["type"]) for row in rows for label in row.get("labels", [])})
    output: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for defect in defects:
        positives = [row for row in rows
                     if defect in {str(label["type"]) for label in row.get("labels", [])}]
        negatives = [row for row in rows
                     if defect in set(row.get("metadata", {}).get("confident_absent", []))
                     and defect not in {str(label["type"]) for label in row.get("labels", [])}]
        positives = sorted(positives, key=lambda item: str(item["sample_id"]))[:per_class]
        negatives = sorted(negatives, key=lambda item: str(item["sample_id"]))[:per_class]
        counts[defect] = {"positive": len(positives), "confident_absent": len(negatives)}
        for is_clean, cohort in ((False, positives), (True, negatives)):
            for source in cohort:
                source_id = str(source["sample_id"])
                sample_id = f"{source_id}__{defect}__{'absent' if is_clean else 'present'}"
                image = _relocatable(str(source["image_path"]), repo)
                output.append({
                    "record_id": sample_id + "__image_only", "sample_id": sample_id,
                    "pair_id": f"slideaudit__{defect}__{source_id}", "defect": defect,
                    "is_clean": is_clean, "is_clean_deck": False, "severity": 1.0,
                    "severity_chain": f"{sample_id}|{defect}", "split": "validation",
                    "availability": "image_only", "target_action": "ANSWER",
                    "images": [image], "messages": _message([image], "image_only"),
                    "external_source": "SlideAudit",
                    "negative_definition": "confident_absent" if is_clean else "present",
                })
    return output, {"source_rows": len(rows), "records": len(output),
                    "per_class": counts, "native_ir": False, "native_reference": False}


def materialize(args: argparse.Namespace) -> None:
    if args.split == "final_test":
        if not args.freeze_registry:
            raise RuntimeError("--freeze-registry is mandatory before reading final_test")
        assert_final_test_unlocked(args.repo.resolve(), args.freeze_registry.resolve())
    source_rows = [row for manifest in args.manifest for row in read_jsonl(manifest)]
    rows, summary = materialize_paired_images(
        source_rows, args.repo.resolve(), args.per_class, split=args.split,
        offset_per_class=args.offset_per_class)
    write_jsonl(args.output, rows)
    summary.update({"split": args.split,
                    "manifests": [{"path": str(path), "sha256": sha256(path)}
                                  for path in args.manifest], "output": str(args.output),
                    "output_sha256": sha256(args.output)})
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def materialize_slice(args: argparse.Namespace) -> None:
    source = read_jsonl(args.input)
    rows, summary = drop_availability(source, args.unavailable)
    write_jsonl(args.output, rows)
    summary.update({"input": str(args.input), "input_sha256": sha256(args.input),
                    "output": str(args.output), "output_sha256": sha256(args.output),
                    "final_test_read": False})
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def materialize_decks(args: argparse.Namespace) -> None:
    positives = [row for path in args.manifest for row in read_jsonl(path)]
    cleans = [row for path in args.clean_manifest for row in read_jsonl(path)]
    rows, summary = materialize_deck_pairs(
        positives, cleans, args.repo.resolve(), args.per_class)
    write_jsonl(args.output, rows)
    summary.update({
        "manifests": [{"path": str(path), "sha256": sha256(path)}
                      for path in [*args.manifest, *args.clean_manifest]],
        "output": str(args.output), "output_sha256": sha256(args.output),
        "final_test_read": False,
    })
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def materialize_real(args: argparse.Namespace) -> None:
    rows, summary = materialize_slideaudit(
        read_jsonl(args.manifest), args.repo.resolve(), args.per_class)
    write_jsonl(args.output, rows)
    summary.update({"manifest": str(args.manifest), "manifest_sha256": sha256(args.manifest),
                    "output": str(args.output), "output_sha256": sha256(args.output),
                    "final_test_read": False})
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


def _api_messages(row: dict[str, Any], repo: Path, prompt_mode: str) -> list[dict[str, Any]]:
    """Convert a local D3 prompt into OpenAI-compatible multimodal messages."""
    messages = json.loads(json.dumps(prompt_row(row, prompt_mode)["messages"]))
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") != "image":
                continue
            value = str(item.pop("image"))
            path = Path(value) if Path(value).is_absolute() else repo / value
            if value.startswith(("http://", "https://", "data:")):
                url = value
            else:
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                url = f"data:{mime};base64,{encoded}"
            item["type"] = "image_url"
            item["image_url"] = {"url": url}
        is_deck = str(row.get("defect", "")).split("_", 1)[0] in {"S2", "S3", "S5"}
        identifier = '"deck_id":"<sample id>"' if is_deck else '"page_id":"<sample id>"'
        allowed_types = (
            "S2_NARRATIVE_ORDER_BREAK, S3_TERMINOLOGY_INCONSISTENCY, "
            "and S5_MISSING_LOGIC_SECTION" if is_deck else
            "G1_TEXT_OVERFLOW, G2_ELEMENT_OVERLAP, G3_ALIGNMENT_OFFSET, "
            "G4_FONT_SIZE_INCONSISTENCY, G5_BRAND_COLOR_VIOLATION, G6_MARGIN_VIOLATION, "
            "G7_RENDER_CONTAINMENT_OVERFLOW, S1_TITLE_BODY_MISMATCH, "
            "S4_DENSITY_RULE_VIOLATION, and S6_IMAGE_TEXT_CONTRADICTION"
        )
        locator = (
            '{"level":"deck","related_page_ids":["<visible page id>"]}' if is_deck else
            '{"level":"page","page_id":"<sample id>","element_id":"<visible element or null>",'
            '"bbox":null,"related_page_ids":[]}'
        )
        contract = (
            "\nSTRICT_OUTPUT_SCHEMA: Return JSON only. Use this exact shape: "
            "{" + identifier + ',"action":"ANSWER|CALL_LINTER|REQUEST_REFERENCE|'
            'REQUEST_DECK|DEFER","confidence":0.0,"requested_context":[],"evidence_source":'
            '"pixels|structure|reference|deck_context|linter|none","has_defect":false,'
            '"findings":[],"clean_dimensions":[]}. Allowed finding types are ' + allowed_types
            + '. Each finding must be '
            '{"type":"<allowed type>","severity":"minor|moderate|severe",'
            '"locator":' + locator + ',"evidence":"<visible '
            'evidence>","fix_suggestion":"<specific fix>"}. Never emit finding strings or '
            'invent new type names; omit an unsupported observation instead. Return at most one '
            'finding, keep evidence and fix_suggestion under 30 words each, and do not explain '
            'your reasoning outside the JSON.'
        )
        for item in reversed(content):
            if item.get("type") == "text":
                item["text"] = str(item.get("text", "")) + contract
                break
    return [{
        "role": "system",
        "content": "Return one compact JSON object only. Do not output reasoning or markdown.",
    }, *messages]


def api_infer(args: argparse.Namespace) -> None:
    """Run API C0/C3 controls into the same row-level runtime contract."""
    load_dotenv(args.env)
    role = resolve_role("examiner", default_model=os.environ.get("OPENAI_MODEL"))
    model = args.model or role["model"]
    if not model:
        raise RuntimeError("Set --model, PART3_EXAMINER_MODEL, or OPENAI_MODEL")
    complete = build_completion_with_metadata(
        str(model), role["base_url"], api_key_env=str(role["api_key_env"]),
        api_style=str(role["api_style"]), max_tokens=args.max_tokens, temperature=0.0,
    )
    source = read_jsonl(args.input)
    selected = source[:args.limit] if args.limit is not None else source
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = ({str(row["record_id"]) for row in read_jsonl(args.output)}
                 if args.output.exists() else set())
    for index, row in enumerate(selected, 1):
        record_id = str(row["record_id"])
        if record_id in completed:
            continue
        trace: dict[str, Any] = {
            "record_id": record_id, "sample_id": row["sample_id"],
            "pair_id": row.get("pair_id"), "defect": row.get("defect"),
            "availability": row.get("availability"), "target_action": row.get("target_action"),
            "is_clean": row.get("is_clean", False), "is_clean_deck": row.get("is_clean_deck", False),
            "api_model_requested": str(model), "api_style": str(role["api_style"]),
            "prompt_mode": args.prompt_mode, "model_calls": 1, "external_calls": 0,
        }
        try:
            response = complete(_api_messages(row, args.repo.resolve(), args.prompt_mode))
            parsed, error, repaired = parse_generated_contract(str(response["text"]), row)
            predicted_action = str((parsed or {}).get("action") or "DEFER")
            trace.update({
                "api_model_actual": response["model"], "raw": response["text"],
                "parsed": parsed or {"has_defect": False, "findings": []},
                "predicted_action": predicted_action, "raw_predicted_action": predicted_action,
                "route_confidence": float((parsed or {}).get("confidence", 0.0) or 0.0),
                "parse_error": error, "contract_repaired": repaired,
                "prompt_tokens": response["prompt_tokens"],
                "completion_tokens": response["completion_tokens"],
                "total_tokens": response["total_tokens"],
                "latency_seconds": response["latency_seconds"],
                "failure": bool(error), "escalation": None,
            })
        except Exception as exc:  # noqa: BLE001 - preserve API failures in the trace
            trace.update({
                "api_model_actual": None, "raw": "", "parsed": {"has_defect": False, "findings": []},
                "predicted_action": "DEFER", "raw_predicted_action": None,
                "route_confidence": 0.0, "parse_error": None,
                "api_error": f"{type(exc).__name__}: {exc}"[:1000], "contract_repaired": False,
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                "latency_seconds": 0.0, "failure": True, "escalation": None,
            })
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(trace, ensure_ascii=False) + "\n")
        if index % 10 == 0 or index == len(selected):
            print(json.dumps({"completed": index, "total": len(selected)}))
    selected_ids = {str(row["record_id"]) for row in selected}
    rows = [row for row in read_jsonl(args.output) if str(row["record_id"]) in selected_ids]
    summary = {
        "records": len(rows), "failures": sum(bool(row.get("failure")) for row in rows),
        "model_requested": str(model),
        "models_actual": sorted({str(row["api_model_actual"]) for row in rows
                                  if row.get("api_model_actual")}),
        "api_style": str(role["api_style"]), "prompt_mode": args.prompt_mode,
        "input": str(args.input), "input_sha256": sha256(args.input),
        "output": str(args.output), "output_sha256": sha256(args.output),
        "final_test_read": False,
    }
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


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
        endpoint = str(spec.get("endpoint", "paired row correctness"))
        left_endpoint, left_summary = endpoint_rows(left, endpoint)
        right_endpoint, right_summary = endpoint_rows(right, endpoint)
        test = exact_mcnemar(left_endpoint, right_endpoint, key=spec.get("key", "record_id"))
        test["left_endpoint_summary"] = left_summary
        test["right_endpoint_summary"] = right_summary
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
    materializer.add_argument("--offset-per-class", type=int, default=0)
    materializer.add_argument("--freeze-registry", type=Path)
    materializer.set_defaults(function=materialize)
    slicer = sub.add_parser("materialize-slice")
    slicer.add_argument("--input", type=Path, required=True)
    slicer.add_argument("--output", type=Path, required=True)
    slicer.add_argument("--unavailable", choices=("image_structure", "reference_available"),
                        required=True)
    slicer.set_defaults(function=materialize_slice)
    deck_materializer = sub.add_parser("materialize-decks")
    deck_materializer.add_argument("--repo", type=Path, default=Path.cwd())
    deck_materializer.add_argument("--manifest", type=Path, nargs="+", required=True)
    deck_materializer.add_argument("--clean-manifest", type=Path, nargs="+", required=True)
    deck_materializer.add_argument("--output", type=Path, required=True)
    deck_materializer.add_argument("--per-class", type=int, default=12)
    deck_materializer.set_defaults(function=materialize_decks)
    real_materializer = sub.add_parser("materialize-slideaudit")
    real_materializer.add_argument("--repo", type=Path, default=Path.cwd())
    real_materializer.add_argument("--manifest", type=Path, required=True)
    real_materializer.add_argument("--output", type=Path, required=True)
    real_materializer.add_argument("--per-class", type=int, default=20)
    real_materializer.set_defaults(function=materialize_real)
    normalizer = sub.add_parser("normalize")
    normalizer.add_argument("--repo", type=Path, default=Path.cwd())
    normalizer.add_argument("--input", type=Path, required=True)
    normalizer.add_argument("--output", type=Path, required=True)
    normalizer.add_argument("--arm", required=True)
    normalizer.add_argument("--split", choices=("dev", "validation", "final_test"), required=True)
    normalizer.add_argument("--freeze-registry", type=Path)
    normalizer.set_defaults(function=normalize)

    api_runner = sub.add_parser("api-infer")
    api_runner.add_argument("--repo", type=Path, default=Path.cwd())
    api_runner.add_argument("--env", type=Path, default=Path(".env"))
    api_runner.add_argument("--input", type=Path, required=True)
    api_runner.add_argument("--output", type=Path, required=True)
    api_runner.add_argument("--prompt-mode", choices=("generic", "c3"), required=True)
    api_runner.add_argument("--model")
    api_runner.add_argument("--max-tokens", type=int, default=384)
    api_runner.add_argument("--limit", type=int)
    api_runner.set_defaults(function=api_infer)

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
