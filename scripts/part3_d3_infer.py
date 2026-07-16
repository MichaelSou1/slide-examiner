#!/usr/bin/env python3
"""Generic-prompt D3 inference with sample-level routing and one escalation."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

from slide_examiner.d3_training import ACTIONS
from slide_examiner.examiner_contract import parse_deck_result, parse_page_result
from scripts.part3_d3_train import D3Heads, JsonlDataset, _images, pooled_at_prompt


def load(run: Path, base: str, device: torch.device):
    processor = AutoProcessor.from_pretrained(run / "adapter", trust_remote_code=True)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        base, torch_dtype=torch.bfloat16, quantization_config=quant, device_map={"": 0},
        trust_remote_code=True, attn_implementation="sdpa",
    )
    model = PeftModel.from_pretrained(model, run / "adapter").eval()
    hidden = model.get_base_model().config.text_config.hidden_size
    heads = D3Heads(hidden).to(device).eval()
    heads.load_state_dict(torch.load(run / "d3_heads.pt", map_location=device, weights_only=True))
    return processor, model, heads


def extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    return json.loads(text[start:end + 1])


def balanced_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Cover action/task/defect/availability cells before adding repeats."""
    selected: list[dict[str, Any]] = []
    remaining = list(rows)
    seen = {key: Counter() for key in ("target_action", "task", "defect", "availability")}
    while remaining and len(selected) < limit:
        def score(row: dict[str, Any]) -> tuple[float, str]:
            novelty = sum(1.0 / (1.0 + seen[key][str(row[key])]) for key in seen)
            required = 2.0 if row["defect"].startswith("G7_") else 0.0
            required += 1.0 if row["target_action"] in {"REQUEST_REFERENCE", "REQUEST_DECK"} else 0.0
            return novelty + required, row["record_id"]
        best = max(remaining, key=score)
        remaining.remove(best)
        selected.append(best)
        for key in seen:
            seen[key][str(best[key])] += 1
    return selected


def parse_contract(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = extract_json(text)
        if "deck_id" in parsed:
            return parse_deck_result(json.dumps(parsed)).model_dump(mode="json"), None
        return parse_page_result(json.dumps(parsed)).model_dump(mode="json"), None
    except Exception as exc:  # noqa: BLE001 - parser failures are measured artifacts
        return None, f"{type(exc).__name__}: {exc}"


def infer_once(processor: Any, model: Any, heads: D3Heads, row: dict[str, Any],
               device: torch.device, max_new_tokens: int) -> dict[str, Any]:
    prompt = processor.apply_chat_template(row["messages"][:1], tokenize=False,
                                           add_generation_prompt=True)
    image_list = _images(row)
    inputs = processor(text=[prompt], images=image_list if image_list else None,
                       return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    prompt_lengths = inputs["attention_mask"].sum(dim=1)
    with torch.no_grad():
        output = model(**inputs, output_hidden_states=True, return_dict=True)
        pooled = pooled_at_prompt(output.hidden_states[-1], prompt_lengths).float()
        action_logits, select_logits, _ = heads(pooled)
        action = ACTIONS[int(action_logits.argmax(-1).item())]
        confidence = float(torch.sigmoid(select_logits).item())
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    continuation = generated[0, inputs["input_ids"].shape[1]:]
    text = processor.decode(continuation, skip_special_tokens=True)
    parsed, error = parse_contract(text)
    return {"predicted_action": action, "route_confidence": confidence,
            "raw": text, "parsed": parsed, "parse_error": error}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--base", default="/home/nvme04/models/Qwen3-VL-8B-Instruct")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--balanced", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=384)
    args = parser.parse_args()
    device = torch.device("cuda")
    processor, model, heads = load(args.run, args.base, device)
    all_rows = JsonlDataset(args.input).rows
    rows = balanced_rows(all_rows, args.limit) if args.balanced else all_rows[:args.limit]
    by_sample_availability = {(row["sample_id"], row["availability"]): row for row in all_rows}
    results, counts = [], {"parser_failure": 0, "action_loop": 0, "teacher_failure": 0}
    for row in rows:
        first = infer_once(processor, model, heads, row, device, args.max_new_tokens)
        if first["parse_error"]:
            counts["parser_failure"] += 1
        escalation = None
        requested = first["predicted_action"]
        availability = {"CALL_LINTER": "image_structure", "REQUEST_REFERENCE": "reference_available",
                        "REQUEST_DECK": "deck_context_available"}.get(requested)
        if availability:
            followup_row = by_sample_availability.get((row["sample_id"], availability))
            if followup_row:
                counts["action_loop"] += 1
                second = infer_once(processor, model, heads, followup_row, device, args.max_new_tokens)
                if second["parse_error"]:
                    counts["parser_failure"] += 1
                escalation = {"requested_action": requested, "performed": True,
                              "provided_availability": availability, "result": second}
            else:
                escalation = {"requested_action": requested, "performed": False,
                              "reason": f"no {availability} counterpart for sample"}
        results.append({"record_id": row["record_id"], "sample_id": row["sample_id"],
                        "defect": row["defect"], "availability": row["availability"],
                        "target_action": row["target_action"], **first, "escalation": escalation})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as stream:
        for result in results:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
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
    summary = {**counts, "records": len(results), "balanced": args.balanced,
               "semantic_counts": semantic,
               "action_distribution": dict(Counter(x["predicted_action"] for x in results)),
               "target_action_distribution": dict(Counter(x["target_action"] for x in results)),
               "parser_success": sum(x["parsed"] is not None for x in results),
               "post_escalation_parser_success": sum(
                   bool(x["escalation"] and x["escalation"]["performed"]
                        and x["escalation"]["result"]["parsed"] is not None) for x in results),
               "action_correct": sum(x["predicted_action"] == x["target_action"] for x in results),
               "output": str(args.output)}
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
