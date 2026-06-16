from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dataset import deck_sample_from_injection, slide_sample_from_injection, write_manifest
from .experiment import DECK_INJECTORS, SLIDE_INJECTORS, inject_deck_defect, inject_slide_defect
from .schemas import Deck, DefectLabel, ManifestSample, Slide
from .taxonomy import DEFECTS


@dataclass(frozen=True)
class SyntheticBuildConfig:
    examples_per_cell: int = 1
    template_condition: str = "freeform"
    heldout_severities: tuple[float, ...] = ()
    heldout_defect_types: tuple[str, ...] = ()
    negative_ratio: float = 0.3


def build_synthetic_manifest(
    slides: list[Slide],
    decks: list[Deck],
    *,
    output_dir: str | Path,
    manifest_path: str | Path,
    config: SyntheticBuildConfig | None = None,
) -> list[ManifestSample]:
    cfg = config or SyntheticBuildConfig()
    samples: list[ManifestSample] = []
    output = Path(output_dir)

    for defect_type, spec in DEFECTS.items():
        severities = spec.severities or (1.0,)
        for severity in severities:
            split = _split_for(defect_type, severity, cfg)
            for repetition in range(cfg.examples_per_cell):
                try:
                    if defect_type in SLIDE_INJECTORS:
                        if not slides:
                            continue
                        slide = slides[(repetition + int(float(severity) * 10)) % len(slides)]
                        injected = inject_slide_defect(slide, defect_type, severity=severity)
                        injected = _apply_template(injected, cfg)
                        sample_id = _sample_id(slide.slide_id, defect_type, severity, repetition)
                        sample = slide_sample_from_injection(
                            injected,
                            sample_id=sample_id,
                            output_dir=output,
                            template_condition=cfg.template_condition,
                        )
                    elif defect_type in DECK_INJECTORS:
                        if not decks:
                            continue
                        deck = decks[(repetition + int(float(severity) * 10)) % len(decks)]
                        injected = inject_deck_defect(deck, defect_type, severity=severity)
                        injected = _apply_template_deck(injected, cfg)
                        sample_id = _sample_id(deck.deck_id, defect_type, severity, repetition)
                        sample = deck_sample_from_injection(
                            injected,
                            sample_id=sample_id,
                            output_dir=output,
                            template_condition=cfg.template_condition,
                        )
                    else:
                        continue
                except Exception:
                    # Real-world slides may lack a suitable target for a given defect
                    # (e.g. an image-only slide for text overflow); skip that cell.
                    continue
                sample = _with_metadata(sample, split=split, severity_grid_value=severity)
                samples.append(sample)

    samples.extend(_negative_samples(slides, output, cfg, len(samples)))
    write_manifest(samples, manifest_path)
    return samples


def _negative_samples(
    slides: list[Slide],
    output: Path,
    cfg: SyntheticBuildConfig,
    positive_count: int,
) -> list[ManifestSample]:
    if not slides or cfg.negative_ratio <= 0:
        return []
    negative_count = max(1, int(positive_count * cfg.negative_ratio))
    samples = []
    for index in range(negative_count):
        slide = slides[index % len(slides)]
        label = DefectLabel("NO_DEFECT", 0.0, ())
        from .injection import InjectedSlide

        sample = slide_sample_from_injection(
            InjectedSlide(clean=slide, defective=slide, label=label),
            sample_id=f"{slide.slide_id}_NO_DEFECT_{index:04d}",
            output_dir=output,
            template_condition=cfg.template_condition,
        )
        samples.append(_with_metadata(sample, split="train", severity_grid_value=0.0))
    return samples


def _apply_template(injected, cfg: SyntheticBuildConfig):
    """Under the template condition, snap the defective slide to the master so
    geometric defects are absorbed (semantic defects survive)."""
    if cfg.template_condition != "template":
        return injected
    from dataclasses import replace
    from .template import snap_slide_to_master

    return replace(injected, defective=snap_slide_to_master(injected.defective))


def _apply_template_deck(injected, cfg: SyntheticBuildConfig):
    if cfg.template_condition != "template":
        return injected
    from dataclasses import replace
    from .template import snap_deck_to_master

    return replace(injected, defective=snap_deck_to_master(injected.defective))


def _split_for(defect_type: str, severity: float, cfg: SyntheticBuildConfig) -> str:
    if defect_type in cfg.heldout_defect_types:
        return "ood_defect"
    if severity in cfg.heldout_severities:
        return "ood_severity"
    order = list(DEFECTS).index(defect_type)
    bucket = (order + int(float(severity) * 100)) % 10
    if bucket < 7:
        return "train"
    if bucket < 9:
        return "val"
    return "test"


def _with_metadata(sample: ManifestSample, **metadata) -> ManifestSample:
    from dataclasses import replace

    return replace(sample, metadata={**sample.metadata, **metadata})


def _sample_id(prefix: str, defect_type: str, severity: float, repetition: int) -> str:
    safe_severity = str(severity).replace(".", "p")
    return f"{prefix}_{defect_type}_{safe_severity}_{repetition:04d}"

