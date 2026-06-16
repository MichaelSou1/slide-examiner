from __future__ import annotations

import hashlib
import ast
import json
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from .dataset import write_manifest
from .geometry import lint_slide
from .ingest import (
    deck_caption,
    extract_pptx_geometry,
    load_deck_json,
    parse_annotated_html,
    save_deck_json,
    slide_caption,
)
from .io import write_jsonl
from .schemas import Deck, DefectLabel, ManifestSample, Slide, oracle_view


DATA_LAYOUT: dict[str, str] = {
    "raw": "data/raw",
    "ir": "data/ir",
    "manifests": "data/manifests",
    "rendered": "runs/rendered",
    "probe": "runs/probe",
    "reports": "reports",
    "data_prep_reports": "reports/data_prep",
}

SUPPORTED_CORPUS_SUFFIXES = frozenset({".json", ".html", ".pptx"})

BENCHMARK_SUBSETS: dict[str, list[dict[str, str]]] = {
    "slidesbench": [
        {
            "subset": "generation_tasks",
            "status": "usable_with_adapter",
            "use": "GEPA task prompts and optional reference-deck comparison.",
        },
        {
            "subset": "reference_decks",
            "status": "usable_after_ir_conversion",
            "use": "Render/reference material for downstream migration checks.",
        },
    ],
    "pptbench": [
        {
            "subset": "detection",
            "status": "primary_transfer_subset",
            "use": "RQ2 migration evaluation for defect/quality detection when labels are present.",
        },
        {
            "subset": "understanding",
            "status": "secondary_transfer_subset",
            "use": "Semantic slide understanding checks; map to S-class examiner requests when possible.",
        },
        {
            "subset": "modification",
            "status": "defer_until_generator_loop",
            "use": "Requires an edit executor, not just an examiner adapter.",
        },
        {
            "subset": "generation",
            "status": "defer_until_generator_loop",
            "use": "Better suited to Part 3 generator/GEPA evaluation than Part 1/2 examiner transfer.",
        },
    ],
}


@dataclass(frozen=True)
class CleanCorpusConfig:
    source_name: str
    raw_path: str | Path
    ir_dir: str | Path
    manifest_path: str | Path
    summary_path: str | Path | None = None
    source_version: str | None = None
    source_url: str | None = None
    min_slides: int = 1
    max_decks: int | None = None
    include_slide_samples: bool = False
    reject_empty_slides: bool = True
    require_linter_clean: bool = True


def ensure_data_layout(root: str | Path = ".") -> dict[str, str]:
    base = Path(root)
    resolved: dict[str, str] = {}
    for key, relative in DATA_LAYOUT.items():
        path = base / relative
        path.mkdir(parents=True, exist_ok=True)
        resolved[key] = str(path)
    return resolved


def prepare_clean_deck_corpus(config: CleanCorpusConfig) -> dict[str, Any]:
    raw_path = Path(config.raw_path)
    ir_dir = Path(config.ir_dir)
    manifest_path = Path(config.manifest_path)
    summary_path = Path(config.summary_path) if config.summary_path else None

    ir_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)

    stats: dict[str, Any] = {
        "source_name": config.source_name,
        "source_version": config.source_version,
        "source_url": config.source_url,
        "raw_path": str(raw_path),
        "ir_dir": str(ir_dir),
        "manifest_path": str(manifest_path),
        "criteria": {
            "min_slides": config.min_slides,
            "include_slide_samples": config.include_slide_samples,
            "reject_empty_slides": config.reject_empty_slides,
            "require_linter_clean": config.require_linter_clean,
        },
        "scanned_files": 0,
        "accepted_decks": 0,
        "accepted_slide_samples": 0,
        "rejected": Counter(),
        "errors": [],
    }
    records: list[ManifestSample] = []
    seen_ids: Counter[str] = Counter()

    for candidate in _iter_corpus_files(raw_path):
        if config.max_decks is not None and stats["accepted_decks"] >= config.max_decks:
            break
        stats["scanned_files"] += 1
        try:
            deck = _load_candidate_deck(candidate)
        except Exception as exc:  # noqa: BLE001 - data cleaning must keep scanning
            _reject(stats, candidate, "parse_error", str(exc))
            continue

        reason = _deck_reject_reason(deck, config)
        if reason is not None:
            _reject(stats, candidate, reason, None)
            continue

        deck_id = _unique_id(_safe_id(deck.deck_id or candidate.stem), seen_ids)
        deck = _with_deck_metadata(
            deck,
            deck_id=deck_id,
            source_name=config.source_name,
            source_path=candidate,
            source_version=config.source_version,
            source_url=config.source_url,
        )
        ir_path = ir_dir / f"{deck_id}.json"
        save_deck_json(deck, ir_path)

        records.append(_deck_clean_sample(deck, ir_path, config, source_path=candidate))
        stats["accepted_decks"] += 1

        if config.include_slide_samples:
            for slide_index, slide in enumerate(deck.slides, start=1):
                records.append(
                    _slide_clean_sample(
                        slide,
                        deck=deck,
                        deck_ir_path=ir_path,
                        source_path=candidate,
                        page_index=slide_index,
                        config=config,
                    )
                )
                stats["accepted_slide_samples"] += 1

    write_manifest(records, manifest_path)
    stats["manifest_records"] = len(records)
    stats["rejected"] = dict(sorted(stats["rejected"].items()))
    if summary_path:
        summary_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def write_benchmark_subset_plan(
    source_name: str,
    output_path: str | Path,
    *,
    source_version: str | None = None,
) -> dict[str, Any]:
    key = source_name.lower()
    if key not in BENCHMARK_SUBSETS:
        raise KeyError(f"Unknown benchmark source: {source_name}")
    plan = {
        "source_name": key,
        "source_version": source_version,
        "usable_subsets": BENCHMARK_SUBSETS[key],
        "adapter_contract": {
            "input": "Source task JSON/JSONL with optional embedded slide/deck IR or artifact paths.",
            "output": "JSONL task adapter records under data/manifests/.",
            "ir_conversion": "Embedded deck/slide IR and existing .pptx/.json/.html paths can be normalized.",
        },
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def prepare_benchmark_tasks(
    source_name: str,
    input_path: str | Path,
    output_jsonl: str | Path,
    *,
    ir_dir: str | Path | None = None,
    summary_path: str | Path | None = None,
    source_version: str | None = None,
    task_subset: str | None = None,
) -> dict[str, Any]:
    source_key = source_name.lower()
    records = _read_task_records(input_path)
    output = Path(output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)
    ir_base = Path(ir_dir) if ir_dir else None
    if ir_base:
        ir_base.mkdir(parents=True, exist_ok=True)

    adapted: list[dict[str, Any]] = []
    task_counts: Counter[str] = Counter()
    converted_ir = 0
    missing_artifacts = 0

    for index, record in enumerate(records):
        task_type = _task_subset(record, default=task_subset)
        task_counts[task_type] += 1
        sample_id = str(record.get("sample_id") or record.get("id") or f"{source_key}_{index:06d}")
        adapted_record = {
            "sample_id": sample_id,
            "source_name": source_key,
            "source_version": source_version,
            "task_subset": task_type,
            "task": _task_payload(record),
            "metadata": {
                "adapter_kind": "benchmark_task",
                "source_record_index": index,
            },
        }
        record_metadata = record.get("metadata")
        if isinstance(record_metadata, dict):
            adapted_record["metadata"].update(record_metadata)

        deck_or_slide = _record_artifact(record)
        if deck_or_slide is not None and ir_base is not None:
            if isinstance(deck_or_slide, Deck):
                path = ir_base / f"{_safe_id(sample_id)}_deck.json"
                save_deck_json(deck_or_slide, path)
                adapted_record["deck_ir_path"] = str(path)
            else:
                deck = Deck(deck_id=sample_id, slides=(deck_or_slide,))
                path = ir_base / f"{_safe_id(sample_id)}_deck.json"
                save_deck_json(deck, path)
                adapted_record["deck_ir_path"] = str(path)
                adapted_record["slide_id"] = deck_or_slide.slide_id
            converted_ir += 1
        elif _artifact_path(record) is not None:
            artifact = _artifact_path(record)
            adapted_record["source_artifact_path"] = artifact
            if artifact and Path(artifact).exists() and ir_base is not None:
                try:
                    deck = _load_candidate_deck(Path(artifact))
                except Exception as exc:  # noqa: BLE001
                    adapted_record["metadata"]["ir_conversion_error"] = str(exc)
                else:
                    path = ir_base / f"{_safe_id(sample_id)}_deck.json"
                    save_deck_json(deck, path)
                    adapted_record["deck_ir_path"] = str(path)
                    converted_ir += 1
            elif artifact:
                missing_artifacts += 1
                adapted_record["metadata"]["requires_artifact"] = True

        adapted.append(adapted_record)

    write_jsonl(adapted, output)
    summary = {
        "source_name": source_key,
        "source_version": source_version,
        "input_path": str(input_path),
        "output_jsonl": str(output),
        "record_count": len(adapted),
        "task_counts": dict(sorted(task_counts.items())),
        "converted_ir_count": converted_ir,
        "missing_artifact_count": missing_artifacts,
    }
    if summary_path:
        summary_output = Path(summary_path)
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def convert_pptbench_arrow_to_benchmark_input(
    input_path: str | Path,
    output_jsonl: str | Path,
    *,
    image_dir: str | Path | None = None,
    summary_path: str | Path | None = None,
    source_version: str | None = None,
    task_subset: str | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Convert PPTBench Arrow shards into prepare-benchmark JSONL records."""

    source = Path(input_path)
    output = Path(output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)
    image_base = Path(image_dir) if image_dir else None
    if image_base:
        image_base.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "source_name": "pptbench",
        "source_version": source_version,
        "input_path": str(source),
        "output_jsonl": str(output),
        "image_dir": str(image_base) if image_base else None,
        "task_subset": task_subset,
        "arrow_files": [],
        "record_count": 0,
        "image_records": 0,
        "structure_records": 0,
        "structure_parse_failures": 0,
        "task_counts": Counter(),
        "schema_fields": {},
        "errors": [],
    }

    for arrow_path in _iter_arrow_files(source):
        stats["arrow_files"].append(str(arrow_path))
        row_count = 0
        for row in _iter_arrow_rows(arrow_path):
            if max_records is not None and len(records) >= max_records:
                break
            index = len(records)
            subset = task_subset or str(row.get("category") or "unknown")
            record, record_stats = _pptbench_row_to_task_record(
                row,
                subset=subset,
                index=index,
                image_dir=image_base,
                source_arrow_path=arrow_path,
            )
            records.append(record)
            row_count += 1
            stats["task_counts"][subset] += 1
            stats["image_records"] += record_stats["image_written"]
            stats["structure_records"] += record_stats["structure_parsed"]
            stats["structure_parse_failures"] += record_stats["structure_parse_failed"]
            if record_stats.get("error") and len(stats["errors"]) < 50:
                stats["errors"].append(record_stats["error"])
        if row_count:
            stats["schema_fields"][str(arrow_path)] = list(records[-1].get("metadata", {}).get("schema_fields", ()))
        if max_records is not None and len(records) >= max_records:
            break

    write_jsonl(records, output)
    stats["record_count"] = len(records)
    stats["task_counts"] = dict(sorted(stats["task_counts"].items()))
    if summary_path:
        summary_output = Path(summary_path)
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def _iter_corpus_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_CORPUS_SUFFIXES:
            yield path
        return
    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_CORPUS_SUFFIXES:
            yield candidate


def _load_candidate_deck(path: Path) -> Deck:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_deck_json(path)
    if suffix == ".html":
        slide = parse_annotated_html(path, slide_id=path.stem)
        return Deck(deck_id=path.stem, slides=(slide,), metadata={"source_path": str(path)})
    if suffix == ".pptx":
        return extract_pptx_geometry(path)
    raise ValueError(f"Unsupported corpus suffix: {suffix}")


def _deck_reject_reason(deck: Deck, config: CleanCorpusConfig) -> str | None:
    if not deck.slides:
        return "empty_deck"
    if len(deck.slides) < config.min_slides:
        return "too_few_slides"
    if config.reject_empty_slides and any(_empty_slide(slide) for slide in deck.slides):
        return "empty_slide"
    if config.require_linter_clean and any(lint_slide(slide) for slide in deck.slides):
        return "linter_defect"
    return None


def _empty_slide(slide: Slide) -> bool:
    if not slide.elements:
        return True
    return not any(element.text.strip() or element.bbox.area > 0 for element in slide.elements)


def _reject(stats: dict[str, Any], path: Path, reason: str, detail: str | None) -> None:
    stats["rejected"][reason] += 1
    if len(stats["errors"]) < 50:
        error = {"path": str(path), "reason": reason}
        if detail:
            error["detail"] = detail
        stats["errors"].append(error)


def _with_deck_metadata(
    deck: Deck,
    *,
    deck_id: str,
    source_name: str,
    source_path: Path,
    source_version: str | None,
    source_url: str | None,
) -> Deck:
    metadata = {
        **deck.metadata,
        "source_name": source_name,
        "source_path": str(source_path),
        "source_sha256": _sha256(source_path),
        "source_version": source_version,
        "source_url": source_url,
        "data_role": "clean_candidate",
    }
    metadata = {key: value for key, value in metadata.items() if value is not None}
    return replace(deck, deck_id=deck_id, metadata=metadata)


def _deck_clean_sample(
    deck: Deck,
    ir_path: Path,
    config: CleanCorpusConfig,
    *,
    source_path: Path,
) -> ManifestSample:
    return ManifestSample(
        sample_id=f"{deck.deck_id}_deck_clean",
        deck=deck,
        oracle=oracle_view(deck.to_dict()),
        caption=deck_caption(deck),
        labels=(DefectLabel("NO_DEFECT", 0, ()),),
        metadata={
            "split": "clean_candidate",
            "source_name": config.source_name,
            "source_version": config.source_version,
            "source_path": str(source_path),
            "deck_ir_path": str(ir_path),
            "level": "deck",
        },
    )


def _slide_clean_sample(
    slide: Slide,
    *,
    deck: Deck,
    deck_ir_path: Path,
    source_path: Path,
    page_index: int,
    config: CleanCorpusConfig,
) -> ManifestSample:
    return ManifestSample(
        sample_id=f"{deck.deck_id}_p{page_index:04d}_clean",
        slide=slide,
        oracle=oracle_view(slide.to_dict()),
        caption=slide_caption(slide),
        labels=(DefectLabel("NO_DEFECT", 0, ()),),
        metadata={
            "split": "clean_candidate",
            "source_name": config.source_name,
            "source_version": config.source_version,
            "source_path": str(source_path),
            "deck_id": deck.deck_id,
            "deck_ir_path": str(deck_ir_path),
            "page_index": page_index,
            "level": "page",
        },
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return clean.strip("_") or "artifact"


def _unique_id(base: str, seen: Counter[str]) -> str:
    seen[base] += 1
    if seen[base] == 1:
        return base
    return f"{base}_{seen[base]:03d}"


def _read_task_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        records = []
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records
    value = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [dict(item) for item in value]
    if isinstance(value, dict) and isinstance(value.get("tasks"), list):
        return [dict(item) for item in value["tasks"]]
    if isinstance(value, dict):
        return [value]
    raise ValueError(f"Unsupported benchmark task format: {path}")


def _iter_arrow_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() == ".arrow":
            yield path
        return
    for candidate in sorted(path.rglob("*.arrow")):
        if candidate.is_file():
            yield candidate


def _iter_arrow_rows(path: Path) -> Iterable[dict[str, Any]]:
    try:
        import pyarrow.ipc as ipc
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Install pyarrow to convert PPTBench Arrow files.") from exc

    with path.open("rb") as handle:
        try:
            reader = ipc.open_stream(handle)
            for batch in reader:
                for row in batch.to_pylist():
                    yield dict(row)
        except Exception:
            handle.seek(0)
            reader = ipc.open_file(handle)
            for index in range(reader.num_record_batches):
                batch = reader.get_batch(index)
                for row in batch.to_pylist():
                    yield dict(row)


def _pptbench_row_to_task_record(
    row: dict[str, Any],
    *,
    subset: str,
    index: int,
    image_dir: Path | None,
    source_arrow_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row_hash = str(row.get("hash") or f"{index:06d}")
    sample_id = _safe_id(f"pptbench_{subset}_{row_hash}")
    structure_field = "json_data" if row.get("json_data") is not None else "json_content"
    structure, structure_error = _parse_pptbench_structure(row.get(structure_field))
    image_path = _write_pptbench_image(row, sample_id=sample_id, image_dir=image_dir)
    source_image_path = row.get("image_path") or _pptbench_image_source_path(row.get("image"))

    task_record: dict[str, Any] = {
        "id": sample_id,
        "task_subset": subset,
        "category": row.get("category"),
        "subcategory": row.get("subcategory"),
        "pptbench_task": row.get("task"),
        "description": row.get("description"),
        "question": row.get("question"),
        "options": _parse_json_or_literal(row.get("options")),
        "ground_truth": row.get("ground_truth"),
        "file_hash": row.get("file_hash"),
        "slide_number": row.get("slide_number"),
        "pptbench_hash": row.get("hash"),
        "image_path": str(image_path) if image_path else source_image_path,
        "source_image_path": source_image_path,
        "structure": structure,
        "metadata": {
            "source_arrow_path": str(source_arrow_path),
            "source_record_index": index,
            "schema_fields": sorted(row.keys()),
            "structure_source_field": structure_field,
        },
    }
    task_record = {key: value for key, value in task_record.items() if value is not None}

    record_stats: dict[str, Any] = {
        "image_written": int(image_path is not None),
        "structure_parsed": int(structure is not None),
        "structure_parse_failed": int(structure_error is not None),
    }
    if structure_error:
        record_stats["error"] = {
            "sample_id": sample_id,
            "source_arrow_path": str(source_arrow_path),
            "reason": "structure_parse_error",
            "detail": structure_error,
        }
    return task_record, record_stats


def _parse_pptbench_structure(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if value in (None, ""):
        return None, None
    if isinstance(value, dict):
        return value, None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError) as exc:
                return None, str(exc)
        if isinstance(parsed, dict):
            return parsed, None
        return None, f"Expected dict structure, got {type(parsed).__name__}"
    return None, f"Unsupported structure type: {type(value).__name__}"


def _parse_json_or_literal(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value


def _write_pptbench_image(row: dict[str, Any], *, sample_id: str, image_dir: Path | None) -> Path | None:
    if image_dir is None:
        return None
    image = row.get("image")
    if not isinstance(image, dict):
        return None
    data = image.get("bytes")
    if not isinstance(data, (bytes, bytearray)):
        return None
    source_path = str(row.get("image_path") or image.get("path") or "")
    suffix = Path(source_path).suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    output = image_dir / f"{sample_id}{suffix}"
    output.write_bytes(bytes(data))
    return output


def _pptbench_image_source_path(image: Any) -> str | None:
    if isinstance(image, dict) and image.get("path"):
        return str(image["path"])
    return None


def _task_subset(record: dict[str, Any], *, default: str | None = None) -> str:
    for key in ("task_subset", "subset", "task_type", "task"):
        value = record.get(key)
        if value:
            return str(value)
    return default or "unknown"


def _task_payload(record: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "deck",
        "slide",
        "slides",
        "pptx_path",
        "deck_path",
        "slide_path",
        "artifact_path",
        "source_artifact_path",
        "metadata",
    }
    return {key: value for key, value in record.items() if key not in blocked}


def _record_artifact(record: dict[str, Any]) -> Deck | Slide | None:
    if "deck" in record and isinstance(record["deck"], dict):
        return Deck.from_mapping(record["deck"])
    if "slide" in record and isinstance(record["slide"], dict):
        return Slide.from_mapping(record["slide"])
    if "slides" in record:
        return Deck.from_mapping({"deck_id": record.get("id", "benchmark_deck"), "slides": record["slides"]})
    return None


def _artifact_path(record: dict[str, Any]) -> str | None:
    for key in ("pptx_path", "deck_path", "slide_path", "artifact_path", "source_artifact_path"):
        value = record.get(key)
        if value:
            return str(value)
    return None
