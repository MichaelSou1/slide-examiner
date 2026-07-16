"""Reproducible data and teacher-supervision utilities for the D3 critic."""
from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

EXPERTS = ("C0_GENERIC", "C3_ATOMIC", "PAIRWISE_REFERENCE", "LINTER", "DEFER")
AVAILABILITY = ("image_only", "image_structure", "reference_available", "deck_context_available")
GEOMETRY = {f"G{i}" for i in range(2, 7)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def defect_of(rec: dict[str, Any]) -> str:
    return rec.get("labels", [{}])[0].get("type", "NO_DEFECT")


def source_deck(rec: dict[str, Any]) -> str:
    obj = rec.get("deck") or rec.get("slide") or rec.get("page") or rec.get("oracle") or {}
    value = obj.get("deck_id") or obj.get("slide_id") or rec.get("sample_id", "unknown")
    if value.startswith("part2_"):
        bits = value.split("_")
        return "_".join(bits[:-1]) if bits[-1].isdigit() else value
    return value.split("_G", 1)[0].split("_S", 1)[0]


def template_id(rec: dict[str, Any]) -> str:
    md = rec.get("metadata", {})
    return str(md.get("template_family") or md.get("template_condition") or "unknown")


def content_cluster(rec: dict[str, Any]) -> str:
    # Conservative grouping: near-duplicate slides from one generated business
    # story can never cross a split.
    return hashlib.sha256(source_deck(rec).encode()).hexdigest()[:16]


def group_split(rec: dict[str, Any], seed: int) -> str:
    # source_deck/content_cluster is the strongest identity.  Template variants
    # of the same story must not be hashed independently.
    key = f"{seed}|{source_deck(rec)}|{content_cluster(rec)}"
    return "train" if int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 10 < 8 else "dev"


def compact_record(rec: dict[str, Any], split: str) -> dict[str, Any]:
    return {
        "sample_id": rec["sample_id"],
        "defect": defect_of(rec),
        "severity": rec.get("labels", [{}])[0].get("severity", 0),
        "scope": "deck" if rec.get("deck") else "page",
        "split": split,
        "source_deck": source_deck(rec),
        "template_id": template_id(rec),
        "content_cluster": content_cluster(rec),
        "severity_chain": f"{source_deck(rec)}|{defect_of(rec)}|{template_id(rec)}",
        "pair": rec.get("pair") or {},
        "record_kind": "positive",
    }


def build_splits(part2: Path, w5: Path, out_dir: Path, seed: int) -> dict[str, Any]:
    records = read_jsonl(part2)
    split_rows = [compact_record(r, group_split(r, seed)) for r in records]
    validation = [compact_record(r, "validation") for r in read_jsonl(w5)]

    # Explicit deck-scope clean controls, separate from page NO_DEFECT.
    seen: set[tuple[str, str, str]] = set()
    deck_negatives = []
    for row in split_rows:
        if row["scope"] != "deck":
            continue
        key = (row["split"], row["source_deck"], row["template_id"])
        if key in seen:
            continue
        seen.add(key)
        clean_path = row["pair"].get("clean_deck_path")
        if not clean_path or not Path(clean_path).exists():
            raise FileNotFoundError(f"missing clean deck for {row['sample_id']}: {clean_path}")
        clean_hash = sha256_file(Path(clean_path))
        deck_negatives.append({**row,
            "sample_id": f"{row['source_deck']}__{row['template_id']}__CLEAN_DECK",
            "defect": "NO_DEFECT", "severity": 0, "negative_scope": "deck",
            "record_kind": "clean_deck_negative",
            "pair": {"clean_deck_path": clean_path, "clean_deck_sha256": clean_hash,
                     "paired_positive_id": row["sample_id"], "reference_arm": "clean"}})

    pairwise = []
    for row in split_rows:
        prefix = row["defect"].split("_", 1)[0]
        if prefix not in {"G1", "S2", "S5", "S6"}:
            continue
        randomization_seed = int(hashlib.sha256(f"{seed}|{row['sample_id']}".encode()).hexdigest()[:8], 16)
        first = random.Random(randomization_seed).choice(["clean_defective", "defective_clean"])
        orders = [first, "defective_clean" if first == "clean_defective" else "clean_defective"]
        for order_index, order in enumerate(orders):
            better = "A" if order == "clean_defective" else "B"
            pairwise.append({"sample_id": row["sample_id"], "split": row["split"],
                             "defect": row["defect"], "order": order, "better": better,
                             "order_index": order_index, "randomization_seed": randomization_seed,
                             "pair_group": row["sample_id"], "source_deck": row["source_deck"],
                             "content_cluster": row["content_cluster"]})
    for row in deck_negatives:
        randomization_seed = int(hashlib.sha256(f"{seed}|{row['sample_id']}".encode()).hexdigest()[:8], 16)
        for order_index, order in enumerate(("clean_clean", "clean_clean")):
            pairwise.append({"sample_id": row["sample_id"], "split": row["split"],
                "defect": "NO_DEFECT", "order": order, "better": "TIE",
                "order_index": order_index, "randomization_seed": randomization_seed,
                "pair_group": row["sample_id"], "source_deck": row["source_deck"],
                "content_cluster": row["content_cluster"]})

    availability = []
    for row in split_rows + deck_negatives:
        prefix = row["defect"].split("_", 1)[0]
        for condition in AVAILABILITY:
            resources = {"image": True, "structure": condition == "image_structure",
                         "reference": condition == "reference_available",
                         "deck_context": condition == "deck_context_available"}
            if prefix in GEOMETRY:
                action = "CALL_LINTER" if resources["structure"] else "DEFER"
            elif prefix in {"G1", "S6"}:
                action = "ANSWER" if condition == "reference_available" else "REQUEST_REFERENCE"
            elif prefix in {"S2", "S5"}:
                action = "ANSWER" if condition == "deck_context_available" else "REQUEST_DECK"
            else:
                action = "ANSWER"
            availability.append({"sample_id": row["sample_id"], "split": row["split"],
                                 "defect": row["defect"], "availability": condition,
                                 "resources": resources, "target_action": action})

    write_jsonl(out_dir / "split_manifest.jsonl", split_rows + deck_negatives + validation)
    write_jsonl(out_dir / "pairwise_orders.jsonl", pairwise)
    write_jsonl(out_dir / "availability_records.jsonl", availability)
    return {"part2": records, "split": split_rows, "validation": validation,
            "deck_negatives": deck_negatives, "pairwise": pairwise, "availability": availability}


def append_grouped_records(built: dict[str, Any], records: list[dict[str, Any]], seed: int) -> None:
    """Add a disjoint source (for example G7) to the train/dev role in-place."""
    extra = [compact_record(r, group_split(r, seed)) for r in records]
    built["part2"].extend(records)
    built["split"].extend(extra)
    for row in extra:
        prefix = row["defect"].split("_", 1)[0]
        for condition in AVAILABILITY:
            resources = {"image": True, "structure": condition == "image_structure",
                         "reference": condition == "reference_available",
                         "deck_context": condition == "deck_context_available"}
            if prefix in GEOMETRY:
                action = "CALL_LINTER" if resources["structure"] else "DEFER"
            elif prefix in {"G1", "S6"}:
                action = "ANSWER" if resources["reference"] else "REQUEST_REFERENCE"
            elif prefix in {"S2", "S5"}:
                action = "ANSWER" if resources["deck_context"] else "REQUEST_DECK"
            else:
                action = "ANSWER"
            built["availability"].append({"sample_id": row["sample_id"], "split": row["split"],
                "defect": row["defect"], "availability": condition,
                "resources": resources, "target_action": action})


def _parse_bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text not in {"true", "false"}:
        raise ValueError(f"invalid boolean: {value!r}")
    return text == "true"


def _bool(value: Any) -> bool:
    try:
        return _parse_bool(value)
    except ValueError:
        return False


def _validate_point_trace(row: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        for key in ("is_clean", "failure", "has_defect", "named_target"):
            _parse_bool(row.get(key))
        for key in ("predicted_types", "other"):
            parsed = json.loads(row.get(key, ""))
            if not isinstance(parsed, list):
                return False, f"{key}_not_list"
        if row.get("locator"):
            locator = json.loads(row["locator"])
            if not isinstance(locator, dict):
                return False, "locator_not_object"
        if not _bool(row.get("failure")) and not row.get("raw"):
            return False, "missing_raw"
    except (ValueError, json.JSONDecodeError) as exc:
        return False, f"parse_error:{exc}"
    return True, None


def _validate_afc_trace(row: dict[str, Any]) -> tuple[bool, str | None]:
    if not row.get("probe_id") or not row.get("partner_id"):
        return False, "missing_id"
    allowed = {"a", "b", "tie"}
    if row.get("pick_order0", "").lower() not in allowed or row.get("pick_order1", "").lower() not in allowed:
        return False, "invalid_pick"
    return True, None


def load_traces(paths: Iterable[Path]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    point: dict[tuple[str, str], dict[str, Any]] = {}
    afc: list[dict[str, Any]] = []
    for path in paths:
        expert = "C3_ATOMIC" if "_C3_" in path.name else "C0_GENERIC"
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                row["trace_path"] = str(path)
                row["trace_sha256"] = sha256_file(path)
                if "probe_id" in row:
                    row["parser_valid"], row["parser_error"] = _validate_afc_trace(row)
                    afc.append(row)
                else:
                    row["parser_valid"], row["parser_error"] = _validate_point_trace(row)
                    point[(row["sample_id"], expert)] = row
    return point, afc


def trace_cache_report(paths: Iterable[Path]) -> dict[str, Any]:
    sources = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        is_afc = bool(rows and "probe_id" in rows[0])
        checked = [_validate_afc_trace(r) if is_afc else _validate_point_trace(r) for r in rows]
        failures = 0 if is_afc else sum(_bool(r.get("failure")) for r in rows)
        valid = sum(ok for ok, _ in checked)
        sources.append({"path": str(path), "sha256": sha256_file(path), "rows": len(rows),
                        "parser_valid": valid, "parse_errors": len(rows) - valid,
                        "failures": failures})
    return {"cache_kind": "immutable_existing_csv", "retry_policy": {"max_retries": 2,
            "status": "future_calls_only; immutable cache was not re-called",
            "implementation": "scripts/part3_elicit.py --resume --max-retries",
            "retry_on": ["transport_error", "rate_limit", "parse_error"]},
            "failure_policy": "exclude_or_downweight; never map failure to negative", "sources": sources,
            "totals": {"rows": sum(x["rows"] for x in sources),
                       "parser_valid": sum(x["parser_valid"] for x in sources),
                       "parse_errors": sum(x["parse_errors"] for x in sources),
                       "failures": sum(x["failures"] for x in sources)}}


def build_training_targets(split_rows: list[dict[str, Any]], availability: list[dict[str, Any]],
                           d3_rows: list[dict[str, Any]], matrix_rows: list[dict[str, Any]],
                           out_path: Path) -> int:
    split_by_id = {r["sample_id"]: r for r in split_rows}
    d3_by_id = {r["sample_id"]: r for r in d3_rows}
    matrix = {(r["sample_id"], r["expert"]): r for r in matrix_rows}
    targets = []
    for condition in availability:
        row = split_by_id[condition["sample_id"]]
        defect, prefix = row["defect"], row["defect"].split("_", 1)[0]
        action = condition["target_action"]
        finding: dict[str, Any] | None = None
        evidence_source = None
        included = True
        weight = d3_by_id.get(row["sample_id"], {}).get("distillation_weight", 1.0)
        if defect == "NO_DEFECT":
            kind, finding, evidence_source = "negative", {"label": "NO_DEFECT"}, "clean_artifact"
        elif prefix in GEOMETRY:
            kind = "route"
            if action == "CALL_LINTER":
                finding, evidence_source = {"label": defect, "evidence_kind": "structure_linter"}, "linter"
        elif prefix in {"G1", "S6"}:
            kind = "pairwise"
            if action == "ANSWER":
                afc = matrix.get((row["sample_id"], "PAIRWISE_REFERENCE"), {})
                finding, evidence_source = {"label": defect, "pairwise_correct": afc.get("correctness")}, "paired_reference"
        elif prefix in {"S2", "S5"}:
            kind = "deck"
            if action == "ANSWER":
                finding, evidence_source = {"label": defect, "scope": "deck"}, "deck_context"
        elif prefix == "G7":
            kind = "distill"
            c3 = matrix.get((row["sample_id"], "C3_ATOMIC"), {})
            included = bool(c3.get("available") and c3.get("evidence_validity"))
            finding = c3.get("teacher_output") if included else None
            evidence_source = "C3_ATOMIC" if included else None
            weight = weight if included else 0.0
        else:
            kind, finding, evidence_source = "direct", {"label": defect}, "ground_truth"
        targets.append({"sample_id": row["sample_id"], "split": row["split"], "defect": defect,
                        "availability": condition["availability"], "resources": condition["resources"],
                        "target_kind": kind, "target_action": action, "target_finding": finding,
                        "evidence_source": evidence_source, "included": included,
                        "distillation_weight": weight})
    # Real clean-clean ties are explicit ranking targets rather than prose in an objective list.
    for row in split_rows:
        if row["defect"] == "NO_DEFECT":
            targets.append({"sample_id": row["sample_id"], "split": row["split"],
                "defect": "NO_DEFECT", "availability": "reference_available",
                "resources": {"image": True, "reference": True}, "target_kind": "clean_clean_pairwise",
                "target_action": "ANSWER", "target_finding": {"preference": "TIE"},
                "evidence_source": "clean_artifact", "included": True, "distillation_weight": 1.0})
    return write_jsonl(out_path, targets)


def _expert_row(sample: dict[str, Any], expert: str, trace: dict[str, Any] | None,
                clean_trace: dict[str, Any] | None, afc_trace: dict[str, Any] | None,
                linter_types: set[str]) -> dict[str, Any]:
    defect = defect_of(sample)
    prefix = defect.split("_", 1)[0]
    available, reason = True, None
    correctness = fp = evidence = 0.0
    calls: int | None = 0
    tokens: int | None = None
    latency: float | None = None
    failure = False
    trace_info: dict[str, Any] = {}
    if expert in {"C0_GENERIC", "C3_ATOMIC"}:
        if trace is None:
            available, reason = False, "no_cached_api_trace"
        else:
            failure = _bool(trace.get("failure"))
            available = bool(trace.get("parser_valid")) and not failure
            reason = "teacher_api_or_parse_failure" if failure else (trace.get("parser_error") if not available else None)
            correctness = float(_bool(trace.get("named_target")))
            if clean_trace and clean_trace.get("parser_valid") and not _bool(clean_trace.get("failure")):
                fp = float(_bool(clean_trace.get("has_defect")))
            else:
                fp = None
            locator = None
            if trace.get("locator"):
                try:
                    locator = json.loads(trace["locator"])
                except json.JSONDecodeError:
                    locator = None
            evidence = float(bool(_bool(trace.get("named_target")) and isinstance(locator, dict)
                                  and (locator.get("element") or locator.get("element_id")
                                       or locator.get("region") or locator.get("page_id"))))
            calls = 1
            trace_info = {"path": trace["trace_path"], "sha256": trace["trace_sha256"],
                          "positive_sample_id": trace.get("sample_id"),
                          "clean_sample_id": clean_trace.get("sample_id") if clean_trace else None}
            trace_info["measurement"] = {"tokens": "unavailable_in_cache", "latency_ms": "unavailable_in_cache"}
            if available:
                trace_info["parser_valid"] = True
            teacher_output = {"has_defect": _bool(trace.get("has_defect")),
                              "named_target": _bool(trace.get("named_target")),
                              "predicted_types": json.loads(trace.get("predicted_types", "[]")),
                              "locator": locator, "raw": trace.get("raw")}
    elif expert == "PAIRWISE_REFERENCE":
        available = bool(afc_trace and afc_trace.get("parser_valid") and prefix in {"G1", "S6"})
        reason = None if available else "reference_or_double_order_trace_unavailable"
        correctness = float(available and afc_trace["pick_order0"].lower() == "a"
                            and afc_trace["pick_order1"].lower() == "b")
        calls = 2 if available else 0
        trace_info = ({"path": afc_trace["trace_path"], "sha256": afc_trace["trace_sha256"],
                       "pick_order0": afc_trace["pick_order0"], "pick_order1": afc_trace["pick_order1"]}
                      if afc_trace else {})
    elif expert == "LINTER":
        available = prefix in GEOMETRY
        reason = None if available else "not_a_structure_owned_class"
        correctness = float(defect in linter_types) if available else 0.0
        evidence = float(correctness)
    else:
        correctness, available = 0.5, True
        calls, tokens, latency = 0, 0, 0.0
    result = {"expert": expert, "available": available, "unavailable_reason": reason,
            "correctness": correctness, "paired_clean_fp": fp,
            "evidence_validity": evidence, "calls": calls, "tokens": tokens,
            "latency_ms": latency, "failure": failure, "trace": trace_info}
    if expert in {"C0_GENERIC", "C3_ATOMIC"} and trace is not None and available:
        result["teacher_output"] = teacher_output
    return result


def expert_to_action(expert: str, defect: str) -> str:
    if expert == "LINTER":
        return "CALL_LINTER"
    if expert == "PAIRWISE_REFERENCE":
        return "REQUEST_REFERENCE"
    if expert == "DEFER":
        return "DEFER"
    if defect.startswith(("S2_", "S5_")):
        return "REQUEST_DECK"
    return "ANSWER"


def build_teacher(records: list[dict[str, Any]], split_rows: list[dict[str, Any]],
                  trace_paths: list[Path], out_dir: Path,
                  lambda_c: float = .05, lambda_fp: float = 1.0,
                  lambda_v: float = .1, margin_threshold: float = .05) -> dict[str, Any]:
    from .geometry import lint_slide
    from .schemas import Slide

    split_by_id = {r["sample_id"]: r for r in split_rows if r["split"] in {"train", "dev"}}
    samples = {r["sample_id"]: r for r in records if r["sample_id"] in split_by_id}
    point, afc = load_traces(trace_paths)
    afc_by_id = {r["probe_id"]: r for r in afc}
    # Materialise a complete sample × expert matrix. Missing cached traces are
    # explicit unavailable rows rather than silently dropping the sample.
    ids = sorted(samples)
    matrix, d3 = [], []
    tie_rank = {"LINTER": 0, "PAIRWISE_REFERENCE": 1, "C0_GENERIC": 2, "C3_ATOMIC": 3, "DEFER": 4}
    for sid in ids:
        sample, split = samples[sid], split_by_id[sid]
        linter_types = {x.type for x in lint_slide(Slide.from_mapping(sample["slide"]))} if sample.get("slide") else set()
        rows = []
        sample_matrix = []
        for expert in EXPERTS:
            row = _expert_row(sample, expert, point.get((sid, expert)),
                              point.get((f"{sid}__CLEAN", expert)), afc_by_id.get(sid), linter_types)
            # The immutable CSV has call counts but no measured usage/latency.
            # Missing measurements remain null and are never treated as zero.
            cost = float(row["calls"] or 0)
            fp_for_utility = row["paired_clean_fp"] if row["paired_clean_fp"] is not None else 0.0
            row["cost_policy"] = "measured_calls_only; tokens_and_latency_unavailable"
            row["utility"] = (row["correctness"] - lambda_c * cost - lambda_fp * fp_for_utility
                              + lambda_v * row["evidence_validity"]) if row["available"] else None
            full = {"sample_id": sid, "split": split["split"], "defect": defect_of(sample), **row}
            matrix.append(full)
            sample_matrix.append(full)
            if row["available"]:
                rows.append(row)
        rows.sort(key=lambda r: (-r["utility"], r["calls"] or 0,
                                 r["paired_clean_fp"] if r["paired_clean_fp"] is not None else 1.0,
                                 -r["evidence_validity"], tie_rank[r["expert"]]))
        best = rows[0]
        second = rows[1] if len(rows) > 1 else best
        margin = best["utility"] - second["utility"] if len(rows) > 1 else 0.0
        chosen = "DEFER" if len(rows) < 2 or margin < margin_threshold else best["expert"]
        d3.append({"sample_id": sid, "split": split["split"], "defect": defect_of(sample),
                   "best_expert": chosen, "raw_best_expert": best["expert"],
                   "second_expert": second["expert"], "margin": margin,
                   "teacher_disagreement": len({r["correctness"] for r in rows}) > 1,
                   "distillation_weight": 0.25 if margin < margin_threshold else 1.0,
                   "target_action": expert_to_action(chosen, defect_of(sample)),
                   "unavailable": {r["expert"]: r["unavailable_reason"] for r in sample_matrix if not r["available"]}})
    write_jsonl(out_dir / "teacher_reward_matrix.jsonl", matrix)
    write_jsonl(out_dir / "d3_records.jsonl", d3)
    summary = {"samples": len(d3), "matrix_rows": len(matrix),
               "split": dict(Counter(r["split"] for r in d3)),
               "best_expert": dict(Counter(r["best_expert"] for r in d3)),
               "failures_excluded": sum(r["failure"] for r in matrix),
               "cost_measurements": {"calls_present": sum(r["calls"] is not None for r in matrix),
                                     "tokens_present": sum(r["tokens"] is not None for r in matrix),
                                     "latency_present": sum(r["latency_ms"] is not None for r in matrix),
                                     "policy": "missing cached token/latency measurements remain null"},
               "utility": {"lambda_c": lambda_c, "lambda_fp": lambda_fp, "lambda_v": lambda_v,
                           "margin_threshold": margin_threshold},
               "tie_policy": ["lower_cost", "lower_fpr", "verifiable_evidence", "deterministic_expert_order"]}
    (out_dir / "teacher_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def select_utility_on_dev(matrix_path: Path, out_path: Path) -> dict[str, Any]:
    """Select coefficients using dev rows only and an invariant audit criterion."""
    matrix = read_jsonl(matrix_path)
    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in matrix:
        if row["split"] == "dev" and row["available"]:
            by_sample[row["sample_id"]].append(row)
    grid = [(c, fp, v, m) for c in (.025, .05, .1) for fp in (.5, 1.0, 2.0)
            for v in (.05, .1, .2) for m in (.025, .05, .1)]
    evaluated = []
    for lc, lfp, lv, margin in grid:
        criterion, deferred = [], 0
        for rows in by_sample.values():
            scored = []
            for row in rows:
                fp = row["paired_clean_fp"] if row["paired_clean_fp"] is not None else 0.0
                utility = row["correctness"] - lc * (row["calls"] or 0) - lfp * fp + lv * row["evidence_validity"]
                scored.append((utility, row))
            scored.sort(key=lambda x: (-x[0], x[1]["calls"] or 0, x[1]["expert"]))
            gap = scored[0][0] - scored[1][0] if len(scored) > 1 else 0
            if gap < margin:
                deferred += 1
                chosen = next((r for _, r in scored if r["expert"] == "DEFER"), scored[0][1])
            else:
                chosen = scored[0][1]
            fp = chosen["paired_clean_fp"] if chosen["paired_clean_fp"] is not None else 0.0
            # Fixed audit criterion prevents selecting coefficients by their own scale.
            criterion.append(chosen["correctness"] - .05 * (chosen["calls"] or 0) - fp
                             + .1 * chosen["evidence_validity"])
        evaluated.append({"lambda_c": lc, "lambda_fp": lfp, "lambda_v": lv,
                          "margin_threshold": margin, "dev_samples": len(criterion),
                          "selection_score": sum(criterion) / len(criterion),
                          "deferred": deferred})
    evaluated.sort(key=lambda x: (-x["selection_score"], x["deferred"], x["lambda_c"],
                                  -x["lambda_fp"], -x["lambda_v"], x["margin_threshold"]))
    report = {"selection_split": "dev", "validation_used": False, "final_test_used": False,
              "criterion": "mean(correctness-.05*calls-paired_clean_fp+.1*evidence_validity)",
              "cost_measurement_policy": "calls measured; tokens/latency null and excluded",
              "grid_size": len(evaluated), "selected": {k: evaluated[0][k] for k in
                  ("lambda_c", "lambda_fp", "lambda_v", "margin_threshold")},
              "selected_score": evaluated[0]["selection_score"], "candidates": evaluated}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def audit(out_dir: Path, final_manifest: Path | None = None) -> dict[str, Any]:
    rows = read_jsonl(out_dir / "split_manifest.jsonl")
    pairs = read_jsonl(out_dir / "pairwise_orders.jsonl")
    avail = read_jsonl(out_dir / "availability_records.jsonl")
    errors: list[str] = []
    ids = [row["sample_id"] for row in rows]
    duplicate_ids = sorted(k for k, n in Counter(ids).items() if n > 1)
    if duplicate_ids:
        errors.append("duplicate sample_id")
    by_source: dict[str, set[str]] = defaultdict(set)
    by_content: dict[str, set[str]] = defaultdict(set)
    by_template_group: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        by_source[row["source_deck"]].add(row["split"])
        by_content[row["content_cluster"]].add(row["split"])
        by_template_group[(row["source_deck"], row["template_id"])].add(row["split"])
    # Validation is an already-seen, role-separated corpus. Leakage is only a
    # train/dev violation; final_test is audited independently at generation.
    source_leaked = {k: sorted(v) for k, v in by_source.items() if {"train", "dev"}.issubset(v)}
    content_leaked = {k: sorted(v) for k, v in by_content.items() if {"train", "dev"}.issubset(v)}
    template_leaked = {str(k): sorted(v) for k, v in by_template_group.items() if {"train", "dev"}.issubset(v)}
    if source_leaked or content_leaked or template_leaked:
        errors.append("group leakage")
    pair_orders: dict[str, set[str]] = defaultdict(set)
    for row in pairs:
        pair_orders[row["sample_id"]].add(row["order"])
    incomplete = [k for k, v in pair_orders.items()
                  if v not in ({"clean_defective", "defective_clean"}, {"clean_clean"})]
    if incomplete:
        errors.append("incomplete pairwise double order")
    answer_mismatch = [r["sample_id"] for r in pairs
        if (r["order"] == "clean_defective" and r["better"] != "A")
        or (r["order"] == "defective_clean" and r["better"] != "B")
        or (r["order"] == "clean_clean" and r["better"] != "TIE")]
    if answer_mismatch:
        errors.append("pairwise answer mapping")
    first_order = Counter(r["order"] for r in pairs if r["order_index"] == 0 and r["order"] != "clean_clean")
    if first_order and abs(first_order["clean_defective"] - first_order["defective_clean"]) > max(2, .1 * sum(first_order.values())):
        errors.append("A/B randomization imbalance")
    av: dict[str, set[str]] = defaultdict(set)
    for row in avail:
        av[row["sample_id"]].add(row["availability"])
    missing_av = [k for k, v in av.items() if v != set(AVAILABILITY)]
    if missing_av:
        errors.append("availability incomplete")
    bad_actions = []
    for row in avail:
        prefix = row["defect"].split("_", 1)[0]
        expected = ("CALL_LINTER" if row["resources"]["structure"] else "DEFER") if prefix in GEOMETRY else None
        if expected and row["target_action"] != expected:
            bad_actions.append(row["sample_id"])
    if bad_actions:
        errors.append("availability action mismatch")
    bad_clean_decks = [r["sample_id"] for r in rows if r.get("record_kind") == "clean_deck_negative"
                       and (not r["pair"].get("clean_deck_path") or not Path(r["pair"]["clean_deck_path"]).exists())]
    if bad_clean_decks:
        errors.append("invalid clean deck artifact")
    severity_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        severity_splits[row["severity_chain"]].add(row["split"])
    severity_leakage = {k: sorted(v) for k, v in severity_splits.items()
                        if {"train", "dev"}.issubset(v)}
    if severity_leakage:
        errors.append("severity chain leakage")
    bad_pairs = []
    def _artifact_exists(value: str) -> bool:
        path = Path(value)
        if path.exists():
            return True
        # Frozen manifests may retain the source-machine absolute prefix; the
        # mirrored repository asset remains the auditable artifact of record.
        marker = "/data/"
        if marker in value:
            return (out_dir.parents[2] / "data" / value.split(marker, 1)[1]).exists()
        return False
    for row in rows:
        if row["split"] == "validation" or row["defect"] == "NO_DEFECT":
            continue
        pair = row.get("pair", {})
        keys = (("clean_deck_path", "defective_deck_path") if row["scope"] == "deck"
                else ("clean_slide_path", "defective_slide_path"))
        # Some rendered manifests use image paths as the paired page artifact.
        if row["scope"] == "page" and not all(pair.get(k) for k in keys):
            keys = ("clean_image_path", "defective_image_path")
        if not all(pair.get(k) and _artifact_exists(pair[k]) for k in keys):
            bad_pairs.append(row["sample_id"])
    if bad_pairs:
        errors.append("paired clean artifact incomplete")
    roundtrip_failures = []
    for row in rows:
        try:
            if json.loads(json.dumps(row, ensure_ascii=False)) != row:
                roundtrip_failures.append(row["sample_id"])
        except (TypeError, ValueError):
            roundtrip_failures.append(row["sample_id"])
    if roundtrip_failures:
        errors.append("JSON parser round-trip failed")
    final_counts: dict[str, int] = {}
    if final_manifest and final_manifest.exists():
        final_counts = dict(Counter(defect_of(r) for r in read_jsonl(final_manifest)))
    report = {"passed": not errors, "errors": errors, "records": len(rows),
              "split_counts": dict(Counter(r["split"] for r in rows)),
              "class_counts": dict(Counter(r["defect"] for r in rows)),
              "scope_counts": dict(Counter(r["scope"] for r in rows)),
              "no_defect_scope": dict(Counter(r["scope"] for r in rows if r["defect"] == "NO_DEFECT")),
              "duplicate_sample_ids": duplicate_ids,
              "source_deck_leakage": source_leaked, "content_cluster_leakage": content_leaked,
              "template_group_leakage": template_leaked, "pairwise_records": len(pairs),
              "pairwise_incomplete": incomplete, "availability_records": len(avail),
              "pairwise_answer_mismatch": answer_mismatch, "first_order_balance": dict(first_order),
              "availability_incomplete": missing_av, "availability_action_mismatch": bad_actions,
              "invalid_clean_decks": bad_clean_decks, "severity_chain_leakage": severity_leakage,
              "paired_clean_incomplete": bad_pairs, "parser_roundtrip_failures": roundtrip_failures,
              "action_composition": dict(Counter(r["target_action"] for r in avail)),
              "availability_composition": dict(Counter(r["availability"] for r in avail)),
              "final_test_classes": final_counts}
    (out_dir / "split_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report
