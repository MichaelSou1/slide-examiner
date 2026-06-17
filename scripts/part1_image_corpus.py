"""Build image-bearing decks so S6 (image-text contradiction) is testable.

Each figure slide has a `diagram` element whose depicted claim + trend live only
in the rendered pixels (the structure oracle strips diagram_claim/false/trend),
plus a body that AGREES with the figure in the clean state. The S6 injector
rewrites the body to the authored `diagram_false_claim`, producing a contradiction
that is visible from the image but not from the structure.
"""
from __future__ import annotations

import json
from pathlib import Path

from slide_examiner.ingest import save_deck_json
from slide_examiner.schemas import BBox, Deck, Element, Slide

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "part1_img" / "decks"

# (true claim shown in the figure, false claim for the contradiction, trend glyph)
FIGS = [
    ("Quarterly revenue rose sharply in Q4", "Quarterly revenue fell sharply in Q4", "up"),
    ("Customer churn dropped to a record low", "Customer churn climbed to a record high", "down"),
    ("Page load time got faster every release", "Page load time got slower every release", "down"),
    ("Market share expanded across all regions", "Market share contracted across all regions", "up"),
    ("The defect rate declined every sprint", "The defect rate rose every sprint", "down"),
    ("Signups accelerated after the launch", "Signups stalled after the launch", "up"),
    ("Operating costs fell quarter over quarter", "Operating costs rose quarter over quarter", "down"),
    ("NPS climbed into the eighties", "NPS sank into the thirties", "up"),
    ("Uptime improved to four nines", "Uptime degraded to two nines", "up"),
    ("Support backlog shrank week over week", "Support backlog grew week over week", "down"),
    ("Conversion rate doubled after the redesign", "Conversion rate halved after the redesign", "up"),
    ("Energy use per unit dropped steadily", "Energy use per unit rose steadily", "down"),
]


def figure_slide(idx: int, claim: str, false_claim: str, trend: str) -> Slide:
    title = Element("s_title", "title", BBox(96, 72, 1728, 72),
                    text=f"Performance update {idx + 1}", style={"font_size_pt": 32, "color": "#111111"},
                    metadata={"role": "title", "text_level": "title"})
    figure = Element("s_fig", "image", BBox(120, 200, 760, 560), text="",
                     style={"font_size_pt": 18, "color": "#222"},
                     metadata={"role": "diagram", "diagram_claim": claim,
                               "diagram_false_claim": false_claim, "diagram_trend": trend})
    # Body AGREES with the figure in the clean state; S6 injection flips it to false_claim.
    body = Element("s_body0", "text", BBox(940, 220, 860, 80), text=claim,
                   style={"font_size_pt": 22, "color": "#222222"}, metadata={"role": "body", "text_level": "body"})
    note = Element("s_body1", "text", BBox(940, 320, 860, 80),
                   text="The chart on the left summarizes the trend.",
                   style={"font_size_pt": 20, "color": "#444444"}, metadata={"role": "body", "text_level": "body"})
    return Slide(slide_id=f"imgslide_{idx}", elements=(title, figure, body, note),
                 metadata={"section": "evidence"})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Group the figure slides into 3 decks of 4.
    written = []
    for d in range(3):
        slides = tuple(figure_slide(d * 4 + i, *FIGS[d * 4 + i]) for i in range(4))
        deck = Deck(deck_id=f"part1img_deck{d}", slides=slides,
                    metadata={"scenario": "full_proposal", "required_sections": ["evidence"]})
        path = OUT / f"{deck.deck_id}.json"
        save_deck_json(deck, path)
        written.append((deck.deck_id, len(deck.slides)))
    print(json.dumps({"decks": written, "out_dir": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
