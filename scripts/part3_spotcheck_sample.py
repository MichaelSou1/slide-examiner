#!/usr/bin/env python3
"""E8 — human perceptual spot-check sampler.

Builds a *human-verification* set for reviewer EIC-W4: injection gives exact
IR-space labels, but the 45%-snap audit shows IR != pixels, so a top reviewer
wants confirmation that the injected defect is perceptually *present* on the
faithfully-rendered slide (and that the clean twin is actually clean).

This script samples ~N defectives per class from the **freeform-only**
(non-``__template``) renders + their clean twins — template renders are dropped
because the snap-to-master absorbs ~45% of injected geometry (the P2 gotcha), so
they would understate the verification rate for the wrong reason. It then emits:

  * ``manifest.json``       — the sampled pairs (ground truth: id, class, paths,
                              the human-readable target-defect phrase). The
                              report step + the Claude-vision cross-check read this.
  * ``spotcheck.html``      — a self-contained page (images embedded as data URIs):
                              for each pair you click "defect visible? Y/N" and
                              "twin clean? Y/N", then Export -> labels.json.
                              Autosaves to localStorage so progress survives a reload.
  * ``pairs/pair_XXX.png``  — side-by-side composites (record + the cross-check input).

No GPU, no model calls — pure sampling + image layout.

Usage:
  python scripts/part3_spotcheck_sample.py --n-per-class 6 --seed 20260624
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

PART2_MANIFEST = REPO / "data/part2/manifest_eval_test_rendered.jsonl"
G7_MANIFEST = REPO / "data/part3/manifest_g7_rendered.jsonl"
# S6 in the generic part-2 manifest is DEGENERATE in the freeform modality: the IR
# carries no figure/diagram element (types = [title,text,text,text]), so the injected
# "image-text contradiction" is a self-referential text sentence with nothing visual to
# contradict (the E8 cross-check caught this). The valid diagram-bearing S6 corpus —
# a real figure ("FIGURE: revenue rose ▲") whose trend contradicts the body text —
# lives here, already rendered with clean twins. Source S6 from it, not the generic set.
S6_MANIFEST = REPO / "data/part1_img/manifest_s6_rendered.jsonl"

# Stratification order (geometry classes first — they are the ones the IR!=pixels
# audit threatens most; semantic S-classes are text edits, less snap-sensitive).
CLASS_ORDER = [
    "G1_TEXT_OVERFLOW",
    "G2_ELEMENT_OVERLAP",
    "G3_ALIGNMENT_OFFSET",
    "G6_MARGIN_VIOLATION",
    "G7_RENDER_CONTAINMENT_OVERFLOW",
    "G5_BRAND_COLOR_VIOLATION",
    "S1_TITLE_BODY_MISMATCH",
    "S2_NARRATIVE_ORDER_BREAK",
    "S3_TERMINOLOGY_INCONSISTENCY",
    "S4_DENSITY_RULE_VIOLATION",
    "S6_IMAGE_TEXT_CONTRADICTION",
]

# Headline elicitation classes get topped up (paper's claims hinge on these).
HEADLINE = {"G1_TEXT_OVERFLOW", "S6_IMAGE_TEXT_CONTRADICTION", "G7_RENDER_CONTAINMENT_OVERFLOW"}

# Concise, human-readable "what to look for" phrasing (informed-confirmation task).
PHRASE = {
    "G1_TEXT_OVERFLOW": "text overflows or is clipped by its text box",
    "G2_ELEMENT_OVERLAP": "two elements overlap / collide",
    "G3_ALIGNMENT_OFFSET": "an element is visibly misaligned (off its expected edge/position)",
    "G6_MARGIN_VIOLATION": "an element breaks the slide margin (touches / runs past the edge)",
    "G7_RENDER_CONTAINMENT_OVERFLOW": "content spills outside the box / card / frame meant to contain it",
    "G5_BRAND_COLOR_VIOLATION": "an off-brand / wrong colour is used",
    "S1_TITLE_BODY_MISMATCH": "the title does not match the body content",
    "S2_NARRATIVE_ORDER_BREAK": "the bullets / sections are in an illogical order",
    "S3_TERMINOLOGY_INCONSISTENCY": "the same concept is named inconsistently",
    "S4_DENSITY_RULE_VIOLATION": "the slide is over-dense (too much content crammed in)",
    "S6_IMAGE_TEXT_CONTRADICTION": "a chart / image contradicts the text near it",
}

SHORT = {c: c.split("_")[0] for c in CLASS_ORDER}


def _abs(p: str | None) -> Path | None:
    if not p:
        return None
    pp = Path(p)
    return pp if pp.is_absolute() else (REPO / pp)


def _defect_of(rec: dict) -> str:
    labs = [x.get("type") for x in rec.get("labels", [])]
    return labs[0] if labs else "NO_DEFECT"


def _clean_path(rec: dict) -> Path | None:
    pair = rec.get("pair") or {}
    meta = rec.get("metadata") or {}
    cp = pair.get("clean_image_path") or meta.get("clean_image_path")
    return _abs(cp)


def _def_path(rec: dict) -> Path | None:
    meta = rec.get("metadata") or {}
    dp = rec.get("image_path") or meta.get("defective_image_path")
    return _abs(dp)


def load_pool() -> dict[str, list[dict]]:
    """class -> list of {def_path, clean_path, src_id} with both files on disk."""
    pool: dict[str, list[dict]] = {c: [] for c in CLASS_ORDER}

    def _ingest(path: Path, *, freeform_only: bool, only=None, skip=None):
        if not path.exists():
            print(f"[warn] missing manifest {path}", file=sys.stderr)
            return
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                cls = _defect_of(rec)
                if cls not in pool:
                    continue
                if only and cls not in only:
                    continue
                if skip and cls in skip:
                    continue
                dp = _def_path(rec)
                if freeform_only and dp and "__template" in str(dp):
                    continue  # snap absorbs ~45% of geometry (P2 gotcha)
                cp = _clean_path(rec)
                if not (dp and cp and dp.exists() and cp.exists()):
                    continue
                pool[cls].append({
                    "def_path": dp,
                    "clean_path": cp,
                    "src_id": rec.get("sample_id") or rec.get("metadata", {}).get(
                        "defective_image_path") or str(dp),
                })

    _ingest(PART2_MANIFEST, freeform_only=True, skip={"S6_IMAGE_TEXT_CONTRADICTION"})
    _ingest(S6_MANIFEST, freeform_only=True, only={"S6_IMAGE_TEXT_CONTRADICTION"})  # valid figure-text S6
    _ingest(G7_MANIFEST, freeform_only=False)  # g7 renders are all freeform
    return pool


def sample(pool: dict[str, list[dict]], n_per_class: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    picks: list[dict] = []
    for cls in CLASS_ORDER:
        avail = list(pool.get(cls, []))
        rng.shuffle(avail)
        target = n_per_class + (2 if cls in HEADLINE else 0)
        chosen = avail[:target]
        if len(chosen) < target:
            print(f"[warn] {cls}: only {len(chosen)}/{target} pairs available", file=sys.stderr)
        for c in chosen:
            picks.append({**c, "class": cls})
    rng.shuffle(picks)  # interleave classes -> reduces labeller fatigue/patterning
    for i, p in enumerate(picks):
        p["pair_id"] = f"{i:03d}"
    return picks


# --------------------------------------------------------------------------- #
# image helpers
# --------------------------------------------------------------------------- #
def _load_rgb(path: Path, width: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    if im.width > width:
        h = round(im.height * width / im.width)
        im = im.resize((width, h), Image.LANCZOS)
    return im


def _data_uri(im: Image.Image, quality: int) -> str:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _composite(defim: Image.Image, clim: Image.Image, header: str) -> Image.Image:
    pad, bar = 12, 30
    w = defim.width + clim.width + pad * 3
    h = max(defim.height, clim.height) + bar + pad * 2
    canvas = Image.new("RGB", (w, h), "#222222")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    draw.text((pad, 7), header, fill="#ffffff", font=font)
    y = bar + pad
    canvas.paste(defim, (pad, y))
    canvas.paste(clim, (pad * 2 + defim.width, y))
    draw.text((pad + 4, y + 2), "DEFECTIVE", fill="#ff5555", font=font)
    draw.text((pad * 2 + defim.width + 4, y + 2), "CLEAN twin", fill="#55ff7f", font=font)
    return canvas


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>E8 perceptual spot-check</title>
<style>
 body{font-family:system-ui,Arial,sans-serif;margin:0;background:#1b1b1f;color:#eee}
 header{position:sticky;top:0;background:#26262c;padding:10px 16px;border-bottom:1px solid #3a3a42;z-index:5}
 #prog{font-size:14px;color:#9ad}
 .wrap{max-width:1500px;margin:0 auto;padding:16px}
 .task{font-size:17px;margin:8px 0 4px}
 .task b{color:#ffd479}
 .imgs{display:flex;gap:14px;flex-wrap:wrap}
 .col{flex:1 1 0;min-width:340px}
 .col .cap{font-weight:600;padding:4px 0}
 .def .cap{color:#ff6b6b}.cln .cap{color:#54d98c}
 img{width:100%;border:1px solid #444;border-radius:4px;background:#fff}
 .q{margin:10px 0;font-size:15px}
 .q span{display:inline-block;min-width:230px}
 button.opt{padding:6px 16px;margin-right:8px;border:1px solid #555;background:#33333a;color:#eee;border-radius:5px;cursor:pointer}
 button.opt.yes.on{background:#1f7a3d;border-color:#2ecc71}
 button.opt.no.on{background:#9a2b2b;border-color:#e74c3c}
 textarea{width:100%;height:42px;background:#26262c;color:#eee;border:1px solid #444;border-radius:4px}
 .nav{margin:14px 0}
 .nav button{padding:8px 18px;margin-right:10px;font-size:15px;border-radius:5px;border:1px solid #555;background:#33333a;color:#eee;cursor:pointer}
 #export{background:#2255aa;border-color:#3a78d8;font-weight:600}
 .done{color:#54d98c}.todo{color:#ffb454}
 kbd{background:#000;border:1px solid #555;border-radius:3px;padding:1px 5px;font-size:12px}
</style></head><body>
<header>
 <div id="prog"></div>
 <div style="font-size:12px;color:#888;margin-top:3px">
  keys: <kbd>d</kbd>/<kbd>D</kbd> defect Yes/No &nbsp; <kbd>t</kbd>/<kbd>T</kbd> twin Yes/No &nbsp;
  <kbd>&larr;</kbd>/<kbd>&rarr;</kbd> prev/next. Answers autosave; click <b>Export labels.json</b> when done.</div>
</header>
<div class="wrap">
 <div class="task" id="task"></div>
 <div class="imgs">
  <div class="col def"><div class="cap">DEFECTIVE (injected)</div><img id="defimg"></div>
  <div class="col cln"><div class="cap">CLEAN twin</div><img id="clnimg"></div>
 </div>
 <div class="q"><span>1) Is the defect visible on the DEFECTIVE slide?</span>
   <button class="opt yes" data-q="defect_visible" data-v="yes">Yes</button>
   <button class="opt no"  data-q="defect_visible" data-v="no">No</button></div>
 <div class="q"><span>2) Is the CLEAN twin actually clean?</span>
   <button class="opt yes" data-q="twin_clean" data-v="yes">Yes</button>
   <button class="opt no"  data-q="twin_clean" data-v="no">No</button></div>
 <div class="q"><textarea id="note" placeholder="optional note (e.g. 'can't tell without brand reference', 'subtle', 'injector artifact')"></textarea></div>
 <div class="nav">
   <button id="prev">&larr; Prev</button><button id="next">Next &rarr;</button>
   <button id="export">Export labels.json</button>
   <span id="count"></span>
 </div>
</div>
<script>
const PAIRS = __PAIRS_JSON__;
const KEY = "e8_spotcheck_labels_v1";
let labels = JSON.parse(localStorage.getItem(KEY) || "{}");
let i = 0;
function cur(){return PAIRS[i];}
function render(){
  const p = cur();
  document.getElementById("task").innerHTML =
    "Pair <b>"+(i+1)+" / "+PAIRS.length+"</b> &nbsp; class <b>"+p.cls+"</b> &mdash; look for: <b>"+p.phrase+"</b>";
  document.getElementById("defimg").src = p.def;
  document.getElementById("clnimg").src = p.clean;
  const rec = labels[p.id] || {};
  document.querySelectorAll("button.opt").forEach(b=>{
    const on = rec[b.dataset.q] === b.dataset.v; b.classList.toggle("on", on);
  });
  document.getElementById("note").value = rec.note || "";
  let done = Object.keys(labels).filter(k=>labels[k].defect_visible&&labels[k].twin_clean).length;
  document.getElementById("prog").innerHTML =
    "E8 perceptual spot-check &mdash; <span class="+(done==PAIRS.length?"'done'":"'todo'")+">"+done+" / "+PAIRS.length+" complete</span>";
  document.getElementById("count").textContent = done+" / "+PAIRS.length+" answered";
}
function setv(q,v){
  const p = cur(); labels[p.id] = labels[p.id] || {cls:p.cls};
  labels[p.id][q] = v; labels[p.id].note = document.getElementById("note").value;
  localStorage.setItem(KEY, JSON.stringify(labels)); render();
}
document.querySelectorAll("button.opt").forEach(b=>b.onclick=()=>setv(b.dataset.q,b.dataset.v));
document.getElementById("note").oninput=()=>{const p=cur();labels[p.id]=labels[p.id]||{cls:p.cls};
  labels[p.id].note=document.getElementById("note").value;localStorage.setItem(KEY,JSON.stringify(labels));};
document.getElementById("prev").onclick=()=>{i=(i-1+PAIRS.length)%PAIRS.length;render();};
document.getElementById("next").onclick=()=>{i=(i+1)%PAIRS.length;render();};
document.getElementById("export").onclick=()=>{
  const out = {}; PAIRS.forEach(p=>{out[p.id]=labels[p.id]||{cls:p.cls};});
  const blob = new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="labels.json"; a.click();
};
document.addEventListener("keydown",e=>{
  if(e.target.tagName==="TEXTAREA")return;
  if(e.key==="d")setv("defect_visible","yes"); else if(e.key==="D")setv("defect_visible","no");
  else if(e.key==="t")setv("twin_clean","yes"); else if(e.key==="T")setv("twin_clean","no");
  else if(e.key==="ArrowLeft")document.getElementById("prev").click();
  else if(e.key==="ArrowRight")document.getElementById("next").click();
});
render();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-class", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20260624)
    ap.add_argument("--out-dir", default=str(REPO / "docs/spotcheck"))
    ap.add_argument("--img-width", type=int, default=720)
    ap.add_argument("--quality", type=int, default=82)
    ap.add_argument("--no-composites", action="store_true",
                    help="skip per-pair composite PNGs (HTML + manifest only)")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pairs_dir = out / "pairs"

    pool = load_pool()
    print("[pool] available pairs per class:")
    for c in CLASS_ORDER:
        print(f"  {c:34s} {len(pool[c])}")
    picks = sample(pool, args.n_per_class, args.seed)
    print(f"[sample] {len(picks)} pairs (seed={args.seed})")

    manifest, html_pairs = [], []
    if not args.no_composites:
        pairs_dir.mkdir(exist_ok=True)
    for p in picks:
        cls = p["class"]
        defim = _load_rgb(p["def_path"], args.img_width)
        clim = _load_rgb(p["clean_path"], args.img_width)
        rel_def = str(p["def_path"].relative_to(REPO)) if str(p["def_path"]).startswith(str(REPO)) else str(p["def_path"])
        rel_cln = str(p["clean_path"].relative_to(REPO)) if str(p["clean_path"]).startswith(str(REPO)) else str(p["clean_path"])
        comp_name = f"pair_{p['pair_id']}_{SHORT[cls]}.png"
        manifest.append({
            "pair_id": p["pair_id"], "class": cls, "short": SHORT[cls],
            "phrase": PHRASE.get(cls, cls), "src_id": p["src_id"],
            "defective_path": rel_def, "clean_path": rel_cln,
            "composite": f"pairs/{comp_name}",
        })
        html_pairs.append({
            "id": p["pair_id"], "cls": cls, "phrase": PHRASE.get(cls, cls),
            "def": _data_uri(defim, args.quality), "clean": _data_uri(clim, args.quality),
        })
        if not args.no_composites:
            header = f"pair {p['pair_id']}  |  {cls}  |  look for: {PHRASE.get(cls, cls)}"
            _composite(defim, clim, header).save(pairs_dir / comp_name)

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    html = HTML_TEMPLATE.replace("__PAIRS_JSON__", json.dumps(html_pairs))
    (out / "spotcheck.html").write_text(html)

    mb = len(html.encode()) / 1e6
    print(f"[write] {out/'manifest.json'}  ({len(manifest)} pairs)")
    print(f"[write] {out/'spotcheck.html'}  ({mb:.1f} MB self-contained)")
    if not args.no_composites:
        print(f"[write] {pairs_dir}/  ({len(manifest)} composites)")
    # per-class tally actually drawn
    drawn: dict[str, int] = {}
    for m in manifest:
        drawn[m["class"]] = drawn.get(m["class"], 0) + 1
    print("[sample] drawn per class:", {k: drawn[k] for k in CLASS_ORDER if k in drawn})


if __name__ == "__main__":
    main()
