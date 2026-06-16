"""Diagnostic: characterize Qwen3-VL-4B's geometry perception threshold.

After the injector/renderer fix, the pilot's G1/G2 defects are unambiguously
visible to a human (text spilling past a drawn box border; two boxes blending
into a darker overlap). This script asks the model, in free form, whether it
*perceives* them — on a moderate pilot case vs a blatant case — to show the
zeros are a model detection-threshold effect, not an invisible-defect artifact.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from openai import OpenAI
from slide_examiner.model_adapters import _image_url

OUT = Path("runs/pilot/sanity/geometry_threshold.json")
DESC = ("Describe this slide's layout. Does any text run outside the borders of its box, "
        "or do any two boxes overlap each other? Answer plainly.")


def find(recs, substr, sev):
    for r in recs:
        if substr in r["sample_id"] and str(r.get("metadata", {}).get("severity_grid_value")) == str(sev):
            return r
    return None


def main() -> None:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url="http://localhost:8011/v1")
    recs = [json.loads(l) for l in open("data/pilot/manifest_rendered.jsonl") if l.strip()]
    sanity = json.loads(Path("runs/pilot/sanity/sanity_results.json").read_text()) if Path("runs/pilot/sanity/sanity_results.json").exists() else []

    cases = [
        ("pilot_G1_overflow_64px", find(recs, "G1_TEXT_OVERFLOW", 64)["image_path"]),
        ("pilot_G2_overlap_IoU0.4", find(recs, "G2_ELEMENT_OVERLAP", 0.4)["image_path"]),
    ]
    if sanity:
        cases.append(("blatant_overflow", sanity[0]["image_path"]))

    results = []
    for name, img in cases:
        msg = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _image_url(img)}},
            {"type": "text", "text": DESC}]}]
        out = client.chat.completions.create(model="qwen3vl-4b", messages=msg, max_tokens=200, temperature=0)
        text = (out.choices[0].message.content or "").strip()
        results.append({"case": name, "image_path": img, "free_description": text})
        print(f"### {name}\n  {text[:300]}\n")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
