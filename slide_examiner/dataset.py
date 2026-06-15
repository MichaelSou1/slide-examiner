from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from .ingest import deck_caption, save_deck_json, save_slide_json, slide_caption
from .injection import InjectedDeck, InjectedSlide
from .io import write_jsonl
from .schemas import Deck, ManifestSample, Slide, oracle_view


def slide_sample_from_injection(
    injected: InjectedSlide,
    *,
    sample_id: str,
    output_dir: str | Path,
    template_condition: str = "freeform",
) -> ManifestSample:
    base = Path(output_dir) / sample_id
    clean_path = base / "clean_slide.json"
    defective_path = base / "defective_slide.json"
    save_slide_json(injected.clean, clean_path)
    save_slide_json(injected.defective, defective_path)
    return ManifestSample(
        sample_id=sample_id,
        slide=injected.defective,
        oracle=oracle_view(injected.defective.to_dict()),
        caption=slide_caption(injected.defective),
        labels=(injected.label,),
        pair={"clean_slide_path": str(clean_path), "defective_slide_path": str(defective_path)},
        metadata={
            "template_condition": template_condition,
            "clean_slide_path": str(clean_path),
            "defective_slide_path": str(defective_path),
        },
    )


def deck_sample_from_injection(
    injected: InjectedDeck,
    *,
    sample_id: str,
    output_dir: str | Path,
    template_condition: str = "freeform",
) -> ManifestSample:
    base = Path(output_dir) / sample_id
    clean_path = base / "clean_deck.json"
    defective_path = base / "defective_deck.json"
    save_deck_json(injected.clean, clean_path)
    save_deck_json(injected.defective, defective_path)
    return ManifestSample(
        sample_id=sample_id,
        deck=injected.defective,
        oracle=oracle_view(injected.defective.to_dict()),
        caption=deck_caption(injected.defective),
        labels=(injected.label,),
        pair={"clean_deck_path": str(clean_path), "defective_deck_path": str(defective_path)},
        metadata={
            "template_condition": template_condition,
            "clean_deck_path": str(clean_path),
            "defective_deck_path": str(defective_path),
        },
    )


def build_manifest(
    artifacts: Iterable[Slide | Deck],
    injectors: Iterable[Callable],
    *,
    output_dir: str | Path,
    template_condition: str = "freeform",
) -> list[ManifestSample]:
    samples: list[ManifestSample] = []
    for artifact_index, artifact in enumerate(artifacts):
        for injector_index, injector in enumerate(injectors):
            injected = injector(artifact)
            sample_id = f"{artifact_index:05d}_{injector_index:03d}_{injected.label.type}"
            if isinstance(injected, InjectedDeck):
                samples.append(
                    deck_sample_from_injection(
                        injected,
                        sample_id=sample_id,
                        output_dir=output_dir,
                        template_condition=template_condition,
                    )
                )
            else:
                samples.append(
                    slide_sample_from_injection(
                        injected,
                        sample_id=sample_id,
                        output_dir=output_dir,
                        template_condition=template_condition,
                    )
                )
    return samples


def write_manifest(samples: Iterable[ManifestSample], path: str | Path) -> int:
    return write_jsonl([_sample_to_dict(sample) for sample in samples], path)


def _sample_to_dict(sample: ManifestSample) -> dict:
    return {
        "sample_id": sample.sample_id,
        "slide": sample.slide.to_dict() if sample.slide else None,
        "deck": sample.deck.to_dict() if sample.deck else None,
        "image_path": sample.image_path,
        "oracle": sample.oracle,
        "caption": sample.caption,
        "labels": [label.to_dict() for label in sample.labels],
        "pair": sample.pair,
        "metadata": sample.metadata,
    }

