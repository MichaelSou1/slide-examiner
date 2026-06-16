from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import run_code_audit
from .analysis import summarize_probe_records
from .adapters import MockAdapter
from .data_sources import download_data_source, list_data_sources
from .data_prep import (
    CleanCorpusConfig,
    convert_pptbench_arrow_to_benchmark_input,
    ensure_data_layout,
    prepare_benchmark_tasks,
    prepare_clean_deck_corpus,
    write_benchmark_subset_plan,
)
from .distribution import summarize_linter_distribution, summarize_manifest_distribution
from .experiment import inject_artifact_to_manifest
from .gepa_runner import GEPARunConfig, write_gepa_condition_plan, write_gepa_plan
from .generator import deck_from_content_json, load_content_json, write_deck_html
from .hacking import audit_deck_hacking, audit_slide_hacking
from .hypotheses import evaluate_hypotheses
from .geometry import lint_slide
from .ingest import extract_pptx_geometry, load_deck_json, parse_annotated_html, save_deck_json, save_slide_json
from .io import read_jsonl
from .matrix import ExperimentMatrix, write_matrix_json
from .orchestrator import MatrixRunConfig, run_matrix
from .panel import summarize_panel_ratings
from .power import two_proportion_sample_size
from .probe import ProbeRunner
from .render import (
    RESOLUTION_LONG_EDGES,
    render_manifest,
    render_manifest_resolutions,
    render_pptx_to_pngs,
    render_slide_html_file,
)
from .repair import repair_slide
from .reports import write_analysis_report
from .schemas import ManifestSample, Slide
from .sft import export_llamafactory_jsonl, export_sft_jsonl_with_stats
from .synthetic import SyntheticBuildConfig, build_synthetic_manifest
from .training import TrainingConfig, run_training, write_training_config


def _cmd_lint(args: argparse.Namespace) -> int:
    slide = Slide.from_mapping(json.loads(Path(args.slide_json).read_text(encoding="utf-8")))
    labels = [label.to_dict() for label in lint_slide(slide)]
    print(json.dumps({"defects": labels}, ensure_ascii=False, indent=2))
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    samples = [ManifestSample.from_mapping(item) for item in read_jsonl(args.manifest)]
    runner = ProbeRunner(MockAdapter())
    records = runner.run_jsonl(samples, args.output)
    print(f"Wrote {len(records)} probe records to {args.output}")
    return 0


def _cmd_eval_examiner(args: argparse.Namespace) -> int:
    samples = [ManifestSample.from_mapping(item) for item in read_jsonl(args.manifest)]
    runner = ProbeRunner(MockAdapter())
    records = runner.run_jsonl(samples, args.probe_output)
    summary = summarize_probe_records(records)
    output_path = Path(args.summary_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} eval records to {args.probe_output} and summary to {args.summary_output}")
    return 0


def _cmd_build_sft(args: argparse.Namespace) -> int:
    samples = [ManifestSample.from_mapping(item) for item in read_jsonl(args.manifest)]
    stats = export_sft_jsonl_with_stats(
        samples,
        args.output,
        mode=args.mode,
        min_a_image_only_ratio=args.min_a_image_only_ratio,
        b_struct_ratio=args.b_struct_ratio,
        c_both_ratio=args.c_both_ratio,
        parse_summary_path=args.parse_summary,
    )
    print(
        f"Wrote {stats.record_count} {args.mode} SFT records to {args.output}; "
        f"modalities={stats.modality_counts}; parse_failures={stats.parse_failures}"
    )
    return 0


def _cmd_render_manifest(args: argparse.Namespace) -> int:
    target = render_manifest(
        args.manifest,
        args.output_dir,
        output_manifest=args.output_manifest,
        render_clean=not args.no_clean,
        long_edge=args.long_edge,
    )
    suffix = f" at {args.long_edge}px long edge" if args.long_edge else ""
    print(f"Rendered manifest images to {args.output_dir}{suffix} and wrote {target}")
    return 0


def _cmd_render_resolutions(args: argparse.Namespace) -> int:
    long_edges = tuple(args.long_edges) if args.long_edges else RESOLUTION_LONG_EDGES
    result = render_manifest_resolutions(
        args.manifest,
        args.output_root,
        long_edges=long_edges,
        render_clean=args.clean,
        quality_report=args.quality_report,
    )
    for long_edge in long_edges:
        summary = result["quality"].get(long_edge, {})
        print(
            f"  {long_edge}px: {summary.get('ok', 0)}/{summary.get('total', 0)} images passed quality checks "
            f"-> {result['manifests'][long_edge]}"
        )
    if args.quality_report:
        print(f"Wrote render quality report to {args.quality_report}")
    return 0


def _cmd_render_pptx(args: argparse.Namespace) -> int:
    result = render_pptx_to_pngs(args.pptx, args.output_dir, dpi=args.dpi)
    status = "ordered OK" if result.order_ok else "ORDER/COUNT MISMATCH"
    print(
        f"Rendered {result.page_count} page(s) from {args.pptx} to {args.output_dir} ({status})"
    )
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote PPTX render summary to {args.summary}")
    return 0


def _cmd_export_llamafactory(args: argparse.Namespace) -> int:
    samples = [ManifestSample.from_mapping(item) for item in read_jsonl(args.manifest)]
    count = export_llamafactory_jsonl(samples, args.output, dataset_name=args.dataset_name)
    print(f"Wrote {count} LLaMA-Factory records to {args.output} (dataset '{args.dataset_name}')")
    return 0


def _cmd_repair(args: argparse.Namespace) -> int:
    slide = Slide.from_mapping(json.loads(Path(args.slide_json).read_text(encoding="utf-8")))
    repaired = repair_slide(slide)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(repaired.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote repaired slide IR to {output}")
    return 0


def _cmd_hacking_audit(args: argparse.Namespace) -> int:
    value = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    if "slides" in value:
        findings = audit_deck_hacking(load_deck_json(args.input_json))
    else:
        findings = [finding.to_dict() for finding in audit_slide_hacking(Slide.from_mapping(value))]
    result = {"finding_count": len(findings), "findings": findings}
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote hacking audit to {output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_panel(args: argparse.Namespace) -> int:
    ratings = read_jsonl(args.ratings_jsonl)
    summary = summarize_panel_ratings(ratings, pass_threshold=args.pass_threshold)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote panel summary to {output}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_data_sources(args: argparse.Namespace) -> int:
    print(json.dumps({"sources": list_data_sources()}, ensure_ascii=False, indent=2))
    return 0


def _cmd_download_source(args: argparse.Namespace) -> int:
    output = download_data_source(args.name, args.output, manifest_path=args.manifest, url=args.url)
    print(f"Wrote data source {args.name} to {output}")
    return 0


def _cmd_init_data_layout(args: argparse.Namespace) -> int:
    layout = ensure_data_layout(args.root)
    print(json.dumps({"layout": layout}, ensure_ascii=False, indent=2))
    return 0


def _cmd_prepare_clean_corpus(args: argparse.Namespace) -> int:
    stats = prepare_clean_deck_corpus(
        CleanCorpusConfig(
            source_name=args.source_name,
            raw_path=args.raw_path,
            ir_dir=args.ir_dir,
            manifest_path=args.manifest,
            summary_path=args.summary,
            source_version=args.source_version,
            source_url=args.source_url,
            min_slides=args.min_slides,
            max_decks=args.max_decks,
            include_slide_samples=args.include_slide_samples,
            reject_empty_slides=not args.allow_empty_slides,
            require_linter_clean=not args.allow_linter_defects,
        )
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def _cmd_benchmark_plan(args: argparse.Namespace) -> int:
    plan = write_benchmark_subset_plan(
        args.source_name,
        args.output,
        source_version=args.source_version,
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _cmd_prepare_benchmark(args: argparse.Namespace) -> int:
    summary = prepare_benchmark_tasks(
        args.source_name,
        args.input,
        args.output,
        ir_dir=args.ir_dir,
        summary_path=args.summary,
        source_version=args.source_version,
        task_subset=args.task_subset,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_convert_pptbench_arrow(args: argparse.Namespace) -> int:
    summary = convert_pptbench_arrow_to_benchmark_input(
        args.input,
        args.output,
        image_dir=args.image_dir,
        summary_path=args.summary,
        source_version=args.source_version,
        task_subset=args.task_subset,
        max_records=args.max_records,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_power(args: argparse.Namespace) -> int:
    estimate = two_proportion_sample_size(
        baseline_rate=args.baseline_rate,
        target_rate=args.target_rate,
        alpha=args.alpha,
        power=args.power,
    )
    print(json.dumps(estimate.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    suffix = input_path.suffix.lower()
    if suffix == ".html":
        slide = parse_annotated_html(input_path, slide_id=args.id)
        save_slide_json(slide, args.output)
        print(f"Wrote slide IR to {args.output}")
    elif suffix == ".pptx":
        deck = extract_pptx_geometry(input_path)
        save_deck_json(deck, args.output)
        print(f"Wrote PPTX deck IR to {args.output}")
    elif suffix == ".json":
        deck = load_deck_json(input_path)
        save_deck_json(deck, args.output)
        print(f"Normalized deck IR to {args.output}")
    else:
        raise SystemExit(f"Unsupported ingest input suffix: {suffix}")
    return 0


def _cmd_render_html(args: argparse.Namespace) -> int:
    slide = Slide.from_mapping(json.loads(Path(args.slide_json).read_text(encoding="utf-8")))
    path = render_slide_html_file(slide, args.output)
    print(f"Wrote HTML render scaffold to {path}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    deck = deck_from_content_json(load_content_json(args.content_json))
    paths = write_deck_html(deck, args.output_dir)
    print(f"Wrote {len(paths)} generated slide HTML files to {args.output_dir}")
    return 0


def _cmd_inject(args: argparse.Namespace) -> int:
    sample = inject_artifact_to_manifest(
        args.input_json,
        defect_type=args.defect,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        template_condition=args.template_condition,
        severity=args.severity,
    )
    print(f"Wrote injected sample {sample.sample_id} to {args.manifest}")
    return 0


def _cmd_build_synthetic(args: argparse.Namespace) -> int:
    slides = []
    decks = []
    for path in args.inputs:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if "slides" in value:
            deck = load_deck_json(path)
            decks.append(deck)
            slides.extend(deck.slides)
        else:
            slides.append(Slide.from_mapping(value))
    config = SyntheticBuildConfig(
        examples_per_cell=args.examples_per_cell,
        template_condition=args.template_condition,
        heldout_severities=tuple(args.heldout_severity or ()),
        heldout_defect_types=tuple(args.heldout_defect or ()),
        negative_ratio=args.negative_ratio,
    )
    samples = build_synthetic_manifest(
        slides,
        decks,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        config=config,
    )
    print(f"Wrote {len(samples)} synthetic samples to {args.manifest}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    records = read_jsonl(args.probe_jsonl)
    summary = summarize_probe_records(records)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote analysis summary to {output_path}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_distribution(args: argparse.Namespace) -> int:
    records = read_jsonl(args.input_jsonl)
    if args.kind == "manifest":
        summary = summarize_manifest_distribution(records)
    else:
        summary = summarize_linter_distribution([record["slide"] if "slide" in record else record for record in records])
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote distribution summary to {output}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_hypotheses(args: argparse.Namespace) -> int:
    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    result = evaluate_hypotheses(summary)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote hypothesis gate results to {output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    path = write_analysis_report(summary, args.output)
    print(f"Wrote report to {path}")
    return 0


def _cmd_train_plan(args: argparse.Namespace) -> int:
    config = TrainingConfig(
        model_name_or_path=args.model,
        train_jsonl=args.train_jsonl,
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
    )
    if args.config:
        write_training_config(config, args.config)
    result = run_training(config, dry_run=not args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_gepa_plan(args: argparse.Namespace) -> int:
    config = GEPARunConfig(
        train_tasks=args.train_tasks,
        val_tasks=args.val_tasks,
        test_tasks=args.test_tasks,
        rollout_budget=args.rollout_budget,
        seeds=tuple(args.seeds),
        feedback_condition=args.feedback_condition,
    )
    path = write_gepa_plan(config, args.output)
    print(f"Wrote GEPA dry-run plan to {path}")
    return 0


def _cmd_gepa_conditions(args: argparse.Namespace) -> int:
    config = GEPARunConfig(
        train_tasks=args.train_tasks,
        val_tasks=args.val_tasks,
        test_tasks=args.test_tasks,
        rollout_budget=args.rollout_budget,
        seeds=tuple(args.seeds),
    )
    path = write_gepa_condition_plan(config, args.output)
    print(f"Wrote GEPA feedback-condition plan to {path}")
    return 0


def _cmd_matrix(args: argparse.Namespace) -> int:
    matrix = ExperimentMatrix()
    path = write_matrix_json(matrix, args.output)
    print(f"Wrote {len(matrix.records())} experiment cells to {path}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    result = run_code_audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


def _cmd_run_matrix(args: argparse.Namespace) -> int:
    records = run_matrix(
        args.manifest,
        args.matrix,
        args.output,
        config=MatrixRunConfig(
            adapter=args.adapter,
            model=args.model,
            replay_path=args.replay_path,
            base_url=args.base_url,
            limit=args.limit,
        ),
    )
    print(f"Wrote {len(records)} matrix probe records to {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slide-examiner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint = subparsers.add_parser("lint", help="Run geometry linter on a slide JSON file.")
    lint.add_argument("slide_json")
    lint.set_defaults(func=_cmd_lint)

    repair = subparsers.add_parser("repair", help="Apply deterministic G1-G6 geometry repairs to a slide JSON file.")
    repair.add_argument("slide_json")
    repair.add_argument("output")
    repair.set_defaults(func=_cmd_repair)

    hacking = subparsers.add_parser("hacking-audit", help="Detect reward-hacking style slide artifacts.")
    hacking.add_argument("input_json")
    hacking.add_argument("-o", "--output")
    hacking.set_defaults(func=_cmd_hacking_audit)

    panel = subparsers.add_parser("panel", help="Aggregate human/API panel ratings JSONL.")
    panel.add_argument("ratings_jsonl")
    panel.add_argument("-o", "--output")
    panel.add_argument("--pass-threshold", type=float, default=0.7)
    panel.set_defaults(func=_cmd_panel)

    audit = subparsers.add_parser(
        "audit",
        help=(
            "Check the import/entrypoint surface only: verifies expected modules import and "
            "expose named symbols. Does NOT validate correctness or any empirical claims."
        ),
    )
    audit.set_defaults(func=_cmd_audit)

    sources = subparsers.add_parser("data-sources", help="List known dataset sources and acquisition notes.")
    sources.set_defaults(func=_cmd_data_sources)

    download = subparsers.add_parser("download-source", help="Download a configured or explicit data source URL.")
    download.add_argument("name")
    download.add_argument("output")
    download.add_argument("--manifest")
    download.add_argument("--url")
    download.set_defaults(func=_cmd_download_source)

    init_layout = subparsers.add_parser("init-data-layout", help="Create the real-data directory layout.")
    init_layout.add_argument("--root", default=".")
    init_layout.set_defaults(func=_cmd_init_data_layout)

    clean_corpus = subparsers.add_parser(
        "prepare-clean-corpus",
        help="Normalize real deck files into clean-candidate IR and manifest JSONL.",
    )
    clean_corpus.add_argument("source_name")
    clean_corpus.add_argument("raw_path")
    clean_corpus.add_argument("ir_dir")
    clean_corpus.add_argument("manifest")
    clean_corpus.add_argument("--summary")
    clean_corpus.add_argument("--source-version")
    clean_corpus.add_argument("--source-url")
    clean_corpus.add_argument("--min-slides", type=int, default=1)
    clean_corpus.add_argument("--max-decks", type=int)
    clean_corpus.add_argument("--include-slide-samples", action="store_true")
    clean_corpus.add_argument("--allow-empty-slides", action="store_true")
    clean_corpus.add_argument("--allow-linter-defects", action="store_true")
    clean_corpus.set_defaults(func=_cmd_prepare_clean_corpus)

    benchmark_plan = subparsers.add_parser(
        "benchmark-plan",
        help="Write the selected SlidesBench/PPTBench migration subset plan.",
    )
    benchmark_plan.add_argument("source_name", choices=["slidesbench", "pptbench"])
    benchmark_plan.add_argument("output")
    benchmark_plan.add_argument("--source-version")
    benchmark_plan.set_defaults(func=_cmd_benchmark_plan)

    prepare_benchmark = subparsers.add_parser(
        "prepare-benchmark",
        help="Adapt SlidesBench/PPTBench-style task JSON/JSONL into project task records.",
    )
    prepare_benchmark.add_argument("source_name", choices=["slidesbench", "pptbench"])
    prepare_benchmark.add_argument("input")
    prepare_benchmark.add_argument("output")
    prepare_benchmark.add_argument("--ir-dir")
    prepare_benchmark.add_argument("--summary")
    prepare_benchmark.add_argument("--source-version")
    prepare_benchmark.add_argument("--task-subset")
    prepare_benchmark.set_defaults(func=_cmd_prepare_benchmark)

    convert_pptbench = subparsers.add_parser(
        "convert-pptbench-arrow",
        help="Convert PPTBench Arrow shards into prepare-benchmark JSONL input records.",
    )
    convert_pptbench.add_argument("input")
    convert_pptbench.add_argument("output")
    convert_pptbench.add_argument("--image-dir")
    convert_pptbench.add_argument("--summary")
    convert_pptbench.add_argument("--source-version")
    convert_pptbench.add_argument("--task-subset", choices=["detection", "understanding"])
    convert_pptbench.add_argument("--max-records", type=int)
    convert_pptbench.set_defaults(func=_cmd_convert_pptbench_arrow)

    power = subparsers.add_parser("power", help="Estimate per-group sample size for two-proportion comparisons.")
    power.add_argument("baseline_rate", type=float)
    power.add_argument("target_rate", type=float)
    power.add_argument("--alpha", type=float, default=0.05)
    power.add_argument("--power", type=float, default=0.8)
    power.set_defaults(func=_cmd_power)

    matrix = subparsers.add_parser("matrix", help="Write the pre-registered SlideProbe experiment matrix.")
    matrix.add_argument("output")
    matrix.set_defaults(func=_cmd_matrix)

    run_matrix_parser = subparsers.add_parser("run-matrix", help="Run selected experiment matrix cells.")
    run_matrix_parser.add_argument("manifest")
    run_matrix_parser.add_argument("matrix")
    run_matrix_parser.add_argument("output")
    run_matrix_parser.add_argument("--adapter", choices=["mock", "replay", "qwen-local", "openai"], default="mock")
    run_matrix_parser.add_argument("--model")
    run_matrix_parser.add_argument("--replay-path")
    run_matrix_parser.add_argument("--base-url")
    run_matrix_parser.add_argument("--limit", type=int)
    run_matrix_parser.set_defaults(func=_cmd_run_matrix)

    ingest = subparsers.add_parser("ingest", help="Convert JSON/HTML/PPTX into Slide-Examiner IR.")
    ingest.add_argument("input")
    ingest.add_argument("output")
    ingest.add_argument("--id")
    ingest.set_defaults(func=_cmd_ingest)

    render_html = subparsers.add_parser("render-html", help="Write an HTML scaffold for a slide IR.")
    render_html.add_argument("slide_json")
    render_html.add_argument("output")
    render_html.set_defaults(func=_cmd_render_html)

    render = subparsers.add_parser("render", help="Alias for render-html in the v0 local renderer.")
    render.add_argument("slide_json")
    render.add_argument("output")
    render.set_defaults(func=_cmd_render_html)

    generate = subparsers.add_parser("generate", help="Generate a deck HTML scaffold from structured content JSON.")
    generate.add_argument("content_json")
    generate.add_argument("output_dir")
    generate.set_defaults(func=_cmd_generate)

    inject = subparsers.add_parser("inject", help="Inject one spec defect and write a manifest JSONL.")
    inject.add_argument("input_json")
    inject.add_argument("defect")
    inject.add_argument("output_dir")
    inject.add_argument("manifest")
    inject.add_argument("--template-condition", default="freeform")
    inject.add_argument("--severity", type=float)
    inject.set_defaults(func=_cmd_inject)

    synthetic = subparsers.add_parser("build-synthetic", help="Build a severity-grid synthetic manifest.")
    synthetic.add_argument("output_dir")
    synthetic.add_argument("manifest")
    synthetic.add_argument("inputs", nargs="+")
    synthetic.add_argument("--examples-per-cell", type=int, default=1)
    synthetic.add_argument("--template-condition", default="freeform")
    synthetic.add_argument("--heldout-severity", type=float, action="append")
    synthetic.add_argument("--heldout-defect", action="append")
    synthetic.add_argument("--negative-ratio", type=float, default=0.3)
    synthetic.set_defaults(func=_cmd_build_synthetic)

    probe = subparsers.add_parser("probe", help="Run mock SlideProbe over a manifest JSONL file.")
    probe.add_argument("manifest")
    probe.add_argument("output")
    probe.set_defaults(func=_cmd_probe)

    eval_examiner = subparsers.add_parser("eval-examiner", help="Run mock examiner evaluation and analysis.")
    eval_examiner.add_argument("manifest")
    eval_examiner.add_argument("probe_output")
    eval_examiner.add_argument("summary_output")
    eval_examiner.set_defaults(func=_cmd_eval_examiner)

    sft = subparsers.add_parser("build-sft", help="Export QwenVL-style SFT JSONL records.")
    sft.add_argument("manifest")
    sft.add_argument("output")
    sft.add_argument("--mode", choices=["pointwise", "pairwise"], default="pointwise")
    sft.add_argument("--min-a-image-only-ratio", type=float, default=0.30)
    sft.add_argument("--b-struct-ratio", type=float, default=0.35)
    sft.add_argument("--c-both-ratio", type=float, default=0.35)
    sft.add_argument("--parse-summary", help="Write SFT assistant JSON parse summary to this JSON file.")
    sft.set_defaults(func=_cmd_build_sft)

    render_manifest_parser = subparsers.add_parser(
        "render-manifest", help="Render defective/clean slide images for a manifest and write image paths back."
    )
    render_manifest_parser.add_argument("manifest")
    render_manifest_parser.add_argument("output_dir")
    render_manifest_parser.add_argument("--output-manifest", help="Write the updated manifest here (default: in place).")
    render_manifest_parser.add_argument("--no-clean", action="store_true", help="Render only the defective image.")
    render_manifest_parser.add_argument(
        "--long-edge", type=int, default=None, help="Render at this long-edge resolution (default: native slide size)."
    )
    render_manifest_parser.set_defaults(func=_cmd_render_manifest)

    render_resolutions_parser = subparsers.add_parser(
        "render-resolutions",
        help="Render a manifest at every ablation resolution (768/1024/1536/2048) with per-resolution manifests + quality report.",
    )
    render_resolutions_parser.add_argument("manifest")
    render_resolutions_parser.add_argument("output_root")
    render_resolutions_parser.add_argument(
        "--long-edges", type=int, nargs="+", default=None, help=f"Long-edge sizes to render (default: {list(RESOLUTION_LONG_EDGES)})."
    )
    render_resolutions_parser.add_argument("--clean", action="store_true", help="Also render the clean counterpart image.")
    render_resolutions_parser.add_argument("--quality-report", help="Write a JSON render-quality report here.")
    render_resolutions_parser.set_defaults(func=_cmd_render_resolutions)

    render_pptx_parser = subparsers.add_parser(
        "render-pptx", help="Render a PPTX deck to ordered page PNGs via LibreOffice + poppler."
    )
    render_pptx_parser.add_argument("pptx")
    render_pptx_parser.add_argument("output_dir")
    render_pptx_parser.add_argument("--dpi", type=int, default=150, help="Raster DPI for page images (default: 150).")
    render_pptx_parser.add_argument("--summary", help="Write a JSON render summary here.")
    render_pptx_parser.set_defaults(func=_cmd_render_pptx)

    export_lf = subparsers.add_parser(
        "export-llamafactory", help="Export a LLaMA-Factory sharegpt+images SFT dataset (+dataset_info.json)."
    )
    export_lf.add_argument("manifest")
    export_lf.add_argument("output")
    export_lf.add_argument("--dataset-name", default="slide_examiner")
    export_lf.set_defaults(func=_cmd_export_llamafactory)

    analyze = subparsers.add_parser("analyze", help="Summarize mock or real SlideProbe JSONL records.")
    analyze.add_argument("probe_jsonl")
    analyze.add_argument("-o", "--output")
    analyze.set_defaults(func=_cmd_analyze)

    distribution = subparsers.add_parser("distribution", help="Summarize manifest or linter defect distributions.")
    distribution.add_argument("input_jsonl")
    distribution.add_argument("--kind", choices=["manifest", "slides"], default="manifest")
    distribution.add_argument("-o", "--output")
    distribution.set_defaults(func=_cmd_distribution)

    hypotheses = subparsers.add_parser("hypotheses", help="Evaluate pre-registered Go/No-Go gates from analysis summary.")
    hypotheses.add_argument("summary_json")
    hypotheses.add_argument("-o", "--output")
    hypotheses.set_defaults(func=_cmd_hypotheses)

    report = subparsers.add_parser("report", help="Render an analysis summary JSON as Markdown.")
    report.add_argument("summary_json")
    report.add_argument("output")
    report.set_defaults(func=_cmd_report)

    train = subparsers.add_parser("train-plan", help="Write or print a Qwen-VL LoRA training command.")
    train.add_argument("train_jsonl")
    train.add_argument("output_dir")
    train.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    train.add_argument("--epochs", type=float, default=1.0)
    train.add_argument("--config")
    train.add_argument("--execute", action="store_true")
    train.set_defaults(func=_cmd_train_plan)

    train_examiner = subparsers.add_parser("train-examiner", help="Alias for train-plan; use --execute to launch.")
    train_examiner.add_argument("train_jsonl")
    train_examiner.add_argument("output_dir")
    train_examiner.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    train_examiner.add_argument("--epochs", type=float, default=1.0)
    train_examiner.add_argument("--config")
    train_examiner.add_argument("--execute", action="store_true")
    train_examiner.set_defaults(func=_cmd_train_plan)

    gepa = subparsers.add_parser("gepa-plan", help="Write a GEPA dry-run rollout plan.")
    gepa.add_argument("train_tasks")
    gepa.add_argument("val_tasks")
    gepa.add_argument("test_tasks")
    gepa.add_argument("output")
    gepa.add_argument("--rollout-budget", type=int, default=200)
    gepa.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    gepa.add_argument("--feedback-condition", default="hybrid")
    gepa.set_defaults(func=_cmd_gepa_plan)

    run_gepa = subparsers.add_parser("run-gepa", help="Alias for gepa-plan; writes a dry-run plan in v0.")
    run_gepa.add_argument("train_tasks")
    run_gepa.add_argument("val_tasks")
    run_gepa.add_argument("test_tasks")
    run_gepa.add_argument("output")
    run_gepa.add_argument("--rollout-budget", type=int, default=200)
    run_gepa.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    run_gepa.add_argument("--feedback-condition", default="hybrid")
    run_gepa.set_defaults(func=_cmd_gepa_plan)

    gepa_conditions = subparsers.add_parser("gepa-conditions", help="Write all Part 3 feedback-condition dry-run plans.")
    gepa_conditions.add_argument("train_tasks")
    gepa_conditions.add_argument("val_tasks")
    gepa_conditions.add_argument("test_tasks")
    gepa_conditions.add_argument("output")
    gepa_conditions.add_argument("--rollout-budget", type=int, default=200)
    gepa_conditions.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    gepa_conditions.set_defaults(func=_cmd_gepa_conditions)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
