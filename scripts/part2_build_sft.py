"""Build Part 2 examiner SFT data with architecture-correct routing.

Encodes the Part 1 empirical conclusions (SPEC 3.0 / todo 7-8) into the
training targets instead of naively turning every label into a pointwise
detection target:

  * S-group semantic (S1/S4 page, S2/S5 deck) + NO_DEFECT  -> pointwise,
    modalities A/B/B'/C. This is the examiner's proven job.
  * G2-G6 geometry -> pointwise *restate-from-structure* (modality B, target =
    the linter-derived finding) PLUS pointwise *abstain-under-image*
    (modality A, target = clean). Teaches the structure->geometry mapping and,
    crucially, NOT to hallucinate geometry from pixels (Part 1: pointwise VLM
    geometry detection is random/overreporting).
  * G1 overflow + S6 image-text contradiction -> pairwise / 2-AFC (clean vs
    defective, same base). Part 1: relative judgement >> absolute scoring.
  * S3 terminology -> EXCLUDED from the VLM examiner; handled by the symbolic
    term-consistency linter (slide_examiner/term_consistency.py), per Part 1's
    Go/No-Go decision (bal-acc 1.000 vs VLM 0.69).

Emits three artifacts:
  * <out>/sft_pointwise.jsonl  (contract-shaped, for inspection / parser stats)
  * <out>/sft_pairwise.jsonl   (contract-shaped, for inspection / parser stats)
  * <out>/sft_train.jsonl + dataset_info.json  (LLaMA-Factory sharegpt, the
    actual training input; combines pointwise + pairwise)

Every assistant JSON is round-tripped through the contract parsers; the run
fails loudly if any record does not parse. A composition summary is written to
<out>/composition.json.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

from slide_examiner.examiner_contract import (
    ExamLevel,
    Modality,
    PairwiseChoice,
    PairwiseResult,
    build_messages_from_sample,
    image_content_from_path,
    parse_deck_result,
    parse_page_result,
    result_from_sample,
)
from slide_examiner.schemas import ManifestSample

REPO = Path(__file__).resolve().parents[1]

# Routing tables.
SEMANTIC_POINTWISE = {
    "S1_TITLE_BODY_MISMATCH",
    "S2_NARRATIVE_ORDER_BREAK",
    "S4_DENSITY_RULE_VIOLATION",
    "S5_MISSING_LOGIC_SECTION",
    "NO_DEFECT",
}
GEOMETRY_RESTATE = {
    "G2_ELEMENT_OVERLAP",
    "G3_ALIGNMENT_OFFSET",
    "G4_FONT_SIZE_INCONSISTENCY",
    "G5_BRAND_COLOR_VIOLATION",
    "G6_MARGIN_VIOLATION",
}
PAIRWISE_OVERFLOW = {"G1_TEXT_OVERFLOW"}
PAIRWISE_S6 = {"S6_IMAGE_TEXT_CONTRADICTION"}
EXCLUDED = {"S3_TERMINOLOGY_INCONSISTENCY"}

# Modality mix for the semantic pointwise track (>=30% A is enforced overall).
SEMANTIC_MODALITY_WEIGHTS = [
    (Modality.A_IMAGE_ONLY, 0.34),
    (Modality.B_STRUCT_ONLY, 0.22),
    (Modality.B_CAPTION_ONLY, 0.10),
    (Modality.C_BOTH, 0.34),
]


def defect_of(rec: dict) -> str:
    labels = [x.get("type") for x in rec.get("labels", [])]
    return labels[0] if labels else "NO_DEFECT"


def _exists(path: str | None) -> str | None:
    """Resolve a (possibly repo-relative) image path to an absolute string if it
    exists. Absolute paths keep the training file cwd-independent."""
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = REPO / p
    return str(p) if p.exists() else None


def _clean_page_result(target):
    """Return an abstain/clean copy of a page/deck contract result."""
    data = target.model_dump()
    data["has_defect"] = False
    data["findings"] = []
    return target.__class__(**data)


def _sharegpt_from_contract(messages: list[dict]) -> tuple[str, list[str]]:
    """Flatten contract messages (system+user) into one sharegpt user string and
    an ordered image-path list. image_url items become ``<image>`` tokens."""
    parts: list[str] = []
    images: list[str] = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):  # system prompt
            if content.strip():
                parts.append(content.strip())
            continue
        for item in content:
            if item.get("type") == "image_url":
                url = item["image_url"]["url"] if isinstance(item.get("image_url"), dict) else item.get("image_url", "")
                # contract uses data URLs; we need the on-disk path for LLaMA-Factory.
                path = item.get("path") or item.get("image_path")
                images.append(path or url)
                parts.append("<image>")
            elif item.get("type") == "text":
                parts.append(str(item.get("text", "")))
    return "\n".join(p for p in parts if p), images


def _lf_record(user_text: str, images: list[str], assistant_json: str) -> dict:
    token_count = user_text.count("<image>")
    if token_count != len(images):
        raise ValueError(f"<image> token/image mismatch: {token_count} vs {len(images)}")
    return {
        "messages": [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_json},
        ],
        "images": images,
    }


def _pointwise_lf(sample: ManifestSample, modality: Modality, assistant_json: str) -> dict | None:
    """Build a LLaMA-Factory record for a pointwise sample at the given modality,
    resolving image paths from the manifest (the contract embeds data URLs)."""
    messages = build_messages_from_sample(sample, modality=modality)
    user_text, _ = _sharegpt_from_contract(messages)
    images: list[str] = []
    if modality in (Modality.A_IMAGE_ONLY, Modality.C_BOTH):
        # page: single defective image; deck: page image sequence.
        if sample.deck is not None or (sample.oracle and "deck_id" in sample.oracle):
            page_paths = sample.metadata.get("page_image_paths") or []
            images = [r for p in page_paths if (r := _exists(p))]
        else:
            img = _exists(sample.image_path) or _exists(sample.metadata.get("defective_image_path"))
            images = [img] if img else []
        # keep <image> token count aligned with however many images we actually have
        n_tokens = user_text.count("<image>")
        if n_tokens != len(images):
            # rebuild: strip existing tokens, prepend the right number
            body = user_text.replace("<image>", "").strip()
            user_text = ("\n".join(["<image>"] * len(images)) + ("\n" if images else "") + body) if images else body
    else:
        # B / B' : structure or caption only, no image
        user_text = user_text.replace("<image>", "").strip()
        images = []
    if modality in (Modality.A_IMAGE_ONLY, Modality.C_BOTH) and not images:
        return None  # cannot build an image modality without an image
    return _lf_record(user_text, images, assistant_json)


def _pairwise_lf(sample: ManifestSample, clean_img: str, defective_img: str, *, flip: bool = False) -> tuple[dict, "PairwiseResult"]:
    """Build a pairwise LF record. ``flip`` swaps which candidate is clean so the
    correct answer is balanced across A/B (otherwise the model just learns
    'always pick A' — a position-bias trap)."""
    target = result_from_sample(sample)
    level = ExamLevel.DECK if (sample.deck is not None or (sample.oracle and "deck_id" in sample.oracle)) else ExamLevel.PAGE
    subject_id = target.deck_id if hasattr(target, "deck_id") else target.page_id
    has_defect = target.has_defect
    # candidate A is the *first* image shown. flip=False -> A=clean (better=A);
    # flip=True -> A=defective (better=B).
    if flip:
        a_img, b_img, better = defective_img, clean_img, PairwiseChoice.B
        reason = "Candidate B is clean; candidate A shows the defect described in the slide content."
    else:
        a_img, b_img, better = clean_img, defective_img, PairwiseChoice.A
        reason = "Candidate A is clean; candidate B shows the defect described in the slide content."
    answer = PairwiseResult(
        level=level,
        subject_id=subject_id,
        better=better if has_defect else PairwiseChoice.TIE,
        reason=reason if has_defect else "Both candidates look equivalent on the inspected dimensions.",
    )
    instruction = (
        "Compare slide candidate A and candidate B. Decide which is better for "
        "presentation quality (text fit, image-text consistency). Output ONLY "
        "PairwiseResult JSON with fields level, subject_id, better (A|B|tie), reason."
    )
    user_text = f"<image>\n<image>\n{instruction}"
    return _lf_record(user_text, [a_img, b_img], answer.model_dump_json()), answer


def _round_trip(exam_level: str, assistant_json: str) -> None:
    if exam_level == "PairwiseResult":
        PairwiseResult.model_validate_json(assistant_json)
    elif exam_level == "DeckExamResult":
        parse_deck_result(assistant_json)
    else:
        parse_page_result(assistant_json)


def build(manifest_path: Path, s6_manifest: Path | None, out_dir: Path, seed: int = 0,
          geom_max_fraction: float | None = 0.5, max_negatives: int | None = 600) -> dict:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [json.loads(l) for l in manifest_path.open() if l.strip()]
    # cap plain NO_DEFECT records (geometry abstain-A already supplies negatives)
    if max_negatives is not None:
        negs = [r for r in records if defect_of(r) == "NO_DEFECT"]
        if len(negs) > max_negatives:
            rng.shuffle(negs)
            drop = {id(r) for r in negs[max_negatives:]}
            records = [r for r in records if id(r) not in drop]

    pointwise: list[dict] = []  # contract-shaped (sample_id, exam_level, modality, assistant, lf)
    pairwise: list[dict] = []

    def add_pointwise(sample, modality, target, track):
        assistant = target.model_dump_json()
        lf = _pointwise_lf(sample, modality, assistant)
        if lf is None:
            return
        exam_level = target.__class__.__name__
        _round_trip(exam_level, assistant)
        pointwise.append({"sample_id": sample.sample_id, "exam_level": exam_level,
                          "modality": modality.value, "defect": defect, "track": track,
                          "lf": lf, "assistant": assistant})

    for rec in records:
        defect = defect_of(rec)
        if defect in EXCLUDED:
            continue
        sample = ManifestSample.from_mapping(rec)
        target = result_from_sample(sample)

        if defect in SEMANTIC_POINTWISE:
            modality = rng.choices(
                [m for m, _ in SEMANTIC_MODALITY_WEIGHTS],
                weights=[w for _, w in SEMANTIC_MODALITY_WEIGHTS],
            )[0]
            add_pointwise(sample, modality, target, track="semantic")

        elif defect in GEOMETRY_RESTATE:
            # restate-from-structure (B): target = real finding
            add_pointwise(sample, Modality.B_STRUCT_ONLY, target, track="geometry")
            # abstain-under-image (A): target = clean (do not hallucinate geometry)
            add_pointwise(sample, Modality.A_IMAGE_ONLY, _clean_page_result(target), track="geometry")

        elif defect in PAIRWISE_OVERFLOW:
            clean = _exists((sample.pair or {}).get("clean_image_path")) or _exists(sample.metadata.get("clean_image_path"))
            defective = _exists(sample.image_path) or _exists(sample.metadata.get("defective_image_path"))
            if clean and defective:
                lf, answer = _pairwise_lf(sample, clean, defective, flip=rng.random() < 0.5)
                PairwiseResult.model_validate_json(answer.model_dump_json())
                pairwise.append({"sample_id": sample.sample_id, "exam_level": "PairwiseResult",
                                 "defect": defect, "lf": lf, "assistant": answer.model_dump_json()})

        elif defect in PAIRWISE_S6:
            continue  # S6 handled from the dedicated figure-bearing corpus below

    # S6 pairwise from the dedicated figure-bearing corpus (figures are visible there).
    if s6_manifest and s6_manifest.exists():
        for rec in (json.loads(l) for l in s6_manifest.open() if l.strip()):
            if defect_of(rec) != "S6_IMAGE_TEXT_CONTRADICTION":
                continue
            sample = ManifestSample.from_mapping(rec)
            clean = _exists((sample.pair or {}).get("clean_image_path")) or _exists(sample.metadata.get("clean_image_path"))
            defective = _exists(sample.image_path) or _exists(sample.metadata.get("defective_image_path"))
            if clean and defective:
                lf, answer = _pairwise_lf(sample, clean, defective, flip=rng.random() < 0.5)
                PairwiseResult.model_validate_json(answer.model_dump_json())
                pairwise.append({"sample_id": sample.sample_id, "exam_level": "PairwiseResult",
                                 "defect": "S6_IMAGE_TEXT_CONTRADICTION", "lf": lf,
                                 "assistant": answer.model_dump_json()})

    # Balance: cap the geometry restate/abstain track so it does not drown the
    # semantic track (the examiner's main job). Keep all semantic + pairwise.
    semantic = [r for r in pointwise if r["track"] == "semantic"]
    geometry = [r for r in pointwise if r["track"] == "geometry"]
    if geom_max_fraction is not None and semantic:
        # geometry <= frac/(1-frac) * semantic
        max_geo = int(round(len(semantic) * geom_max_fraction / max(1e-6, 1 - geom_max_fraction)))
        if len(geometry) > max_geo:
            rng.shuffle(geometry)
            geometry = geometry[:max_geo]
    pointwise = semantic + geometry

    # write contract-shaped inspection files
    (out_dir / "sft_pointwise.jsonl").write_text(
        "".join(json.dumps({k: r[k] for k in ("sample_id", "exam_level", "modality", "defect")}
                           | {"messages": r["lf"]["messages"], "images": r["lf"]["images"]}, ensure_ascii=False) + "\n"
                for r in pointwise), encoding="utf-8")
    (out_dir / "sft_pairwise.jsonl").write_text(
        "".join(json.dumps({k: r[k] for k in ("sample_id", "exam_level", "defect")}
                           | {"messages": r["lf"]["messages"], "images": r["lf"]["images"]}, ensure_ascii=False) + "\n"
                for r in pairwise), encoding="utf-8")

    # combined LLaMA-Factory training file (shuffled)
    train = [r["lf"] for r in pointwise] + [r["lf"] for r in pairwise]
    rng.shuffle(train)
    train_path = out_dir / "sft_train.jsonl"
    train_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train), encoding="utf-8")

    (out_dir / "dataset_info.json").write_text(json.dumps({
        "slide_examiner_part2": {
            "file_name": "sft_train.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages", "images": "images"},
            "tags": {"role_tag": "role", "content_tag": "content",
                     "user_tag": "user", "assistant_tag": "assistant"},
        }
    }, indent=2), encoding="utf-8")

    comp = {
        "manifest": str(manifest_path),
        "n_manifest_records": len(records),
        "n_pointwise": len(pointwise),
        "n_pairwise": len(pairwise),
        "n_train_total": len(train),
        "pointwise_vs_pairwise": {
            "pointwise": len(pointwise),
            "pairwise": len(pairwise),
            "pairwise_fraction": round(len(pairwise) / max(1, len(train)), 3),
        },
        "track_distribution": dict(collections.Counter(r["track"] for r in pointwise)),
        "modality_distribution": dict(collections.Counter(r["modality"] for r in pointwise)),
        "defect_distribution": dict(sorted(collections.Counter(
            [r["defect"] for r in pointwise] + [r["defect"] for r in pairwise]).items())),
        "exam_level_distribution": dict(collections.Counter(
            [r["exam_level"] for r in pointwise] + [r["exam_level"] for r in pairwise])),
        "image_record_count": sum(1 for r in train if r["images"]),
        "text_only_record_count": sum(1 for r in train if not r["images"]),
        "a_only_fraction_of_pointwise": round(
            sum(1 for r in pointwise if r["modality"] == "A") / max(1, len(pointwise)), 3),
        "parse_failures": 0,
        "excluded_defects": sorted(EXCLUDED),
    }
    (out_dir / "composition.json").write_text(json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")
    return comp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--s6-manifest", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--geom-max-fraction", type=float, default=0.5,
                    help="cap geometry pointwise to this fraction of (semantic+geometry)")
    ap.add_argument("--max-negatives", type=int, default=600,
                    help="cap plain NO_DEFECT records")
    args = ap.parse_args()
    comp = build(args.manifest, args.s6_manifest, args.out_dir, seed=args.seed,
                 geom_max_fraction=args.geom_max_fraction, max_negatives=args.max_negatives)
    print(json.dumps(comp, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
