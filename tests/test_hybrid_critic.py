"""Tests for the Part 3 Protocol-2 hybrid critic (router + linter/VLM/LLM engines).

Linter behaviour is checked against real synthetic data (deterministic, offline);
the LLM engine and the unified HybridCritic are exercised with a scripted fake
client (no server)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from slide_examiner import hybrid_critic as hc  # noqa: E402
from slide_examiner.defect_types import G7_RENDER_CONTAINMENT_OVERFLOW  # noqa: E402
from slide_examiner.taxonomy import DefectType  # noqa: E402

SYNTH = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
G7 = REPO / "data/part3/manifest_g7_rendered.jsonl"


class _FakeClient:
    """Minimal OpenAI-compatible client: responder(messages, n) -> content str."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = 0
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, *, model, messages, max_tokens, temperature=0.0, **kw):
        self.calls += 1
        content = self._responder(messages, self.calls)
        msg = type("M", (), {"content": content})
        return type("R", (), {"choices": [type("C", (), {"message": msg})]})


def _load(path):
    return [json.loads(l) for l in Path(path).open() if l.strip()]


def _by_defect(recs, d):
    return [r for r in recs if r.get("labels") and r["labels"][0]["type"] == d]


# --------------------------------------------------------------------------- #
# Router completeness
# --------------------------------------------------------------------------- #
def test_router_covers_all_classes():
    expected = {d.value for d in DefectType} | {G7_RENDER_CONTAINMENT_OVERFLOW}
    assert set(hc.ROUTER) == expected
    assert set(hc.ROUTER.values()) <= {hc.LINTER, hc.VLM, hc.LLM}
    # the render/calibration classes are the VLM's; G7 specifically
    assert hc.ROUTER[G7_RENDER_CONTAINMENT_OVERFLOW] == hc.VLM
    assert hc.VLM_ELICIT[G7_RENDER_CONTAINMENT_OVERFLOW] == "C3"


# --------------------------------------------------------------------------- #
# Linter engine — deterministic on real data
# --------------------------------------------------------------------------- #
def test_linter_blind_to_g7():
    g7 = _load(G7)[:20]
    assert g7, "G7 manifest missing"
    # by construction the geometry linter sees nothing on G7 defectives
    for r in g7:
        assert G7_RENDER_CONTAINMENT_OVERFLOW not in hc.linter_types(r)
        assert hc.linter_types(r) == set() or "G7" not in str(hc.linter_types(r))


def test_linter_detects_declared_geometry():
    syn = [r for r in _load(SYNTH) if "__template" not in (r.get("image_path") or "")]
    g5 = _by_defect(syn, "G5_BRAND_COLOR_VIOLATION")[:10]
    assert g5
    hits = sum("G5_BRAND_COLOR_VIOLATION" in hc.linter_types(r) for r in g5)
    assert hits >= 8  # G5 is the linter's strong suit (~1.0 recall)


# --------------------------------------------------------------------------- #
# LLM engine — text-only semantic probe
# --------------------------------------------------------------------------- #
def test_llm_engine_present_and_absent():
    syn = [r for r in _load(SYNTH) if "__template" not in (r.get("image_path") or "")]
    s1 = _by_defect(syn, "S1_TITLE_BODY_MISMATCH")[:1]
    assert s1 and s1[0].get("slide")
    blank = lambda rec: {"sample_id": rec.get("sample_id"), "has_defect": False,
                         "named_target": False, "predicted_types": [], "locator": None,
                         "raw": "", "failure": False}

    yes = _FakeClient(lambda m, n: json.dumps({"present": True, "evidence": "body off-topic"}))
    out = hc.llm_engine(yes, "m", s1[0], target_defect="S1_TITLE_BODY_MISMATCH",
                        max_tokens=64, blank=blank)
    assert out["named_target"] and out["predicted_types"] == ["S1_TITLE_BODY_MISMATCH"]

    no = _FakeClient(lambda m, n: json.dumps({"present": False, "evidence": ""}))
    out2 = hc.llm_engine(no, "m", s1[0], target_defect="S1_TITLE_BODY_MISMATCH",
                         max_tokens=64, blank=blank)
    assert not out2["named_target"] and out2["predicted_types"] == []


# --------------------------------------------------------------------------- #
# Unified HybridCritic — image-only degradation + routing
# --------------------------------------------------------------------------- #
def test_hybrid_image_only_skips_linter():
    """No IR -> the linter engine is not run (honest real-data degradation)."""
    crit = hc.HybridCritic(client=None, model=None, has_structure=False)
    out = crit.critique({"sample_id": "img1", "image_path": "x.png"})
    assert hc.LINTER not in out["engines_run"]
    assert out["findings"] == []
