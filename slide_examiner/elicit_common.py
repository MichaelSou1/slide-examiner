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

_raw = os.environ.get("PART3_CHAT_KWARGS", "").strip()
ELICIT_EXTRA_BODY: dict | None = json.loads(_raw) if _raw else None


def chat_complete(client, model, messages, max_tokens, temperature: float = 0.0) -> str:
    """One temperature-0 chat completion, forwarding ELICIT_EXTRA_BODY if set.
    Returns the message content (empty string if the model returned none)."""
    kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens,
              "temperature": temperature}
    if ELICIT_EXTRA_BODY:
        kwargs["extra_body"] = ELICIT_EXTRA_BODY
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
