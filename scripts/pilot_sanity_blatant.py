"""Sanity check: does Qwen3-VL-4B catch BLATANT defects?

If the pilot's 0% on G1/G2 is about weak synthetic injection (not a useless
model), then making the defect obvious should flip the model to detected.
Renders three hand-crafted slides (blatant overflow, blatant overlap, clearly
clean) and probes modality C with the same pilot prompt.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from openai import OpenAI
from slide_examiner.schemas import Slide, Element, BBox, ManifestSample
from slide_examiner.render import render_slide_multi_resolution
from slide_examiner.adapters import build_probe_payload
from slide_examiner.model_adapters import _openai_content
import scripts.run_pilot as rp

OUT = Path("runs/pilot/sanity"); OUT.mkdir(parents=True, exist_ok=True)

def el(eid, typ, x, y, w, h, text, role=None, fill=None, fs=24):
    style = {"font_size_pt": fs, "color": "#111111"}
    if fill: style["fill_color"] = fill
    meta = {"role": role, "text_level": role} if role else {}
    return Element(element_id=eid, type=typ, bbox=BBox(x, y, w, h), text=text, style=style, metadata=meta)

# 1) BLATANT overflow: long title in a narrow 360px box -> text spills far past it
overflow = Slide("blatant_overflow", (
    el("title", "title", 96, 72, 360, 60,
       "This title is far too long to ever fit inside its small fixed box and clearly spills out", role="title", fs=30),
    el("body0", "text", 96, 200, 1512, 60, "A normal bullet that fits fine", role="body"),
))
# 2) BLATANT overlap: two big filled shapes sitting almost on top of each other
overlap = Slide("blatant_overlap", (
    el("title", "title", 96, 60, 1512, 60, "Two boxes overlap heavily", role="title", fs=30),
    el("boxA", "shape", 300, 250, 600, 360, "Box A", fill="#cc4444"),
    el("boxB", "shape", 420, 320, 600, 360, "Box B", fill="#4444cc"),
))
# 3) Clearly clean control
clean = Slide("clearly_clean", (
    el("title", "title", 96, 72, 1512, 60, "A clean, well laid out slide", role="title", fs=30),
    el("body0", "text", 144, 200, 1400, 50, "First point sits in its lane", role="body"),
    el("body1", "text", 144, 280, 1400, 50, "Second point sits in its lane", role="body"),
))

cases = [("blatant_overflow", overflow, ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "S1_TITLE_BODY_MISMATCH"]),
         ("blatant_overlap", overlap, ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "S1_TITLE_BODY_MISMATCH"]),
         ("clearly_clean", clean, ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "S1_TITLE_BODY_MISMATCH"])]

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url="http://localhost:8011/v1")

results = []
for name, slide, scope in cases:
    arts = render_slide_multi_resolution(slide, OUT / name, long_edges=(1024,))
    img = arts[0].image_path if hasattr(arts[0], "image_path") else arts["1024"].image_path
    rec = {"sample_id": name, "slide": slide.to_dict(), "image_path": str(img),
           "labels": [], "metadata": {}}
    sample = ManifestSample.from_mapping(rec)
    p = build_probe_payload(sample, modality="C", task="T1")
    p["prompt"] = rp.build_pilot_prompt(rec, "T1")
    r = client.chat.completions.create(model="qwen3vl-4b",
        messages=[{"role": "user", "content": _openai_content(p)}], max_tokens=400, temperature=0)
    raw = r.choices[0].message.content or ""
    print(f"\n### {name}  (img={img})")
    print(" ", raw[:400])
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"raw": raw}
    results.append({"case": name, "image_path": str(img), "output": parsed})

(OUT / "sanity_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nWrote {OUT / 'sanity_results.json'}")
