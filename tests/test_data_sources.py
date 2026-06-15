import json

import pytest

from slide_examiner.data_sources import download_data_source, list_data_sources, resolve_data_source


def test_list_data_sources() -> None:
    sources = list_data_sources()
    assert any(source["name"] == "pptagent_zenodo10k" for source in sources)


def test_download_data_source_file_url(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("deck", encoding="utf-8")
    output = tmp_path / "out.txt"
    path = download_data_source("internal_desensitized", output, url=f"file://{source}")
    assert path.read_text(encoding="utf-8") == "deck"


def test_resolve_data_source_from_manifest(tmp_path) -> None:
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps({"custom": {"purpose": "test", "landing_page": "local", "download_url": "file:///tmp/x"}}),
        encoding="utf-8",
    )
    assert resolve_data_source("custom", manifest_path=manifest).download_url == "file:///tmp/x"


def test_download_source_without_url_errors(tmp_path) -> None:
    with pytest.raises(ValueError):
        download_data_source("pptagent_zenodo10k", tmp_path / "out")

