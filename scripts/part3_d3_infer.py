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
from transformers import (
    AutoConfig,
    AutoProcessor,
    BitsAndBytesConfig,
    Qwen3VLForConditionalGeneration,
    Qwen3VLMoeForConditionalGeneration,
)

from slide_examiner.d3_evaluation import (
    generated_route_action,
    parse_generated_contract,
    prompt_row,
    reference_followup_kwargs,
    route_requires_heads,
    validate_deployment,
)
from slide_examiner.d3_training import (
    ACTIONS, authoritative_result, balanced_smoke_rows, bounded_route_action,
    evaluate_semantic_gate, resolve_inference_policy, run_linter,
)
from slide_examiner.examiner_contract import ExaminerAction
from scripts.part3_d3_train import D3Heads, JsonlDataset, _images, pooled_at_prompt


def load(run: Path | None, base: str, device: torch.device,
         merged_model: Path | None = None, lm_adapter: Path | None = None,
         max_image_pixels: int | None = None):
    """Load either the QLoRA training bundle or its merged serving equivalent."""
    processor_source = merged_model or lm_adapter or ((run / "adapter") if run else base)
    processor = AutoProcessor.from_pretrained(processor_source, trust_remote_code=True)
    if max_image_pixels is not None:
        processor.image_processor.size["longest_edge"] = max_image_pixels
    model_source = merged_model or base
    config = AutoConfig.from_pretrained(model_source, trust_remote_code=True)
    model_class = (Qwen3VLMoeForConditionalGeneration
                   if config.model_type == "qwen3_vl_moe"
                   else Qwen3VLForConditionalGeneration)
    if merged_model is not None:
        model = model_class.from_pretrained(
            merged_model, torch_dtype=torch.bfloat16, device_map={"": 0},
            trust_remote_code=True, attn_implementation="sdpa",
        ).eval()
    else:
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_compute_dtype=torch.bfloat16,
                                  bnb_4bit_use_double_quant=True)
        model = model_class.from_pretrained(
            base, torch_dtype=torch.bfloat16, quantization_config=quant, device_map={"": 0},
            trust_remote_code=True, attn_implementation="sdpa",
        )
        adapter = lm_adapter or ((run / "adapter") if run else None)
        model = PeftModel.from_pretrained(model, adapter).eval() if adapter else model.eval()
    if run is None:
        return processor, model, None
    config = model.get_base_model().config if hasattr(model, "get_base_model") else model.config
    hidden = config.text_config.hidden_size
    heads = D3Heads(hidden).to(device).eval()
    heads.load_state_dict(torch.load(run / "d3_heads.pt", map_location=device, weights_only=True))
    return processor, model, heads


def balanced_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return balanced_smoke_rows(rows, limit)


def infer_answer_batch(processor: Any, model: Any, rows: list[dict[str, Any]],
                       device: torch.device, max_new_tokens: int, *,
                       prompt_mode: str = "generic",
                       max_escalations: int = 1) -> list[dict[str, Any]]:
    """Generate independent LM-only ANSWER rows in one padded batch."""
    prompted = [prompt_row(row, prompt_mode) for row in rows]
    prompts = [processor.apply_chat_template(
        row["messages"][:1], tokenize=False, add_generation_prompt=True)
        for row in prompted]
    images = [_images(row) for row in prompted]
    previous_padding_side = processor.tokenizer.padding_side
    processor.tokenizer.padding_side = "left"
    try:
        inputs = processor(
            text=prompts, images=images if any(images) else None,
            padding=True, return_tensors="pt")
    finally:
        processor.tokenizer.padding_side = previous_padding_side
    inputs = {key: value.to(device) for key, value in inputs.items()}
    prompt_lengths = inputs["attention_mask"].sum(dim=1)
    input_width = inputs["input_ids"].shape[1]
    started = time.perf_counter()
    with torch.inference_mode():
        generated = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False,
            pad_token_id=processor.tokenizer.pad_token_id)
    elapsed = time.perf_counter() - started
    special_ids = {item for item in (
        processor.tokenizer.pad_token_id, processor.tokenizer.eos_token_id)
        if item is not None}
    outputs = []
    for index, continuation in enumerate(generated[:, input_width:]):
        text = processor.decode(continuation, skip_special_tokens=True)
        generated_parsed, error, repaired = parse_generated_contract(text, prompted[index])
        fallback_defer = generated_parsed is None
        raw_action = (ExaminerAction.DEFER.value if fallback_defer
                      else str(generated_parsed["action"]))
        # The escalation budget controls execution, not what the LM predicted.
        # Preserve route-like generations so zero-call baselines remain faithful.
        action = generated_route_action(raw_action)
        parsed, mismatch, consistency_error = authoritative_result(
            generated_parsed if not fallback_defer else None, action)
        prompt_tokens = int(prompt_lengths[index].item())
        completion_tokens = sum(token not in special_ids for token in continuation.tolist())
        outputs.append({
            "predicted_action": action,
            "raw_predicted_action": raw_action,
            "route_confidence": 1.0,
            "raw": text,
            "generated_parsed": generated_parsed,
            "generated_action": (generated_parsed or {}).get("action"),
            "parsed": parsed,
            "parse_error": error,
            "generation_error": error,
            "action_mismatch": mismatch,
            "consistency_error": consistency_error,
            "contract_repaired": repaired,
            "fallback_defer": fallback_defer,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                # Synchronous batch latency is the latency experienced by each request.
                "latency_seconds": elapsed,
                "batch_size": len(rows),
            },
        })
    return outputs


def infer_once(processor: Any, model: Any, heads: D3Heads | None, row: dict[str, Any],
               device: torch.device, max_new_tokens: int, *, terminal: bool = False,
               confidence_threshold: float = 0.0, max_escalations: int = 1,
               route_mode: str = "sample", fixed_action: str | None = None,
               class_routes: dict[str, str] | None = None,
               route_only: bool = False, prompt_mode: str = "generic") -> dict[str, Any]:
    row = prompt_row(row, prompt_mode)
    prompt = processor.apply_chat_template(row["messages"][:1], tokenize=False,
                                           add_generation_prompt=True)
    image_list = _images(row)
    inputs = processor(text=[prompt], images=image_list if image_list else None,
                       return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    prompt_lengths = inputs["attention_mask"].sum(dim=1)
    started = time.perf_counter()
    with torch.inference_mode():
        if not route_requires_heads(route_mode):
            raw_action, confidence = ExaminerAction.ANSWER.value, 1.0
        else:
            if heads is None:
                raise ValueError("D3 heads are required unless route_mode=answer")
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
    generated_parsed, error, repaired = parse_generated_contract(text, row)
    generated_action = (generated_parsed or {}).get("action")
    fallback_defer = generated_parsed is None
    if fallback_defer:
        action = ExaminerAction.DEFER.value
        parsed, mismatch, consistency_error = authoritative_result(None, action)
    elif route_mode == "answer":
        raw_action = str(generated_action)
        # On the first pass, retain the LM's generated action even when the
        # external-call budget is zero. Only a terminal follow-up projects a
        # repeated request to DEFER to prevent an action loop.
        action = generated_route_action(raw_action, terminal=terminal)
        parsed, mismatch, consistency_error = authoritative_result(generated_parsed, action)
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



def infer_reference_followup(processor: Any, model: Any, heads: D3Heads | None,
                             row: dict[str, Any], device: torch.device,
                             max_new_tokens: int) -> dict[str, Any]:
    """Compare an acquired reference exactly once and force a terminal answer attempt."""
    return infer_once(
        processor, model, heads, row, device, max_new_tokens,
        **reference_followup_kwargs(),
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path,
                        help="D3 run containing adapter/d3_heads.pt; optional for LM-only baselines")
    parser.add_argument("--base", default="/home/nvme04/models/Qwen3-VL-8B-Instruct")
    parser.add_argument("--merged-model", type=Path,
                        help="Merged LM directory; D3 heads and policy still come from --run")
    parser.add_argument("--lm-adapter", type=Path,
                        help="PEFT adapter for an LM-only baseline (Part 2 or compute-matched vanilla)")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", default="32",
                        help="Number of records, or 'all' for the complete input")
    parser.add_argument("--balanced", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=192)
    parser.add_argument("--batch-size", type=int, default=1,
                        help="Padded generation batch size for route-mode=answer")
    parser.add_argument("--max-image-pixels", type=int,
                        help="Processor pixel budget per image; frozen identically across arms")
    parser.add_argument("--policy", type=Path,
                        help="Frozen inference-policy JSON; overrides threshold and escalation limit")
    parser.add_argument("--confidence-threshold", type=float, default=0.0)
    parser.add_argument("--max-escalations", type=int, choices=(0, 1), default=1)
    parser.add_argument("--route-mode", choices=("sample", "class", "fixed", "answer"),
                        default="sample")
    parser.add_argument("--prompt-mode", choices=("generic", "c3"), default="generic")
    parser.add_argument("--class-router", type=Path,
                        help="class_router.json used when --route-mode=class")
    parser.add_argument("--fixed-action", choices=ACTIONS,
                        help="single action used when --route-mode=fixed")
    parser.add_argument("--route-only", action="store_true",
                        help="Score router/action/cost without generating ANSWER JSON")
    args = parser.parse_args()
    deployment_error = validate_deployment(
        args.run, args.merged_model, args.lm_adapter, args.route_mode)
    if deployment_error:
        parser.error(deployment_error)
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
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if args.max_image_pixels is not None and args.max_image_pixels < 1:
        parser.error("--max-image-pixels must be positive")
    if args.batch_size > 1 and args.route_mode != "answer":
        parser.error("--batch-size > 1 currently requires --route-mode=answer")
    class_routes = None
    if args.class_router:
        router_payload = json.loads(args.class_router.read_text())
        class_routes = {name: str(route["prediction"])
                        for name, route in router_payload["routes"].items()}
    device = torch.device("cuda")
    processor, model, heads = load(
        args.run, args.base, device, args.merged_model, args.lm_adapter,
        args.max_image_pixels)
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
    pending = [row for row in rows if row["record_id"] not in completed]
    work_batches = [pending[offset:offset + args.batch_size]
                    for offset in range(0, len(pending), args.batch_size)]
    for batch in work_batches:
        if args.batch_size > 1:
            first_results = infer_answer_batch(
                processor, model, batch, device, args.max_new_tokens,
                prompt_mode=args.prompt_mode, max_escalations=max_escalations)
        else:
            first_results = [infer_once(
                processor, model, heads, batch[0], device, args.max_new_tokens,
                confidence_threshold=confidence_threshold,
                max_escalations=max_escalations, route_mode=args.route_mode,
                fixed_action=args.fixed_action, class_routes=class_routes,
                route_only=args.route_only, prompt_mode=args.prompt_mode)]
        for row, first in zip(batch, first_results, strict=True):
            if first["parse_error"]:
                counts["parser_failure"] += 1
            counts["action_mismatch"] += int(first["action_mismatch"])
            counts["consistency_failure"] += int(bool(first["consistency_error"]))
            escalation = None
            requested = first["predicted_action"]
            availability = ({
                "CALL_LINTER": "image_structure",
                "REQUEST_REFERENCE": "reference_available",
                "REQUEST_DECK": "deck_context_available",
            }.get(requested) if max_escalations else None)
            if availability:
                followup_row = (by_sample_availability.get((row["sample_id"], availability))
                                or by_chain_availability.get((row["severity_chain"], availability)))
                if followup_row:
                    if requested == "CALL_LINTER":
                        try:
                            final = run_linter(followup_row)
                            escalation = {"requested_action": requested, "performed": True,
                                          "provided_availability": availability,
                                          "executor": "geometry_linter",
                                          "final_action": "ANSWER", "final_parsed": final}
                        except Exception as exc:  # noqa: BLE001 - explicit runtime failure artifact
                            counts["escalation_failure"] += 1
                            escalation = {"requested_action": requested, "performed": False,
                                          "provided_availability": availability,
                                          "reason": f"{type(exc).__name__}: {exc}"}
                    else:
                        if requested == ExaminerAction.REQUEST_REFERENCE.value:
                            second = infer_reference_followup(
                                processor, model, heads, followup_row, device,
                                args.max_new_tokens)
                        else:
                            second = infer_once(
                                processor, model, heads, followup_row, device,
                                args.max_new_tokens, terminal=True,
                                confidence_threshold=confidence_threshold,
                                max_escalations=max_escalations,
                                route_mode=args.route_mode,
                                fixed_action=args.fixed_action,
                                class_routes=class_routes,
                                route_only=args.route_only,
                                prompt_mode=args.prompt_mode)
                        if second["parse_error"]:
                            counts["parser_failure"] += 1
                        counts["action_mismatch"] += int(second["action_mismatch"])
                        counts["consistency_failure"] += int(bool(second["consistency_error"]))
                        final_action = second["predicted_action"]
                        if final_action not in {"ANSWER", "DEFER"}:
                            counts["action_loop"] += 1
                            counts["escalation_failure"] += 1
                        escalation = {
                            "requested_action": requested, "performed": True,
                            "provided_availability": availability,
                            "executor": ("reference_comparison" if requested ==
                                         ExaminerAction.REQUEST_REFERENCE.value else
                                         "student_followup"),
                            "counterpart_match": (
                                "sample_id" if followup_row["sample_id"] == row["sample_id"]
                                else "severity_chain"),
                            "final_action": final_action, "final_parsed": second["parsed"],
                            "result": second}
                else:
                    counts["escalation_failure"] += 1
                    escalation = {"requested_action": requested, "performed": False,
                                  "reason": f"no {availability} counterpart for sample"}
            result = {"record_id": row["record_id"], "sample_id": row["sample_id"],
                        "pair_id": row.get("pair_id", row["sample_id"]),
                        "defect": row["defect"], "availability": row["availability"],
                        "target_action": row["target_action"],
                        "is_clean": bool(row.get("is_clean")),
                        "is_clean_deck": bool(row.get("is_clean_deck")),
                        **first, "escalation": escalation,
                        "model_calls": 1 + int(bool(escalation and escalation.get("executor") in
                                                      {"student_followup", "reference_comparison"})),
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
               "deployment": {"lm": ("merged" if args.merged_model else
                                      "base_plus_adapter" if (args.run or args.lm_adapter) else "base"),
                              "model_path": str(args.merged_model or args.base),
                              "adapter_path": str(args.lm_adapter or (args.run / "adapter" if args.run else ""))
                              or None,
                              "heads_path": str(args.run / "d3_heads.pt") if args.run else None,
                              "policy_path": (str(args.policy or args.run / "run_config.json")
                                              if args.run else str(args.policy) if args.policy else None),
                              "confidence_threshold": confidence_threshold,
                              "max_escalations": max_escalations,
                              "route_mode": args.route_mode,
                              "prompt_mode": args.prompt_mode,
                              "class_router_path": str(args.class_router) if args.class_router else None,
                              "fixed_action": args.fixed_action,
                              "batch_size": args.batch_size,
                              "max_image_pixels": args.max_image_pixels,
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
