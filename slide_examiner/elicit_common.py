"""Shared LLM-call config for the Part 3 elicitation engines.

The ``PART3_CHAT_KWARGS`` env var (a JSON object) is forwarded as the OpenAI
``extra_body`` on EVERY elicitation completion. Used to disable thinking on
reasoning VLMs (e.g. ERNIE-4.5-VL) so they emit an answer instead of spending the
token budget on reasoning_content and returning empty ``content``:

    PART3_CHAT_KWARGS='{"chat_template_kwargs":{"enable_thinking":false}}'

Centralizing it here means C0/C1/C2/C3 all honour the same setting without each
call site re-reading the environment.
"""
from __future__ import annotations

import json
import os
import threading

_raw = os.environ.get("PART3_CHAT_KWARGS", "").strip()
ELICIT_EXTRA_BODY: dict | None = json.loads(_raw) if _raw else None


# --------------------------------------------------------------------------- #
# Per-thread token-usage accounting (W2 2.0)
# --------------------------------------------------------------------------- #
# `chat_complete` accumulates `response.usage` into a THREAD-LOCAL counter so a
# per-sample engine — which may call the model once (C0/C3) or K times (C0_rep)
# in one worker thread — can read back exactly what that sample cost. Thread-local
# keeps it correct under the ThreadPoolExecutor without changing chat_complete's
# return signature (fully backward compatible: callers that never reset/pop are
# unaffected). Reasoning tokens (some hosted VLMs bill them under a
# completion_tokens_details block) are tracked separately for the reasoning-token
# audit the sweep needs.
_usage = threading.local()


def reset_usage() -> None:
    """Start a fresh usage window on the CURRENT thread. Call at the top of each
    per-sample engine invocation, then read back with :func:`pop_usage`."""
    _usage.calls = 0
    _usage.prompt_tokens = 0
    _usage.completion_tokens = 0
    _usage.reasoning_tokens = 0


def pop_usage() -> dict:
    """Usage accumulated since the last :func:`reset_usage` on this thread."""
    return {
        "calls": getattr(_usage, "calls", 0),
        "prompt_tokens": getattr(_usage, "prompt_tokens", 0),
        "completion_tokens": getattr(_usage, "completion_tokens", 0),
        "reasoning_tokens": getattr(_usage, "reasoning_tokens", 0),
    }


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _record_usage(resp) -> None:
    """Fold one OpenAI-compatible response's usage into the thread-local counter.
    Counts the call even when the endpoint omits ``usage`` (older mocks / stubs)."""
    _usage.calls = getattr(_usage, "calls", 0) + 1
    u = getattr(resp, "usage", None)
    if u is None:
        return
    _usage.prompt_tokens = getattr(_usage, "prompt_tokens", 0) + _int(getattr(u, "prompt_tokens", None))
    _usage.completion_tokens = getattr(_usage, "completion_tokens", 0) + _int(getattr(u, "completion_tokens", None))
    details = getattr(u, "completion_tokens_details", None)
    rt = None
    if details is not None:
        rt = getattr(details, "reasoning_tokens", None)
        if rt is None and isinstance(details, dict):
            rt = details.get("reasoning_tokens")
    _usage.reasoning_tokens = getattr(_usage, "reasoning_tokens", 0) + _int(rt)


def chat_complete(client, model, messages, max_tokens, temperature: float = 0.0) -> str:
    """One chat completion (temperature 0 by default), forwarding ELICIT_EXTRA_BODY
    if set. Records token usage into the thread-local counter (see :func:`pop_usage`).
    Returns the message content (empty string if the model returned none)."""
    kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens,
              "temperature": temperature}
    if ELICIT_EXTRA_BODY:
        kwargs["extra_body"] = ELICIT_EXTRA_BODY
    resp = client.chat.completions.create(**kwargs)
    _record_usage(resp)
    return resp.choices[0].message.content or ""
