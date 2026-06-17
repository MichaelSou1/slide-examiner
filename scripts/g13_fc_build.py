"""Build a paired forced-choice dataset for G1/G3 (the geometry defects with the
most signal), to render at higher resolution and probe with 2-AFC.

For each base slide and each defect, write a CLEAN record and a DEFECTIVE record
sharing a `pair_key`, so a forced-choice probe can show both and ask which has
the defect. Severe severities (the most detectable end of the grid).
"""
from __future__ import annotations

import json
from pathlib import Path

from slide_examiner.experiment import inject_slide_defect
from slide_examiner.ingest import load_deck_json

REPO = Path(__file__).resolve().parents[1]
DECKS = sorted((REPO / "data" / "part1" / "decks").glob("*.json"))
OUT = REPO / "data" / "part1_fc" / "manifest.jsonl"
N_BASE = 24
DEFECTS = [("G1_TEXT_OVERFLOW", 64.0), ("G3_ALIGNMENT_OFFSET", 32.0)]


def main() -> None:
    slides = [s for p in DECKS for s in load_deck_json(p).slides][:N_BASE]
    recs = []
    for defect, sev in DEFECTS:
        for s in slides:
            try:
                inj = inject_slide_defect(s, defect, severity=sev)
            except Exception:
                continue
            key = f"{s.slide_id}__{defect}"
            meta = {"pair_key": key, "defect": defect, "template_condition": "freeform"}
            recs.append({"sample_id": f"{key}__clean", "slide": s.to_dict(), "labels": [],
                         "metadata": {**meta, "role": "clean"}})
            recs.append({"sample_id": f"{key}__def", "slide": inj.defective.to_dict(),
                         "labels": [inj.label.to_dict()], "metadata": {**meta, "role": "def"}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as h:
        for r in recs:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(recs)} records ({len(recs)//4} pairs/defect) to {OUT}")


if __name__ == "__main__":
    main()
