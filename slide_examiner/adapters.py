from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from .schemas import DefectLabel, ManifestSample, oracle_view


MODALITIES = ("A", "B", "Bprime", "C")
TASKS = ("T1", "T2", "T3")
VALID_MODALITIES = set(MODALITIES)
VALID_TASKS = set(TASKS)

TASK_INSTRUCTIONS = {
    "T1": "Detect whether the requested slide defect is present. Return JSON only.",
    "T2": "Localize the defective element ids. Return JSON only.",
    "T3": "Suggest executable fixes for the detected defects. Return JSON only.",
}


def sample_value(sample: Any, key: str, default: Any = None) -> Any:
    if isinstance(sample, Mapping):
        return sample.get(key, default)
    return getattr(sample, key, default)


def sample_id(sample: Any, fallback: Any | None = None) -> Any:
    value = sample_value(sample, "id")
    if value is not None:
        return value
    value = sample_value(sample, "sample_id")
    if value is not None:
        return value
    return fallback


def target_defect(sample: Any) -> Any:
    value = sample_value(sample, "defect_type")
    if value is not None:
        return value
    value = sample_value(sample, "defect")
    if value is not None:
        return value

    oracle = sample_value(sample, "oracle")
    if isinstance(oracle, Mapping):
        if "defect_type" in oracle:
            return oracle["defect_type"]
        if "defect" in oracle:
            return oracle["defect"]

    labels = sample_value(sample, "labels", ())
    if labels:
        first = labels[0]
        return sample_value(first, "type")
    return None


def validate_modality(modality: str) -> str:
    if modality not in VALID_MODALITIES:
        raise ValueError(f"Unsupported modality: {modality}")
    return modality


def validate_task(task: str) -> str:
    if task not in VALID_TASKS:
        raise ValueError(f"Unsupported task: {task}")
    return task


class ExaminerAdapter(ABC):
    name = "examiner"

    @abstractmethod
    def examine(self, payload: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Run an examiner on a prepared payload and return parsed JSON."""


def build_probe_payload(
    sample: ManifestSample | dict[str, Any],
    *,
    modality: str,
    task: str,
) -> dict[str, Any]:
    validate_modality(modality)
    validate_task(task)

    manifest = ManifestSample.from_mapping(sample)
    inputs: dict[str, Any] = {}
    payload: dict[str, Any] = {
        "sample_id": manifest.sample_id,
        "modality": modality,
        "task": task,
        "instruction": TASK_INSTRUCTIONS[task],
        "target_defect": target_defect(sample),
        "expected_labels": [label.to_dict() for label in manifest.labels],
        "metadata": manifest.metadata,
        "inputs": inputs,
    }

    if modality in {"A", "C"}:
        payload["image_path"] = manifest.image_path
        inputs["image_path"] = manifest.image_path
    if modality in {"B", "C"}:
        oracle = manifest.oracle
        if oracle is None and manifest.slide:
            oracle = oracle_view(manifest.slide.to_dict())
        if oracle is None and manifest.deck:
            oracle = oracle_view(manifest.deck.to_dict())
        payload["oracle"] = oracle
        inputs["oracle"] = oracle
    if modality == "Bprime":
        payload["caption"] = manifest.caption or ""
        inputs["caption"] = manifest.caption or ""

    prompt_parts = [payload["instruction"]]
    if payload.get("oracle"):
        prompt_parts.append("Use the structured slide oracle for geometry and text.")
    if payload.get("caption"):
        prompt_parts.append("Use the natural-language caption as the perception oracle.")
    if payload.get("image_path"):
        prompt_parts.append("Inspect the rendered slide image.")
    payload["prompt"] = "\n".join(prompt_parts)
    return payload


def build_examiner_payload(
    sample: ManifestSample | dict[str, Any],
    modality: str,
    task: str,
) -> dict[str, Any]:
    return build_probe_payload(sample, modality=modality, task=task)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def parse_examiner_json(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    text = raw.strip()
    errors: list[str] = []

    for candidate in _json_candidates(text):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(f"{exc.msg} at char {exc.pos}")
            continue
        if not isinstance(value, dict):
            raise ValueError("Could not parse examiner JSON: top-level value is not an object")
        return value

    detail = "; ".join(errors[-3:]) if errors else "no JSON object found"
    preview = text[:120].replace("\n", "\\n")
    raise ValueError(f"Could not parse examiner JSON: {detail}. Preview: {preview!r}")


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    stripped = _strip_json_fence(text)
    if stripped:
        candidates.append(stripped)

    fence_pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
    candidates.extend(match.group(1).strip() for match in fence_pattern.finditer(text))
    candidates.extend(_balanced_json_objects(text))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _balanced_json_objects(text: str) -> list[str]:
    snippets: list[str] = []
    for start, char in enumerate(text):
        if char != "{":
            continue

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    snippets.append(text[start : index + 1])
                    break
    return snippets


def normalize_examiner_output(value: dict[str, Any]) -> dict[str, Any]:
    defects = value.get("defects", [])
    normalized_defects: list[dict[str, Any]] = []
    for defect in defects:
        element_ids = defect.get("element_ids", defect.get("target_element_ids", []))
        normalized_defects.append(
            {
                "type": defect.get("type", "UNKNOWN"),
                "present": bool(defect.get("present", True)),
                "element_ids": list(element_ids),
                "severity": float(defect.get("severity", 0.0)),
                "confidence": float(defect.get("confidence", 1.0)),
                "evidence": defect.get("evidence", ""),
                "fix": defect.get("fix", ""),
            }
        )
    return {
        "defects": normalized_defects,
        "overall_score": float(value.get("overall_score", 1.0 if not normalized_defects else 0.0)),
        "pairwise_winner": value.get("pairwise_winner"),
        "raw": value,
    }


class MockAdapter(ExaminerAdapter):
    """Deterministic adapter for pipeline tests before real VLM integration."""

    def __init__(
        self,
        *,
        name: str = "mock",
        response: Mapping[str, Any] | None = None,
        fenced: bool = False,
        miss_modalities: set[str] | None = None,
    ) -> None:
        self.name = name
        self.response = dict(response) if response is not None else None
        self.fenced = fenced
        self.miss_modalities = miss_modalities or set()

    def complete(self, payload: Mapping[str, Any]) -> str:
        response = self.response or self._default_response(payload)
        text = json.dumps(response, ensure_ascii=False, sort_keys=True)
        if self.fenced:
            return f"```json\n{text}\n```"
        return text

    def examine(
        self,
        payload: dict[str, Any],
        modality: str | None = None,
        task: str | None = None,
    ) -> dict[str, Any]:
        if modality is not None and task is not None:
            built_payload = build_examiner_payload(payload, modality, task)
            raw_output = self.complete(built_payload)
            return {
                "payload": built_payload,
                "raw_output": raw_output,
                "parsed": parse_examiner_json(raw_output),
            }

        raw_output = self.complete(payload)
        return normalize_examiner_output(parse_examiner_json(raw_output))

    def _default_response(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        labels = [DefectLabel.from_mapping(item) for item in payload.get("expected_labels", [])]
        if payload["modality"] in self.miss_modalities:
            labels = []
        if labels:
            return self._label_response(labels)

        inputs = payload.get("inputs", {})
        task = payload.get("task", "T1")
        defect_present = self._oracle_says_defective(inputs)
        response: dict[str, Any] = {
            "defect_present": defect_present,
            "confidence": 1.0 if defect_present else 0.0,
            "rationale": "mock response derived from structured sample fields",
        }
        if task == "T2":
            response["elements"] = self._oracle_elements(inputs)
        if task == "T3":
            response["repair_actions"] = [
                {
                    "action": "inspect_target_defect",
                    "target": payload.get("target_defect"),
                    "status": "mock_action",
                }
            ]
        return response

    @staticmethod
    def _label_response(labels: list[DefectLabel]) -> dict[str, Any]:
        active_labels = [label for label in labels if label.type != "NO_DEFECT"]
        defects = [
            {
                "type": label.type,
                "present": True,
                "element_ids": list(label.target_element_ids),
                "severity": label.severity,
                "confidence": 1.0,
                "evidence": "mock label echo",
                "fix": "restore the clean slide geometry or content",
            }
            for label in active_labels
        ]
        return {"defects": defects, "overall_score": max(0.0, 1.0 - 0.2 * len(defects))}

    @staticmethod
    def _oracle_says_defective(inputs: Any) -> bool:
        if not isinstance(inputs, Mapping):
            return False
        oracle = inputs.get("oracle")
        if isinstance(oracle, Mapping):
            for key in ("defect_present", "has_defect", "label"):
                if key in oracle:
                    return bool(oracle[key])
        if inputs.get("caption"):
            return True
        return False

    @staticmethod
    def _oracle_elements(inputs: Any) -> list[Any]:
        if not isinstance(inputs, Mapping):
            return []
        oracle = inputs.get("oracle")
        if not isinstance(oracle, Mapping):
            return []
        elements = oracle.get("elements", [])
        if isinstance(elements, list):
            return elements
        return [elements]
