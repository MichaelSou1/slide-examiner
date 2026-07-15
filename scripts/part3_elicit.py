"""Part 3 Protocol-1 elicitation harness (A.4).

Generalizes ``playground/probe_toc.py`` into a 4-condition elicitation sweep over
the "rescuable" defect classes (G1 / S6 / G7). The science is **C3 vs C0**: same
model, same taxonomy, same image, the only difference is "ask the whole taxonomy
in one overloaded call" (C0) vs "ask one atomic binary per type with forced
localization" (C3, PresentBench-style).

Conditions:
  C0  pointwise + rubric + whole-taxonomy single call  (reuses part2_eval)
  C3  atomic per-type binary YES/NO + forced evidence   (this module)
  C1  free-form describe -> classify to taxonomy         (slide_examiner.elicit_freeform)
  C2  synth-twin pairwise (geometry-normalized counterfactual) (slide_examiner.elicit_pairwise)

Every per-sample result records BOTH a detection-level signal (``has_defect`` —
model asserts something is wrong) and a named-level signal (``named_target`` —
model names the *asked* defect type). Scoring then reports paired-clean
balanced-accuracy / recall / FPR / precision at each level with Wilson CIs.
  * G1 / S6 are in the frozen taxonomy -> the NAMED level is the headline.
  * G7 is our extension and absent from C0's taxonomy (C0 cannot emit the literal
    string) -> the DETECTION level is the headline for the C3-vs-C0 contrast.

Usage:
  python scripts/part3_elicit.py --condition C3 \
    --manifest data/part3/manifest_g7_rendered.jsonl \
    --base-url http://localhost:8101/v1 --model ft-8b --style trained \
    --defects G7_RENDER_CONTAINMENT_OVERFLOW --modalities A \
    --out data/part3/p1_ft8b_C3_g7.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from slide_examiner.adapters import parse_examiner_json  # noqa: E402
from slide_examiner.elicit_common import chat_complete, pop_usage, reset_usage  # noqa: E402
from slide_examiner.defect_types import (  # noqa: E402
    G7_RENDER_CONTAINMENT_OVERFLOW,
    G7_SPEC,
    is_extension,
)
from slide_examiner.examiner_contract import image_content_from_path  # noqa: E402
from slide_examiner.statistics import balanced_accuracy_ci, wilson_interval  # noqa: E402
from slide_examiner.taxonomy import DEFECTS  # noqa: E402

# part2_eval gives us build_messages (trained|scoped), call, clean_variant, defect_of.
from part2_eval import build_messages, call, clean_variant, defect_of, is_deck  # noqa: E402
from run_pilot import DECK_SCOPE  # noqa: E402  (deck candidate types for C0_full defs)

DECK_DEFECTS = {"S2_NARRATIVE_ORDER_BREAK", "S3_TERMINOLOGY_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION"}


# --------------------------------------------------------------------------- #
# Per-type binary questions (C3 / used as the localization target by C1)
# --------------------------------------------------------------------------- #
_SPECIFIC_QUESTIONS = {
    "G1_TEXT_OVERFLOW": (
        "Does any text visibly overflow or get clipped by its text box — letters "
        "cut off at an edge, or a line running past the box boundary?"
    ),
    "S6_IMAGE_TEXT_CONTRADICTION": (
        "Does any chart, diagram, or image visibly contradict the text near it — "
        "e.g. the text states a trend, label, or number that the figure does not "
        "show?"
    ),
    # G3/G5 re-operationalised as INTERNAL contrast (E8): decidable from the slide
    # alone — one item out of line with / a different colour from its sibling list.
    "G3_ALIGNMENT_OFFSET": (
        "Among a list of bullet/body items that should line up, is ONE of them "
        "misaligned — indented or shifted so it does not line up with the rest?"
    ),
    "G5_BRAND_COLOR_VIOLATION": (
        "Among a list of bullet/body items that share one text colour, does ONE of "
        "them have a text colour that clearly differs from the others?"
    ),
    # G6 re-operationalised as a PAGE-OFFSET (E8): the whole content block is shifted
    # toward one side -> asymmetric margins (decidable from the slide alone).
    "G6_MARGIN_VIOLATION": (
        "Is the slide's whole block of content shifted toward one side, leaving clearly "
        "unequal left/right margins — one side crowded against (or running off) the edge "
        "while the opposite side is noticeably empty?"
    ),
    G7_RENDER_CONTAINMENT_OVERFLOW: G7_SPEC.elicit_question,
}

# E8 re-operationalisation hooks: when set (via --question / --afc-phrase), the C3 /
# C0_named atomic query and the 2-AFC phrase use a custom 口径 instead of the taxonomy
# description. Used to re-pose G3/G5 as INTERNAL-contrast defects (one element
# inconsistent with its siblings — decidable from the slide alone, no external ref).
_Q_OVERRIDE: str | None = None
_AFC_OVERRIDE: str | None = None


def question_for(defect: str) -> str:
    if _Q_OVERRIDE:  # E8 re-operationalisation: pass a custom 口径 (e.g. internal-contrast)
        return _Q_OVERRIDE
    if defect in _SPECIFIC_QUESTIONS:
        return _SPECIFIC_QUESTIONS[defect]
    spec = DEFECTS.get(defect)
    desc = spec.description if spec else defect.replace("_", " ").lower()
    return f"Does this slide visibly exhibit the following defect — {desc}?"


C3_SYSTEM = (
    "You are a meticulous slide-quality inspector. You will be asked about ONE "
    "specific possible defect. Look only at what is visibly rendered. Answer with "
    "a single JSON object and nothing else."
)

C3_SCHEMA_HINT = (
    'Answer strictly as JSON:\n'
    '{{"present": true|false, "evidence_element": "<concrete element/region you '
    'point to, or empty>", "evidence_region": "<top-left|top|top-right|left|'
    'center|right|bottom-left|bottom|bottom-right|empty>", "confidence": 0.0-1.0}}\n'
    'If present=true you MUST name a concrete evidence_element (e.g. "the title", '
    '"the right-hand card", "the bottom list item"). If you cannot point to '
    "concrete visible evidence, answer present=false."
)


# --------------------------------------------------------------------------- #
# Unified per-sample elicitation result
# --------------------------------------------------------------------------- #
def _blank_result(rec: dict, sample_id: str | None = None) -> dict:
    return {
        "sample_id": sample_id or rec["sample_id"],
        "has_defect": False,
        "named_target": False,
        "predicted_types": [],
        "locator": None,
        "confidence": None,
        "other": [],          # off-taxonomy free-form items (C1 only)
        "raw": "",
        "failure": False,
    }


# --------------------------------------------------------------------------- #
# C0 — whole-taxonomy single pointwise call (reuse part2_eval prompt path)
# --------------------------------------------------------------------------- #
def _c0_call(client, model, rec, modality, target_defect, style, max_tokens, temperature=0.0):
    """One C0 whole-taxonomy pointwise completion, scored paired-clean. Factored out
    so C0_rep can draw K samples at temperature>0 without duplicating the prompt/parse
    path. temperature=0.0 reproduces engine_c0 exactly."""
    out = _blank_result(rec)
    try:
        messages = build_messages(rec, modality, style)
        raw = chat_complete(client, model, messages, max_tokens, temperature=temperature)
    except Exception as exc:  # noqa: BLE001 - bad record / API error must not abort the run
        out["failure"] = True
        out["raw"] = f"ERR {exc}"[:300]
        return out
    out["raw"] = raw[:400]
    try:
        parsed = parse_examiner_json(raw)
    except Exception:  # noqa: BLE001
        out["failure"] = True
        return out
    findings = parsed.get("findings", []) or []
    types = sorted({f.get("type") for f in findings if f.get("type")})
    out["predicted_types"] = types
    out["has_defect"] = bool(parsed.get("has_defect")) or bool(findings)
    out["named_target"] = target_defect in types
    return out


def engine_c0(client, model, rec, modality, target_defect, style, max_tokens):
    return _c0_call(client, model, rec, modality, target_defect, style, max_tokens, temperature=0.0)


# --------------------------------------------------------------------------- #
# C0_rep (E1, W2 2.1) — COMPUTE-MATCHED C0: draw K temperature-sampled C0 calls on
# the same slide (K = the number of atomic questions C3 asks per slide in
# deployment, i.e. the routed hybrid's page taxonomy = 9 frozen page types + G7),
# then aggregate. This isolates "does C3 win only because it spends K× the
# test-time compute?" — give C0 the SAME K-call budget and check whether a union /
# majority vote of K independent C0 draws matches C3's single-question recovery.
#   * union    (has_defect / named_target): ANY of the K draws asserts it -> the
#              most generous reading of "more samples = more coverage".
#   * majority (has_defect_maj / named_target_maj): strict majority of the
#              SUCCESSFUL draws -> the self-consistency reading.
# Both are scored paired-clean (the clean twin gets its own K draws) so specificity
# is defined for each aggregation. Every raw draw is kept in `reps` for audit.
# --------------------------------------------------------------------------- #
# Deployment K for a page-level defect: the routed hybrid runs one atomic binary
# per page-taxonomy type (9) plus the G7 extension. Overridable via --rep-k.
C0_REP_DEFAULT_K = 10
C0_REP_DEFAULT_TEMP = 0.7


def engine_c0_rep(client, model, rec, modality, target_defect, style, max_tokens,
                  rep_k=None, rep_temp=C0_REP_DEFAULT_TEMP):
    k = rep_k if (rep_k and rep_k > 0) else C0_REP_DEFAULT_K
    out = _blank_result(rec)
    reps = []
    det_votes = named_votes = n_ok = 0
    types_union: set = set()
    for _ in range(k):
        r = _c0_call(client, model, rec, modality, target_defect, style, max_tokens,
                     temperature=rep_temp)
        reps.append({"has_defect": r["has_defect"], "named_target": r["named_target"],
                     "predicted_types": r["predicted_types"], "failure": r["failure"],
                     "raw": r["raw"][:200]})
        if r["failure"]:
            continue
        n_ok += 1
        det_votes += int(bool(r["has_defect"]))
        named_votes += int(bool(r["named_target"]))
        types_union |= set(r["predicted_types"])
    out["reps"] = reps
    out["rep_k"] = k
    out["rep_temp"] = rep_temp
    out["rep_n_ok"] = n_ok
    out["rep_det_votes"] = det_votes
    out["rep_named_votes"] = named_votes
    if n_ok == 0:  # every draw failed (quota death) -> resume will retry this probe
        out["failure"] = True
        return out
    # union = primary scored signal (has_defect/named_target); majority stored
    # alongside for the second aggregation the scorer picks up automatically.
    out["has_defect"] = det_votes >= 1
    out["named_target"] = named_votes >= 1
    out["has_defect_maj"] = det_votes * 2 > n_ok
    out["named_target_maj"] = named_votes * 2 > n_ok
    out["predicted_types"] = sorted(types_union)
    out["raw"] = reps[0]["raw"]
    return out


# --------------------------------------------------------------------------- #
# C0plus — C0 whole-taxonomy single pointwise call, but with G7 ADDED to the
# candidate catalog. (RC-01 / DA-1 control.) C0 cannot *name* G7 because G7 is
# off-taxonomy: the scoped suffix says "Consider ONLY these candidate defect
# types: <12 frozen, no G7>." C0plus holds the overloaded whole-taxonomy FORMAT
# fixed and changes ONE thing — it lists G7 (with a one-line def) among the
# candidates, so the model is both told about it and permitted to emit the
# string. This separates the two readings of the C0->C3 G7 recovery:
#   * prompt-coverage artifact: C0 simply never asked about G7 -> if C0plus
#     recovers G7, the effect is coverage, not format.
#   * format suppression: the whole-taxonomy-at-once format buries an
#     off-taxonomy render class even when it IS named -> if C0plus still floors
#     G7 (and only the atomic C3 recovers it), the format claim is earned.
# Scored paired-clean exactly like C0 (detection = any finding; named = G7 named).
# --------------------------------------------------------------------------- #
_G7_CATALOG_DEF = (
    "an element whose declared box is legal (in-margin, non-overlapping) but whose "
    "rendered content visibly spills outside its container, card, or frame"
)


_CATALOG_ANCHOR = ".\nReport a finding only when you are confident the defect is actually present."
_SCOPE_ANCHOR = "'S6_IMAGE_TEXT_CONTRADICTION']"
_SCOPE_REPL = "'S6_IMAGE_TEXT_CONTRADICTION', 'G7_RENDER_CONTAINMENT_OVERFLOW']"


def _build_c0plus_messages(rec, modality, style):
    """Build the scoped whole-taxonomy messages with G7 injected into the candidate
    catalog (and the CHECK_SCOPE list), holding the overloaded FORMAT fixed. Shared
    by C0plus and C0_full. Fail closed: raises if the scoped anchor is absent."""
    messages = build_messages(rec, modality, style)
    g7_entry = f"; {G7_RENDER_CONTAINMENT_OVERFLOW}: {_G7_CATALOG_DEF}"
    user = messages[-1]
    catalog_patched = False
    if isinstance(user.get("content"), list):
        for part in user["content"]:
            if part.get("type") != "text":
                continue
            if _CATALOG_ANCHOR in part["text"]:
                part["text"] = part["text"].replace(_CATALOG_ANCHOR, g7_entry + _CATALOG_ANCHOR, 1)
                catalog_patched = True
            if _SCOPE_ANCHOR in part["text"]:
                part["text"] = part["text"].replace(_SCOPE_ANCHOR, _SCOPE_REPL, 1)
    if not catalog_patched:
        raise RuntimeError("C0plus/C0_full requires --style scoped (catalog anchor not found)")
    return messages


def engine_c0plus(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    try:
        # Inject G7 into the scoped candidate catalog, holding everything else fixed.
        # The scoped suffix lists candidates as "...<last type>: <def>.\nReport a
        # finding only when you are confident the defect is actually present." We
        # append G7 as one more "; <ID>: <def>" entry just before that catalog
        # terminator, and mirror it into the CHECK_SCOPE list, so G7 is both named
        # and permitted everywhere the frozen taxonomy is. Fail closed if not scoped.
        messages = _build_c0plus_messages(rec, modality, style)
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
    findings = parsed.get("findings", []) or []
    types = sorted({f.get("type") for f in findings if f.get("type")})
    out["predicted_types"] = types
    out["has_defect"] = bool(parsed.get("has_defect")) or bool(findings)
    out["named_target"] = target_defect in types
    return out


# --------------------------------------------------------------------------- #
# C0_full (E2, W2 2.1) — the DEFINITION+EVIDENCE-matched single call. Holds the
# C0plus whole-taxonomy single-call FORMAT fixed and adds the two ingredients that
# otherwise only C3 has:
#   * definitions — each candidate type is spelled out with the exact binary
#     decision question C3 uses (question_for), appended as a DEFINITIONS block.
#   * forced evidence — every reported finding MUST name a concrete visible element;
#     findings with no element/evidence pointer are DROPPED (not counted), the same
#     gate C3 applies. This lets the decomposition read:
#       C0plus -> C0_full  = the contribution of definitions + forced evidence
#       C0_full -> C3      = the contribution of DECOMPOSITION (atomic per-type call)
# Still ONE model call per slide -> compute-matched to C0/C0plus (unlike C0_rep).
# Scored paired-clean exactly like C0/C0plus (detection = any surviving finding).
# --------------------------------------------------------------------------- #
def _c0_full_definitions(rec) -> str:
    """DEFINITIONS block: each in-scope candidate type + the C3 binary question that
    operationalises it, plus G7. Mirrors the scoped catalog so every named type has a
    decision rule."""
    scope = list(DECK_SCOPE) if is_deck(rec) else [
        "G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
        "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION",
        "S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION"]
    if G7_RENDER_CONTAINMENT_OVERFLOW not in scope:
        scope.append(G7_RENDER_CONTAINMENT_OVERFLOW)
    lines = [f"- {d}: {question_for(d)}" for d in scope]
    return ("DEFINITIONS — a candidate is PRESENT only if the answer to its question "
            "is yes:\n" + "\n".join(lines))


_C0_FULL_EVIDENCE_RULE = (
    "\nFor EVERY finding you report you MUST fill `evidence` with the concrete "
    "visible element or region it points to (e.g. \"the bottom-right card\", \"the "
    "title line\"). If you cannot point to a concrete visible element, DO NOT report "
    "that finding."
)


def _finding_has_evidence(f: dict) -> bool:
    """Forced-evidence gate (matches C3): a finding counts only if it names a
    concrete element — a non-placeholder `evidence` string or a locator element_id."""
    placeholder = {"", "none", "n/a", "null", "empty", "-"}
    ev = str(f.get("evidence") or "").strip()
    loc = f.get("locator") if isinstance(f.get("locator"), dict) else {}
    el = str((loc or {}).get("element_id") or "").strip()
    return (ev.lower() not in placeholder) or (el.lower() not in placeholder)


def engine_c0_full(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    try:
        messages = _build_c0plus_messages(rec, modality, style)
        # Append DEFINITIONS + forced-evidence rule to the last text part (after the
        # scoped schema), holding the whole-taxonomy single-call format fixed.
        addendum = "\n\n" + _c0_full_definitions(rec) + _C0_FULL_EVIDENCE_RULE
        user = messages[-1]
        if isinstance(user.get("content"), list):
            for part in reversed(user["content"]):
                if part.get("type") == "text":
                    part["text"] = part["text"] + addendum
                    break
        else:
            user["content"] = f"{user.get('content', '')}{addendum}"
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
    findings = parsed.get("findings", []) or []
    kept = [f for f in findings if f.get("type") and _finding_has_evidence(f)]
    types = sorted({f.get("type") for f in kept})
    out["predicted_types"] = types
    out["has_defect"] = bool(kept)
    out["named_target"] = target_defect in types
    out["dropped_no_evidence"] = len(findings) - len(kept)
    return out


# --------------------------------------------------------------------------- #
# C0_named — single-slide ABSOLUTE, NAMED target, atomic yes/no, NO evidence gate
# (E1 decomposition: isolates "naming the target" from "pairing" (vs 2-AFC) and
#  from "forced evidence/localization" (vs C3). Scored paired-clean exactly like
#  C0/C3 — the clean twin gets the same named yes/no, so specificity is defined.)
# --------------------------------------------------------------------------- #
C0_NAMED_SYSTEM = (
    "You are a meticulous slide-quality inspector. You will be asked whether ONE "
    "specific named defect is present on a single slide. Look only at what is "
    "visibly rendered. Answer with a single JSON object and nothing else."
)

C0_NAMED_SCHEMA_HINT = (
    'Answer strictly as JSON: {{"present": true|false, "confidence": 0.0-1.0}}.\n'
    "Judge only this one slide — there is no reference image. Answer present=true "
    "only if the named defect is actually visible here."
)


def engine_c0_named(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    img = rec.get("image_path") or rec.get("metadata", {}).get("defective_image_path")
    if not img:
        out["failure"] = True
        return out
    question = question_for(target_defect)
    text = f"Question: {question}\n\n{C0_NAMED_SCHEMA_HINT}"
    content = [image_content_from_path(img), {"type": "text", "text": text}]
    messages = [{"role": "system", "content": C0_NAMED_SYSTEM}, {"role": "user", "content": content}]
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
    # detection == named: the target type is named in the question, but there is
    # NO forced-evidence gate (the C3 differentiator) and NO clean reference (the
    # 2-AFC differentiator).
    out["has_defect"] = present
    out["named_target"] = present
    out["confidence"] = parsed.get("confidence")
    out["predicted_types"] = [target_defect] if present else []
    return out


# --------------------------------------------------------------------------- #
# C3 — atomic per-type binary + forced localization (PresentBench-style)
# --------------------------------------------------------------------------- #
def engine_c3(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    img = rec.get("image_path") or rec.get("metadata", {}).get("defective_image_path")
    if not img:
        out["failure"] = True
        return out
    question = question_for(target_defect)
    text = f"Question: {question}\n\n{C3_SCHEMA_HINT}"
    content = [image_content_from_path(img), {"type": "text", "text": text}]
    messages = [{"role": "system", "content": C3_SYSTEM}, {"role": "user", "content": content}]
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
    locator = (parsed.get("evidence_element") or "").strip()
    region = (parsed.get("evidence_region") or "").strip()
    # Forced-evidence gate: YES only counts if it points somewhere concrete.
    has_evidence = bool(locator) and locator.lower() not in {"empty", "none", "n/a"}
    asserted = present and has_evidence
    out["has_defect"] = asserted
    out["named_target"] = asserted
    out["locator"] = {"element": locator, "region": region} if asserted else None
    out["confidence"] = parsed.get("confidence")
    out["predicted_types"] = [target_defect] if asserted else []
    return out


# --------------------------------------------------------------------------- #
# C1 / C2 — implemented in dedicated engine modules (Phase 1); imported lazily.
# --------------------------------------------------------------------------- #
def engine_c1(client, model, rec, modality, target_defect, style, max_tokens):
    from slide_examiner.elicit_freeform import run_freeform_sample
    return run_freeform_sample(
        client, model, rec, modality=modality, target_defect=target_defect,
        max_tokens=max_tokens, blank=_blank_result,
    )


def engine_c2(client, model, rec, modality, target_defect, style, max_tokens):
    from slide_examiner.elicit_pairwise import run_pairwise_sample
    return run_pairwise_sample(
        client, model, rec, target_defect=target_defect,
        max_tokens=max_tokens, blank=_blank_result,
    )


ENGINES = {"C0": engine_c0, "C0_rep": engine_c0_rep, "C0plus": engine_c0plus,
           "C0_full": engine_c0_full, "C0_named": engine_c0_named,
           "C1": engine_c1, "C2": engine_c2, "C3": engine_c3}


# --------------------------------------------------------------------------- #
# AFC / AFC_clean — two-alternative forced choice (E1 pairing decomposition)
# --------------------------------------------------------------------------- #
# The paper's "2-AFC -> 1.00" recovery (Fig 2 / Table 4) is a forced choice between
# a DEFECTIVE slide and its CLEAN twin. To split that recovery into a *pairing*
# component vs a *guess-floor* artifact (DA-C1 / R1-W2) we run, on the same items:
#   * AFC        (mode=paired): defective vs its own clean twin, both orders -> the
#                 true 2-AFC accuracy (rate the model calls the defective worse).
#   * AFC_clean  (mode=clean):  one clean slide vs a DISTINCT clean slide, both
#                 orders -> the always-pick-one / position-bias floor that inflates
#                 a forced choice when there is no real difference.
# In BOTH, "probe" = the slide presented first in order 0 (the defective for paired,
# an arbitrary clean for clean-mode). No rendering needed -> thread-safe.
_AFC_PHRASE = {
    "G1_TEXT_OVERFLOW": "text that visibly overflows or is clipped by its text box",
    "S6_IMAGE_TEXT_CONTRADICTION": "a chart, diagram, or image that contradicts the text near it",
    "G3_ALIGNMENT_OFFSET": "a bullet that does not line up with the other bullets (indented differently from the rest)",
    "G5_BRAND_COLOR_VIOLATION": "a bullet whose text colour clearly differs from the other bullets in the same list",
    "G6_MARGIN_VIOLATION": "all the content shifted to one side, with one margin crowded against the edge and the opposite side noticeably empty",
    G7_RENDER_CONTAINMENT_OVERFLOW: "content spilling outside the box, card, or frame meant to contain it",
}

AFC_SYSTEM = ("You compare two slides and decide which one, if either, shows a specific "
              "defect. Output ONLY a JSON object.")
AFC_PROMPT = ('Candidate A and Candidate B are two different slides. Which candidate '
              'shows {phrase}? If neither one does, answer "tie". '
              'Output JSON: {{"worse": "A" | "B" | "tie"}}.')


def afc_phrase(defect: str) -> str:
    if _AFC_OVERRIDE:
        return _AFC_OVERRIDE
    if defect in _AFC_PHRASE:
        return _AFC_PHRASE[defect]
    spec = DEFECTS.get(defect)
    return spec.description if spec else defect.replace("_", " ").lower()


def _img_of(rec: dict) -> str | None:
    return rec.get("image_path") or (rec.get("metadata") or {}).get("defective_image_path")


def build_afc_pairs(recs, defects, max_per_defect, mode):
    """(defect, probe_rec, partner_rec) per pair.
      mode='paired': probe = the DEFECTIVE record, partner = its clean twin (the
                     true 2-AFC; probe-worse == correct detection).
      mode='clean':  probe = a clean slide, partner = the NEXT distinct clean slide
                     in the same defect pool (rotation; no correct answer)."""
    bydef = collections.defaultdict(list)
    for r in recs:
        bydef[defect_of(r)].append(r)
    targets = defects or [d for d in bydef if d != "NO_DEFECT"]
    pairs = []
    for d in targets:
        pos = bydef.get(d, [])[:max_per_defect]
        if mode == "paired":
            for r in pos:
                clean = clean_variant(r)
                if clean and _img_of(r) and _img_of(clean):
                    pairs.append((d, r, clean))
        else:  # clean
            cleans = [c for r in pos if (c := clean_variant(r))]
            n = len(cleans)
            if n < 2:
                continue
            for i, c in enumerate(cleans):
                pairs.append((d, c, cleans[(i + 1) % n]))
    return pairs


def ask_afc(client, model, a_img, b_img, phrase, max_tokens):
    content = [image_content_from_path(a_img), image_content_from_path(b_img),
               {"type": "text", "text": AFC_PROMPT.format(phrase=phrase)}]
    messages = [{"role": "system", "content": AFC_SYSTEM}, {"role": "user", "content": content}]
    try:
        raw = chat_complete(client, model, messages, max_tokens)
        w = str(parse_examiner_json(raw).get("worse", "")).strip().lower()
    except Exception:  # noqa: BLE001 - one bad call must not abort the sweep
        return None
    return w if w in {"a", "b", "tie"} else None


def aggregate_afc(rows, defects, mode):
    """Per-defect forced-choice metrics. Each row has pick_order0 / pick_order1 in
    {a,b,tie,None}; order0 presents A=probe,B=partner and order1 swaps them, so a
    judgement names the PROBE worse iff (order0='a') or (order1='b')."""
    out = {}
    targets = defects or sorted({r["defect"] for r in rows})
    for d in targets:
        drows = [r for r in rows if r["defect"] == d]
        probe = partner = tie = first = second = 0
        n_pairs_valid = probe_both = partner_both = 0
        for r in drows:
            p0, p1 = r["pick_order0"], r["pick_order1"]
            for pos, pk in ((0, p0), (1, p1)):
                # order0: A=probe,B=partner. order1: A=partner,B=probe.
                if pk == "tie":
                    tie += 1
                elif pk == "a":            # picked the first-presented slide
                    first += 1
                    probe += 1 if pos == 0 else 0
                    partner += 1 if pos == 1 else 0
                elif pk == "b":            # picked the second-presented slide
                    second += 1
                    partner += 1 if pos == 0 else 0
                    probe += 1 if pos == 1 else 0
            if p0 in {"a", "b"} and p1 in {"a", "b"}:
                n_pairs_valid += 1
                if (p0, p1) == ("a", "b"):
                    probe_both += 1
                elif (p0, p1) == ("b", "a"):
                    partner_both += 1
        n_judg = probe + partner + tie
        if not n_judg:
            continue
        decisive = probe + partner
        cell = {
            "mode": mode, "n_pairs": len(drows), "n_judgements": n_judg,
            "decisive_rate": round(decisive / n_judg, 3),
            "tie_rate": round(tie / n_judg, 3),
            "pick_first_rate": round(first / decisive, 3) if decisive else None,  # 0.5=unbiased
            "n_pairs_both_orders_valid": n_pairs_valid,
        }
        if mode == "paired":
            # the true 2-AFC accuracy: how often the DEFECTIVE (probe) is called worse
            cell["afc_accuracy_strict"] = round(probe_both / n_pairs_valid, 3) if n_pairs_valid else None
            cell["afc_accuracy_loose"] = round(probe / n_judg, 3)
            cell["n_probe_worse_both"] = probe_both          # raw count for downstream CIs
            cell["n_probe_worse"], cell["n_partner_worse"], cell["n_tie"] = probe, partner, tie
        else:
            # purest guess-floor: a fabricated consistent winner between two clean slides
            cell["consistent_invention_rate"] = (
                round((probe_both + partner_both) / n_pairs_valid, 3) if n_pairs_valid else None)
            cell["n_consistent_invention"] = probe_both + partner_both   # raw count for downstream CIs
            cell["n_probe_worse"], cell["n_partner_worse"], cell["n_tie"] = probe, partner, tie
        out[d] = cell
    return out


def run_afc(args, client, recs, mode):
    label = "AFC" if mode == "paired" else "AFC_clean"
    pairs = build_afc_pairs(recs, args.defects, args.max_per_defect, mode)
    print(f"[{args.model}/{label}/{args.style}] {len(pairs)} {mode} pairs over "
          f"defects={args.defects} (modality A, image-only)")
    if not pairs:
        raise SystemExit(f"{label}: no pairs (need clean twins; >=2 clean slides per defect for clean mode)")

    def work(defect, probe, partner):
        phrase = afc_phrase(defect)
        ip, iq = _img_of(probe), _img_of(partner)
        reset_usage()  # both orders = 2 calls in this thread; captured together
        row = {"defect": defect, "modality": "A", "mode": mode,
               "probe_id": probe.get("sample_id"), "partner_id": partner.get("sample_id"),
               "pick_order0": ask_afc(client, args.model, ip, iq, phrase, args.max_tokens),
               "pick_order1": ask_afc(client, args.model, iq, ip, phrase, args.max_tokens)}
        row["usage"] = pop_usage()
        return row

    rows, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, *pr) for pr in pairs]
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 50 == 0 or done == len(pairs):
                print(f"  {done}/{len(pairs)} {time.time()-t0:.0f}s")

    afc = aggregate_afc(rows, args.defects, mode)
    failures = sum(1 for r in rows if not r["pick_order0"] and not r["pick_order1"])
    result = {"condition": label, "mode": mode, "model": args.model, "style": args.style,
              "manifest": args.manifest, "modalities": ["A"], "defects": args.defects,
              "n_pairs": len(pairs), "failures": failures,
              "usage": usage_summary(rows), "afc": afc}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dump_rows:
        Path(args.dump_rows).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(afc, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Job construction + run
# --------------------------------------------------------------------------- #
def _level_of(defect: str) -> str:
    return "deck" if defect in DECK_DEFECTS else "page"


def _row_key(sample_id, modality, defect, is_clean) -> str:
    """Stable identity of one probe (sample x modality x defect x pos/clean).
    Used by --resume to skip probes already present in the durable row sidecar."""
    return f"{sample_id}\t{modality}\t{defect}\t{int(bool(is_clean))}"


def build_jobs(recs, defects, modalities, max_per_defect):
    bydef = collections.defaultdict(list)
    for r in recs:
        bydef[defect_of(r)].append(r)
    jobs = []  # (rec, modality, target_defect, is_clean)
    targets = defects or [d for d in bydef if d != "NO_DEFECT"]
    for d in targets:
        pos = bydef.get(d, [])[:max_per_defect]
        cleans = [c for r in pos if (c := clean_variant(r))]
        for r in pos:
            for m in modalities:
                jobs.append((r, m, d, False))
        for c in cleans:
            for m in modalities:
                jobs.append((c, m, d, True))
    return jobs


def run(args):
    from openai import OpenAI

    # Hosted OpenAI-compatible endpoints enforce a tight per-minute quota (429 is
    # routine under any real concurrency), and thinking models can take >90s per
    # non-streaming call. Give the SDK room to ride out 429s with its built-in
    # exponential backoff (max_retries) and a longer ceiling for slow responses.
    # Both are CLI-overridable for tighter/looser endpoints.
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url,
                    timeout=args.timeout, max_retries=args.max_retries)
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    if args.freeform_only:
        # Drop template renders: the snap-to-master template absorbs ~45% of
        # injected geometry (P2 gotcha), so a "defective" template render can be
        # pixel-clean -> silent label noise. E1 holds the items fixed across all
        # conditions and must not include those (no-op on G7, which has no twins).
        # AUTHORITATIVE flag = metadata.template_condition (E8 corpora carry it);
        # path heuristics are fragile (the corpus uses a '/template/' DIRECTORY, not
        # a '__template' suffix) so fall back to them only when the field is absent.
        def _is_tmpl(r):
            tc = (r.get("metadata") or {}).get("template_condition")
            if tc is not None:
                return tc == "template"
            p = r.get("image_path") or ""
            return "__template" in p or "/template/" in p
        before = len(recs)
        recs = [r for r in recs if not _is_tmpl(r)]
        print(f"[freeform-only] kept {len(recs)}/{before} records")
    if args.condition in ("AFC", "AFC_clean"):
        # forced-choice paths: distinct scoring (pick-rate/bias), own run path.
        return run_afc(args, client, recs, mode="paired" if args.condition == "AFC" else "clean")
    engine = ENGINES[args.condition]
    if args.condition == "C0_rep":
        from functools import partial
        engine = partial(engine, rep_k=args.rep_k, rep_temp=args.rep_temp)
    jobs = build_jobs(recs, args.defects, args.modalities, args.max_per_defect)
    if args.condition == "C2":
        # Playwright sync API is not thread-safe -> batch-render the snap-twins for
        # ONLY the records actually used (dedup by slide_id), in the main thread,
        # before the pool starts.
        from slide_examiner.elicit_pairwise import prepare_twins
        seen, used = set(), []
        for rec, _m, _d, _clean in jobs:
            sid = (rec.get("slide") or {}).get("slide_id")
            if sid and sid not in seen:
                seen.add(sid)
                used.append(rec)
        prepared = prepare_twins(used)
        print(f"[C2] prepared {len(prepared)} snap-twins from {len(used)} unique IR records")
    print(f"[{args.model}/{args.condition}/{args.style}] {len(jobs)} probes "
          f"over defects={args.defects} modalities={args.modalities}")

    # --- resume: skip probes already committed to the durable row sidecar -----
    # Sidecar path is derived from --out (independent of --dump-rows) so the final
    # aggregate/dump-rows semantics stay byte-for-byte identical when --resume is off.
    rows_sidecar = Path(str(args.out) + ".rows.jsonl")
    preloaded: list[dict] = []
    if args.resume and rows_sidecar.exists():
        # Only a SUCCESSFUL probe counts as done: rows that recorded failure=True
        # (usually a 429/quota death — exactly what a resume is meant to recover)
        # are dropped here so they get re-attempted. Keyed dict also collapses any
        # duplicate success lines from earlier non-resumed runs (keep the latest).
        good_by_key: dict[str, dict] = {}
        for line in rows_sidecar.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a torn final line from a hard kill
            if r.get("failure"):
                continue
            good_by_key[_row_key(r.get("sample_id"), r.get("modality"),
                                 r.get("defect"), r.get("is_clean"))] = r
        preloaded = list(good_by_key.values())
        done_keys = set(good_by_key)
        kept = [j for j in jobs
                if _row_key(j[0].get("sample_id"), j[1], j[2], j[3]) not in done_keys]
        print(f"[resume] {len(preloaded)} good rows in sidecar; "
              f"{len(jobs) - len(kept)} probes done, {len(kept)} to (re)run")
        jobs = kept

    def work(rec, modality, target_defect, is_clean):
        reset_usage()  # per-probe token window (thread-local); read back below
        res = engine(client, args.model, rec, modality, target_defect, args.style, args.max_tokens)
        res["usage"] = pop_usage()
        res["modality"] = modality
        res["defect"] = target_defect
        res["is_clean"] = is_clean
        res["level"] = "deck" if is_deck(rec) else "page"
        return res

    rows = list(preloaded)
    t0 = time.time()
    # Under --resume, append each completed probe to the sidecar immediately (and
    # flush) so a daily-quota abort mid-sweep loses nothing: re-running the same
    # command skips everything already on disk. as_completed is drained in the main
    # thread, so a single unlocked handle is safe.
    sink = None
    if args.resume:
        rows_sidecar.parent.mkdir(parents=True, exist_ok=True)
        sink = rows_sidecar.open("a", encoding="utf-8")
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(work, *job) for job in jobs]
            done = 0
            for fut in as_completed(futs):
                row = fut.result()
                rows.append(row)
                if sink is not None:
                    sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                    sink.flush()
                done += 1
                if done % 50 == 0 or done == len(jobs):
                    print(f"  {done}/{len(jobs)} {time.time()-t0:.0f}s")
    finally:
        if sink is not None:
            sink.close()

    metrics = score(rows, args.modalities, args.defects)
    result = {
        "condition": args.condition, "model": args.model, "style": args.style,
        "manifest": args.manifest, "modalities": args.modalities,
        "defects": args.defects, "n_jobs": len(rows),
        "failures": sum(1 for r in rows if r.get("failure")),
        "usage": usage_summary(rows),
        "metrics": metrics,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dump_rows:
        Path(args.dump_rows).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Token-usage aggregation (W2 2.0) — per-condition totals for the cost table
# --------------------------------------------------------------------------- #
def usage_summary(rows) -> dict | None:
    """Aggregate per-record ``usage`` into condition-level totals and per-record
    means. Returns None if no row carries usage (old runs / mock clients) so the
    field is simply absent — backward compatible with usage-less JSON."""
    urows = [r["usage"] for r in rows if r.get("usage") and r["usage"].get("calls")]
    if not urows:
        return None
    n = len(urows)
    calls = sum(u.get("calls", 0) for u in urows)
    pt = sum(u.get("prompt_tokens", 0) for u in urows)
    ct = sum(u.get("completion_tokens", 0) for u in urows)
    rt = sum(u.get("reasoning_tokens", 0) for u in urows)
    return {
        "n_records": n, "total_calls": calls,
        "prompt_tokens": pt, "completion_tokens": ct, "reasoning_tokens": rt,
        "total_tokens": pt + ct,
        "calls_per_record": round(calls / n, 3),
        "prompt_tokens_per_record": round(pt / n, 1),
        "completion_tokens_per_record": round(ct / n, 1),
        "reasoning_tokens_per_record": round(rt / n, 1),
    }


# --------------------------------------------------------------------------- #
# Scoring — paired-clean, two levels (detection / named), with Wilson CIs
# --------------------------------------------------------------------------- #
def _cell(pos_rows, neg_rows, key):
    tp = sum(bool(r.get(key)) for r in pos_rows)
    fn = len(pos_rows) - tp
    fp = sum(bool(r.get(key)) for r in neg_rows)
    tn = len(neg_rows) - fp
    n_pos, n_neg = len(pos_rows), len(neg_rows)
    recall = tp / n_pos if n_pos else 0.0
    spec = tn / n_neg if n_neg else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    bacc = balanced_accuracy_ci(tp, n_pos, tn, n_neg)
    rec_ci = wilson_interval(tp, n_pos)
    prec_ci = wilson_interval(tp, tp + fp) if (tp + fp) else None
    return {
        "recall": round(recall, 3), "specificity": round(spec, 3),
        "bal_acc": round(bacc.estimate, 3), "bal_acc_ci": [round(bacc.low, 3), round(bacc.high, 3)],
        "precision": round(precision, 3),
        "precision_ci": [round(prec_ci.low, 3), round(prec_ci.high, 3)] if prec_ci else None,
        "fpr": round(1 - spec, 3), "f1": round(f1, 3),
        "recall_ci": [round(rec_ci.low, 3), round(rec_ci.high, 3)],
        "tp": tp, "fn": fn, "fp": fp, "tn": tn, "n_pos": n_pos, "n_neg": n_neg,
    }


def score(rows, modalities, defects):
    metrics = {}
    target_defects = defects or sorted({r["defect"] for r in rows})
    for mod in modalities:
        mrows = [r for r in rows if r["modality"] == mod and not r.get("failure")]
        per_defect = {}
        for d in target_defects:
            lvl = _level_of(d)
            pos = [r for r in mrows if not r["is_clean"] and r["defect"] == d]
            neg = [r for r in mrows if r["is_clean"] and r["defect"] == d and r["level"] == lvl]
            if not pos or not neg:
                continue
            per_defect[d] = {
                "detection": _cell(pos, neg, "has_defect"),
                "named": _cell(pos, neg, "named_target"),
                # Headline = detection universally: the C3-vs-C0 science is about
                # asserting-a-defect vs abstaining (a free-form critic that sees an
                # overflow but the cheap classifier labels it a neighbour type still
                # *detected* it). `named` is kept as a stricter secondary metric.
                "headline_level": "detection",
            }
            # C0_rep carries a second aggregation (strict majority of K draws) next
            # to the primary union in has_defect/named_target. Emit its cells too so
            # both union and majority are scored paired-clean in one run.
            if any("has_defect_maj" in r for r in pos + neg):
                per_defect[d]["detection_majority"] = _cell(pos, neg, "has_defect_maj")
                per_defect[d]["named_majority"] = _cell(pos, neg, "named_target_maj")
        metrics[mod] = {"per_defect": per_defect}
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", choices=list(ENGINES) + ["AFC", "AFC_clean"], required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--base-url", default="http://localhost:8101/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--style", choices=["trained", "scoped"], default="trained")
    ap.add_argument("--defects", nargs="+", default=None,
                    help="Defect-type strings to probe (e.g. G1_TEXT_OVERFLOW "
                         "S6_IMAGE_TEXT_CONTRADICTION G7_RENDER_CONTAINMENT_OVERFLOW).")
    ap.add_argument("--modalities", nargs="+", default=["A"])
    ap.add_argument("--max-per-defect", type=int, default=60)
    ap.add_argument("--rep-k", type=int, default=None,
                    help=f"C0_rep: number of temperature-sampled C0 draws per slide "
                         f"(default {C0_REP_DEFAULT_K} = deployed router's page-taxonomy "
                         f"atomic-question count = 9 frozen page types + G7).")
    ap.add_argument("--rep-temp", type=float, default=C0_REP_DEFAULT_TEMP,
                    help="C0_rep: sampling temperature for the repeated C0 draws.")
    ap.add_argument("--freeform-only", action="store_true",
                    help="drop __template renders (snap absorbs ~45%% of geometry; E1 freeform set).")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="per-request timeout (s); raise to 180 for slow thinking models.")
    ap.add_argument("--max-retries", type=int, default=5,
                    help="SDK retries with exponential backoff; hosted quotas make 429 routine.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-rows", default=None)
    ap.add_argument("--resume", action="store_true",
                    help="incrementally append each probe to <out>.rows.jsonl and, on "
                         "restart, skip probes already committed there (daily-quota safe).")
    ap.add_argument("--question", default=None,
                    help="override the C3/C0_named atomic question (E8 internal-contrast 口径).")
    ap.add_argument("--afc-phrase", default=None,
                    help="override the 2-AFC defect phrase (E8 internal-contrast 口径).")
    args = ap.parse_args()
    global _Q_OVERRIDE, _AFC_OVERRIDE
    _Q_OVERRIDE, _AFC_OVERRIDE = args.question, args.afc_phrase
    run(args)


if __name__ == "__main__":
    main()
