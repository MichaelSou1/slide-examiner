#!/usr/bin/env python3
"""E8 strict — magnitude-stratified perceptual test for the sub-perceptual classes.

The side-by-side spot-check understates fine-geometry / achromatic-colour
detectability: a uniform 2 px shift or a near-black lightness change is real (IR
audit: 51/51 present) but invisible when the two slides sit apart. This tool gives
G3/G5/G6 a fairer, harder test:

  * **magnitude strata** — G3 {4px, 32px}, G5 {ΔE2000≈3.2, 12, 23.8},
    G6 {flush x→0, gap x→28} — so we report a psychometric curve, not one number;
  * **blink overlay** — defective and clean alternate IN PLACE (the eye catches a
    uniform shift as motion / a colour change as flicker — the classic blink
    comparator), plus an **amplified difference image** (changed pixels glow);
  * **two questions per pair** — Q1 unaided (first-look side-by-side salience) and
    Q2 aided (can you confirm + locate it with blink/diff). Q1 is the honest
    "perceptible in normal viewing?" rate; Q2≈1.0 perceptually re-confirms the
    injection is present (complementing the IR audit).

Strata are NOT shown in the UI (so Q1 stays unbiased); they are revealed only in
the report. Emits manifest_strict.json + spotcheck_strict.html (self-contained).

Usage: python scripts/part3_spotcheck_strict.py --n-per-stratum 5 --seed 20260624
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from part3_spotcheck_sample import (  # noqa: E402
    PART2_MANIFEST, _abs, _clean_path, _data_uri, _def_path, _defect_of, _load_rgb,
)

OUT_DEFAULT = REPO / "docs/spotcheck"


def _load_slide(p):
    p = _abs(p)
    return json.loads(p.read_text()) if p and p.exists() else None


def _elem(slide, eid):
    for e in (slide or {}).get("elements", []):
        if e.get("element_id") == eid:
            return e
    return None


def stratum_of(cls, rec):
    """A short magnitude-stratum label for a part-2 record, or None if undetermined."""
    lab = (rec.get("labels") or [{}])[0]
    lm = lab.get("metadata", {})
    if cls == "G3_ALIGNMENT_OFFSET":
        return f"{int(lm.get('offset_px', 0))}px"
    if cls == "G5_BRAND_COLOR_VIOLATION":
        de = round(lm.get("delta_e", 0), 1)
        return f"ΔE≈{3 if de < 5 else (12 if de < 18 else 24)}"
    if cls == "G6_MARGIN_VIOLATION":
        tgt = (lab.get("target_element_ids") or [None])[0]
        ds = _load_slide(rec.get("metadata", {}).get("defective_slide_path"))
        e = _elem(ds, tgt)
        if not e:
            return None
        x = e["bbox"]["x"]
        return "flush(x->0)" if x == 0 else (f"gap(x->{int(x)})")
    return None


CLASSES = ["G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]
PHRASE = {
    "G3_ALIGNMENT_OFFSET": "an element shifted off its expected position",
    "G5_BRAND_COLOR_VIOLATION": "a wrong / off-brand text colour",
    "G6_MARGIN_VIOLATION": "an element too close to / over the slide edge",
}
SHORT = {c: c.split("_")[0] for c in CLASSES}


def load_pool():
    pool = {c: {} for c in CLASSES}  # cls -> stratum -> [rec]
    with PART2_MANIFEST.open() as fh:
        for line in fh:
            r = json.loads(line)
            cls = _defect_of(r)
            if cls not in pool:
                continue
            dp, cp = _def_path(r), _clean_path(r)
            if dp and "__template" in str(dp):
                continue
            if not (dp and cp and dp.exists() and cp.exists()):
                continue
            st = stratum_of(cls, r)
            if not st:
                continue
            pool[cls].setdefault(st, []).append({"rec": r, "def": dp, "clean": cp,
                                                 "src_id": r.get("sample_id")})
    # chromatic (hue) G5 variants — rendered separately (part3_g5_chromatic.py), with an
    # explicit stratum (ΔE≈12·hue / ΔE≈24·hue / ΔE≈40·hue) so the test contrasts an
    # achromatic lightness shift vs a real hue swap at matched ΔE2000.
    chroma = REPO / "data/part3/g5_chromatic.jsonl"
    if chroma.exists():
        with chroma.open() as fh:
            for line in fh:
                r = json.loads(line)
                dp = _abs(r["image_path"])
                cp = _abs(r["metadata"]["clean_image_path"])
                if not (dp and cp and dp.exists() and cp.exists()):
                    continue
                st = r["metadata"]["stratum"]
                pool["G5_BRAND_COLOR_VIOLATION"].setdefault(st, []).append(
                    {"rec": r, "def": dp, "clean": cp, "src_id": r.get("sample_id")})
    # relative-misalignment G3 variants (part3_g3_relmisalign.py): one bullet shifted out
    # of an aligned column -> a perceptually-anchored misalignment (visible without the
    # clean reference), contrasted against the shipped absolute-translation G3 (4px/32px).
    g3rel = REPO / "data/part3/g3_relmisalign.jsonl"
    if g3rel.exists():
        with g3rel.open() as fh:
            for line in fh:
                r = json.loads(line)
                dp, cp = _abs(r["image_path"]), _abs(r["metadata"]["clean_image_path"])
                if not (dp and cp and dp.exists() and cp.exists()):
                    continue
                pool["G3_ALIGNMENT_OFFSET"].setdefault(r["metadata"]["stratum"], []).append(
                    {"rec": r, "def": dp, "clean": cp, "src_id": r.get("sample_id")})
    return pool


def sample(pool, n, seed):
    rng = random.Random(seed)
    picks = []
    for cls in CLASSES:
        for st in sorted(pool[cls]):
            items = list(pool[cls][st])
            rng.shuffle(items)
            for it in items[:n]:
                picks.append({**it, "class": cls, "stratum": st})
    rng.shuffle(picks)
    for i, p in enumerate(picks):
        p["pair_id"] = f"s{i:02d}"
    return picks


def diff_uri(dimg, cimg, amp, quality):
    # |defective - clean|, then NORMALIZE so the brightest real change -> 255. Renders
    # are lossless twins (no noise), so normalization can't amplify artefacts; it makes
    # a sub-perceptual change (ΔE2000≈3 lightness, 2px shift) glow as clearly as a large
    # one. `amp` is an extra boost cap on top (default 1.0 = pure normalize).
    dd = ImageChops.difference(dimg.convert("RGB"), cimg.convert("RGB"))
    mx = max((hi for _lo, hi in dd.getextrema()), default=0) or 1
    scale = (255.0 / mx) * max(amp, 1.0)
    dd = dd.point(lambda x: min(255, int(x * scale)))
    return _data_uri(dd, quality)


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>E8 strict perceptual test</title><style>
 body{font-family:system-ui,Arial,sans-serif;margin:0;background:#1b1b1f;color:#eee}
 header{position:sticky;top:0;background:#26262c;padding:10px 16px;border-bottom:1px solid #3a3a42;z-index:5}
 #prog{font-size:14px;color:#9ad}.wrap{max-width:1300px;margin:0 auto;padding:16px}
 .task{font-size:17px;margin:6px 0}.task b{color:#ffd479}
 .modes button{padding:6px 14px;margin-right:8px;border:1px solid #555;background:#33333a;color:#eee;border-radius:5px;cursor:pointer}
 .modes button.on{background:#2255aa;border-color:#3a78d8}
 #stage{margin:12px 0;min-height:300px}
 #sbs{display:flex;gap:12px}.col{flex:1}.col .cap{padding:3px 0;font-weight:600}
 .def .cap{color:#ff6b6b}.cln .cap{color:#54d98c}
 img.slide{width:100%;border:1px solid #444;border-radius:4px;background:#fff;display:block}
 #blinkbox{position:relative;max-width:760px;margin:auto}#blinkbox img{position:absolute;top:0;left:0}
 #blinkbox img.base{position:relative}
 #blinkflag{position:absolute;top:6px;left:6px;background:#000a;padding:2px 8px;border-radius:4px;font-weight:700}
 #diffwrap{max-width:760px;margin:auto}#diffwrap .hint{color:#888;font-size:13px}
 .q{margin:9px 0;font-size:15px}.q span{display:inline-block;min-width:340px}
 button.opt{padding:6px 16px;margin-right:8px;border:1px solid #555;background:#33333a;color:#eee;border-radius:5px;cursor:pointer}
 button.opt.yes.on{background:#1f7a3d;border-color:#2ecc71}button.opt.no.on{background:#9a2b2b;border-color:#e74c3c}
 textarea{width:100%;height:38px;background:#26262c;color:#eee;border:1px solid #444;border-radius:4px}
 .nav button{padding:8px 18px;margin-right:10px;border-radius:5px;border:1px solid #555;background:#33333a;color:#eee;cursor:pointer}
 #export{background:#2255aa;border-color:#3a78d8;font-weight:600}kbd{background:#000;border:1px solid #555;border-radius:3px;padding:1px 5px;font-size:12px}
</style></head><body>
<header><div id="prog"></div><div style="font-size:12px;color:#888;margin-top:3px">
 modes: <kbd>1</kbd> side-by-side <kbd>2</kbd> blink <kbd>3</kbd> diff &nbsp;|&nbsp; in blink <kbd>space</kbd> = step frame &nbsp;|&nbsp;
 <kbd>q</kbd>/<kbd>Q</kbd> = unaided yes/no, <kbd>a</kbd>/<kbd>A</kbd> = aided yes/no, <kbd>&larr;</kbd>/<kbd>&rarr;</kbd> nav. Autosaves.</div></header>
<div class="wrap">
 <div class="task" id="task"></div>
 <div class="modes"><button data-m="0" class="on">1 · Side-by-side</button><button data-m="1">2 · Blink overlay</button><button data-m="2">3 · Diff (amplified)</button></div>
 <div id="stage"></div>
 <div class="q"><span>Q1 — unaided: first look (side-by-side), is the defect visible?</span>
   <button class="opt yes" data-q="unaided" data-v="yes">Yes</button><button class="opt no" data-q="unaided" data-v="no">No</button></div>
 <div class="q"><span>Q2 — aided: with blink/diff, can you confirm &amp; locate it?</span>
   <button class="opt yes" data-q="aided" data-v="yes">Yes</button><button class="opt no" data-q="aided" data-v="no">No</button></div>
 <div class="q"><textarea id="note" placeholder="optional note"></textarea></div>
 <div class="nav"><button id="prev">&larr; Prev</button><button id="next">Next &rarr;</button><button id="export">Export labels_strict.json</button> <span id="count"></span></div>
</div>
<script>
const PAIRS = __PAIRS_JSON__;
const KEY="e8_strict_v1"; let labels=JSON.parse(localStorage.getItem(KEY)||"{}"); let i=0,mode=0,blinkOn=false,timer=null;
function cur(){return PAIRS[i];}
function stage(){
 const p=cur(); const s=document.getElementById("stage");
 if(timer){clearInterval(timer);timer=null;}
 if(mode===0){s.innerHTML=`<div id=sbs><div class="col def"><div class=cap>DEFECTIVE</div><img class=slide src="${p.def}"></div><div class="col cln"><div class=cap>CLEAN twin</div><img class=slide src="${p.clean}"></div></div>`;}
 else if(mode===1){s.innerHTML=`<div id=blinkbox><img class="slide base" src="${p.clean}"><img id=ov class=slide src="${p.def}"><div id=blinkflag>DEFECTIVE</div></div>`;
   let show=true; const ov=document.getElementById("ov"),flag=document.getElementById("blinkflag");
   timer=setInterval(()=>{show=!show;ov.style.visibility=show?"visible":"hidden";flag.textContent=show?"DEFECTIVE":"CLEAN";flag.style.color=show?"#ff6b6b":"#54d98c";},560);}
 else {s.innerHTML=`<div id=diffwrap><div class=hint>amplified |defective − clean| — changed pixels glow; black = identical</div><img class=slide src="${p.diff}"></div>`;}
}
function render(){
 const p=cur();
 document.getElementById("task").innerHTML=`Pair <b>${i+1}/${PAIRS.length}</b> &nbsp; <b>${p.cls}</b> &mdash; look for: <b>${p.phrase}</b>`;
 document.querySelectorAll(".modes button").forEach(b=>b.classList.toggle("on",+b.dataset.m===mode));
 const rec=labels[p.id]||{};
 document.querySelectorAll("button.opt").forEach(b=>b.classList.toggle("on",rec[b.dataset.q]===b.dataset.v));
 document.getElementById("note").value=rec.note||"";
 const done=Object.keys(labels).filter(k=>labels[k].unaided&&labels[k].aided).length;
 document.getElementById("prog").innerHTML=`E8 strict perceptual test &mdash; ${done}/${PAIRS.length} complete`;
 document.getElementById("count").textContent=`${done}/${PAIRS.length}`;
 stage();
}
function setv(q,v){const p=cur();labels[p.id]=labels[p.id]||{cls:p.cls,stratum:p.stratum};labels[p.id][q]=v;labels[p.id].note=document.getElementById("note").value;localStorage.setItem(KEY,JSON.stringify(labels));render();}
document.querySelectorAll("button.opt").forEach(b=>b.onclick=()=>setv(b.dataset.q,b.dataset.v));
document.querySelectorAll(".modes button").forEach(b=>b.onclick=()=>{mode=+b.dataset.m;render();});
document.getElementById("note").oninput=()=>{const p=cur();labels[p.id]=labels[p.id]||{cls:p.cls,stratum:p.stratum};labels[p.id].note=document.getElementById("note").value;localStorage.setItem(KEY,JSON.stringify(labels));};
document.getElementById("prev").onclick=()=>{i=(i-1+PAIRS.length)%PAIRS.length;mode=0;render();};
document.getElementById("next").onclick=()=>{i=(i+1)%PAIRS.length;mode=0;render();};
document.getElementById("export").onclick=()=>{const out={};PAIRS.forEach(p=>out[p.id]=labels[p.id]||{cls:p.cls,stratum:p.stratum});const b=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="labels_strict.json";a.click();};
document.addEventListener("keydown",e=>{if(e.target.tagName==="TEXTAREA")return;
 if(e.key==="1")mode=0,render();else if(e.key==="2")mode=1,render();else if(e.key==="3")mode=2,render();
 else if(e.key==="q")setv("unaided","yes");else if(e.key==="Q")setv("unaided","no");
 else if(e.key==="a")setv("aided","yes");else if(e.key==="A")setv("aided","no");
 else if(e.key==="ArrowLeft")document.getElementById("prev").click();else if(e.key==="ArrowRight")document.getElementById("next").click();
 else if(e.key===" "&&mode===1){e.preventDefault();const ov=document.getElementById("ov");if(ov)ov.style.visibility=ov.style.visibility==="hidden"?"visible":"hidden";}});
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-stratum", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20260624)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    ap.add_argument("--img-width", type=int, default=1024)
    ap.add_argument("--amp", type=float, default=6.0)
    ap.add_argument("--quality", type=int, default=88)
    ap.add_argument("--only-stratum", default=None,
                    help="keep only strata whose label contains this substring (e.g. 'rel·' for the relative-G3 mini-set)")
    ap.add_argument("--out-name", default="strict", help="basename: manifest_<name>.json / spotcheck_<name>.html")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pool = load_pool()
    if args.only_stratum:
        for c in CLASSES:
            pool[c] = {st: v for st, v in pool[c].items() if args.only_stratum in st}
    print("[pool] strata available:")
    for c in CLASSES:
        print(f"  {c}: " + ", ".join(f"{st}={len(v)}" for st, v in sorted(pool[c].items())))
    picks = sample(pool, args.n_per_stratum, args.seed)

    manifest, hp = [], []
    for p in picks:
        d = _load_rgb(p["def"], args.img_width)
        c = _load_rgb(p["clean"], args.img_width)
        manifest.append({"pair_id": p["pair_id"], "class": p["class"], "stratum": p["stratum"],
                         "phrase": PHRASE[p["class"]], "src_id": p["src_id"]})
        hp.append({"id": p["pair_id"], "cls": p["class"], "stratum": p["stratum"], "phrase": PHRASE[p["class"]],
                   "def": _data_uri(d, args.quality), "clean": _data_uri(c, args.quality),
                   "diff": diff_uri(d, c, args.amp, args.quality)})

    (out / f"manifest_{args.out_name}.json").write_text(json.dumps(manifest, indent=2))
    html = HTML.replace("__PAIRS_JSON__", json.dumps(hp))
    (out / f"spotcheck_{args.out_name}.html").write_text(html)
    bycls: dict[str, dict[str, int]] = {}
    for m in manifest:
        bycls.setdefault(m["class"], {})
        bycls[m["class"]][m["stratum"]] = bycls[m["class"]].get(m["stratum"], 0) + 1
    print(f"[sample] {len(manifest)} pairs across strata: " +
          " | ".join(f"{SHORT[c]}:{s}" for c, s in bycls.items()))
    print(f"[write] {out/f'manifest_{args.out_name}.json'}")
    print(f"[write] {out/f'spotcheck_{args.out_name}.html'}  ({len(html.encode())/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
