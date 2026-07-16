import json
from pathlib import Path

from slide_examiner.d3_data import (AVAILABILITY, _validate_afc_trace, audit,
                                    build_splits, group_split)


def _record(sample_id: str, deck: str, defect: str, *, scope: str = "page",
            template: str = "freeform", clean_path: str | None = None) -> dict:
    obj = {"deck_id": deck, "slides": []} if scope == "deck" else {"slide_id": f"{deck}_1", "elements": []}
    return {"sample_id": sample_id, scope: obj, "labels": [{"type": defect, "severity": 1}],
            "metadata": {"template_condition": template},
            "pair": ({"clean_deck_path": clean_path, "defective_deck_path": "b"}
                     if scope == "deck" else {"clean": "a", "defective": "b"})}


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_group_split_keeps_same_deck_together():
    a = _record("a", "part2_alpha", "G1_TEXT_OVERFLOW")
    b = _record("b", "part2_alpha", "G2_ELEMENT_OVERLAP", template="template")
    assert group_split(a, 7) == group_split(b, 7)


def test_build_and_audit_double_order_availability_and_deck_negative(tmp_path):
    part2 = tmp_path / "part2.jsonl"
    w5 = tmp_path / "w5.jsonl"
    clean = tmp_path / "clean.json"
    clean.write_text('{"deck_id":"part2_beta","slides":[]}')
    defective = tmp_path / "defective.json"
    defective.write_text('{"deck_id":"part2_beta","slides":[]}')
    clean_slide = tmp_path / "clean_slide.json"
    clean_slide.write_text('{"slide_id":"part2_alpha_1","elements":[]}')
    defective_slide = tmp_path / "defective_slide.json"
    defective_slide.write_text('{"slide_id":"part2_alpha_1","elements":[]}')
    g1 = _record("g1", "part2_alpha", "G1_TEXT_OVERFLOW")
    g1["pair"] = {"clean_slide_path": str(clean_slide), "defective_slide_path": str(defective_slide)}
    rows = [g1, _record("s2", "part2_beta", "S2_NARRATIVE_ORDER_BREAK",
                        scope="deck", clean_path=str(clean))]
    rows[1]["pair"]["defective_deck_path"] = str(defective)
    _write(part2, rows)
    _write(w5, [_record("v", "w5_unique", "S4_DENSITY_RULE_VIOLATION")])
    out = tmp_path / "out"
    built = build_splits(part2, w5, out, seed=9)
    assert len(built["deck_negatives"]) == 1
    assert {r["order"] for r in built["pairwise"] if r["sample_id"] == "g1"} == {
        "clean_defective", "defective_clean"}
    assert len([r for r in built["availability"] if r["sample_id"] == "g1"]) == len(AVAILABILITY)
    report = audit(out)
    assert report["passed"]
    assert not report["duplicate_sample_ids"]
    assert built["deck_negatives"][0]["pair"]["clean_deck_sha256"]
    geometry = [r for r in built["availability"] if r["sample_id"] == "g1"]
    # G1 is reference-owned, and only reference availability can answer.
    assert {r["target_action"] for r in geometry if r["availability"] == "reference_available"} == {"ANSWER"}


def test_afc_correctness_parser_rejects_invalid_pick():
    assert _validate_afc_trace({"probe_id": "p", "partner_id": "c",
                                "pick_order0": "a", "pick_order1": "b"}) == (True, None)
    assert not _validate_afc_trace({"probe_id": "p", "partner_id": "c",
                                    "pick_order0": "left", "pick_order1": "b"})[0]
