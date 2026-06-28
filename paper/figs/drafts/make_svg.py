#!/usr/bin/env python3
"""Hand-authored vector finals for the five concept figures.

Each function returns an SVG string. Compositions follow the .2 draft
renders in this folder, but every shape and label is redrawn cleanly
(no auto-trace) so the output is small, editable, and print-safe.
Run:  python3 make_svg.py    -> writes *.svg + *.pdf + *_preview.png
"""
from pathlib import Path
import cairosvg

OUT = Path(__file__).parent

# ---- palette -------------------------------------------------------------
INK    = "#2B3440"   # dark stroke / text
SLATE  = "#5A6675"   # neutral arrows / text
BLUE   = "#3F6FB5"   # linter / perception-true path
BLUE_L = "#AFC6E6"
ORANGE = "#E07F2C"   # VLM / format-suppressed path
ORANGE_L = "#F2C79A"
GREY   = "#9AA4B0"
GREY_L = "#E7EBF0"
PANEL  = "#F5F7FA"
DASHC  = "#7E8896"
RED    = "#D24A43"
GREEN  = "#4E9A6B"
NEUT   = "#8A93A0"

FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"

# ---- low-level helpers ---------------------------------------------------
def rrect(x, y, w, h, r, fill="none", stroke="none", sw=0, dash=None, op=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} '
            f'opacity="{op}"/>')

def line(x1, y1, x2, y2, stroke=SLATE, sw=2, dash=None, cap="round"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linecap="{cap}"{d}/>')

NOTEXT = False        # when True, txt() draws nothing and records the label instead
LABELS = []           # collected (x,y,s,size,fill,anchor,weight,style) in NOTEXT mode

def txt(x, y, s, size=20, fill=INK, anchor="middle", weight="400", style="normal"):
    if NOTEXT:
        LABELS.append(dict(x=x, y=y, s=s, size=size, fill=fill,
                           anchor=anchor, weight=weight, style=style))
        return ""
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" '
            f'font-style="{style}">{s}</text>')

def bar(x, y, w, h, fill=GREY, r=3, op=1):
    return rrect(x, y, w, h, r, fill=fill, op=op)

def mountain(x, y, w, h, bg=BLUE_L, ink=BLUE, op=1):
    """little image-placeholder thumbnail."""
    s = [rrect(x, y, w, h, 4, fill=bg, op=op)]
    s.append(f'<circle cx="{x+w*0.30}" cy="{y+h*0.30}" r="{h*0.11}" '
             f'fill="#FFFFFF" opacity="{0.85*op}"/>')
    p1 = f'{x+w*0.10},{y+h*0.82} {x+w*0.40},{y+h*0.45} {x+w*0.62},{y+h*0.82}'
    p2 = f'{x+w*0.45},{y+h*0.82} {x+w*0.70},{y+h*0.55} {x+w*0.92},{y+h*0.82}'
    s.append(f'<polygon points="{p1}" fill="{ink}" opacity="{op}"/>')
    s.append(f'<polygon points="{p2}" fill="{ink}" opacity="{0.7*op}"/>')
    return "".join(s)

def arrow_marker(idn, color):
    return (f'<marker id="{idn}" markerWidth="9" markerHeight="9" refX="6.5" '
            f'refY="3.2" orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M0,0 L7,3.2 L0,6.4 Z" fill="{color}"/></marker>')

def path(d, stroke=SLATE, sw=3, marker=None, fill="none", dash=None):
    m = f' marker-end="url(#{marker})"' if marker else ""
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linejoin="round" stroke-linecap="round"{m}{da}/>')

# ---- icon glyphs ---------------------------------------------------------
def icon_ruler(cx, cy, s, color=BLUE):
    """right-triangle ruler over a faint grid."""
    g = []
    for i in range(1, 4):
        g.append(line(cx-s, cy-s+i*s/2, cx+s, cy-s+i*s/2, stroke=color, sw=1, dash="3 4", cap="butt"))
        g.append(line(cx-s+i*s/2, cy-s, cx-s+i*s/2, cy+s, stroke=color, sw=1, dash="3 4", cap="butt"))
    tri = f'{cx-s*0.7},{cy+s*0.7} {cx+s*0.7},{cy+s*0.7} {cx-s*0.7},{cy-s*0.55}'
    g.append(f'<polygon points="{tri}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round"/>')
    for i in range(1, 4):
        g.append(line(cx-s*0.7+i*s*0.35, cy+s*0.7, cx-s*0.7+i*s*0.35, cy+s*0.55, stroke=color, sw=1.6))
    return "".join(g)

def icon_eye(cx, cy, s, color=ORANGE):
    d = (f'M{cx-s},{cy} Q{cx},{cy-s*0.85} {cx+s},{cy} '
         f'Q{cx},{cy+s*0.85} {cx-s},{cy} Z')
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.4"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{s*0.34}" fill="{color}"/>')

def icon_scale(cx, cy, s, color=INK, lc=BLUE, rc=ORANGE):
    g = [line(cx, cy-s*0.9, cx, cy+s*0.9, stroke=color, sw=2.6),         # post
         line(cx-s, cy-s*0.7, cx+s, cy-s*0.7, stroke=color, sw=2.6),     # beam
         f'<circle cx="{cx}" cy="{cy-s*0.9}" r="3.2" fill="{color}"/>',
         line(cx-s*0.55, cy+s*0.9, cx+s*0.55, cy+s*0.9, stroke=color, sw=2.6)]
    for px, pc in [(cx-s, lc), (cx+s, rc)]:
        g.append(line(px, cy-s*0.7, px-s*0.32, cy-s*0.05, stroke=color, sw=1.6))
        g.append(line(px, cy-s*0.7, px+s*0.32, cy-s*0.05, stroke=color, sw=1.6))
        g.append(f'<path d="M{px-s*0.34},{cy-s*0.05} Q{px},{cy+s*0.30} {px+s*0.34},{cy-s*0.05} Z" '
                 f'fill="{pc}" opacity="0.85"/>')
    return "".join(g)

def icon_net(cx, cy, s, color=SLATE):
    pts = [(-s,-s*0.5),(-s,s*0.5),(0,-s),(0,0),(0,s),(s,-s*0.5),(s,s*0.5)]
    g = []
    edges = [(0,3),(1,3),(2,3),(4,3),(3,5),(3,6),(2,5),(4,6)]
    for a,b in edges:
        g.append(line(cx+pts[a][0], cy+pts[a][1], cx+pts[b][0], cy+pts[b][1], stroke=color, sw=1.4))
    for px,py in pts:
        g.append(f'<circle cx="{cx+px}" cy="{cy+py}" r="{s*0.16}" fill="{color}"/>')
    return "".join(g)

def icon_magnifier(cx, cy, s, color=INK):
    return (f'<circle cx="{cx-s*0.15}" cy="{cy-s*0.15}" r="{s*0.55}" fill="none" '
            f'stroke="{color}" stroke-width="2.6"/>'
            f'<line x1="{cx+s*0.28}" y1="{cy+s*0.28}" x2="{cx+s*0.7}" y2="{cy+s*0.7}" '
            f'stroke="{color}" stroke-width="3" stroke-linecap="round"/>')

def icon_crosshair(cx, cy, s, color=INK):
    g = [f'<circle cx="{cx}" cy="{cy}" r="{s*0.5}" fill="none" stroke="{color}" stroke-width="2.4"/>',
         f'<circle cx="{cx}" cy="{cy}" r="{s*0.12}" fill="{color}"/>']
    for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
        g.append(line(cx+dx*s*0.5, cy+dy*s*0.5, cx+dx*s*0.8, cy+dy*s*0.8, stroke=color, sw=2.4))
    return "".join(g)

def icon_wrench(cx, cy, s, color=INK):
    # diagonal handle + open-jaw head
    g = [f'<line x1="{cx-s*0.55}" y1="{cy+s*0.55}" x2="{cx+s*0.18}" y2="{cy-s*0.18}" '
         f'stroke="{color}" stroke-width="{s*0.30}" stroke-linecap="round"/>']
    g.append(f'<path d="M{cx+s*0.58},{cy-s*0.66} a{s*0.36},{s*0.36} 0 1 1 -{s*0.34},{s*0.12}" '
             f'fill="none" stroke="{color}" stroke-width="{s*0.24}" stroke-linecap="round"/>')
    return "".join(g)

def cross_out(cx, cy, s, color=RED):
    return (line(cx-s, cy-s, cx+s, cy+s, stroke=color, sw=4) +
            line(cx-s, cy+s, cx+s, cy-s, stroke=color, sw=4))

def check_badge(cx, cy, r, color=GREEN):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'
            f'<path d="M{cx-r*0.42},{cy} l{r*0.28},{r*0.32} l{r*0.6},{-r*0.62}" '
            f'fill="none" stroke="#fff" stroke-width="{r*0.18}" stroke-linecap="round" stroke-linejoin="round"/>')

def cross_badge(cx, cy, r, color=RED):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'
            f'<path d="M{cx-r*0.4},{cy-r*0.4} l{r*0.8},{r*0.8} M{cx-r*0.4},{cy+r*0.4} l{r*0.8},{-r*0.8}" '
            f'stroke="#fff" stroke-width="{r*0.18}" stroke-linecap="round"/>')

def svg_wrap(w, h, body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}"><defs>{defs}</defs>'
            f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>{body}</svg>')

def slide_card(x, y, w, h, accent=BLUE, accent_l=BLUE_L, sw=2.2, stroke=INK,
               lines=4, img=True, chart=False, op=1):
    s = [rrect(x, y, w, h, 8, fill="#fff", stroke=stroke, sw=sw, op=op)]
    s.append(bar(x+w*0.07, y+h*0.10, w*0.45, h*0.075, fill=accent, op=op))   # title
    if img:
        s.append(mountain(x+w*0.07, y+h*0.28, w*0.38, h*0.40, bg=accent_l, ink=accent, op=op))
        tx = x+w*0.52
        for i in range(lines):
            s.append(bar(tx, y+h*0.30+i*h*0.12, w*0.40, h*0.05, fill=GREY, op=op))
    return "".join(s), s

# =========================================================================
# FIG 1 — teaser: diagnosis routes to two engines, converge in hybrid critic
# =========================================================================
def fig_teaser():
    W, H = 1200, 770
    defs = (arrow_marker("aGrey", SLATE) + arrow_marker("aBlue", BLUE) +
            arrow_marker("aOrange", ORANGE))
    b = []
    # input slide
    card, _ = slide_card(60, 300, 220, 150, accent=SLATE, accent_l=GREY_L, lines=3)
    b.append(card)
    b.append(txt(170, 478, "input slide", size=19, fill=SLATE))
    # diamond diagnosis
    dcx, dcy, dr = 430, 375, 72
    b.append(f'<polygon points="{dcx},{dcy-dr} {dcx+dr},{dcy} {dcx},{dcy+dr} {dcx-dr},{dcy}" '
             f'fill="{PANEL}" stroke="{INK}" stroke-width="2.2"/>')
    b.append(txt(dcx, dcy-4, "perception /", size=17, fill=INK))
    b.append(txt(dcx, dcy+16, "reasoning", size=17, fill=INK))
    b.append(txt(dcx, dcy+34, "diagnosis", size=17, fill=INK, weight="600"))
    # arrow input->diamond
    b.append(path(f'M285,375 L{dcx-dr-6},375', stroke=SLATE, sw=3, marker="aGrey"))
    # top branch -> linter
    lx, ly, lw, lh = 600, 95, 170, 130
    b.append(path(f'M{dcx},{dcy-dr} V160 H{lx-6}', stroke=BLUE, sw=3, marker="aBlue"))
    b.append(rrect(lx, ly, lw, lh, 12, fill="#fff", stroke=BLUE, sw=2.4))
    b.append(icon_ruler(lx+lw/2, ly+lh*0.42, 34, color=BLUE))
    b.append(txt(lx+lw/2, ly+lh+26, "symbolic linter", size=19, fill=BLUE, weight="600"))
    b.append(txt(lx+lw/2, ly+lh+48, "declared geometry", size=16, fill=SLATE))
    # bottom branch -> VLM
    vx, vy, vw, vh = 600, 500, 170, 135
    b.append(path(f'M{dcx},{dcy+dr} V570 H{vx-6}', stroke=ORANGE, sw=3, marker="aOrange"))
    b.append(rrect(vx, vy, vw, vh, 12, fill="#fff", stroke=ORANGE, sw=2.4))
    b.append(icon_eye(vx+vw/2, vy+34, 26, color=ORANGE))
    sc,_ = slide_card(vx+vw*0.22, vy+58, vw*0.56, vh*0.42, accent=ORANGE, accent_l=ORANGE_L, sw=1.6, lines=2)
    b.append(sc)
    b.append(txt(vx+vw/2, vy+vh+26, "re-elicited VLM", size=19, fill=ORANGE, weight="600"))
    b.append(txt(vx+vw/2, vy+vh+48, "format-suppressed", size=16, fill=SLATE))
    # hybrid critic
    hx, hy, hw, hh = 980, 295, 175, 160
    b.append(path(f'M{lx+lw},160 H{hx+hw/2} V{hy-6}', stroke=BLUE, sw=3, marker="aBlue"))
    b.append(path(f'M{vx+vw},567 H{hx+hw/2} V{hy+hh+6}', stroke=ORANGE, sw=3, marker="aOrange"))
    b.append(rrect(hx, hy, hw, hh, 12, fill=PANEL, stroke=INK, sw=2.4))
    b.append(icon_scale(hx+hw/2, hy+hh*0.42, 38))
    b.append(txt(hx+hw/2, hy+hh+26, "hybrid critic", size=20, fill=INK, weight="600"))
    # title + G7 footnote
    b.append(txt(W/2, 44, "Diagnosis routes each defect to its bottleneck-appropriate engine",
                 size=23, fill=INK, weight="600"))
    b.append(txt(W/2, 748, "G7 render-overflow (legal box, overflowing pixels) is linter-blind by "
                 "construction; only a rendered-quality read-out catches it",
                 size=16, fill=SLATE, style="italic"))
    return svg_wrap(W, H, "".join(b), defs)

# =========================================================================
# FIG 2 — G7 render-overflow: declared box legal, pixels overflow
# =========================================================================
def fig_g7():
    W, H = 1200, 720
    b = []
    b.append(txt(W/2, 46, "G7 render-overflow: the declared box is legal; only the rendered pixels overflow",
                 size=22, fill=INK, weight="600"))
    def deck(x, overflow):
        s = []
        cw, ch = 470, 470
        y = 100
        s.append(rrect(x, y, cw, ch, 10, fill="#fff", stroke=INK, sw=2.4))
        # header
        s.append(f'<circle cx="{x+50}" cy="{y+48}" r="20" fill="{GREY}"/>')
        s.append(bar(x+85, y+38, 200, 20, fill=GREY))
        s.append(line(x+30, y+88, x+cw-30, y+88, stroke=GREY_L, sw=2))
        # declared box (identical in both)
        dx, dy, dw, dh = x+45, y+115, cw-90, ch-180
        s.append(rrect(dx, dy, dw, dh, 4, stroke=DASHC, sw=2, dash="7 6"))
        # 7 text lines
        for i in range(7):
            ly = dy+28+i*((dh-50)/6)
            base = dw-60
            extra = [40,70,55,30,95,60,18][i] if overflow else 0
            grey_w = base if overflow else [base,base,base,base,base,base,base*0.62][i]
            s.append(f'<rect x="{dx+30}" y="{ly-8}" width="11" height="11" rx="2" fill="{GREY}"/>')
            s.append(bar(dx+50, ly-9, grey_w, 15, fill=GREY))
            if overflow:
                s.append(bar(dx+50+grey_w, ly-9, extra, 15, fill=RED))
        # page-number chip
        s.append(bar(x+cw-70, y+ch-40, 40, 12, fill=GREY))
        return "".join(s), (x+cw/2, y+ch)
    left, (lcx, lby) = deck(70, overflow=False)
    right, (rcx, rby) = deck(660, overflow=True)
    b.append(left); b.append(right)
    b.append(check_badge(lcx, lby+45, 28))
    b.append(cross_badge(rcx, rby+45, 28))
    b.append(txt(lcx, lby+100, "rendered text fits the box", size=20, fill=INK))
    b.append(txt(rcx, rby+100, "rendered pixels overflow the box", size=20, fill=INK))
    b.append(txt(W/2, 690, "The linter sees two identical, legal declared boxes — it is blind to the difference by construction",
                 size=16, fill=SLATE, style="italic"))
    return svg_wrap(W, H, "".join(b))

# =========================================================================
# FIG 3 — attribution protocol: modality (rows) x task (cols)
# =========================================================================
def fig_modtask():
    W, H = 1200, 820
    b = []
    b.append(txt(W/2, 44, "Attribution protocol: every paired slide seen under 4 input modalities × 3 tasks",
                 size=22, fill=INK, weight="600"))
    # grid geometry
    x0, y0 = 250, 90
    colw, rowh = 290, 150
    cols = [("Detect", icon_magnifier), ("Localize", icon_crosshair), ("Repair", icon_wrench)]
    rows = ["image-only", "structured oracle", "VLM-caption", "image + oracle"]
    # column headers
    for c, (name, ic) in enumerate(cols):
        cx = x0 + colw*c + colw/2
        b.append(ic(cx, y0+30, 22))
        b.append(txt(cx, y0+72, name, size=19, fill=INK, weight="600"))
    hdr = 90
    # row modality glyph drawer
    def modality(cx, cy, kind, op=1, scale=1.0):
        w, h = 150*scale, 95*scale
        if kind == 0:    # image-only slide
            sc,_ = slide_card(cx-w/2, cy-h/2, w, h, accent=BLUE, accent_l=BLUE_L, sw=1.8, lines=3, op=op)
            return sc
        if kind == 1:    # structured oracle = dashed wireframe
            g=[rrect(cx-w/2, cy-h/2, w, h, 4, stroke=BLUE, sw=1.6, dash="6 5", op=op)]
            g.append(rrect(cx-w/2+10, cy-h/2+10, w*0.5, h*0.30, 2, stroke=BLUE, sw=1.4, dash="5 4", op=op))
            g.append(rrect(cx-w/2+10, cy+2, w*0.5, h*0.32, 2, stroke=BLUE, sw=1.4, dash="5 4", op=op))
            g.append(rrect(cx+2, cy-h/2+10, w*0.40, h*0.66, 2, stroke=BLUE, sw=1.4, dash="5 4", op=op))
            return "".join(g)
        if kind == 2:    # caption bubble
            g=[f'<path d="M{cx-w*0.42},{cy-h*0.34} h{w*0.84} a10,10 0 0 1 10,10 v{h*0.40} '
               f'a10,10 0 0 1 -10,10 h{-w*0.62} l{-12},16 v-16 h{-w*0.22+12} '
               f'a10,10 0 0 1 -10,-10 v{-h*0.40} a10,10 0 0 1 10,-10 Z" '
               f'fill="none" stroke="{SLATE}" stroke-width="1.8" opacity="{op}"/>']
            for i in range(3):
                g.append(bar(cx-w*0.32, cy-h*0.20+i*15, w*(0.5-0.08*i), 6, fill=SLATE, op=op))
            return "".join(g)
        # kind 3: image + oracle overlay
        sc,_ = slide_card(cx-w/2, cy-h/2, w, h, accent=BLUE, accent_l=BLUE_L, sw=1.6, lines=3, op=0.55*op)
        ov = rrect(cx-w/2, cy-h/2, w, h, 4, stroke=BLUE, sw=1.5, dash="5 4", op=op)
        return sc+ov
    for r, name in enumerate(rows):
        cy = y0 + hdr + rowh*r + rowh/2
        # row label + modality glyph in label column
        b.append(modality(x0-130, cy, r, scale=0.78))
        b.append(txt(x0-130, cy+58, name, size=17, fill=INK, weight="600"))
        for c, (_, ic) in enumerate(cols):
            cx = x0 + colw*c + colw/2
            b.append(rrect(x0+colw*c+18, cy-rowh/2+10, colw-36, rowh-20, 8,
                           fill=PANEL, stroke=GREY_L, sw=1.4))
            b.append(modality(cx-26, cy, r, op=0.9, scale=0.74))
            b.append(ic(cx+58, cy+26, 17))
    return svg_wrap(W, H, "".join(b))

# =========================================================================
# FIG 4 — relative vs. absolute elicitation
# =========================================================================
def fig_relabs():
    W, H = 1200, 640
    b = []
    # left panel: absolute / pointwise
    b.append(rrect(50, 70, 510, 500, 16, fill="#F3F5F9", stroke=BLUE_L, sw=2))
    b.append(txt(305, 120, "absolute  (pointwise)", size=22, fill=INK, weight="600"))
    b.append(f'<circle cx="305" cy="200" r="40" fill="{GREY_L}" stroke="{SLATE}" stroke-width="1.5"/>')
    b.append(txt(305, 214, "?", size=46, fill=SLATE, weight="700"))
    b.append(line(305, 244, 305, 300, stroke=SLATE, sw=2, dash="3 5"))
    sc,_ = slide_card(150, 305, 310, 210, accent=BLUE, accent_l=BLUE_L, lines=4)
    b.append(sc)
    b.append(txt(305, 548, "score one slide alone → at chance for G1/S6",
                 size=17, fill=SLATE, style="italic"))
    # right panel: relative / forced choice
    b.append(rrect(640, 70, 510, 500, 16, fill="#FBF4EC", stroke=ORANGE_L, sw=2))
    b.append(txt(895, 120, "relative  (forced choice)", size=22, fill=INK, weight="600"))
    b.append(icon_scale(895, 200, 40))
    # two slides on a balance
    b.append(line(820, 250, 820, 320, stroke=SLATE, sw=2, dash="3 5"))
    b.append(line(970, 250, 970, 320, stroke=SLATE, sw=2, dash="3 5"))
    sl,_ = slide_card(688, 325, 195, 175, accent=BLUE, accent_l=BLUE_L, sw=1.8, lines=3)
    sr,_ = slide_card(905, 325, 195, 175, accent=ORANGE, accent_l=ORANGE_L, sw=1.8, lines=3)
    b.append(sl); b.append(sr)
    b.append(txt(895, 548, "compare a pair → recovers perfect detection",
                 size=17, fill=SLATE, style="italic"))
    b.append(txt(W/2, 42, "Same model, same images; only the elicitation changes",
                 size=22, fill=INK, weight="600"))
    return svg_wrap(W, H, "".join(b))

# =========================================================================
# FIG 5 — open-world: structure recovered from pixels does not restore linter
# =========================================================================
def fig_openworld():
    W, H = 1280, 620
    defs = arrow_marker("aGrey5", SLATE)
    b = []
    b.append(txt(W/2, 42, "Open world: structure recovered from pixels does not restore the symbolic linter",
                 size=22, fill=INK, weight="600"))
    # raw slide (no IR)
    sc,_ = slide_card(60, 230, 240, 175, accent=BLUE, accent_l=BLUE_L, lines=3, chart=True)
    b.append(sc)
    # add a tiny bar chart to raw slide
    bx, by = 200, 360
    for i,(hh,cl) in enumerate([(18,BLUE_L),(30,BLUE),(40,GREEN)]):
        b.append(bar(bx+i*16, by-hh, 11, hh, fill=cl))
    b.append(txt(180, 432, "raw pixels (no IR)", size=18, fill=SLATE))
    b.append(path("M312,317 H372", stroke=SLATE, sw=3, marker="aGrey5"))
    # layout parser
    b.append(rrect(380, 262, 130, 110, 12, fill=PANEL, stroke=SLATE, sw=2))
    b.append(icon_net(445, 312, 30))
    b.append(txt(445, 398, "layout parser", size=18, fill=SLATE))
    b.append(path("M518,317 H578", stroke=SLATE, sw=3, marker="aGrey5"))
    # recovered structure (dashed wireframe)
    rx, ry, rw, rh = 588, 240, 240, 160
    b.append(rrect(rx, ry, rw, rh, 8, fill="#fff", stroke=GREY, sw=1.6))
    b.append(rrect(rx+18, ry+16, rw-36, 24, 2, stroke=DASHC, sw=1.4, dash="5 4"))
    b.append(rrect(rx+18, ry+50, rw*0.42, rh-78, 2, stroke=DASHC, sw=1.4, dash="5 4"))
    b.append(rrect(rx+rw*0.50, ry+50, rw*0.42, rh*0.34, 2, stroke=DASHC, sw=1.4, dash="5 4"))
    b.append(rrect(rx+rw*0.50, ry+rh*0.55, rw*0.42, rh*0.30, 2, stroke=DASHC, sw=1.4, dash="5 4"))
    b.append(txt(rx+rw/2, ry+rh+28, "recovered structure", size=18, fill=SLATE))
    b.append(txt(rx+rw/2, ry+rh+50, "(approximate, not native IR)", size=14, fill=GREY, style="italic"))
    # fork
    b.append(path(f"M{rx+rw},320 H900 V150 H958", stroke=SLATE, sw=3, marker="aGrey5"))
    b.append(path(f"M{rx+rw},320 H900 V490 H958", stroke=SLATE, sw=3, marker="aGrey5"))
    # linter crossed out
    b.append(rrect(965, 95, 150, 120, 12, fill="#FBEDEC", stroke=RED, sw=2))
    b.append(icon_ruler(1040, 150, 30, color=GREY))
    b.append(cross_out(1040, 150, 42, color=RED))
    b.append(txt(1040, 238, "symbolic linter", size=18, fill=RED, weight="600"))
    b.append(txt(1040, 260, "not restored", size=15, fill=RED, style="italic"))
    # VLM active
    b.append(rrect(965, 430, 150, 120, 12, fill="#fff", stroke=BLUE, sw=2))
    b.append(icon_eye(1040, 472, 26, color=BLUE))
    scv,_ = slide_card(1000, 500, 80, 40, accent=BLUE, accent_l=BLUE_L, sw=1.4, lines=2)
    b.append(scv)
    b.append(txt(1030, 575, "re-elicited VLM", size=18, fill=BLUE, weight="600"))
    b.append(check_badge(1108, 569, 11, color=GREEN))
    return svg_wrap(W, H, "".join(b), defs)

# ---- build ---------------------------------------------------------------
FIGS = {
    "fig_teaser":     fig_teaser,
    "fig_g7_overflow":fig_g7,
    "fig_modality_task":fig_modtask,
    "fig_rel_vs_abs": fig_relabs,
    "fig_openworld":  fig_openworld,
}

# ---- overpic emitter -----------------------------------------------------
import re

COLOR_NAME = {INK:"figink", SLATE:"figslate", BLUE:"figblue", ORANGE:"figorange",
              RED:"figred", GREEN:"figgreen", GREY:"figgrey", DASHC:"figslate"}

def latex_escape(s):
    s = (s.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")
           .replace("_", r"\_"))
    s = (s.replace("×", r"$\times$").replace("→", r"$\rightarrow$")
           .replace("≈", r"$\approx$").replace("—", "--").replace("·", r"$\cdot$"))
    return s

def latex_size(sz):
    if sz >= 22: return r"\small"
    if sz >= 18: return r"\footnotesize"
    return r"\scriptsize"

def overpic_block(name, W, H, labels):
    out = [f"% ---- {name}: text overlay (font follows the paper, edit here) ----",
           f"% tip: add  grid,tics=10  to the options below to align, then remove.",
           f"\\begin{{overpic}}[width=\\linewidth,percent]{{figs/{name}_notext.pdf}}%"]
    for L in labels:
        xop = round(100 * L["x"] / W, 2)
        yop = round(100 * (H - L["y"]) / W, 2)
        pos = {"middle":"b", "start":"lb", "end":"rb"}.get(L["anchor"], "b")
        fmt = latex_size(L["size"])
        if L["weight"] in ("600", "700"): fmt += r"\bfseries"
        if L["style"] == "italic":        fmt += r"\itshape"
        cname = COLOR_NAME.get(L["fill"], "figink")
        body = f'{fmt}\\color{{{cname}}} {latex_escape(L["s"])}'
        line_ = f'  \\put({xop},{yop}){{\\makebox(0,0)[{pos}]{{{body}}}}}'
        if L["size"] >= 22:   # in-figure title: usually redundant with \caption
            line_ = "%" + line_ + "   % title -- drop if you use \\caption"
        out.append(line_)
    out.append(r"\end{overpic}")
    return "\n".join(out)

PREAMBLE = "\n".join([
    "% ---- add once to the preamble ----",
    r"\usepackage[percent]{overpic}",
    r"\definecolor{figink}{HTML}{2B3440}",
    r"\definecolor{figslate}{HTML}{5A6675}",
    r"\definecolor{figblue}{HTML}{3F6FB5}",
    r"\definecolor{figorange}{HTML}{E07F2C}",
    r"\definecolor{figred}{HTML}{D24A43}",
    r"\definecolor{figgreen}{HTML}{4E9A6B}",
    r"\definecolor{figgrey}{HTML}{9AA4B0}",
])

if __name__ == "__main__":
    # pass 1: full figures (text baked in) -- kept as visual reference
    NOTEXT = False
    for name, fn in FIGS.items():
        svg = fn()
        (OUT / f"{name}.svg").write_text(svg)
        cairosvg.svg2pdf(bytestring=svg.encode(), write_to=str(OUT / f"{name}.pdf"))
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(OUT / f"{name}_preview.png"), scale=1.3)
        print("wrote", name, "(.svg/.pdf/_preview.png)")
    # pass 2: text-free base art + overpic overlay blocks (plan B)
    (OUT / "_preamble.tex").write_text(PREAMBLE + "\n")
    for name, fn in FIGS.items():
        NOTEXT = True
        LABELS = []
        nsvg = fn()                      # text suppressed, labels collected
        labels = list(LABELS)
        (OUT / f"{name}_notext.svg").write_text(nsvg)
        cairosvg.svg2pdf(bytestring=nsvg.encode(), write_to=str(OUT / f"{name}_notext.pdf"))
        cairosvg.svg2png(bytestring=nsvg.encode(), write_to=str(OUT / f"{name}_notext_preview.png"), scale=1.3)
        m = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', nsvg)
        W, H = float(m.group(1)), float(m.group(2))
        (OUT / f"{name}_overpic.tex").write_text(overpic_block(name, W, H, labels) + "\n")
        print("wrote", name, f"_notext.pdf + _overpic.tex ({len(labels)} labels)")
    NOTEXT = False
