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
from slide_examiner.elicit_common import chat_complete  # noqa: E402
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
def engine_c0(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    try:
        messages = build_messages(rec, modality, style)
        raw = chat_complete(client, model, messages, max_tokens)
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


ENGINES = {"C0": engine_c0, "C0_named": engine_c0_named,
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
        return {"defect": defect, "modality": "A", "mode": mode,
                "probe_id": probe.get("sample_id"), "partner_id": partner.get("sample_id"),
                "pick_order0": ask_afc(client, args.model, ip, iq, phrase, args.max_tokens),
                "pick_order1": ask_afc(client, args.model, iq, ip, phrase, args.max_tokens)}

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
              "n_pairs": len(pairs), "failures": failures, "afc": afc}
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

    # timeout/max_retries so a crashed server makes calls FAIL FAST (caught ->
    # marked failure) instead of hanging the whole sweep indefinitely.
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url,
                    timeout=90.0, max_retries=1)
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

    def work(rec, modality, target_defect, is_clean):
        res = engine(client, args.model, rec, modality, target_defect, args.style, args.max_tokens)
        res["modality"] = modality
        res["defect"] = target_defect
        res["is_clean"] = is_clean
        res["level"] = "deck" if is_deck(rec) else "page"
        return res

    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, *job) for job in jobs]
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 50 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} {time.time()-t0:.0f}s")

    metrics = score(rows, args.modalities, args.defects)
    result = {
        "condition": args.condition, "model": args.model, "style": args.style,
        "manifest": args.manifest, "modalities": args.modalities,
        "defects": args.defects, "n_jobs": len(jobs),
        "failures": sum(1 for r in rows if r.get("failure")),
        "metrics": metrics,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dump_rows:
        Path(args.dump_rows).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Scoring — paired-clean, two levels (detection / named), with Wilson CIs
# --------------------------------------------------------------------------- #
def _cell(pos_rows, neg_rows, key):
    tp = sum(bool(r[key]) for r in pos_rows)
    fn = len(pos_rows) - tp
    fp = sum(bool(r[key]) for r in neg_rows)
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
    ap.add_argument("--freeform-only", action="store_true",
                    help="drop __template renders (snap absorbs ~45% of geometry; E1 freeform set).")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-rows", default=None)
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
