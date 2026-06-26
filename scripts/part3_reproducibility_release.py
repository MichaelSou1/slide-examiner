"""Build a small reproducibility bundle for Part 3 derived artifacts.

The bundle keeps only derived, releaseable artifacts:
  - paired manifests used by the headline tables;
  - per-item rollout rows behind the paired-clean McNemar tables, exported as CSV;
  - machine-readable and human-readable indices.

Weights, raw source corpora, and upstream licensed decks stay out of the bundle.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "release" / "part3"
MANIFEST_DIR = OUT_ROOT / "manifests"
ROWS_DIR = OUT_ROOT / "rows"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def short_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def csv_fields(rows: list[dict]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    priority = [k for k in ("sample_id", "defect", "modality", "is_clean", "failure") if k in fields]
    rest = [k for k in fields if k not in priority]
    return priority + rest


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = csv_fields(rows)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: short_value(row.get(k)) for k in fields})


def first_source(record: dict) -> str:
    meta = record.get("metadata") or {}
    return str(meta.get("source") or meta.get("license") or "")


def manifest_specs() -> list[dict]:
    return [
        {
            "name": "part2_eval_test_rendered",
            "path": REPO / "data/part2/manifest_eval_test_rendered.jsonl",
            "regen": "python scripts/part2_build_dataset.py",
            "seed": None,
            "deterministic": True,
            "notes": "paired-clean synthetic evaluation manifest used by the main Part 2/Part 3 tables.",
        },
        {
            "name": "part3_g7_rendered",
            "path": REPO / "data/part3/manifest_g7_rendered.jsonl",
            "regen": "python scripts/part3_build_g7.py --per-variant 30 --seed 20260620",
            "seed": 20260620,
            "deterministic": True,
            "notes": "synthetic G7 paired images with clean twins and render-containment overflow labels.",
        },
        {
            "name": "part3_real_rendered",
            "path": REPO / "data/part3/manifest_real_rendered.jsonl",
            "regen": "python scripts/part3_real_inject.py --seed 20260622",
            "seed": 20260622,
            "deterministic": True,
            "notes": "real-layout paired images from licensed decks; only derived artifacts are released here.",
        },
        {
            "name": "part3_g6_internal",
            "path": REPO / "data/part3/manifest_g6_internal.jsonl",
            "regen": "python scripts/part3_e8_make_g6_internal.py",
            "seed": None,
            "deterministic": True,
            "notes": "internal-contrast G6 corpus; deterministic through the fixed build pipeline.",
        },
        {
            "name": "part3_coverage_internal",
            "path": REPO / "data/part3/manifest_coverage_internal.jsonl",
            "regen": "python scripts/part3_e8_regen_corpus.py --target coverage",
            "seed": None,
            "deterministic": True,
            "notes": "paired clean-twin coverage corpus; deterministic through the fixed build pipeline.",
        },
    ]


def row_specs() -> list[dict]:
    return [
        {
            "name": "protocol1_rows",
            "pattern": "data/part3/p1*_rows.jsonl",
            "notes": "row-level outputs behind the paired-clean Protocol-1 / McNemar tables.",
        },
        {
            "name": "pc_real_rows",
            "pattern": "data/part3/pc_real*_rows.jsonl",
            "notes": "row-level outputs behind the real-layout A/B/C paired-clean tables.",
        },
    ]


def copy_manifests(manifest_dir: Path) -> list[dict]:
    copied = []
    for spec in manifest_specs():
        path = spec["path"]
        if not path.exists():
            continue
        dst = manifest_dir / path.name
        dst.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        rows = read_jsonl(path)
        copied.append({
            "name": spec["name"],
            "source": display_path(path),
            "copy": display_path(dst),
            "n_records": len(rows),
            "source_label": first_source(rows[0]) if rows else "",
            "regen": spec["regen"],
            "seed": spec["seed"],
            "deterministic": spec["deterministic"],
            "notes": spec["notes"],
        })
    return copied


def copy_rows(rows_dir: Path) -> list[dict]:
    copied = []
    for spec in row_specs():
        matches = sorted(REPO.glob(spec["pattern"]))
        files = []
        for path in matches:
            rows = read_jsonl(path)
            dst = rows_dir / path.with_suffix(".csv").name
            write_csv(rows, dst)
            files.append({
                "source": display_path(path),
                "copy": display_path(dst),
                "n_rows": len(rows),
            })
        copied.append({
            "name": spec["name"],
            "pattern": spec["pattern"],
            "notes": spec["notes"],
            "files": files,
            "n_files": len(files),
            "n_rows": sum(item["n_rows"] for item in files),
        })
    return copied


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_ROOT))
    args = ap.parse_args()

    out_root = REPO / args.out_dir
    manifest_dir = out_root / "manifests"
    rows_dir = out_root / "rows"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows_dir.mkdir(parents=True, exist_ok=True)

    manifests = copy_manifests(manifest_dir)
    rows = copy_rows(rows_dir)

    index = {
        "generated_from": "scripts/part3_reproducibility_release.py",
        "release_root": display_path(out_root),
        "manifests": manifests,
        "rows": rows,
    }
    (out_root / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Part 3 reproducibility release",
        "",
        "This bundle exposes derived paired-image manifests and per-item rollout CSVs.",
        "Weights, raw source corpora, and other upstream licensed items stay outside the bundle.",
        "",
    ]
    md.append("## Manifests")
    for item in manifests:
        md.append(f"- `{item['source']}` -> `{item['copy']}`")
        if item.get("seed") is not None:
            md.append(f"  - seed: `{item['seed']}`")
        md.append(f"  - regen: `{item['regen']}`")
        md.append(f"  - note: {item['notes']}")
    md.append("")
    md.append("## Row CSVs")
    for group in rows:
        md.append(f"- `{group['pattern']}` -> {group['n_files']} CSVs, {group['n_rows']} rows")
        md.append(f"  - note: {group['notes']}")
    md.append("")
    md.append("## License note")
    md.append("The withheld upstream items are licensing-constrained, not convenience-constrained.")
    md.append("Only derived artifacts are released here.")

    (out_root / "index.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(index, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
