"""Part 1 small-scale pilot: real-VLM SlideProbe over the pilot manifest.

Runs a real OpenAI-compatible VLM (Qwen3-VL-4B served by vLLM) over every
(sample x modality x task) cell of the rendered pilot manifest and writes
probe records compatible with `slide_examiner.analysis.summarize_probe_records`.

Differences from the mock `probe` path (these are the protocol refinements the
pilot is meant to surface and are documented in reports/pilot_slideprobe.md):
  * the probe prompt is made schema- and scope-aware so a zero-shot model knows
    which defect IDs to consider and the exact JSON shape to emit;
  * raw model text, parse-failure detail, and per-call latency are recorded.

Usage:
  OPENAI_API_KEY=EMPTY PYTHONPATH=. python scripts/run_pilot.py \
      --manifest data/pilot/manifest_rendered.jsonl \
      --base-url http://localhost:8011/v1 --model qwen3vl-4b \
      --out runs/probe/pilot_probe.jsonl --workers 8
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from slide_examiner.adapters import (
    JSON_RETRY_INSTRUCTION,
    MODALITIES,
    parse_examiner_json,
)
from slide_examiner.examiner_contract import build_messages_from_sample
from slide_examiner.schemas import ManifestSample

TASKS = ("T1", "T2", "T3")

PAGE_SCOPE = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
              "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION",
              "S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION"]
DECK_SCOPE = ["S2_NARRATIVE_ORDER_BREAK", "S3_TERMINOLOGY_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION"]

DEFECT_DEFS = {
    "G1_TEXT_OVERFLOW": "text overflows or spills beyond the bounds of its box/placeholder",
    "G2_ELEMENT_OVERLAP": "two elements visually overlap or collide when they should not",
    "G3_ALIGNMENT_OFFSET": "an element is misaligned / offset from where it should sit",
    "G4_FONT_SIZE_INCONSISTENCY": "inconsistent font sizes among text that should match",
    "G5_BRAND_COLOR_VIOLATION": "a color is off-brand / wrong for an element",
    "G6_MARGIN_VIOLATION": "an element bleeds past the page margin or off the canvas edge",
    "S1_TITLE_BODY_MISMATCH": "the slide title does not match the body content / topic",
    "S4_DENSITY_RULE_VIOLATION": "the slide is overcrowded / too dense with text",
    "S6_IMAGE_TEXT_CONTRADICTION": "the image content contradicts the slide text",
    "S2_NARRATIVE_ORDER_BREAK": "the slides are out of their logical narrative order",
    "S3_TERMINOLOGY_INCONSISTENCY": "a key term is used inconsistently across slides",
    "S5_MISSING_LOGIC_SECTION": "a required section / logical step is missing from the deck",
}

TASK_LINE = {
    "T1": "TASK: Decide for each candidate type whether the defect is PRESENT.",
    "T2": "TASK: For any present defect, localize it by filling element_ids (page) or related page ids (deck).",
    "T3": "TASK: For any present defect, give an executable fix in fix.",
}


def is_deck(rec: dict) -> bool:
    return bool(rec.get("deck"))


def cell_suffix(rec: dict, task: str) -> str:
    scope = DECK_SCOPE if is_deck(rec) else PAGE_SCOPE
    catalog = "; ".join(f"{d}: {DEFECT_DEFS[d]}" for d in scope)
    schema = (
        '{"has_defect": <bool>, "findings": [{"type": "<one candidate ID>", '
        '"severity": "minor|moderate|severe", "locator": {"level": "%s", "page_id": "<id>", '
        '"element_id": "<id-or-null>", "related_page_ids": []}, "evidence": "<short grounded reason>", '
        '"fix_suggestion": "<one executable action>"}]}'
    ) % ("deck" if is_deck(rec) else "page")
    return (
        f"\n{TASK_LINE[task]}\n"
        f"Consider ONLY these candidate defect types: {catalog}.\n"
        "Report a finding only when you are confident the defect is actually present.\n"
        f"Output ONLY one JSON object (no prose, no code fences) matching:\n{schema}\n"
        'If the slide/deck is clean, output {"has_defect": false, "findings": []}.'
    )


def build_cell_messages(rec: dict, modality: str, task: str) -> list[dict]:
    """Production path: the contract serializer (handles A/B/B'/C, page/deck,
    multi-image decks) plus a per-task + schema reminder appended to the user turn."""
    messages = build_messages_from_sample(rec, modality=modality)
    suffix = cell_suffix(rec, task)
    user = messages[-1]
    if isinstance(user.get("content"), list):
        user["content"].append({"type": "text", "text": suffix})
    else:
        user["content"] = f"{user.get('content', '')}\n{suffix}"
    return messages


def call_model(client, model: str, messages: list[dict], max_tokens: int) -> str:
    resp = client.chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens, temperature=0.0,
    )
    return resp.choices[0].message.content or "{}"


def run_cell(client, model: str, sample: ManifestSample, rec: dict, modality: str, task: str, max_tokens: int) -> dict:
    from slide_examiner.examiner_contract import normalize_modality
    modality_value = normalize_modality(modality).value
    record = {
        "sample_id": sample.sample_id,
        "model": model,
        "modality": modality_value,
        "task": task,
        "labels": [label.to_dict() for label in sample.labels],
        "label_types": [label.type for label in sample.labels],
        "metadata": sample.metadata,
        "template_condition": sample.metadata.get("template_condition"),
        "level": "deck" if is_deck(rec) else "page",
    }
    messages = build_cell_messages(rec, modality, task)
    attempts: list[dict] = []
    start = time.time()
    for attempt in range(2):  # 1 retry with stricter JSON instruction
        try:
            raw = call_model(client, model, messages, max_tokens)
        except Exception as exc:  # network / server error
            record.update(output=None, examiner_failure=True, failure_type="api_error",
                          failure_message=str(exc)[:300], latency_s=round(time.time() - start, 3))
            return record
        try:
            parsed = parse_examiner_json(raw)
            record.update(output=parsed, raw_output=raw, parse_attempts=attempt + 1,
                          latency_s=round(time.time() - start, 3))
            return record
        except ValueError as exc:
            attempts.append({"raw_output": raw, "error": str(exc)})
            messages = messages + [{"role": "user", "content": JSON_RETRY_INSTRUCTION}]
    record.update(output=None, examiner_failure=True, failure_type="parse_error",
                  failure_message=attempts[-1]["error"][:300], raw_output=attempts[-1]["raw_output"],
                  parse_attempts=len(attempts), latency_s=round(time.time() - start, 3))
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/pilot/manifest_rendered.jsonl")
    ap.add_argument("--base-url", default="http://localhost:8011/v1")
    ap.add_argument("--model", default="qwen3vl-4b")
    ap.add_argument("--out", default="runs/probe/pilot_probe.jsonl")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=640)
    ap.add_argument("--modalities", nargs="+", default=list(MODALITIES))
    ap.add_argument("--tasks", nargs="+", default=list(TASKS))
    args = ap.parse_args()

    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url)
    raw_records = [json.loads(line) for line in Path(args.manifest).open() if line.strip()]
    samples = [ManifestSample.from_mapping(r) for r in raw_records]

    jobs = []
    for rec, sample in zip(raw_records, samples):
        for modality in args.modalities:
            for task in args.tasks:
                jobs.append((sample, rec, modality, task))

    print(f"Running {len(jobs)} cells ({len(samples)} samples x {len(args.modalities)} modalities x {len(args.tasks)} tasks)")
    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_cell, client, args.model, s, r, m, t, args.max_tokens): (s.sample_id, m, t)
                for (s, r, m, t) in jobs}
        done = 0
        for fut in as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 50 == 0 or done == len(jobs):
                fails = sum(1 for x in results if x.get("examiner_failure"))
                print(f"  {done}/{len(jobs)} done, {fails} failures, {time.time()-t0:.0f}s")

    results.sort(key=lambda r: (r["sample_id"], r["modality"], r["task"]))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for r in results:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    fails = sum(1 for x in results if x.get("examiner_failure"))
    print(f"Wrote {len(results)} records to {out} ({fails} failures, {fails/len(results):.1%})")


if __name__ == "__main__":
    main()
