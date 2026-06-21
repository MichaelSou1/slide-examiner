"""C1 elicitation engine — free-form describe -> classify-to-taxonomy (A.4).

Two stages:
  Stage 1 (high recall): the VLM freely describes everything wrong with the
    slide, concretely localized. No taxonomy is shown -> it is not anchored to a
    fixed checklist, so it can surface off-taxonomy problems.
  Stage 2 (precision): a text-only classification call maps the free description
    onto the fixed G/S taxonomy + an explicit OTHER bucket (A.3.1.2). Anything
    that maps to no defined type is preserved verbatim in OTHER -> the open-scan
    signal that a fixed checklist (PresentBench / C3) cannot produce.

Both stages are cached per (model, image) so probing N target defects on one
image costs 2 calls, not 2N, and stays internally consistent.
"""
from __future__ import annotations

import threading
from pathlib import Path

from .adapters import JSON_RETRY_INSTRUCTION, parse_examiner_json
from .defect_types import ALL_DEFECT_STRINGS, G7_SPEC, G7_RENDER_CONTAINMENT_OVERFLOW
from .elicit_common import chat_complete
from .examiner_contract import image_content_from_path
from .taxonomy import DEFECTS

# Candidate taxonomy shown to the Stage-2 classifier (12 frozen + G7 + OTHER).
_CANDIDATE_LINES = [f"  {d}: {spec.description}" for d, spec in DEFECTS.items()]
_CANDIDATE_LINES.append(f"  {G7_RENDER_CONTAINMENT_OVERFLOW}: {G7_SPEC.description}")
_CANDIDATE_BLOCK = "\n".join(_CANDIDATE_LINES)

S1_SYSTEM = (
    "You are a senior presentation-design reviewer. Look only at what is visibly "
    "rendered on this single slide."
)
S1_PROMPT = (
    "Describe everything that looks wrong, broken, low-quality, or off about this "
    "slide — layout, text, figures, spacing, color, or anything spilling outside "
    "where it belongs. For each problem, say concretely WHERE it is (which element "
    "or region of the slide). If the slide looks fine, reply exactly: NO PROBLEMS."
)

S2_SYSTEM = (
    "You map a free-form slide critique onto a fixed defect taxonomy. Output ONLY "
    "a JSON object, no prose."
)
S2_PROMPT = (
    "TAXONOMY (id: meaning):\n{taxonomy}\n  OTHER: a real problem fitting none of "
    "the above.\n\n"
    "CRITIQUE:\n{critique}\n\n"
    "List each distinct problem the critique asserts as one taxonomy id. Keep each "
    "locator to AT MOST 8 words. Output ONLY this compact JSON, nothing else:\n"
    '{{"defects": [{{"type": "<id or OTHER>", "locator": "<=8 words"}}]}}\n'
    "If the critique asserts no problems, output {{\"defects\": []}}."
)

_cache: dict[tuple[str, str], dict] = {}
_lock = threading.Lock()


def _image_path(rec: dict) -> str | None:
    return rec.get("image_path") or (rec.get("metadata") or {}).get("defective_image_path")


def _call(client, model, messages, max_tokens):
    return chat_complete(client, model, messages, max_tokens)


def _classify_image(client, model, img: str, max_tokens: int) -> dict:
    """Run Stage 1 + Stage 2 once for an image; return {stage1, defects:[...]}."""
    # Stage 1 — free description (with image).
    s1_messages = [
        {"role": "system", "content": S1_SYSTEM},
        {"role": "user", "content": [image_content_from_path(img), {"type": "text", "text": S1_PROMPT}]},
    ]
    try:
        critique = _call(client, model, s1_messages, max_tokens).strip()
    except Exception as exc:  # noqa: BLE001
        return {"stage1": f"ERR {exc}"[:200], "defects": [], "failure": True}

    if not critique or critique.upper().startswith("NO PROBLEM"):
        return {"stage1": critique, "defects": []}

    # Stage 2 — classify to taxonomy (text only). Robust to (a) bare-array vs
    # {"defects":[...]} shapes and (b) a first malformed reply (one JSON retry).
    s2_messages = [
        {"role": "system", "content": S2_SYSTEM},
        {"role": "user", "content": S2_PROMPT.format(taxonomy=_CANDIDATE_BLOCK, critique=critique)},
    ]
    raw, parsed = "", None
    for attempt in range(2):
        msgs = s2_messages if attempt == 0 else (
            s2_messages + [{"role": "user", "content": JSON_RETRY_INSTRUCTION}])
        try:
            raw = _call(client, model, msgs, max_tokens)
            parsed = parse_examiner_json(raw)
            break
        except Exception:  # noqa: BLE001
            parsed = None
    if parsed is None:
        return {"stage1": critique, "stage2_raw": raw[:300], "defects": [], "classify_failed": True}
    items = parsed if isinstance(parsed, list) else (parsed.get("defects") or [])
    defects = []
    for d in items:
        if not isinstance(d, dict) or not d.get("present", True):
            continue
        t = str(d.get("type", "")).strip()
        if not t:
            continue
        defects.append({"type": t, "locator": str(d.get("locator", "") or ""),
                        "quote": str(d.get("quote", "") or "")})
    return {"stage1": critique, "stage2_raw": raw[:300], "defects": defects}


def run_freeform_sample(client, model, rec, *, modality, target_defect, max_tokens, blank):
    out = blank(rec)
    img = _image_path(rec)
    if not img:
        out["failure"] = True
        return out
    key = (model, img)
    with _lock:
        cached = _cache.get(key)
    if cached is None:
        cached = _classify_image(client, model, img, max_tokens)
        with _lock:
            _cache[key] = cached
    if cached.get("failure"):
        out["failure"] = True
        out["raw"] = cached.get("stage1", "")[:400]
        return out

    defined = [d for d in cached["defects"] if d["type"] in ALL_DEFECT_STRINGS]
    other = [d for d in cached["defects"] if d["type"] not in ALL_DEFECT_STRINGS]
    named = next((d for d in defined if d["type"] == target_defect), None)
    out["has_defect"] = bool(defined)
    out["named_target"] = named is not None
    out["predicted_types"] = sorted({d["type"] for d in defined})
    out["locator"] = {"element": named["locator"], "quote": named["quote"]} if named else None
    out["other"] = [{"text": d["quote"] or d["locator"], "raw_type": d["type"]} for d in other]
    out["raw"] = cached.get("stage1", "")[:400]
    out["stage2_raw"] = cached.get("stage2_raw", "")
    return out


def reset_cache() -> None:
    """Clear the per-image cache (call between models / between runs)."""
    with _lock:
        _cache.clear()
