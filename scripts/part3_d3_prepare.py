#!/usr/bin/env python3
"""Freeze and materialise the W7.0-W7.2 D3 data protocol."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from slide_examiner.d3_data import (append_grouped_records, audit, build_splits, build_teacher,
                                    build_training_targets, read_jsonl, sha256_file,
                                    select_utility_on_dev, trace_cache_report, write_jsonl)

OUT = REPO / "release/part3/d3"
DATA = REPO / "data/part3/d3"
FINAL_RUNS = REPO / "runs/part3/d3_final"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def freeze() -> dict:
    files = [REPO / "data/part2/manifest.jsonl", REPO / "configs/part2_qlora_v2.yaml",
             REPO / "data/part2/sft/composition.json",
             REPO / "release/part3/manifests/manifest_g7_rendered.jsonl",
             REPO / "release/part3/w5/heldout_fidelity.json",
             REPO / "release/part3/w5/heldout_routed.json"]
    files += [REPO / f"release/part3/rows/p1e1_qwen35-27b_{kind}_{expert}_rows.csv"
              for kind in ("geo", "g7") for expert in ("C0", "C3", "AFC")]
    protocol = {"generation_seed": 2026071607, "pairs_per_image_class": 30,
            "classes": ["G1", "G2", "G3", "G5", "G6", "G7", "S1", "S4", "S6"],
            "positive_negative_ratio": "1:1 paired", "severity": "one frozen severe/recoverable level per class",
            "template_pool": "d3_split_panel_v1; disjoint generated ids/content",
            "deck_classes": ["S2", "S5"], "deck_pairs_per_class": 20,
            "fidelity_gate": ["unique twins", "nonidentical pixels", "target injection valid",
                              "clean linter no target", "parser round-trip", "source/content disjoint"],
            "primary_comparisons": ["D3_vs_vanilla_v2", "D3_vs_fixed_route", "D3_vs_single_C3"],
            "statistical_family": "9 class paired comparisons + macro; Holm correction",
            "failure_policy": "API/parser failures excluded, never mapped to negative; report rate",
            "student_access_before_freeze": False}
    protocol_sha = hashlib.sha256(json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    artifact = {
        "frozen_at": "2026-07-16T00:00:00+08:00", "tag": "d3-start-20260716",
        "baseline_commit": git("rev-list", "-n", "1", "d3-start-20260716"),
        "baseline_parent_commit": git("rev-parse", "d3-start-20260716^"),
        "tag_object": git("rev-parse", "d3-start-20260716"),
        "baseline_tree": git("rev-parse", "d3-start-20260716^{tree}"),
        "research_questions": {
            "RQ-D": "Retain C3 G7 recovery under generic single-call student inference without raising clean FPR.",
            "RQ-R": "Learned action improves macro balanced accuracy at equal or lower average call cost than fixed route/C3.",
            "RQ-F": "Route unreliable G2-G6 image-only inputs to linter/defer rather than false positives."},
        "primary_metrics": ["macro_balanced_accuracy", "paired_clean_fpr", "named_evidence_validity",
                            "correct_action_accuracy", "average_model_calls", "token_latency_cost",
                            "selective_risk_coverage"],
        "success_gates": ["generic_student_G7_gt_vanilla_v2", "G2_G6_image_only_FPR_le_vanilla_v2",
                          "accuracy_cost_pareto_noninferior", "per_class_CI_required"],
        "utility": "U=R-lambda_c*C-lambda_fp*FP+lambda_v*V",
        "utility_defaults": {"lambda_c": .05, "lambda_fp": 1.0, "lambda_v": .1, "margin_threshold": .05},
        "tie_policy": ["lower_cost", "lower_fpr", "verifiable_evidence", "low_margin_defer_or_downweight"],
        "cost_measurement_policy": "calls measured; cached CSV lacks tokens/latency, store null and exclude them from utility",
        "final_test_protocol": protocol, "protocol_sha256": protocol_sha,
        "run_provenance_required": ["parent_commit", "config_hash", "seed", "data_hash", "model_hash"],
        "hashes": {str(p.relative_to(REPO)): sha256_file(p) for p in files if p.exists()},
        "adapter": {"expected": "Part 2 v2 QLoRA adapter", "local_checkpoint_present": False,
                    "frozen_config": "configs/part2_qlora_v2.yaml"}}
    OUT.mkdir(parents=True, exist_ok=True)
    freeze_path = OUT / "freeze.json"
    if freeze_path.exists():
        previous = json.loads(freeze_path.read_text())
        for manifest in (DATA / "final_test_image.jsonl", DATA / "final_test_deck.jsonl"):
            if manifest.exists() and previous.get("protocol_sha256") not in {None, protocol_sha}:
                raise RuntimeError("final-test protocol changed after generation; refusing to overwrite freeze")
    freeze_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    return artifact


def generate_final_image(protocol_sha: str) -> Path:
    """Generate the frozen image test and run fidelity checks only (no student)."""
    from scripts.part3_e8_regen_corpus import build_heldout
    from slide_examiner.geometry import lint_slide
    from slide_examiner.schemas import Slide

    out = DATA / "final_test_image.jsonl"
    base = DATA / "final_test_image_base.jsonl"
    if not base.exists():
        build_heldout(2026071607, 30, FINAL_RUNS / "image", base, template_family="d3_split_panel_v1")
    g7 = DATA / "final_test_g7.jsonl"
    if not g7.exists():
        subprocess.check_call([sys.executable, str(REPO / "scripts/part3_build_g7.py"),
            "--per-variant", "10", "--seed", "2026071607", "--out", str(g7.relative_to(REPO)),
            "--img-dir", str((FINAL_RUNS / "g7_images").relative_to(REPO))], cwd=REPO)
    rows = read_jsonl(base) + read_jsonl(g7)
    for row in rows:
        if row["labels"][0]["type"].startswith("G7_"):
            original = row["sample_id"]
            row["sample_id"] = f"d3final_2026071607_{original}"
            row["slide"]["slide_id"] = row["sample_id"]
            if isinstance(row.get("oracle"), dict):
                row["oracle"]["slide_id"] = row["sample_id"]
        md = row.setdefault("metadata", {})
        md.update({"split": "final_test", "source_deck": row.get("slide", {}).get("slide_id"),
                   "template_id": "d3_novel_seeded", "template_family": "d3_novel_seeded",
                   "content_cluster": row.get("slide", {}).get("slide_id"),
                   "generation_seed": 2026071607, "protocol_sha256": protocol_sha,
                   "student_accessed": False})
    write_jsonl(out, rows)

    errors, pixel_pairs, clean_target_hits = [], 0, 0
    seen_ids, seen_images, seen_clean = set(), set(), set()
    for row in rows:
        sid = row["sample_id"]
        if sid in seen_ids:
            errors.append(f"duplicate sample_id:{sid}")
        seen_ids.add(sid)
        pair = row.get("pair", {})
        clean = Path(pair.get("clean_image_path", "")); defective = Path(pair.get("defective_image_path", row.get("image_path", "")))
        clean = clean if clean.is_absolute() else REPO / clean
        defective = defective if defective.is_absolute() else REPO / defective
        if not clean.exists() or not defective.exists():
            errors.append(f"missing image:{sid}")
            continue
        hashes = (sha256_file(clean), sha256_file(defective))
        if hashes[0] == hashes[1]:
            errors.append(f"identical pixels:{sid}")
        else:
            pixel_pairs += 1
        if hashes in seen_images:
            errors.append(f"duplicate pair:{sid}")
        seen_images.add(hashes)
        if hashes[0] in seen_clean:
            errors.append(f"duplicate clean image:{sid}")
        seen_clean.add(hashes[0])
        defect = row["labels"][0]["type"]
        # Linter-owned target classes must be present on the defective IR.
        if defect.split("_", 1)[0] in {"G1", "G2", "G3", "G5", "G6"}:
            defective_types = {x.type for x in lint_slide(Slide.from_mapping(row["slide"]))}
            if defect not in defective_types:
                errors.append(f"defective target lint miss:{sid}")
        # Semantic classes require explicit injected target metadata.
        elif not row.get("labels", [{}])[0].get("target_element_ids"):
            errors.append(f"missing semantic target metadata:{sid}")
        # Clean IR is the source slide for generated injections; target-class
        # findings on it would invalidate the paired control.
        clean_ir = pair.get("clean_slide_path")
        if clean_ir:
            p = Path(clean_ir); p = p if p.is_absolute() else REPO / p
            if p.exists():
                clean_types = {x.type for x in lint_slide(Slide.from_mapping(json.loads(p.read_text())))}
                if defect in clean_types:
                    clean_target_hits += 1
                    errors.append(f"clean target lint hit:{sid}")
    counts = Counter(r["labels"][0]["type"].split("_", 1)[0] for r in rows)
    expected = {k: 30 for k in ["G1", "G2", "G3", "G5", "G6", "G7", "S1", "S4", "S6"]}
    if dict(counts) != expected:
        errors.append(f"class counts:{dict(counts)}")
    required_md = {"split", "source_deck", "template_id", "content_cluster", "protocol_sha256"}
    missing_md = [r["sample_id"] for r in rows if not required_md.issubset(r.get("metadata", {}))]
    if missing_md:
        errors.append(f"metadata incomplete:{missing_md[:3]}")
    prior = read_jsonl(DATA / "split_manifest.jsonl")
    prior_sources = {r["source_deck"] for r in prior}
    prior_content = {r["content_cluster"] for r in prior}
    source_overlap = sorted({r["metadata"]["source_deck"] for r in rows} & prior_sources)
    content_overlap = sorted({r["metadata"]["content_cluster"] for r in rows} & prior_content)
    if source_overlap or content_overlap:
        errors.append("final source/content overlap")
    fidelity = {"passed": not errors, "student_invoked": False, "protocol_frozen_before_generation": True,
                "protocol_sha256": protocol_sha,
                "manifest": str(out.relative_to(REPO)), "manifest_sha256": sha256_file(out),
                "pairs": len(rows), "class_counts": dict(counts), "nonidentical_pixel_pairs": pixel_pairs,
                "clean_target_linter_hits": clean_target_hits, "metadata_missing": missing_md,
                "source_overlap": source_overlap, "content_overlap": content_overlap, "errors": errors}
    (OUT / "final_test_fidelity.json").write_text(json.dumps(fidelity, indent=2))
    if errors:
        raise RuntimeError(f"final image fidelity failed: {errors[:3]}")
    return out


def generate_final_deck(protocol_sha: str) -> Path:
    """Generate independent S2/S5 positive-clean pairs; no model evaluation."""
    from scripts.part3_e8_regen_corpus import _heldout_slides
    from slide_examiner.injection import inject_missing_logic_section, inject_narrative_order_break
    from slide_examiner.schemas import Deck, oracle_view

    slides = _heldout_slides(2026071608, 160)
    rows = []
    for class_index, (defect, injector) in enumerate([
        ("S2_NARRATIVE_ORDER_BREAK", inject_narrative_order_break),
        ("S5_MISSING_LOGIC_SECTION", lambda d: inject_missing_logic_section(d, section="validation"))]):
        for i in range(20):
            chunk = slides[(class_index * 80 + i * 4):(class_index * 80 + (i + 1) * 4)]
            sections = ("context", "method", "evidence", "validation")
            chunk = [replace(s, slide_id=f"d3deck_{class_index}_{i:02d}_{j}",
                             metadata={**s.metadata, "section": sections[j]}) for j, s in enumerate(chunk)]
            deck_id = f"d3final_{2026071608}_{class_index}_{i:02d}"
            deck = Deck(deck_id, tuple(chunk), {"required_sections": list(sections),
                        "source": "d3_final_deck", "generation_seed": 2026071608})
            injected = injector(deck)
            common = {"split": "final_test", "source_deck": deck_id, "template_id": "d3_deck_novel",
                      "content_cluster": deck_id, "generation_seed": 2026071608,
                      "protocol_sha256": protocol_sha, "student_accessed": False, "scope": "deck"}
            pair_id = f"{deck_id}_{defect}"
            rows.append({"sample_id": pair_id, "deck": injected.defective.to_dict(),
                "oracle": oracle_view(injected.defective.to_dict()), "labels": [injected.label.to_dict()],
                "pair": {"clean_deck": deck.to_dict(), "defective_deck": injected.defective.to_dict(),
                         "reference_arm": True}, "metadata": common})
            rows.append({"sample_id": f"{deck_id}_CLEAN_DECK", "deck": deck.to_dict(),
                "oracle": oracle_view(deck.to_dict()), "labels": [],
                "pair": {"paired_positive_id": pair_id, "reference_arm": True},
                "metadata": {**common, "negative_scope": "deck"}})
    out = DATA / "final_test_deck.jsonl"
    write_jsonl(out, rows)
    positives = Counter((r.get("labels") or [{"type": "NO_DEFECT"}])[0]["type"] for r in rows)
    errors = []
    if positives != Counter({"S2_NARRATIVE_ORDER_BREAK": 20, "S5_MISSING_LOGIC_SECTION": 20, "NO_DEFECT": 40}):
        errors.append(f"composition:{dict(positives)}")
    for row in rows[::2]:
        if row["pair"]["clean_deck"] == row["pair"]["defective_deck"]:
            errors.append(f"identical deck:{row['sample_id']}")
        clean, defective, defect = row["pair"]["clean_deck"], row["pair"]["defective_deck"], row["labels"][0]["type"]
        if defect.startswith("S2_"):
            clean_ids = [s["slide_id"] for s in clean["slides"]]
            defective_ids = [s["slide_id"] for s in defective["slides"]]
            if sorted(clean_ids) != sorted(defective_ids) or clean_ids == defective_ids:
                errors.append(f"invalid S2 reorder:{row['sample_id']}")
        if defect.startswith("S5_"):
            clean_sections = {s.get("metadata", {}).get("section") for s in clean["slides"]}
            defective_sections = {s.get("metadata", {}).get("section") for s in defective["slides"]}
            if "validation" not in clean_sections or "validation" in defective_sections:
                errors.append(f"invalid S5 removal:{row['sample_id']}")
    required_md = {"split", "source_deck", "template_id", "content_cluster", "protocol_sha256"}
    missing_md = [r["sample_id"] for r in rows if not required_md.issubset(r.get("metadata", {}))]
    prior = read_jsonl(DATA / "split_manifest.jsonl")
    source_overlap = sorted({r["metadata"]["source_deck"] for r in rows} & {r["source_deck"] for r in prior})
    content_overlap = sorted({r["metadata"]["content_cluster"] for r in rows} & {r["content_cluster"] for r in prior})
    if missing_md or source_overlap or content_overlap:
        errors.append("deck metadata/source/content disjointness failed")
    fidelity = {"passed": not errors, "student_invoked": False, "protocol_sha256": protocol_sha,
                "manifest": str(out.relative_to(REPO)),
                "manifest_sha256": sha256_file(out), "records": len(rows), "composition": dict(positives),
                "page_macro_included": False, "metadata_missing": missing_md,
                "source_overlap": source_overlap, "content_overlap": content_overlap, "errors": errors}
    (OUT / "final_test_deck_fidelity.json").write_text(json.dumps(fidelity, indent=2))
    if errors:
        raise RuntimeError(f"final deck fidelity failed: {errors}")
    return out


def main() -> None:
    frozen = freeze()  # Protocol is persisted before any final-test generation.
    built = build_splits(REPO / "data/part2/manifest.jsonl", REPO / "data/part3/w5_heldout.jsonl",
                         DATA, seed=2026071603)
    g7_records = read_jsonl(REPO / "release/part3/manifests/manifest_g7_rendered.jsonl")
    append_grouped_records(built, g7_records, seed=2026071603)
    write_jsonl(DATA / "split_manifest.jsonl", built["split"] + built["deck_negatives"] + built["validation"])
    write_jsonl(DATA / "availability_records.jsonl", built["availability"])
    traces = [REPO / f"release/part3/rows/p1e1_qwen35-27b_{kind}_{expert}_rows.csv"
              for kind in ("geo", "g7") for expert in ("C0", "C3")]
    traces += [REPO / "release/part3/rows/p1e1_qwen35-27b_geo_AFC_rows.csv",
               REPO / "release/part3/rows/p1e1_qwen35-27b_g7_AFC_rows.csv"]
    teacher = build_teacher(built["part2"], built["split"], traces, OUT,
                            **frozen["utility_defaults"])
    utility_selection = select_utility_on_dev(OUT / "teacher_reward_matrix.jsonl", OUT / "utility_selection.json")
    if utility_selection["selected"] != frozen["utility_defaults"]:
        teacher = build_teacher(built["part2"], built["split"], traces, OUT,
                                **utility_selection["selected"])
    build_training_targets(built["split"] + built["deck_negatives"], built["availability"],
                           read_jsonl(OUT / "d3_records.jsonl"),
                           read_jsonl(OUT / "teacher_reward_matrix.jsonl"),
                           OUT / "training_targets.jsonl")
    (OUT / "teacher_trace_cache.json").write_text(json.dumps(trace_cache_report(traces), indent=2))
    report = audit(DATA)
    shutil.copy2(DATA / "split_audit.json", OUT / "split_audit.json")
    final_image = generate_final_image(frozen["protocol_sha256"])
    final_deck = generate_final_deck(frozen["protocol_sha256"])
    inventory = {p.name: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
                 for p in sorted(OUT.glob("*")) if p.is_file() and p.name != "artifact_inventory.json"}
    inventory.update({f"data/{p.name}": {"sha256": sha256_file(p), "bytes": p.stat().st_size}
                      for p in sorted(DATA.glob("*")) if p.is_file()})
    (OUT / "artifact_inventory.json").write_text(json.dumps(inventory, indent=2))
    print(json.dumps({"freeze": frozen["baseline_commit"], "teacher": teacher,
                      "audit": report, "final_image": str(final_image), "final_deck": str(final_deck),
                      "artifacts": len(inventory)}, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
