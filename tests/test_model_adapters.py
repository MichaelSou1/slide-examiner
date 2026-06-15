from slide_examiner.model_adapters import _image_url, _openai_content


def test_image_url_converts_local_file_to_data_uri(tmp_path) -> None:
    image = tmp_path / "slide.png"
    image.write_bytes(b"png")
    uri = _image_url(str(image))
    assert uri.startswith("data:image/png;base64,")


def test_openai_content_keeps_remote_url() -> None:
    content = _openai_content({"image_path": "https://example.com/slide.png", "prompt": "Inspect."})
    assert content[0]["image_url"]["url"] == "https://example.com/slide.png"

