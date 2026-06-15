from slide_examiner.hacking import audit_deck_hacking, audit_slide_hacking, hacking_score
from slide_examiner.schemas import BBox, Deck, Element, Slide


def hacked_slide() -> Slide:
    return Slide(
        slide_id="hack",
        elements=(
            Element("hidden", "text", BBox(100, 100, 200, 40), text="Hidden", style={"overflow": "hidden", "font_size_pt": 4, "opacity": 0.1}),
            Element("off", "shape", BBox(3000, 100, 100, 100)),
            Element("covered", "text", BBox(300, 300, 200, 100), text="Covered"),
            Element("overlay", "shape", BBox(300, 300, 200, 100), style={"fill_color": "#ffffff"}),
        ),
        metadata={"texture_background": True, "background_color": "#ffffff"},
    )


def test_audit_slide_hacking() -> None:
    findings = audit_slide_hacking(hacked_slide())
    types = {finding.type for finding in findings}
    assert "HACK_OVERFLOW_HIDDEN" in types
    assert "HACK_TINY_TEXT" in types
    assert "HACK_INVISIBLE_TEXT" in types
    assert "HACK_OFF_CANVAS_ELEMENT" in types
    assert "HACK_TEXTURE_BACKGROUND" in types
    assert "HACK_COVERING_OVERLAY" in types
    assert hacking_score(findings) < 1.0


def test_audit_deck_hacking() -> None:
    records = audit_deck_hacking(Deck("d", (hacked_slide(),)))
    assert records[0]["slide_id"] == "hack"

