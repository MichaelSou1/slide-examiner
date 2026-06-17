"""Deck-level terminology-consistency linter (S3).

Part 1 showed S3_TERMINOLOGY_INCONSISTENCY is *not* a VLM task: the structure
channel already feeds the full deck text (both variants present) yet a 30B VLM
scores ~0.56 balanced accuracy, and forced-choice does not rescue it — the
bottleneck is OCR-from-pixels + per-defect yes/no framing, not reasoning. The
signal is mechanically decidable from the extracted text, exactly like geometry
(G2-G6). So S3 leaves the examiner and is handled here, symbolically.

Pipeline (image-free):
    deck text  ->  per-term occurrence table  ->  near-duplicate variant cluster
               ->  DefectLabel(S3_TERMINOLOGY_INCONSISTENCY)

`detect_terminology_inconsistency` is the symbolic fast path: it catches clean
variants (a canonical form used on most slides + a near-duplicate on a few — e.g.
"the Platform" vs "the PlatformX"). For messy real-world drift where the variants
are not edit-distance close (e.g. "K8s" / "Kubernetes" / "kube"), the same
occurrence table is the input a text-LLM consumes instead of the symbolic
clusterer; `build_term_occurrences` is exposed for that path.
"""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

from .schemas import Deck, DefectLabel, Slide

# Candidate "product term" tokens: CamelCase or capitalised words >= 4 chars,
# optionally preceded by "the " (so "the Platform" and "HelpBot" both match).
_TERM_RE = re.compile(r"\b(?:the\s+)?[A-Z][a-z]{2,}(?:[A-Z][a-z]*)*[A-Za-z]*\b")


def _norm(term: str) -> str:
    """Canonical key for grouping case/whitespace variants of the *same* term."""
    return re.sub(r"\s+", " ", term).strip()


def extract_terms(text: str) -> set[str]:
    """Pull candidate multi-word / CamelCase product terms from one text blob."""
    return {_norm(m.group(0)) for m in _TERM_RE.finditer(text)}


def build_term_occurrences(deck: Deck) -> dict[str, dict]:
    """term -> {"slides": sorted slide-index list, "element_ids": [...]}.

    This is the deck-level occurrence table — the shared input for both the
    symbolic clusterer below and a text-LLM consistency check.
    """
    occ: dict[str, dict] = defaultdict(lambda: {"slides": set(), "element_ids": set()})
    for index, slide in enumerate(deck.slides):
        for element in slide.elements:
            if not element.text:
                continue
            for term in extract_terms(element.text):
                occ[term]["slides"].add(index)
                occ[term]["element_ids"].add(element.element_id)
    return {
        term: {"slides": sorted(rec["slides"]), "element_ids": sorted(rec["element_ids"])}
        for term, rec in occ.items()
    }


def _stem(term: str) -> str:
    """Lower-cased, trailing-non-alpha-stripped stem for variant matching."""
    return re.sub(r"[^a-z]+$", "", term.lower())


def _edit_distance(a: str, b: str) -> int:
    # small Levenshtein; terms are short so the DP is cheap.
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_variant_pair(a: str, b: str, *, max_edit: int, min_ratio: float) -> bool:
    """True if a and b look like the same term written two ways (not unrelated)."""
    if a == b:
        return False
    if min(len(a), len(b)) < 4:
        return False
    if _stem(a) == _stem(b):  # differ only by case / trailing punctuation
        return True
    if _edit_distance(a.lower(), b.lower()) > max_edit:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= min_ratio


def detect_terminology_inconsistency(
    deck: Deck,
    *,
    glossary: list[str] | None = None,
    min_canonical_slides: int = 2,
    max_edit: int = 2,
    min_ratio: float = 0.8,
) -> list[DefectLabel]:
    """Flag terms used inconsistently across the deck.

    A flag fires when two near-duplicate forms of the same term coexist: the
    *canonical* form (the more widely used one, or — if a `glossary` is given —
    the glossary entry) plus a *variant* used on fewer slides. On a clean deck
    every mention is identical, so no pair forms and nothing fires (0 FP).
    """
    occ = build_term_occurrences(deck)
    terms = sorted(occ)
    glossary_norm = {_norm(g) for g in glossary} if glossary else None

    labels: list[DefectLabel] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(terms):
        for b in terms[i + 1:]:
            if not _is_variant_pair(a, b, max_edit=max_edit, min_ratio=min_ratio):
                continue
            a_slides, b_slides = occ[a]["slides"], occ[b]["slides"]
            # Decide which form is canonical.
            by_glossary = glossary_norm is not None and (a in glossary_norm) != (b in glossary_norm)
            if by_glossary:
                canonical, variant = (a, b) if a in glossary_norm else (b, a)
            else:
                # majority by slide coverage; tie-break on total — else skip (ambiguous)
                if len(a_slides) == len(b_slides):
                    continue
                canonical, variant = (a, b) if len(a_slides) > len(b_slides) else (b, a)
                # Without a glossary, require the canonical to be established (seen on
                # >= min_canonical_slides) so a single typo'd term is not treated as the
                # standard. With a glossary the canonical authority is the glossary itself.
                if len(occ[canonical]["slides"]) < min_canonical_slides:
                    continue
            key = (canonical, variant)
            if key in seen:
                continue
            seen.add(key)
            labels.append(
                DefectLabel(
                    type="S3_TERMINOLOGY_INCONSISTENCY",
                    severity=1.0,
                    target_element_ids=tuple(occ[variant]["element_ids"]),
                    metadata={
                        "canonical": canonical,
                        "variant": variant,
                        "canonical_slides": occ[canonical]["slides"],
                        "variant_slides": occ[variant]["slides"],
                    },
                )
            )
    return labels


def lint_deck(deck: Deck | Slide, **kwargs) -> list[DefectLabel]:
    """Deck-level lint entry point (currently the terminology checker).

    Accepts a single Slide too (wrapped into a 1-slide deck) so callers can treat
    it symmetrically with `geometry.lint_slide`.
    """
    if isinstance(deck, Slide):
        deck = Deck(deck_id=deck.slide_id, slides=(deck,))
    return detect_terminology_inconsistency(deck, **kwargs)
