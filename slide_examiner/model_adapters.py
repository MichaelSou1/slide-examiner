from __future__ import annotations

import json
import base64
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import ExaminerAdapter, parse_examiner_json


@dataclass(frozen=True)
class QwenVLConfig:
    model_id: str
    max_new_tokens: int = 768
    temperature: float = 0.0
    device_map: str = "auto"


class QwenVLTransformersAdapter(ExaminerAdapter):
    """Lazy transformers adapter for Qwen-VL style local inference."""

    def __init__(self, config: QwenVLConfig) -> None:
        self.config = config
        self.name = f"qwen-vl:{config.model_id}"
        self._model = None
        self._processor = None

    def examine(self, payload: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._ensure_loaded()
        raw = self._complete(payload)
        return parse_examiner_json(raw)

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("Install transformers and the Qwen-VL dependencies to use local inference.") from exc
        self._processor = AutoProcessor.from_pretrained(self.config.model_id, trust_remote_code=True)
        self._model = AutoModelForImageTextToText.from_pretrained(
            self.config.model_id,
            device_map=self.config.device_map,
            trust_remote_code=True,
        )

    def _complete(self, payload: dict[str, Any]) -> str:
        if self._model is None or self._processor is None:
            raise RuntimeError("Model was not loaded")
        messages = [{"role": "user", "content": _payload_content(payload)}]
        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        processor_kwargs: dict[str, Any] = {"text": [text], "return_tensors": "pt"}
        try:
            from qwen_vl_utils import process_vision_info

            image_inputs, video_inputs = process_vision_info(messages)
            if image_inputs:
                processor_kwargs["images"] = image_inputs
            if video_inputs:
                processor_kwargs["videos"] = video_inputs
        except ImportError:
            pass
        inputs = self._processor(**processor_kwargs).to(self._model.device)
        output = self._model.generate(
            **inputs,
            max_new_tokens=self.config.max_new_tokens,
            do_sample=self.config.temperature > 0,
            temperature=max(self.config.temperature, 1e-5),
        )
        decoded = self._processor.batch_decode(output[:, inputs.input_ids.shape[-1] :], skip_special_tokens=True)
        return decoded[0]


class JSONLReplayAdapter(ExaminerAdapter):
    """Replay saved raw or parsed model outputs keyed by sample/modality/task."""

    def __init__(self, path: str | Path) -> None:
        self.name = "jsonl-replay"
        self.records: dict[tuple[str, str, str], dict[str, Any]] = {}
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                key = (str(record["sample_id"]), str(record["modality"]), str(record["task"]))
                self.records[key] = record

    def examine(self, payload: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        key = (str(payload["sample_id"]), str(payload["modality"]), str(payload["task"]))
        if key not in self.records:
            raise KeyError(f"No replay record for {key}")
        record = self.records[key]
        if record.get("output") is not None:
            return record["output"]
        if record.get("parsed") is not None:
            return record["parsed"]
        return parse_examiner_json(record["raw_output"])


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    model: str
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    max_tokens: int = 768
    temperature: float = 0.0


class OpenAICompatibleAdapter(ExaminerAdapter):
    """Adapter for OpenAI-compatible chat completions with optional image URLs."""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self.config = config
        self.name = f"openai-compatible:{config.model}"

    def examine(self, payload: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai to use the OpenAI-compatible adapter.") from exc
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {self.config.api_key_env}")
        client = OpenAI(api_key=api_key, base_url=self.config.base_url)
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": _openai_content(payload)}],
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        raw = response.choices[0].message.content or "{}"
        return parse_examiner_json(raw)


def _payload_content(payload: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if payload.get("image_path"):
        content.append({"type": "image", "image": payload["image_path"]})
    text_parts = [payload.get("prompt", "Inspect the slide and return JSON.")]
    if payload.get("oracle") is not None:
        text_parts.append("Structured oracle:")
        text_parts.append(json.dumps(payload["oracle"], ensure_ascii=False))
    if payload.get("caption"):
        text_parts.append(f"Caption oracle: {payload['caption']}")
    content.append({"type": "text", "text": "\n".join(text_parts)})
    return content


def _openai_content(payload: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if payload.get("image_path"):
        content.append({"type": "image_url", "image_url": {"url": _image_url(str(payload["image_path"]))}})
    text_parts = [payload.get("prompt", "Inspect the slide and return JSON.")]
    if payload.get("oracle") is not None:
        text_parts.append(json.dumps(payload["oracle"], ensure_ascii=False))
    if payload.get("caption"):
        text_parts.append(str(payload["caption"]))
    content.append({"type": "text", "text": "\n".join(text_parts)})
    return content


def _image_url(value: str) -> str:
    path = Path(value)
    if value.startswith(("http://", "https://", "data:")) or not path.exists():
        return value
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
