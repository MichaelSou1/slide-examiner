"""Tests for the Part 3 Protocol-1 elicitation engines (C0/C1/C2/C3) and the G7
data + taxonomy-map artifacts. Engines are exercised with a scripted fake client
(no server); the G7 manifest's linter-blindness is checked against real data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import part3_elicit as pe  # noqa: E402
from slide_examiner import elicit_freeform, elicit_pairwise  # noqa: E402
from slide_examiner.defect_types import (  # noqa: E402
    G7_RENDER_CONTAINMENT_OVERFLOW,
    RESCUABLE_DEFECTS,
    is_extension,
)
from slide_examiner.geometry import lint_slide  # noqa: E402
from slide_examiner.schemas import Slide  # noqa: E402


# --------------------------------------------------------------------------- #
# scripted fake OpenAI-compatible client
# --------------------------------------------------------------------------- #
class _FakeClient:
    def __init__(self, responder):
        self._responder = responder
        self.calls = 0
        self.chat = self  # client.chat.completions.create

    @property
    def completions(self):
        return self

    def create(self, *, model, messages, max_tokens, temperature=0.0):
        self.calls += 1
        content = self._responder(messages, self.calls)
        msg = type("M", (), {"content": content})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


def _rec(image="x.png", slide_id=None, slide=None):
    rec = {"sample_id": slide_id or "s1", "image_path": image, "labels": []}
    if slide is not None:
        rec["slide"] = slide
    return rec


# --------------------------------------------------------------------------- #
# C3 — atomic binary + forced-evidence gate
# --------------------------------------------------------------------------- #
def test_c3_present_with_evidence():
    client = _FakeClient(lambda m, n: json.dumps(
        {"present": True, "evidence_element": "the bottom list item",
         "evidence_region": "bottom", "confidence": 0.9}))
    out = pe.engine_c3(client, "m", _rec(), "A", G7_RENDER_CONTAINMENT_OVERFLOW, "trained", 256)
    assert out["has_defect"] and out["named_target"]
    assert out["locator"]["element"] == "the bottom list item"
    assert out["predicted_types"] == [G7_RENDER_CONTAINMENT_OVERFLOW]


def test_c3_absent():
    client = _FakeClient(lambda m, n: json.dumps({"present": False, "evidence_element": ""}))
    out = pe.engine_c3(client, "m", _rec(), "A", "G1_TEXT_OVERFLOW", "trained", 256)
    assert not out["has_defect"] and not out["named_target"]


def test_c3_forced_evidence_gate_rejects_unlocated_yes():
    # present=true but no concrete evidence -> must NOT count as a detection.
    client = _FakeClient(lambda m, n: json.dumps({"present": True, "evidence_element": "empty"}))
    out = pe.engine_c3(client, "m", _rec(), "A", "G1_TEXT_OVERFLOW", "trained", 256)
    assert not out["has_defect"]


# --------------------------------------------------------------------------- #
# C1 — describe -> classify, with OTHER bucket
# --------------------------------------------------------------------------- #
def _is_stage1(messages):
    user = messages[-1]["content"]
    return isinstance(user, list)  # stage1 carries an image -> list content


def test_c1_classify_named_plus_other():
    elicit_freeform.reset_cache()

    def responder(messages, n):
        if _is_stage1(messages):
            return "The bottom bullets render below the card. Also a logo looks off-brand."
        return json.dumps({"defects": [
            {"type": G7_RENDER_CONTAINMENT_OVERFLOW, "present": True,
             "locator": "bottom of the card", "quote": "bullets render below the card"},
            {"type": "OTHER", "present": True, "locator": "logo", "quote": "off-brand logo"},
        ]})

    client = _FakeClient(responder)
    out = elicit_freeform.run_freeform_sample(
        client, "m", _rec(), modality="A", target_defect=G7_RENDER_CONTAINMENT_OVERFLOW,
        max_tokens=256, blank=pe._blank_result)
    assert out["named_target"]
    assert G7_RENDER_CONTAINMENT_OVERFLOW in out["predicted_types"]
    assert len(out["other"]) == 1 and out["other"][0]["raw_type"] == "OTHER"


def test_c1_no_problems_is_clean():
    elicit_freeform.reset_cache()
    client = _FakeClient(lambda m, n: "NO PROBLEMS")
    out = elicit_freeform.run_freeform_sample(
        client, "m", _rec(image="clean.png"), modality="A",
        target_defect="G1_TEXT_OVERFLOW", max_tokens=256, blank=pe._blank_result)
    assert not out["has_defect"] and not out["named_target"]
    assert client.calls == 1  # stage-2 skipped when stage-1 says NO PROBLEMS


def test_c1_cache_is_per_image():
    elicit_freeform.reset_cache()
    client = _FakeClient(lambda m, n: "NO PROBLEMS")
    rec = _rec()
    for _ in range(3):
        elicit_freeform.run_freeform_sample(
            client, "m", rec, modality="A", target_defect="G1_TEXT_OVERFLOW",
            max_tokens=256, blank=pe._blank_result)
    assert client.calls == 1  # one stage-1 call serves all repeated probes


# --------------------------------------------------------------------------- #
# C2 — snap-twin pairwise, both-orders agreement
# --------------------------------------------------------------------------- #
def test_c2_present_requires_both_orders(tmp_path):
    elicit_pairwise.reset_cache()
    twin = tmp_path / "twin.png"
    twin.write_bytes(b"\x89PNG\r\n")  # non-empty stub; engine only checks existence
    elicit_pairwise._twins["sid"] = str(twin)
    rec = _rec(image="orig.png", slide_id="sid", slide={"slide_id": "sid", "elements": []})

    # order0 -> "b" (orig worse), order1 -> "a" (orig worse): both agree -> present
    client = _FakeClient(lambda m, n: json.dumps({"worse": "b" if n == 1 else "a"}))
    out = elicit_pairwise.run_pairwise_sample(client, "m", rec,
                                              target_defect=G7_RENDER_CONTAINMENT_OVERFLOW,
                                              max_tokens=64, blank=pe._blank_result)
    assert out["has_defect"] and out["locator"]["orig_worse_orders"] == 2


def test_c2_tie_is_clean(tmp_path):
    elicit_pairwise.reset_cache()
    twin = tmp_path / "twin.png"
    twin.write_bytes(b"\x89PNG\r\n")
    elicit_pairwise._twins["sid"] = str(twin)
    rec = _rec(slide_id="sid", slide={"slide_id": "sid", "elements": []})
    client = _FakeClient(lambda m, n: json.dumps({"worse": "tie"}))
    out = elicit_pairwise.run_pairwise_sample(client, "m", rec,
                                              target_defect=G7_RENDER_CONTAINMENT_OVERFLOW,
                                              max_tokens=64, blank=pe._blank_result)
    assert not out["has_defect"]


def test_c2_no_twin_is_failure():
    elicit_pairwise.reset_cache()
    client = _FakeClient(lambda m, n: json.dumps({"worse": "a"}))
    out = elicit_pairwise.run_pairwise_sample(client, "m", _rec(slide_id="missing"),
                                              target_defect=G7_RENDER_CONTAINMENT_OVERFLOW,
                                              max_tokens=64, blank=pe._blank_result)
    assert out["failure"]  # no IR/twin -> C2 N/A


# --------------------------------------------------------------------------- #
# scorer — two levels, headline picks detection for the extension type
# --------------------------------------------------------------------------- #
def test_score_two_levels_and_headline():
    rows = []
    for _ in range(6):
        rows.append({"defect": G7_RENDER_CONTAINMENT_OVERFLOW, "modality": "A", "is_clean": False,
                     "level": "page", "has_defect": True, "named_target": True, "failure": False})
    for i in range(6):
        rows.append({"defect": G7_RENDER_CONTAINMENT_OVERFLOW, "modality": "A", "is_clean": True,
                     "level": "page", "has_defect": False, "named_target": False, "failure": False})
    m = pe.score(rows, ["A"], [G7_RENDER_CONTAINMENT_OVERFLOW])["A"]["per_defect"][G7_RENDER_CONTAINMENT_OVERFLOW]
    assert m["headline_level"] == "detection"
    assert m["detection"]["recall"] == 1.0 and m["detection"]["fpr"] == 0.0
    assert m["detection"]["bal_acc"] == 1.0


# --------------------------------------------------------------------------- #
# data + artifact integrity
# --------------------------------------------------------------------------- #
def test_g7_manifest_is_linter_blind():
    path = REPO / "data/part3/manifest_g7_rendered.jsonl"
    if not path.exists():
        pytest.skip("G7 manifest not built yet")
    recs = [json.loads(l) for l in path.open() if l.strip()]
    assert recs, "empty G7 manifest"
    blind = sum(1 for r in recs if not lint_slide(Slide.from_mapping(r["slide"])))
    assert blind / len(recs) >= 0.90  # the defining property of G7
    # every record is a labelled G7 with a paired clean image
    for r in recs:
        assert r["labels"][0]["type"] == G7_RENDER_CONTAINMENT_OVERFLOW
        assert r["pair"]["clean_image_path"]


def test_defect_types_registry():
    assert is_extension(G7_RENDER_CONTAINMENT_OVERFLOW)
    assert not is_extension("G1_TEXT_OVERFLOW")
    assert len(RESCUABLE_DEFECTS) == 3 and G7_RENDER_CONTAINMENT_OVERFLOW in RESCUABLE_DEFECTS


def test_taxonomy_map_bidirectional_consistency():
    data = json.loads((REPO / "data/part3/taxonomy_map.json").read_text())
    dims = set(data["slideaudit_taxonomy"])
    assert len(dims) == 19
    # every SlideAudit dim has a reverse entry
    assert set(data["slideaudit_to_ours"]) == dims
    # G7 is flagged as our extension and points at its nearest neighbour
    g7 = data["our_to_slideaudit"][G7_RENDER_CONTAINMENT_OVERFLOW]
    assert g7["relation"] == "our_extension_refines"
    assert g7["slideaudit"] == ["Content Overflow/Cut-off"]
    # forward maps reference only real SlideAudit dims
    for entry in data["our_to_slideaudit"].values():
        for dim in entry["slideaudit"]:
            assert dim in dims
