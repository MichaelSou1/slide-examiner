from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable

from .taxonomy import DEFECTS, GEOMETRY_DEFECTS, SEMANTIC_DEFECTS


@dataclass(frozen=True)
class AuditItem:
    name: str
    passed: bool
    detail: str


def run_code_audit() -> dict:
    checks = [
        _check_taxonomy,
        _check_module("slide_examiner.ingest", ["extract_pptx_geometry", "parse_annotated_html"]),
        _check_module("slide_examiner.data_sources", ["list_data_sources", "download_data_source"]),
        _check_module("slide_examiner.distribution", ["summarize_manifest_distribution", "summarize_linter_distribution"]),
        _check_module("slide_examiner.render", ["render_slide_html_file", "render_html_to_png", "render_pptx_to_pdf"]),
        _check_module("slide_examiner.synthetic", ["build_synthetic_manifest", "SyntheticBuildConfig"]),
        _check_module("slide_examiner.probe", ["ProbeRunner", "ProbeRunConfig"]),
        _check_module("slide_examiner.analysis", ["summarize_probe_records", "template_collapse", "variance_gates"]),
        _check_module("slide_examiner.repair", ["repair_slide", "repair_passes_linter"]),
        _check_module("slide_examiner.sft", ["export_sft_jsonl", "build_pairwise_record"]),
        _check_module("slide_examiner.model_adapters", ["QwenVLTransformersAdapter", "OpenAICompatibleAdapter", "JSONLReplayAdapter"]),
        _check_module("slide_examiner.panel", ["PanelRating", "summarize_panel_ratings"]),
        _check_module("slide_examiner.power", ["two_proportion_sample_size"]),
        _check_module("slide_examiner.training", ["TrainingConfig", "run_training"]),
        _check_module("slide_examiner.gepa_runner", ["GEPARunConfig", "run_gepa_experiment", "build_gepa_condition_plan"]),
        _check_module("slide_examiner.hacking", ["audit_slide_hacking", "audit_deck_hacking", "hacking_score"]),
        _check_module("slide_examiner.hypotheses", ["evaluate_hypotheses"]),
        _check_module("slide_examiner.orchestrator", ["run_matrix", "MatrixRunConfig"]),
        _check_module("slide_examiner.reports", ["write_analysis_report"]),
    ]
    items = [check() for check in checks]
    return {
        "passed": all(item.passed for item in items),
        "check_type": "import_surface_only",
        "items": [item.__dict__ for item in items],
        "note": (
            "This entrypoint check ONLY verifies that code entrypoints import and expose "
            "the expected symbols. It performs NO behavioral or empirical validation, and "
            "does not check correctness or completion of external empirical runs."
        ),
    }


def _check_taxonomy() -> AuditItem:
    expected = {
        "G1_TEXT_OVERFLOW",
        "G2_ELEMENT_OVERLAP",
        "G3_ALIGNMENT_OFFSET",
        "G4_FONT_SIZE_INCONSISTENCY",
        "G5_BRAND_COLOR_VIOLATION",
        "G6_MARGIN_VIOLATION",
        "S1_TITLE_BODY_MISMATCH",
        "S2_NARRATIVE_ORDER_BREAK",
        "S3_TERMINOLOGY_INCONSISTENCY",
        "S4_DENSITY_RULE_VIOLATION",
        "S5_MISSING_LOGIC_SECTION",
        "S6_IMAGE_TEXT_CONTRADICTION",
    }
    present = set(DEFECTS)
    passed = expected.issubset(present) and len(GEOMETRY_DEFECTS) == 6 and len(SEMANTIC_DEFECTS) == 6
    return AuditItem("taxonomy", passed, f"{len(present)} defects present")


def _check_module(module_name: str, names: list[str]) -> Callable[[], AuditItem]:
    def check() -> AuditItem:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            return AuditItem(module_name, False, f"import failed: {exc}")
        missing = [name for name in names if not hasattr(module, name)]
        return AuditItem(module_name, not missing, "ok" if not missing else f"missing {missing}")

    return check
