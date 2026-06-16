# Real Data Preparation

This guide turns the Part 1 data task from "find some decks" into a reproducible
local workflow. It intentionally does not mark full corpus acquisition complete:
large public datasets and private decks must be downloaded, licensed, and
checked by a human before empirical claims are made.

## Directory Contract

Run:

```bash
slide-examiner init-data-layout
```

The project uses:

- `data/raw/`: original downloads or desensitized source files.
- `data/ir/`: normalized Slide/Deck IR.
- `data/manifests/`: manifest JSONL files.
- `runs/rendered/`: rendered PNGs.
- `runs/probe/`: examiner/model outputs.
- `reports/`: analysis and cleaning reports.

`data/raw`, generated IR, manifests, runs, and generated reports are ignored by
git. Keep public release artifacts in a separate, reviewed bundle.

## Source Registry

List known sources:

```bash
slide-examiner data-sources
```

For public corpora, create a local source manifest when the final URL or revision
is known:

```json
{
  "pptagent_zenodo10k": {
    "purpose": "Real deck corpus for clean deck extraction and sim2real transfer.",
    "landing_page": "https://huggingface.co/datasets/Forceless/Zenodo10K",
    "download_url": "file:///mnt/datasets/Zenodo10K.zip",
    "license_note": "Pinned local mirror; record upstream revision/date before release."
  }
}
```

Then download or copy:

```bash
slide-examiner download-source pptagent_zenodo10k data/raw/zenodo10k.zip \
  --manifest data/source_manifest.local.json
```

If using Hugging Face directly, prefer `huggingface-cli download` with a pinned
revision and store the command in `reports/data_prep/source_acquisition.md`.
Zenodo10K is large, so test with a small extracted subset before full ingestion.

## Zenodo10K / PPTAgent Clean Candidates

After extracting a subset or full corpus into `data/raw/zenodo10k/`, normalize
and clean it:

```bash
slide-examiner prepare-clean-corpus pptagent_zenodo10k \
  data/raw/zenodo10k \
  data/ir/zenodo10k_clean \
  data/manifests/zenodo10k_clean_candidates.jsonl \
  --summary reports/data_prep/zenodo10k_cleaning_summary.json \
  --source-version "<pinned revision or date>" \
  --source-url "https://huggingface.co/datasets/Forceless/Zenodo10K" \
  --include-slide-samples \
  --min-slides 1
```

The cleaner currently accepts `.pptx`, project `.json` IR, and annotated `.html`.
It rejects:

- unparseable or damaged files,
- empty decks,
- decks with empty slides,
- decks whose slides trigger the current G1-G6 linter, unless
  `--allow-linter-defects` is explicitly set.

Required artifact before using the corpus in experiments:
`reports/data_prep/zenodo10k_cleaning_summary.json`.

## PPTBench Migration Data

First write a subset plan:

```bash
python -m slide_examiner.cli benchmark-plan pptbench reports/data_prep/pptbench_plan.json
```

Current disk-aware scope:

- PPTBench: detection as the primary examiner transfer subset; understanding as
  the secondary semantic transfer subset.
- Do not download SlidesBench, Slides-Align, PPTBench modification/generation,
  or full Zenodo10K for this step. They remain recorded in
  `reports/data_prep/dataset_search_2026-06-16.md` for later phases.

After downloading ModelScope `tyrionhuu/PPTBench-Detection` and
`tyrionhuu/PPTBench-Understanding`, convert Arrow shards into adapter input
JSONL and extract the embedded slide images:

```bash
python -m slide_examiner.cli convert-pptbench-arrow \
  data/raw/pptbench_detection_modelscope \
  data/raw/pptbench_detection_modelscope_adapter_input.jsonl \
  --image-dir runs/rendered/pptbench_detection_modelscope \
  --summary reports/data_prep/pptbench_detection_arrow_convert_summary.json \
  --source-version bf3310bd011bd2a4b2316646efc260243f0b95a8 \
  --task-subset detection

python -m slide_examiner.cli convert-pptbench-arrow \
  data/raw/pptbench_understanding_modelscope \
  data/raw/pptbench_understanding_modelscope_adapter_input.jsonl \
  --image-dir runs/rendered/pptbench_understanding_modelscope \
  --summary reports/data_prep/pptbench_understanding_arrow_convert_summary.json \
  --source-version d26501d5fb9a7e0daf68b3331aa14b4f1b699592 \
  --task-subset understanding
```

Then adapt those JSONL files into benchmark task manifests:

```bash
python -m slide_examiner.cli prepare-benchmark pptbench \
  data/raw/pptbench_detection_modelscope_adapter_input.jsonl \
  data/manifests/pptbench_detection_tasks.jsonl \
  --ir-dir data/ir/pptbench_detection \
  --summary reports/data_prep/pptbench_detection_adapter_summary.json \
  --source-version bf3310bd011bd2a4b2316646efc260243f0b95a8 \
  --task-subset detection

python -m slide_examiner.cli prepare-benchmark pptbench \
  data/raw/pptbench_understanding_modelscope_adapter_input.jsonl \
  data/manifests/pptbench_understanding_tasks.jsonl \
  --ir-dir data/ir/pptbench_understanding \
  --summary reports/data_prep/pptbench_understanding_adapter_summary.json \
  --source-version d26501d5fb9a7e0daf68b3331aa14b4f1b699592 \
  --task-subset understanding
```

Required artifact before claiming PPTBench migration data is ready:
`reports/data_prep/pptbench_adapter_summary.json`.

## Human Annotation Plan

Target roughly 100 real problem pages after clean-candidate extraction and manual
screening.

Use the same taxonomy as the examiner:

- Page level: G1-G6, S1, S4, S6.
- Deck level: S2, S3, S5.
- Severity: `minor`, `moderate`, `severe`.

Recommended JSONL fields for `eval/human_real_defects.jsonl`:

```json
{"sample_id":"deck_001_p0003","annotator_id":"a1","level":"page","defect_type":"G1_TEXT_OVERFLOW","severity":"moderate","target_element_ids":["title"],"evidence":"Title text extends past the right edge on page 3.","fix_suggestion":"Reduce title font size or widen the title box."}
```

Process:

1. Sample candidate pages/decks from `data/manifests/*clean_candidates.jsonl`.
2. Render images after Part 5 rendering is validated.
3. Have annotator A label all selected items.
4. Have annotator B review at least 20-30% stratified by defect type and source.
5. Resolve disagreements into a final JSONL and write
   `reports/data_prep/human_annotation_summary.json`.

Do not mark the annotation task complete until both the final labels and summary
exist.
