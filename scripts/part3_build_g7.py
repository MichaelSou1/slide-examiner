"""Synthesize G7_RENDER_CONTAINMENT_OVERFLOW pairs (A.3).

G7 = an element whose **declared bbox is legal** (inside margins, no sibling
overlap) but whose **rendered content overflows its container/card/page**. The
defining property is that the geometry linter — which reasons over declared
bboxes — is BLIND to it (asserted by the inline self-check; samples the linter
*can* see are dropped).

Mechanism: the IR (`slide`) describes only the LEGAL layout (short fitting card
text, non-overlapping in-margin bboxes), so `lint_slide` returns nothing and the
structure oracle (modality B) also cannot see the defect. A dedicated HTML
builder then draws extra *overflow content* (held in element metadata, NOT in IR
text) that spills past the card border in the DEFECTIVE render; the paired CLEAN
render draws the same card with content that fits. Only the rendered pixels show
the defect => it is a VLM-only (image-modality) class. No snap-to-master is used
(freeform), so nothing absorbs the overflow.

Three variants (A.3 a/b/c):
  card_height       last list items render below a too-short card
  unbreakable_text  a long unbreakable token spills past the card's right edge
  image_objectfit   an image's content bleeds out of its frame

Usage:
  ~/anaconda3/envs/slide-examiner/bin/python scripts/part3_build_g7.py \
    --per-variant 30 --out data/part3/manifest_g7_rendered.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(REPO))

from slide_examiner.defect_types import G7_RENDER_CONTAINMENT_OVERFLOW  # noqa: E402
from slide_examiner.geometry import lint_slide  # noqa: E402
from slide_examiner.render import _RasterJob, _rasterize_jobs, build_render_spec, image_size  # noqa: E402
from slide_examiner.schemas import BBox, Element, Slide  # noqa: E402

W, H = 1280, 720
MARGIN = 48  # keep all declared bboxes well inside the safe margin (linter margin=32)

TOPICS = [
    ("Q3 Go-to-Market Plan", ["Expand into 3 new verticals", "Hire 4 field reps", "Launch partner program",
                              "Refresh pricing tiers", "Localize for APAC", "Pilot usage-based billing",
                              "Stand up a customer council", "Ship the self-serve trial"]),
    ("Platform Architecture", ["Ingestion service", "Feature store", "Model registry", "Serving gateway",
                               "Observability stack", "Offline eval harness", "Drift monitors", "Cost governor"]),
    ("Implementation Roadmap", ["Discovery & scoping", "Data wiring", "Pilot deployment", "Security review",
                                "Production rollout", "Enablement & training", "SLA hardening", "Quarterly business review"]),
    ("Risk Register", ["Data residency exposure", "Vendor lock-in", "Model drift", "Key-person dependency",
                       "Integration debt", "Latency regressions", "Cost overrun", "Change-management gaps"]),
    ("Success Metrics", ["Activation rate +18%", "Time-to-value < 14 days", "NRR 122%", "CSAT 4.6/5",
                         "p95 latency < 800ms", "Inference cost -31%", "Ticket deflection 44%", "Logo retention 96%"]),
    ("Solution Overview", ["Unified data plane", "Governed model catalog", "Policy-aware routing", "Human-in-the-loop review",
                           "Audit & lineage", "Cost attribution", "Multi-tenant isolation", "Zero-downtime upgrades"]),
]
LONG_TOKENS = [
    "https://portal.enterprise-customer.example.com/onboarding/2026/q3/provisioning?tenant=acme-global-manufacturing&flow=self-serve",
    "registry.internal.acme-global.example/ml-platform/inference/qwen3-vl-30b-a3b-instruct-awq:2026.06-rc4-hotfix-containment",
    "C:\\Users\\enterprise\\Deployments\\2026\\Q3\\acme-global-manufacturing\\production\\inference-gateway-config-final-v7.yaml",
    "arn:aws:iam::920183746551:role/acme-global-manufacturing-prod-inference-gateway-cross-account-readonly-2026q3",
]
CARD_TINTS = [("#ffffff", "#2b6cb0"), ("#fff8f0", "#c05621"), ("#f0fff4", "#2f855a"), ("#f7fafc", "#4a5568")]
REGIONS = {"card_height": "bottom", "unbreakable_text": "right", "image_objectfit": "bottom-right"}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _page_open() -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"></head>'
            f'<body style="margin:0;width:{W}px;height:{H}px;position:relative;'
            f'background:#ffffff;font-family:Arial,Helvetica,sans-serif;">')


def _abs(x, y, w, h, extra=""):
    return f"position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;box-sizing:border-box;{extra}"


def _title_html(text, x, y, w):
    return (f'<div style="{_abs(x, y, w, 70)}font-size:34pt;font-weight:700;color:#1a202c;">'
            f'{_esc(text)}</div>')


def build_slide_and_html(variant: str, idx: int, rng: random.Random):
    """Return (slide_ir, defective_html, clean_html, target_id, region)."""
    title, bullets = rng.choice(TOPICS)
    fill, accent = rng.choice(CARD_TINTS)
    card_x, card_y = MARGIN, 150
    card_w, card_h = W - 2 * MARGIN, 360
    card_id = "card_main"
    title_id = "slide_title"
    region = REGIONS[variant]

    # --- declared IR: legal, short, non-overlapping, in-margin ---------------
    short_label = title  # fits easily in the wide card -> linter sees no overflow
    elements = [
        Element(element_id=title_id, type="title", text=title,
                bbox=BBox(MARGIN, 56, W - 2 * MARGIN, 70), style={"font_size_pt": 34, "color": "#1a202c"}, z=1),
        Element(element_id=card_id, type="body", text=short_label,
                bbox=BBox(card_x, card_y, card_w, card_h),
                style={"font_size_pt": 18, "color": "#2d3748", "fill_color": fill}, z=2,
                metadata={"g7_variant": variant}),
    ]
    slide = Slide(slide_id=f"g7_{variant}_{idx:03d}", width=W, height=H, elements=tuple(elements),
                  metadata={"scene": "full_proposal", "g7": True})

    # --- rendered HTML: defective overflows the card, clean fits -------------
    head = _page_open() + _title_html(title, MARGIN, 56, W - 2 * MARGIN)
    card_frame = (f'<div style="{_abs(card_x, card_y, card_w, card_h)}'
                  f'background:{fill};border:2px solid {accent};border-radius:6px;overflow:visible;">'
                  f'<div style="position:absolute;left:18px;top:12px;font-size:20pt;font-weight:700;color:{accent};">'
                  f'{_esc(title)}</div>')

    if variant == "card_height":
        def items_block(items):
            lis = "".join(f'<li style="margin:10px 0;">{_esc(b)}</li>' for b in items)
            return (f'<ul style="position:absolute;left:18px;top:64px;right:18px;'
                    f'font-size:21pt;color:#2d3748;line-height:1.5;padding-left:28px;'
                    f'list-style:disc;overflow:visible;white-space:normal;">{lis}</ul>')
        # defective: render MANY items -> total height exceeds the 360px card -> spill below border
        dh = head + card_frame + items_block(bullets) + "</div></body></html>"
        # clean: render only the items that fit comfortably inside the card
        ch = head + card_frame + items_block(bullets[:4]) + "</div></body></html>"

    elif variant == "unbreakable_text":
        token = rng.choice(LONG_TOKENS)
        label = "Endpoint:"
        def line(txt, wrap):
            ws = "normal;word-break:break-all" if wrap else "nowrap"
            return (f'<div style="position:absolute;left:18px;top:80px;right:18px;'
                    f'font-size:22pt;color:#2d3748;white-space:{ws};overflow:visible;'
                    f'font-family:Consolas,Menlo,monospace;">'
                    f'<span style="color:{accent};font-weight:700;">{label} </span>{_esc(txt)}</div>')
        # defective: unbreakable token, nowrap -> spills past the card's right edge (and page)
        dh = head + card_frame + line(token, wrap=False) + "</div></body></html>"
        # clean: the same endpoint wrapped to stay inside the card
        ch = head + card_frame + line(token, wrap=True) + "</div></body></html>"

    else:  # image_objectfit
        # an "image" tile whose intrinsic content is larger than its frame.
        frame_x, frame_y, frame_w, frame_h = 22, 70, 360, 250

        def img_tile(scale):
            iw, ih = int(frame_w * scale), int(frame_h * scale)
            inner = (f'background:repeating-linear-gradient(45deg,{accent} 0 28px,#ffffff 28px 56px);'
                     f'width:{iw}px;height:{ih}px;')
            cap = (f'<div style="position:absolute;left:8px;bottom:8px;background:rgba(0,0,0,0.55);'
                   f'color:#fff;font-size:13pt;padding:4px 8px;">Figure 1: architecture</div>')
            return (f'<div style="position:absolute;left:{frame_x}px;top:{frame_y}px;'
                    f'width:{frame_w}px;height:{frame_h}px;border:2px solid {accent};overflow:visible;">'
                    f'<div style="{inner}"></div>{cap}</div>')
        note = (f'<div style="position:absolute;left:{frame_x + frame_w + 28}px;top:80px;right:18px;'
                f'font-size:18pt;color:#2d3748;line-height:1.5;">Reference architecture for the proposed '
                f'deployment. See appendix for the detailed component diagram.</div>')
        # defective: image intrinsic size 1.6x the frame, overflow:visible -> bleeds out bottom/right
        dh = head + card_frame + img_tile(1.6) + note + "</div></body></html>"
        # clean: image fits the frame exactly
        ch = head + card_frame + img_tile(1.0) + note + "</div></body></html>"

    return slide, dh, ch, card_id, region


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-variant", type=int, default=30)
    ap.add_argument("--out", default="data/part3/manifest_g7_rendered.jsonl")
    ap.add_argument("--img-dir", default="data/part3/g7_images")
    ap.add_argument("--seed", type=int, default=20260620)
    ap.add_argument("--min-blind-rate", type=float, default=0.90)
    args = ap.parse_args()

    img_dir = (REPO / args.img_dir)
    img_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    specs = []  # (slide, def_html, clean_html, target_id, region, variant, idx)
    for variant in ("card_height", "unbreakable_text", "image_objectfit"):
        for i in range(args.per_variant):
            specs.append((*build_slide_and_html(variant, i, rng), variant, i))

    # --- G7 definitional self-check: linter must be blind on the IR ----------
    blind = 0
    kept = []
    for slide, dh, ch, tid, region, variant, i in specs:
        findings = lint_slide(slide)
        if not findings:
            blind += 1
            kept.append((slide, dh, ch, tid, region, variant, i))
        else:
            print(f"  DROP {slide.slide_id}: linter not blind -> {[f.type for f in findings]}")
    rate = blind / len(specs) if specs else 0.0
    print(f"[G7 self-check] linter-blind on {blind}/{len(specs)} = {rate:.3f} "
          f"(threshold {args.min_blind_rate})")
    if rate < args.min_blind_rate:
        raise SystemExit(f"G7 self-check FAILED: linter-blind rate {rate:.3f} < {args.min_blind_rate}")

    # --- render defective + clean pairs --------------------------------------
    jobs, plan = [], []
    for slide, dh, ch, tid, region, variant, i in kept:
        d_png = img_dir / f"{slide.slide_id}_def.png"
        c_png = img_dir / f"{slide.slide_id}_clean.png"
        jobs.append(_RasterJob(html=dh, output=d_png, width=W, height=H))
        jobs.append(_RasterJob(html=ch, output=c_png, width=W, height=H))
        plan.append((slide, d_png, c_png, tid, region, variant))
    print(f"[render] {len(jobs)} images ...")
    _rasterize_jobs(jobs)

    # --- write manifest ------------------------------------------------------
    records = []
    for slide, d_png, c_png, tid, region, variant in plan:
        iw, ih = image_size(d_png)
        spec = build_render_spec(slide_width=W, slide_height=H, image_width=iw, image_height=ih,
                                 renderer="playwright-chromium")
        d_abs, c_abs = str(d_png.resolve()), str(c_png.resolve())
        records.append({
            "sample_id": slide.slide_id,
            "image_path": d_abs,
            "slide": slide.to_dict(),
            "labels": [{"type": G7_RENDER_CONTAINMENT_OVERFLOW, "severity": 1.0,
                        "target_element_ids": [tid]}],
            "pair": {"clean_image_path": c_abs, "defective_image_path": d_abs},
            "metadata": {"scene": "full_proposal", "source": "part3_g7", "g7_variant": variant,
                         "overflow_region": region, "render": spec,
                         "clean_image_path": c_abs, "defective_image_path": d_abs},
        })
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    by_variant = {v: sum(1 for r in records if r["metadata"]["g7_variant"] == v)
                  for v in ("card_height", "unbreakable_text", "image_objectfit")}
    print(f"[done] {len(records)} G7 pairs -> {out}")
    print(f"  per-variant: {by_variant}")


if __name__ == "__main__":
    main()
