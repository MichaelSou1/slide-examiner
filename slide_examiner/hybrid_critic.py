"""Part 3 Protocol-2 — the symbolic–neural **hybrid critic** (A.0 / A.5).

A slide-defect critic should not be one model. The Part-1/2/Protocol-1 evidence
says each defect class has a *bottleneck* that picks its engine (A.2):

  * **declared geometry / rules** (G2 overlap, G3 alignment, G4 font, G5 brand
    colour, G6 margin, S3 terminology) -> a **symbolic linter** — coordinates and
    rules give high precision at ~0 false positives; pixels are sub-perceptual for
    a VLM here (Part 1).
  * **render / calibration classes** (G1 overflow, S6 image-text, and the new
    **G7 render-containment overflow**) -> a **VLM**, but only under a *changed
    elicitation* (Protocol 1: G1 via synth-twin C2, G7 via atomic-binary C3).
  * **text / structural semantics** (S1 title-body, S2 narrative, S4 density) ->
    an **LLM** over the slide text.

This module wires a **static router** (defect -> engine) over three engines and a
single served VLM/LLM endpoint, and exposes both per-class detectors (for the
coverage eval, ``scripts/part3_p2_eval.py``) and a unified ``HybridCritic`` that
emits one merged finding list (for the SlideAudit real-data run + demos).

It does NOT touch the frozen Part-2 taxonomy/contract. The linter is
``slide_examiner.geometry.lint_slide`` at its shipped default operating point
(the same point ``scripts/part2_linter_eval.py`` reports: ~0 FP, recall 0.5-1.0
on declared geometry). The VLM engines are reused verbatim from
``scripts/part3_elicit.py`` so the hybrid's VLM column is identical to Protocol 1.
"""
from __future__ import annotations

import json
from pathlib import Path

from .geometry import lint_slide
from .schemas import Deck, Slide
from .taxonomy import DefectType
from .term_consistency import lint_deck
from .defect_types import G7_RENDER_CONTAINMENT_OVERFLOW
from .elicit_common import chat_complete

REPO = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# Engine identifiers + the static router (the bottleneck dichotomy, A.2).
# --------------------------------------------------------------------------- #
LINTER, VLM, LLM = "linter", "vlm", "llm"

#: defect-type string -> engine. Static, set a-priori by the A.2 dichotomy; the
#: coverage eval shows this static assignment ~matches the per-class oracle best.
ROUTER: dict[str, str] = {
    # G1 declared text-overflow is in the IR -> the linter owns it (bal-acc 1.00,
    # ~0 FP). The Protocol-1 VLM-C2 path is the *pixels-only* fallback (when no IR
    # is available); with structure the hybrid uses the cheaper, perfect linter.
    DefectType.G1_TEXT_OVERFLOW.value: LINTER,
    DefectType.G2_ELEMENT_OVERLAP.value: LINTER,
    DefectType.G3_ALIGNMENT_OFFSET.value: LINTER,
    DefectType.G4_FONT_SIZE_INCONSISTENCY.value: LINTER,
    DefectType.G5_BRAND_COLOR_VIOLATION.value: LINTER,
    DefectType.G6_MARGIN_VIOLATION.value: LINTER,
    G7_RENDER_CONTAINMENT_OVERFLOW: VLM,             # linter-blind by construction (Protocol-1: C3)
    # S1 title-body mismatch is data-routed to the VLM: empirically the rendered
    # slide (title + body together) lets the VLM name it (0.94, prec 0.90), while a
    # text-only LLM probe over-flags (0.25, prec 0.09). Title-body needs the layout.
    DefectType.S1_TITLE_BODY_MISMATCH.value: VLM,
    DefectType.S2_NARRATIVE_ORDER_BREAK.value: LLM,
    DefectType.S3_TERMINOLOGY_INCONSISTENCY.value: LINTER,  # term-consistency lint_deck
    DefectType.S4_DENSITY_RULE_VIOLATION.value: LLM,
    DefectType.S5_MISSING_LOGIC_SECTION.value: LLM,        # deck-level completeness (text-semantic)
    DefectType.S6_IMAGE_TEXT_CONTRADICTION.value: VLM,
}

#: per-class best VLM elicitation (Protocol-1 Result-1). VLM-routed classes use
#: this; everything else (the VLM-only baseline) uses C0 whole-taxonomy pointwise.
VLM_ELICIT: dict[str, str] = {
    DefectType.G1_TEXT_OVERFLOW.value: "C2",         # synth-twin pairwise (declared geometry)
    DefectType.S6_IMAGE_TEXT_CONTRADICTION.value: "C0",
    G7_RENDER_CONTAINMENT_OVERFLOW: "C3",            # atomic-binary + forced evidence
}

LINTER_TYPES = {
    DefectType.G1_TEXT_OVERFLOW.value, DefectType.G2_ELEMENT_OVERLAP.value,
    DefectType.G3_ALIGNMENT_OFFSET.value, DefectType.G4_FONT_SIZE_INCONSISTENCY.value,
    DefectType.G5_BRAND_COLOR_VIOLATION.value, DefectType.G6_MARGIN_VIOLATION.value,
}


# --------------------------------------------------------------------------- #
# Linter engine — pure offline, reasons over the DECLARED bbox IR.
# --------------------------------------------------------------------------- #
def _slide_of(rec: dict) -> Slide | None:
    ir = rec.get("slide")
    if not ir:
        return None
    try:
        return Slide.from_mapping(ir)
    except Exception:  # noqa: BLE001
        return None


def _clean_slide_of(rec: dict) -> Slide | None:
    p = (rec.get("pair") or {}).get("clean_slide_path") or rec.get("metadata", {}).get("clean_slide_path")
    if not p:
        return None
    p = p if Path(p).is_absolute() else REPO / p
    if not Path(p).exists():
        return None
    try:
        from .ingest import load_slide_json
        return load_slide_json(p)
    except Exception:  # noqa: BLE001
        return None


def linter_types(rec: dict, *, use_clean: bool = False) -> set[str]:
    """Defect-type strings the symbolic linter emits for this record's IR.

    G1-G6 via geometry ``lint_slide``; S3 via term-consistency ``lint_deck`` on
    the deck. Returns an empty set when there is no structure (real image-only
    data) — i.e. the linter is *blind without IR*, which is exactly the honest
    SlideAudit degradation.
    """
    out: set[str] = set()
    slide = _clean_slide_of(rec) if use_clean else _slide_of(rec)
    if slide is not None:
        out |= {x.type for x in lint_slide(slide)}
    deck = rec.get("deck")
    if deck:
        try:
            d = Deck.from_mapping(deck)
            out |= {x.type for x in lint_deck(d)}
        except Exception:  # noqa: BLE001
            pass
    return out


# --------------------------------------------------------------------------- #
# LLM engine — text-only over the slide IR (S1 / S2 / S4 semantics).
# --------------------------------------------------------------------------- #
_LLM_SYSTEM = (
    "You are a careful slide-content reviewer. You are given a slide's text only "
    "(no image). Judge ONE specific possible problem. Reply with a single JSON "
    "object and nothing else."
)

_LLM_Q = {
    DefectType.S1_TITLE_BODY_MISMATCH.value: (
        "Does the BODY text belong under this TITLE — i.e. is the body actually "
        "about the topic the title announces? Answer present=true only if the body "
        "is about a clearly DIFFERENT topic than the title."
    ),
    DefectType.S4_DENSITY_RULE_VIOLATION.value: (
        "Is this slide overloaded with an excessive volume of text for a single "
        "slide (too many words / bullets to read comfortably)? Answer present=true "
        "only if the text volume is clearly excessive."
    ),
}
_LLM_SCHEMA = (
    'Answer strictly as JSON: {"present": true|false, "evidence": "<short reason '
    'or empty>"}.'
)


def _slide_text(rec: dict) -> tuple[str, str]:
    """(title_text, body_text) from the slide IR elements."""
    ir = rec.get("slide") or {}
    title, body = [], []
    for el in ir.get("elements", []):
        t = (el.get("text") or "").strip()
        if not t:
            continue
        et = (el.get("type") or "").lower()
        pid = (el.get("placeholder_id") or "").lower()
        if "title" in et or "title" in pid:
            title.append(t)
        else:
            body.append(t)
    return " ".join(title), "\n".join(body)


def _deck_titles(rec: dict) -> list[str]:
    deck = rec.get("deck") or {}
    titles = []
    for sl in deck.get("slides", []):
        ttl = ""
        for el in sl.get("elements", []):
            et = (el.get("type") or "").lower()
            pid = (el.get("placeholder_id") or "").lower()
            if ("title" in et or "title" in pid) and (el.get("text") or "").strip():
                ttl = el["text"].strip()
                break
        titles.append(ttl or "(untitled)")
    return titles


def llm_engine(client, model, rec, *, target_defect, max_tokens, blank):
    """Text-only LLM probe for a single semantic class. blank() -> result dict."""
    from slide_examiner.adapters import parse_examiner_json

    out = blank(rec)
    if target_defect == DefectType.S2_NARRATIVE_ORDER_BREAK.value:
        titles = _deck_titles(rec)
        if len(titles) < 2:
            out["failure"] = True
            return out
        listing = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        question = (
            "Below are the slide titles of a deck in their current order. Is the "
            "narrative order broken — is any slide clearly out of its logical "
            "sequence (e.g. a conclusion before the analysis, results before "
            "methods)?"
        )
        user = f"{question}\n\nSLIDE TITLES (in order):\n{listing}\n\n{_LLM_SCHEMA}"
    else:
        title, body = _slide_text(rec)
        if not body and not title:
            out["failure"] = True
            return out
        question = _LLM_Q.get(target_defect, f"Does the slide text exhibit {target_defect}?")
        user = f"{question}\n\nTITLE: {title}\n\nBODY:\n{body}\n\n{_LLM_SCHEMA}"
    messages = [{"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": user}]
    try:
        raw = chat_complete(client, model, messages, max_tokens)
    except Exception as exc:  # noqa: BLE001
        out["failure"] = True
        out["raw"] = f"ERR {exc}"[:300]
        return out
    out["raw"] = raw[:400]
    try:
        parsed = parse_examiner_json(raw)
    except Exception:  # noqa: BLE001
        out["failure"] = True
        return out
    present = bool(parsed.get("present"))
    out["has_defect"] = present
    out["named_target"] = present
    out["predicted_types"] = [target_defect] if present else []
    out["locator"] = {"element": (parsed.get("evidence") or "")[:120]} if present else None
    return out


# --------------------------------------------------------------------------- #
# VLM engine — reuse the Protocol-1 elicitation engines verbatim.
# --------------------------------------------------------------------------- #
def vlm_engine(client, model, rec, *, target_defect, condition, modality, style, max_tokens, blank):
    """Dispatch to the Protocol-1 condition engine (C0/C1/C2/C3)."""
    import importlib
    elicit = importlib.import_module("part3_elicit")  # scripts/ on sys.path
    fn = elicit.ENGINES[condition]
    return fn(client, model, rec, modality, target_defect, style, max_tokens)


# --------------------------------------------------------------------------- #
# Unified hybrid critic — one merged finding list (for SlideAudit run / demos).
# --------------------------------------------------------------------------- #
class HybridCritic:
    """Router over {linter, vlm, llm}. ``engines='auto'`` runs every routed
    engine that can run on the given record (structure-bearing => linter+vlm+llm;
    image-only => vlm+llm only, the honest real-data degradation)."""

    def __init__(self, client=None, model=None, *, modality="A", style="scoped",
                 max_tokens=512, has_structure=True):
        self.client, self.model = client, model
        self.modality, self.style, self.max_tokens = modality, style, max_tokens
        self.has_structure = has_structure

    def critique(self, rec: dict, *, defects: list[str] | None = None) -> dict:
        defects = defects or list(ROUTER)
        findings, engines_run = [], set()

        # 1) linter — one pass, emits all its types (only if structure present).
        if self.has_structure and rec.get("slide"):
            det = linter_types(rec)
            engines_run.add(LINTER)
            for t in sorted(det):
                if ROUTER.get(t) == LINTER and t in defects:
                    findings.append({"type": t, "engine": LINTER, "evidence": "declared-bbox rule"})

        # 2) vlm / llm — per routed class (need a served endpoint).
        if self.client is not None:
            from part3_elicit import _blank_result
            for d in defects:
                eng = ROUTER.get(d)
                if eng == VLM:
                    cond = VLM_ELICIT.get(d, "C0")
                    res = vlm_engine(self.client, self.model, rec, target_defect=d,
                                     condition=cond, modality=self.modality,
                                     style=self.style, max_tokens=self.max_tokens,
                                     blank=_blank_result)
                    engines_run.add(VLM)
                    if res.get("named_target") or (d in (res.get("predicted_types") or [])):
                        findings.append({"type": d, "engine": VLM, "elicit": cond,
                                         "evidence": res.get("locator")})
                elif eng == LLM:
                    res = llm_engine(self.client, self.model, rec, target_defect=d,
                                     max_tokens=self.max_tokens, blank=_blank_result)
                    engines_run.add(LLM)
                    if res.get("named_target"):
                        findings.append({"type": d, "engine": LLM, "evidence": res.get("locator")})

        return {"sample_id": rec.get("sample_id"), "findings": findings,
                "engines_run": sorted(engines_run),
                "predicted_types": sorted({f["type"] for f in findings})}
