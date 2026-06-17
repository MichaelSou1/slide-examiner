from slide_examiner.schemas import BBox, Deck, Element, Slide
from slide_examiner.term_consistency import (
    build_term_occurrences,
    detect_terminology_inconsistency,
    extract_terms,
    lint_deck,
)


def _slide(sid: str, text: str) -> Slide:
    return Slide(slide_id=sid, elements=(
        Element(element_id=f"{sid}_b0", type="text", bbox=BBox(10, 10, 400, 60), text=text),
    ))


def _deck(*texts: str) -> Deck:
    return Deck(deck_id="d", slides=tuple(_slide(f"s{i}", t) for i, t in enumerate(texts)))


def test_extract_terms_picks_camelcase_and_the_phrases():
    terms = extract_terms("Why the Platform beats HelpBot at peak demand")
    assert "the Platform" in terms
    assert "HelpBot" in terms


def test_flags_minority_variant():
    deck = _deck(
        "the Platform is saturated",
        "the Platform refresh is due",
        "the Platform ships weekly",
        "the PlatformX adoption is slow",  # variant on one slide
    )
    labels = detect_terminology_inconsistency(deck)
    assert len(labels) == 1
    meta = labels[0].metadata
    assert labels[0].type == "S3_TERMINOLOGY_INCONSISTENCY"
    assert meta["canonical"] == "the Platform"
    assert meta["variant"] == "the PlatformX"
    assert meta["variant_slides"] == [3]
    assert labels[0].target_element_ids == ("s3_b0",)


def test_clean_deck_has_no_false_positive():
    deck = _deck(
        "the Platform is saturated",
        "the Platform refresh is due",
        "the Platform ships weekly",
        "the Platform adoption grows",
    )
    assert detect_terminology_inconsistency(deck) == []


def test_unrelated_terms_do_not_cluster():
    deck = _deck("HelpBot launches", "ZeroTrust matters", "FlowNet scales", "HelpBot wins")
    assert detect_terminology_inconsistency(deck) == []


def test_glossary_overrides_majority():
    # variant used on MORE slides than the canonical glossary term; glossary wins.
    deck = _deck(
        "HelpBotX rollout", "HelpBotX metrics", "HelpBotX adoption", "HelpBot baseline",
    )
    labels = detect_terminology_inconsistency(deck, glossary=["HelpBot"])
    assert len(labels) == 1
    assert labels[0].metadata["canonical"] == "HelpBot"
    assert labels[0].metadata["variant"] == "HelpBotX"


def test_build_term_occurrences_tracks_slides_and_elements():
    deck = _deck("HelpBot here", "nothing", "HelpBot again")
    occ = build_term_occurrences(deck)
    assert occ["HelpBot"]["slides"] == [0, 2]
    assert occ["HelpBot"]["element_ids"] == ["s0_b0", "s2_b0"]


def test_lint_deck_accepts_single_slide():
    # a one-slide deck cannot have cross-slide inconsistency -> no flag
    assert lint_deck(_slide("only", "the Platform stands alone")) == []
