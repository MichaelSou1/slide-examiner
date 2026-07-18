#!/usr/bin/env python3
"""Generic-prompt D3 inference with sample-level routing and one escalation."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

from slide_examiner.d3_training import (
    ACTIONS, authoritative_result, balanced_smoke_rows, bounded_route_action,
    evaluate_semantic_gate, resolve_inference_policy, run_linter,
)
from slide_examiner.examiner_contract import (
    DECK_SCOPED_DEFECTS,
    PAGE_SCOPED_DEFECTS,
    ExaminerAction,
    parse_deck_result,
    parse_page_result,
)
from scripts.part3_d3_train import D3Heads, JsonlDataset, _images, pooled_at_prompt


def load(run: Path, base: str, device: torch.device, merged_model: Path | None = None):
    """Load either the QLoRA training bundle or its merged serving equivalent."""
    processor_source = merged_model or (run / "adapter")
    processor = AutoProcessor.from_pretrained(processor_source, trust_remote_code=True)
    if merged_model is not None:
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            merged_model, torch_dtype=torch.bfloat16, device_map={"": 0},
            trust_remote_code=True, attn_implementation="sdpa",
        ).eval()
    else:
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_compute_dtype=torch.bfloat16,
                                  bnb_4bit_use_double_quant=True)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            base, torch_dtype=torch.bfloat16, quantization_config=quant, device_map={"": 0},
            trust_remote_code=True, attn_implementation="sdpa",
        )
        model = PeftModel.from_pretrained(model, run / "adapter").eval()
    config = model.get_base_model().config if hasattr(model, "get_base_model") else model.config
    hidden = config.text_config.hidden_size
    heads = D3Heads(hidden).to(device).eval()
    heads.load_state_dict(torch.load(run / "d3_heads.pt", map_location=device, weights_only=True))
    return processor, model, heads


def extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    return json.loads(text[start:end + 1])


def balanced_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return balanced_smoke_rows(rows, limit)


def _repair_contract(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Apply conservative, content-preserving repairs to generated JSON.

    Repairs only normalize schema aliases and fill locators from identifiers
    already emitted by the model. Free-form string findings are not promoted
    into typed findings because doing so would require an oracle defect label.
    """
    repaired = json.loads(json.dumps(payload))
    if repaired.get("action") not in {action.value for action in ExaminerAction}:
        repaired["action"] = ExaminerAction.ANSWER.value
    findings = repaired.get("findings", [])
    if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
        return None
    is_deck = "deck_id" in repaired
    allowed = DECK_SCOPED_DEFECTS if is_deck else PAGE_SCOPED_DEFECTS
    allowed_by_prefix = {item.value.split("_", 1)[0]: item.value for item in allowed}
    subject_id = str(repaired.get("deck_id" if is_deck else "page_id") or "unknown")
    for finding in findings:
        raw_type = str(finding.get("type", ""))
        if raw_type not in {item.value for item in allowed}:
            replacement = allowed_by_prefix.get(raw_type.split("_", 1)[0])
            if replacement is None:
                return None
            finding["type"] = replacement
        if str(finding.get("severity", "")).lower() in {"critical", "blocker"}:
            finding["severity"] = "severe"
        locator = finding.setdefault("locator", {})
        locator.setdefault("level", "deck" if is_deck else "page")
        # Locator has a page_id field for both page- and deck-level findings;
        # deck identity remains on the enclosing DeckExamResult.
        if not is_deck:
            locator.setdefault("page_id", subject_id)
        locator.setdefault("related_page_ids", [])
        evidence = str(finding.get("evidence", "")).strip()
        visible_id = locator.get("element_id") or locator.get("page_id")
        if visible_id and str(visible_id).lower() not in evidence.lower():
            finding["evidence"] = f"Visible element {visible_id}: {evidence}"
    return repaired


def parse_contract(text: str) -> tuple[dict[str, Any] | None, str | None, bool]:
    try:
        parsed = extract_json(text)
        parser = parse_deck_result if "deck_id" in parsed else parse_page_result
        try:
            return parser(json.dumps(parsed)).model_dump(mode="json"), None, False
        except Exception as original:  # noqa: BLE001 - attempt bounded schema repair
            repaired = _repair_contract(parsed)
            if repaired is not None:
                try:
                    return parser(json.dumps(repaired)).model_dump(mode="json"), None, True
                except Exception:  # noqa: BLE001 - preserve the original useful error
                    pass
            return None, f"{type(original).__name__}: {original}", False
    except Exception as exc:  # noqa: BLE001 - parser failures are measured artifacts
        return None, f"{type(exc).__name__}: {exc}", False


def infer_once(processor: Any, model: Any, heads: D3Heads, row: dict[str, Any],
               device: torch.device, max_new_tokens: int, *, terminal: bool = False,
               confidence_threshold: float = 0.0, max_escalations: int = 1,
               route_mode: str = "sample", fixed_action: str | None = None,
               class_routes: dict[str, str] | None = None,
               route_only: bool = False) -> dict[str, Any]:
    prompt = processor.apply_chat_template(row["messages"][:1], tokenize=False,
                                           add_generation_prompt=True)
    image_list = _images(row)
    inputs = processor(text=[prompt], images=image_list if image_list else None,
                       return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    prompt_lengths = inputs["attention_mask"].sum(dim=1)
    started = time.perf_counter()
    with torch.no_grad():
        output = model(**inputs, output_hidden_states=True, return_dict=True)
        pooled = pooled_at_prompt(output.hidden_states[-1], prompt_lengths).float()
        action_logits, select_logits, _, _ = heads(pooled)
        raw_action = ACTIONS[int(action_logits.argmax(-1).item())]
        confidence = float(torch.sigmoid(select_logits).item())
        if route_mode == "fixed":
            raw_action = str(fixed_action)
            confidence = 1.0
        elif route_mode == "class":
            defect_class = str(row["defect"]).split("_", 1)[0]
            if not class_routes or defect_class not in class_routes:
                raise ValueError(f"class route missing for {defect_class}")
            raw_action = class_routes[defect_class]
            confidence = 1.0
        action = bounded_route_action(
            raw_action, confidence, confidence_threshold=confidence_threshold,
            terminal=terminal, max_escalations=max_escalations)
        # Routing is authoritative. Tool/reference/defer actions have a
        # deterministic legal envelope and must not depend on the LM emitting
        # a finding-shaped JSON object that will be discarded anyway.
        if action != ExaminerAction.ANSWER.value:
            authoritative, mismatch, consistency_error = authoritative_result(None, action)
            return {"predicted_action": action, "raw_predicted_action": raw_action,
                    "route_confidence": confidence,
                    "raw": "", "generated_parsed": None, "generated_action": None,
                    "parsed": authoritative, "parse_error": None,
                    "action_mismatch": mismatch, "consistency_error": consistency_error,
                    "contract_repaired": False, "fallback_defer": False,
                    "usage": {"prompt_tokens": int(prompt_lengths.item()),
                              "completion_tokens": 0,
                              "total_tokens": int(prompt_lengths.item()),
                              "latency_seconds": time.perf_counter() - started}}
        if route_only:
            return {"predicted_action": action, "raw_predicted_action": raw_action,
                    "route_confidence": confidence, "raw": "", "generated_parsed": None,
                    "generated_action": None, "parsed": None, "parse_error": None,
                    "action_mismatch": False, "consistency_error": None,
                    "contract_repaired": False, "fallback_defer": False,
                    "route_only": True,
                    "usage": {"prompt_tokens": int(prompt_lengths.item()),
                              "completion_tokens": 0,
                              "total_tokens": int(prompt_lengths.item()),
                              "latency_seconds": time.perf_counter() - started}}
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    continuation = generated[0, inputs["input_ids"].shape[1]:]
    text = processor.decode(continuation, skip_special_tokens=True)
    generated_parsed, error, repaired = parse_contract(text)
    generated_action = (generated_parsed or {}).get("action")
    fallback_defer = generated_parsed is None
    if fallback_defer:
        action = ExaminerAction.DEFER.value
        parsed, mismatch, consistency_error = authoritative_result(None, action)
    else:
        parsed, mismatch, consistency_error = authoritative_result(generated_parsed, action)
    return {"predicted_action": action, "raw_predicted_action": raw_action,
            "route_confidence": confidence,
            "raw": text, "generated_parsed": generated_parsed,
            "generated_action": generated_action,
            "parsed": parsed, "parse_error": error,
            "generation_error": error, "action_mismatch": mismatch,
            "consistency_error": consistency_error, "contract_repaired": repaired,
            "fallback_defer": fallback_defer,
            "usage": {"prompt_tokens": int(prompt_lengths.item()),
                      "completion_tokens": int(continuation.numel()),
                      "total_tokens": int(prompt_lengths.item() + continuation.numel()),
                      "latency_seconds": time.perf_counter() - started}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--base", default="/home/nvme04/models/Qwen3-VL-8B-Instruct")
    parser.add_argument("--merged-model", type=Path,
                        help="Merged LM directory; D3 heads and policy still come from --run")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", default="32",
                        help="Number of records, or 'all' for the complete input")
    parser.add_argument("--balanced", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--policy", type=Path,
                        help="Frozen inference-policy JSON; overrides threshold and escalation limit")
    parser.add_argument("--confidence-threshold", type=float, default=0.0)
    parser.add_argument("--max-escalations", type=int, choices=(0, 1), default=1)
    parser.add_argument("--route-mode", choices=("sample", "class", "fixed"), default="sample")
    parser.add_argument("--class-router", type=Path,
                        help="class_router.json used when --route-mode=class")
    parser.add_argument("--fixed-action", choices=ACTIONS,
                        help="single action used when --route-mode=fixed")
    parser.add_argument("--route-only", action="store_true",
                        help="Score router/action/cost without generating ANSWER JSON")
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text()) if args.policy else {}
    try:
        confidence_threshold, max_escalations = resolve_inference_policy(
            policy, confidence_threshold=args.confidence_threshold,
            max_escalations=args.max_escalations)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    if args.route_mode == "class" and not args.class_router:
        parser.error("--class-router is required for --route-mode=class")
    if args.route_mode == "fixed" and not args.fixed_action:
        parser.error("--fixed-action is required for --route-mode=fixed")
    class_routes = None
    if args.class_router:
        router_payload = json.loads(args.class_router.read_text())
        class_routes = {name: str(route["prediction"])
                        for name, route in router_payload["routes"].items()}
    device = torch.device("cuda")
    processor, model, heads = load(args.run, args.base, device, args.merged_model)
    all_rows = JsonlDataset(args.input).rows
    if args.limit == "all":
        limit = len(all_rows)
    else:
        try:
            limit = int(args.limit)
        except ValueError:
            parser.error("--limit must be a positive integer or 'all'")
        if limit < 1:
            parser.error("--limit must be a positive integer or 'all'")
    rows = balanced_rows(all_rows, limit) if args.balanced else all_rows[:limit]
    by_sample_availability = {(row["sample_id"], row["availability"]): row for row in all_rows}
    by_chain_availability: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in all_rows:
        by_chain_availability.setdefault(
            (candidate["severity_chain"], candidate["availability"]), candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed: set[str] = set()
    if args.output.exists():
        for line in args.output.read_text().splitlines():
            if line.strip():
                completed.add(str(json.loads(line)["record_id"]))
    results, counts = [], {"parser_failure": 0, "action_loop": 0, "teacher_failure": 0,
                           "action_mismatch": 0, "consistency_failure": 0,
                           "escalation_failure": 0}
    for row in rows:
        if row["record_id"] in completed:
            continue
        first = infer_once(processor, model, heads, row, device, args.max_new_tokens,
                           confidence_threshold=confidence_threshold,
                           max_escalations=max_escalations, route_mode=args.route_mode,
                           fixed_action=args.fixed_action, class_routes=class_routes,
                           route_only=args.route_only)
        if first["parse_error"]:
            counts["parser_failure"] += 1
        counts["action_mismatch"] += int(first["action_mismatch"])
        counts["consistency_failure"] += int(bool(first["consistency_error"]))
        escalation = None
        requested = first["predicted_action"]
        availability = {"CALL_LINTER": "image_structure", "REQUEST_REFERENCE": "reference_available",
                        "REQUEST_DECK": "deck_context_available"}.get(requested)
        if availability:
            followup_row = (by_sample_availability.get((row["sample_id"], availability))
                            or by_chain_availability.get((row["severity_chain"], availability)))
            if followup_row:
                if requested == "CALL_LINTER":
                    try:
                        final = run_linter(followup_row)
                        escalation = {"requested_action": requested, "performed": True,
                                      "provided_availability": availability, "executor": "geometry_linter",
                                      "final_action": "ANSWER", "final_parsed": final}
                    except Exception as exc:  # noqa: BLE001 - explicit runtime failure artifact
                        counts["escalation_failure"] += 1
                        escalation = {"requested_action": requested, "performed": False,
                                      "provided_availability": availability,
                                      "reason": f"{type(exc).__name__}: {exc}"}
                else:
                    second = infer_once(processor, model, heads, followup_row, device,
                                        args.max_new_tokens, terminal=True,
                                        confidence_threshold=confidence_threshold,
                                        max_escalations=max_escalations, route_mode=args.route_mode,
                                        fixed_action=args.fixed_action, class_routes=class_routes,
                                        route_only=args.route_only)
                    if second["parse_error"]:
                        counts["parser_failure"] += 1
                    counts["action_mismatch"] += int(second["action_mismatch"])
                    counts["consistency_failure"] += int(bool(second["consistency_error"]))
                    final_action = second["predicted_action"]
                    if final_action not in {"ANSWER", "DEFER"}:
                        counts["action_loop"] += 1
                        counts["escalation_failure"] += 1
                    escalation = {"requested_action": requested, "performed": True,
                                  "provided_availability": availability, "executor": "student_followup",
                                  "counterpart_match": ("sample_id" if followup_row["sample_id"] == row["sample_id"]
                                                        else "severity_chain"),
                                  "final_action": final_action, "final_parsed": second["parsed"],
                                  "result": second}
            else:
                counts["escalation_failure"] += 1
                escalation = {"requested_action": requested, "performed": False,
                              "reason": f"no {availability} counterpart for sample"}
        result = {"record_id": row["record_id"], "sample_id": row["sample_id"],
                        "defect": row["defect"], "availability": row["availability"],
                        "target_action": row["target_action"],
                        "is_clean_deck": bool(row.get("is_clean_deck")),
                        **first, "escalation": escalation,
                        "model_calls": 1 + int(bool(escalation and escalation.get("executor") == "student_followup")),
                        "external_calls": int(bool(escalation and escalation.get("performed"))),
                        "prompt_tokens": first["usage"]["prompt_tokens"] + int(
                            ((escalation or {}).get("result") or {}).get("usage", {}).get("prompt_tokens", 0)),
                        "completion_tokens": first["usage"]["completion_tokens"] + int(
                            ((escalation or {}).get("result") or {}).get("usage", {}).get("completion_tokens", 0)),
                        "total_tokens": first["usage"]["total_tokens"] + int(
                            ((escalation or {}).get("result") or {}).get("usage", {}).get("total_tokens", 0)),
                        "latency_seconds": first["usage"]["latency_seconds"] + float(
                            ((escalation or {}).get("result") or {}).get("usage", {}).get("latency_seconds", 0.0))}
        results.append(result)
        with args.output.open("a") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            stream.flush()
    all_results = [json.loads(line) for line in args.output.read_text().splitlines() if line.strip()]
    results = [result for result in all_results if result["record_id"] in {row["record_id"] for row in rows}]
    counts = {
        "parser_failure": sum(bool(result.get("parse_error")) + bool(
            ((result.get("escalation") or {}).get("result") or {}).get("parse_error"))
                              for result in results),
        "action_loop": sum(bool(result.get("escalation")) and
                           (result["escalation"].get("final_action") not in {"ANSWER", "DEFER"})
                           for result in results),
        "teacher_failure": 0,
        "action_mismatch": sum(bool(result.get("action_mismatch")) + bool(
            ((result.get("escalation") or {}).get("result") or {}).get("action_mismatch"))
                               for result in results),
        "consistency_failure": sum(bool(result.get("consistency_error")) + bool(
            ((result.get("escalation") or {}).get("result") or {}).get("consistency_error"))
                                   for result in results),
        "escalation_failure": sum(bool(result.get("escalation")) and
                                  not result["escalation"].get("performed") for result in results),
    }
    semantic = {
        "g7_legal_answer": sum(x["defect"].startswith("G7_") and x["predicted_action"] == "ANSWER"
                               and bool((x["parsed"] or {}).get("findings")) for x in results),
        "geometry_image_only_safe_route": sum(
            x["defect"].split("_", 1)[0] in {"G2", "G3", "G4", "G5", "G6"}
            and x["availability"] == "image_only"
            and x["predicted_action"] in {"CALL_LINTER", "DEFER"}
            and not (x["parsed"] or {}).get("findings") for x in results),
        "reference_request": sum(x["defect"].split("_", 1)[0] in {"G1", "S6"}
                                 and x["predicted_action"] == "REQUEST_REFERENCE" for x in results),
        "performed_escalation": sum(bool(x["escalation"] and x["escalation"]["performed"])
                                    for x in results),
    }
    summary = {**counts, "records": len(results), "resumed_records": len(completed),
               "balanced": args.balanced,
               "deployment": {"lm": "merged" if args.merged_model else "base_plus_adapter",
                              "model_path": str(args.merged_model or args.base),
                              "heads_path": str(args.run / "d3_heads.pt"),
                              "policy_path": str(args.policy or args.run / "run_config.json"),
                              "confidence_threshold": confidence_threshold,
                              "max_escalations": max_escalations,
                              "route_mode": args.route_mode,
                              "class_router_path": str(args.class_router) if args.class_router else None,
                              "fixed_action": args.fixed_action,
                              "route_only": args.route_only,
                              "worst_case_model_calls": 1 + max_escalations,
                              "worst_case_tool_calls": max_escalations},
               "semantic_counts": semantic,
               "semantic_gate": evaluate_semantic_gate(results, counts),
               "clean_control_definition": (
                   "is_clean_deck=true, or frozen-dev NO_DEFECT with deck_context_available"
               ),
               "action_distribution": dict(Counter(x["predicted_action"] for x in results)),
               "target_action_distribution": dict(Counter(x["target_action"] for x in results)),
               "parser_success": sum(x["parsed"] is not None for x in results),
               "post_escalation_parser_success": sum(
                   bool(x["escalation"] and x["escalation"]["performed"]
                        and x["escalation"].get("final_parsed") is not None) for x in results),
               "completed_escalation": sum(
                   bool(x["escalation"] and x["escalation"]["performed"]
                        and x["escalation"].get("final_action") in {"ANSWER", "DEFER"}
                        and x["escalation"].get("final_parsed") is not None) for x in results),
               "action_correct": sum(x["predicted_action"] == x["target_action"] for x in results),
               "output": str(args.output)}
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
