from __future__ import annotations

from typing import Any

from .adapters import ExaminerAdapter
from .examiner_contract import (
    DeckExamRequest,
    Modality,
    PageExamRequest,
    build_deck_messages,
    build_page_messages,
    request_from_sample,
)
from .schemas import ManifestSample


def runtime_request_from_sample(sample: ManifestSample | dict[str, Any]) -> PageExamRequest | DeckExamRequest:
    return request_from_sample(sample, modality=Modality.C_BOTH)


def runtime_payload_from_sample(sample: ManifestSample | dict[str, Any]) -> dict[str, Any]:
    manifest = ManifestSample.from_mapping(sample)
    request = runtime_request_from_sample(manifest)
    if isinstance(request, DeckExamRequest):
        messages = build_deck_messages(request)
        subject_id = request.deck_id
    else:
        messages = build_page_messages(request)
        subject_id = request.page_id
    return {
        "sample_id": manifest.sample_id,
        "subject_id": subject_id,
        "level": request.level.value,
        "modality": Modality.C_BOTH.value,
        "messages": messages,
        "metadata": manifest.metadata,
    }


def examine_runtime(sample: ManifestSample | dict[str, Any], adapter: ExaminerAdapter) -> dict[str, Any]:
    return adapter.examine(runtime_payload_from_sample(sample))
