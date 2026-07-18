"""Lightweight .env loader + selectable OpenAI-compatible completion factory.

Part 3 can drive the generator + frozen reflection LLM (and optionally the
zero-shot examiner / judge) through an online API instead of the slow local
27B. The endpoint style is selectable: ``chat`` (``/v1/chat/completions``) or
``responses`` (``/v1/responses``).
"""
from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Callable

Completion = Callable[[list[dict[str, Any]]], str]
CompletionWithMetadata = Callable[[list[dict[str, Any]]], dict[str, Any]]


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> dict[str, str]:
    """Minimal .env parser (no dependency). Populates os.environ.

    Real environment variables win unless ``override=True``. Lines are
    ``KEY=VALUE``; ``#`` comments and blank lines are ignored; surrounding
    single/double quotes are stripped.
    """
    p = Path(path)
    loaded: dict[str, str] = {}
    if not p.exists():
        return loaded
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


def _default_extra_body() -> dict[str, Any] | None:
    """Endpoint-level chat extras, e.g. disabling a reasoning model's thinking.

    Some served models (e.g. mimo-v2.5-pro) are reasoning models that spend the
    token budget on ``reasoning_content`` and return empty ``content`` under a
    tight ``max_tokens``. Set ``PART3_DISABLE_THINKING=1`` to pass
    ``chat_template_kwargs={"enable_thinking": False}`` so the generator/reflection/
    examiner all emit content directly (uniformly across every condition, so the
    frozen-controls invariant holds).
    """
    if os.environ.get("PART3_DISABLE_THINKING", "").strip().lower() in ("1", "true", "yes", "on"):
        # DashScope/Qwen's OpenAI-compatible API consumes ``enable_thinking``
        # directly, while local vLLM servers consume it through the chat
        # template kwargs. Supplying both keeps the frozen control effective on
        # either backend instead of silently spending the output budget on CoT.
        return {
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
    return None


def _first_set_env(*names: str) -> str:
    """Return the first env-var NAME whose value is non-empty; else the last name."""
    for n in names:
        if os.environ.get(n):
            return n
    return names[-1]


def resolve_role(role: str, *, fallback: str | None = None, default_model: str | None = None) -> dict[str, Any]:
    """Resolve an independent API service for one role from ``PART3_<ROLE>_*``.

    Each role (generator / optimizer / judge / examiner) is its OWN service:
    ``MODEL`` / ``BASE_URL`` / ``API_KEY`` / ``API_STYLE``. Resolution order is
    the role's own var → an optional ``fallback`` role's var → shared ``OPENAI_*``
    (``PART3_API_STYLE`` for style). ``api_key`` is returned as the env-var NAME
    that actually holds a value (``build_completion`` reads it, with a final
    fallback to ``OPENAI_API_KEY``), so a role can point at a fully separate
    provider+key, or co-locate by leaving its vars blank.
    """
    R = role.upper()
    F = fallback.upper() if fallback else None

    def pick(suffix: str, shared: str | None = None) -> str | None:
        v = os.environ.get(f"PART3_{R}_{suffix}")
        if not v and F:
            v = os.environ.get(f"PART3_{F}_{suffix}")
        return v or shared

    key_candidates = [f"PART3_{R}_API_KEY"]
    if F:
        key_candidates.append(f"PART3_{F}_API_KEY")
    key_candidates.append("OPENAI_API_KEY")
    return {
        "model": pick("MODEL", default_model),
        "base_url": pick("BASE_URL", os.environ.get("OPENAI_BASE_URL")),
        "api_key_env": _first_set_env(*key_candidates),
        "api_style": pick("API_STYLE", os.environ.get("PART3_API_STYLE", "chat")),
    }


def build_completion(
    model: str,
    base_url: str | None,
    *,
    api_key_env: str = "OPENAI_API_KEY",
    api_style: str = "chat",
    max_tokens: int = 2048,
    temperature: float = 0.0,
    extra_body: dict[str, Any] | None = None,
) -> Completion:
    """Return a ``messages -> text`` callable for chat or responses endpoints."""

    style = (api_style or "chat").lower()
    if extra_body is None:
        extra_body = _default_extra_body()

    def complete(messages: list[dict[str, Any]]) -> str:
        from openai import OpenAI

        # per-role key env, with a fallback to OPENAI_API_KEY so per-role key vars
        # are optional (a single shared key still works for every role).
        key = os.environ.get(api_key_env) or os.environ.get("OPENAI_API_KEY") or "EMPTY"
        client = OpenAI(api_key=key, base_url=base_url or None)
        if style == "responses":
            kwargs: dict[str, Any] = {"model": model, "input": messages, "max_output_tokens": max_tokens}
            if temperature is not None:
                kwargs["temperature"] = temperature
            resp = client.responses.create(**kwargs)
            text = getattr(resp, "output_text", None)
            return text if text else "{}"
        chat_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_body:
            chat_kwargs["extra_body"] = extra_body
        resp = client.chat.completions.create(**chat_kwargs)
        return resp.choices[0].message.content or "{}"

    return complete


def build_completion_with_metadata(
    model: str,
    base_url: str | None,
    *,
    api_key_env: str = "OPENAI_API_KEY",
    api_style: str = "chat",
    max_tokens: int = 2048,
    temperature: float = 0.0,
    extra_body: dict[str, Any] | None = None,
) -> CompletionWithMetadata:
    """Return a completion callable that preserves usage and latency metadata."""
    style = (api_style or "chat").lower()
    if extra_body is None:
        extra_body = _default_extra_body()

    def usage_value(usage: Any, name: str) -> int:
        if usage is None:
            return 0
        value = usage.get(name, 0) if isinstance(usage, dict) else getattr(usage, name, 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def complete(messages: list[dict[str, Any]]) -> dict[str, Any]:
        from openai import OpenAI

        key = os.environ.get(api_key_env) or os.environ.get("OPENAI_API_KEY") or "EMPTY"
        client = OpenAI(api_key=key, base_url=base_url or None)
        started = time.perf_counter()
        if style == "responses":
            kwargs: dict[str, Any] = {
                "model": model, "input": messages, "max_output_tokens": max_tokens,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            response = client.responses.create(**kwargs)
            text = getattr(response, "output_text", None) or ""
        else:
            kwargs = {
                "model": model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if extra_body:
                kwargs["extra_body"] = extra_body
            response = client.chat.completions.create(**kwargs)
            text = response.choices[0].message.content or ""
        latency = time.perf_counter() - started
        usage = getattr(response, "usage", None)
        prompt_tokens = usage_value(usage, "prompt_tokens") or usage_value(usage, "input_tokens")
        completion_tokens = (usage_value(usage, "completion_tokens")
                             or usage_value(usage, "output_tokens"))
        total_tokens = usage_value(usage, "total_tokens") or prompt_tokens + completion_tokens
        return {
            "text": text,
            "model": str(getattr(response, "model", None) or model),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_seconds": latency,
        }

    return complete
