from __future__ import annotations

import json
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DataSource:
    name: str
    purpose: str
    landing_page: str
    download_url: str | None = None
    license_note: str = "Verify license and redistribution rights before publishing derived data."

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "landing_page": self.landing_page,
            "download_url": self.download_url,
            "license_note": self.license_note,
        }


DEFAULT_SOURCES: dict[str, DataSource] = {
    "pptagent_zenodo10k": DataSource(
        name="pptagent_zenodo10k",
        purpose="Real deck corpus for clean deck extraction and sim2real transfer.",
        landing_page="PPTAgent / Zenodo10K project page or paper artifact page",
    ),
    "slidesbench": DataSource(
        name="slidesbench",
        purpose="Slide generation task suite for downstream GEPA evaluation.",
        landing_page="AutoPresent / SlidesBench project page",
    ),
    "pptbench": DataSource(
        name="pptbench",
        purpose="External migration benchmark for slide detection/understanding tasks.",
        landing_page="PPTBench project page",
    ),
    "internal_desensitized": DataSource(
        name="internal_desensitized",
        purpose="Desensitized internship decks and real defect labels.",
        landing_page="Local/private storage",
    ),
}


def list_data_sources() -> list[dict[str, Any]]:
    return [source.to_dict() for source in DEFAULT_SOURCES.values()]


def load_data_source_manifest(path: str | Path) -> dict[str, DataSource]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        key: DataSource(
            name=value.get("name", key),
            purpose=value.get("purpose", ""),
            landing_page=value.get("landing_page", ""),
            download_url=value.get("download_url"),
            license_note=value.get("license_note", DataSource(key, "", "").license_note),
        )
        for key, value in data.items()
    }


def resolve_data_source(name: str, *, manifest_path: str | Path | None = None) -> DataSource:
    sources = dict(DEFAULT_SOURCES)
    if manifest_path is not None:
        sources.update(load_data_source_manifest(manifest_path))
    if name not in sources:
        raise KeyError(f"Unknown data source: {name}")
    return sources[name]


def download_data_source(
    name: str,
    output_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    url: str | None = None,
) -> Path:
    source = resolve_data_source(name, manifest_path=manifest_path)
    download_url = url or source.download_url
    if not download_url:
        raise ValueError(
            f"No download URL configured for {name}. Add one in a local data-source manifest or pass --url."
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if download_url.startswith("file://"):
        shutil.copyfile(download_url.removeprefix("file://"), output)
        return output
    with urllib.request.urlopen(download_url) as response, output.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return output

