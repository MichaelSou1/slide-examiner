#!/usr/bin/env python
"""Drive AutoPresent (SlidesLib code-gen) over mimo to produce real .pptx (todo_0625 R5).

Faithful to AutoPresent: reuses its exact SYSTEM_MESSAGE + INSTRUCTION template, its
library.py API doc, its extract_code_pieces extractor, and real SlidesBench task
instructions. Deviations (all defensible): mimo-v2.5-pro instead of gpt-4o, thinking-off
serving flag, robust file execution instead of the `python -m` path hack, and a
dependency-light SlidesLib shim (verbatim layout helpers; image/search stubbed to a
placeholder; LLM -> mimo) so generation runs offline.

Output: one .pptx per task in --out-dir, then run scripts/part3_g7_prevalence.py on it.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AP = Path("/home/gpus/external_agents/AutoPresent")
SHIM = Path("/home/gpus/external_agents/ap_shim")
sys.path.insert(0, str(AP / "generate"))  # for utils.extract_code_pieces

SYSTEM_MESSAGE = """* You are an expert presentation slides designer who creates modern, fashionable, and stylish slides using Python code. Your job is to generate the required PPTX slide by writing and executing a Python script. Make sure to follow the guidelines below and do not skip any of them:
1.  Ensure your code can successfully execute. If needed, you can also write tests to verify your code.
2. Maintain proper spacing and arrangements of elements in the slide: make sure to keep sufficient spacing between different elements; do not make elements overlap or overflow to the slide page.
3. Carefully select the colors of text, shapes, and backgrounds, to ensure all contents are readable.
4. The slides should not look empty or incomplete. When filling the content in the slides, maintain good design and layout."""

INSTRUCTION = """Follow the instruction below to create the slide.
If the instruction is long and specific, follow the instruction carefully and add all elements as required;
if it is short and concise, you will need to create some content (text, image, layout) and implement it into the slide.
{}

Finally, your code should save the pptx file to path "{}"."""

IMG_NOTE = "If you need to add images, you will need to generate or search for images yourself."


def mimo_chat(messages, model, max_tokens=4096):
    from openai import OpenAI

    client = OpenAI()  # mimo via OPENAI_BASE_URL / OPENAI_API_KEY
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.5,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return resp.choices[0].message.content or ""


# Ensure SlidesLib helpers are in scope even when the model forgets to import them
# (the model treats library.py functions as available globals — faithful to AutoPresent).
PREAMBLE = "from SlidesLib import *\nfrom pptx import Presentation\nfrom pptx.util import Inches, Pt\nfrom pptx.dml.color import RGBColor\n"


def _exec_code(code, pptx_path):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(PREAMBLE + "\n" + code)
        script = f.name
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{SHIM}:{AP/'generate'}:" + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=180, env=env)
    except subprocess.TimeoutExpired:
        return False, "exec timeout"
    finally:
        os.unlink(script)
    if Path(pptx_path).exists():
        return True, ""
    return False, f"rc={r.returncode}: {(r.stderr or '').strip().splitlines()[-1:]}"


def run_one(instr_text, pptx_path, library_content, model, log, attempts=3):
    from utils import extract_code_pieces  # AutoPresent's own extractor

    msgs = [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": INSTRUCTION.format(IMG_NOTE, pptx_path) + "\n\n" + library_content},
        {"role": "user", "content": "## Instruction\n" + instr_text},
    ]
    last = ""
    for _k in range(attempts):
        resp = mimo_chat(msgs, model)
        code = extract_code_pieces(resp, concat=True)
        if not code.strip():
            last = "no code extracted"
            continue
        ok, err = _exec_code(code, pptx_path)
        if ok:
            return True
        last = err
    log(f"  exec failed ({attempts} tries): {last}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="/home/gpus/slide-examiner/data/part3/g7_autopresent")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--model", default="mimo-v2.5-pro")
    ap.add_argument("--instr-name", default="instruction_no_image.txt")
    ap.add_argument("--category", default="", help="optional SlidesBench category filter")
    ap.add_argument("--offset", type=int, default=0, help="skip this many sorted instructions after filtering")
    ap.add_argument("--shuffle", action="store_true", help="shuffle instructions before slicing")
    ap.add_argument("--seed", type=int, default=20260625)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--summary", default="", help="write generation manifest JSON here")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    library_content = (AP / "generate/library/library.py").read_text()

    instrs = sorted((AP / "slidesbench/examples").rglob(args.instr_name))
    if args.category:
        instrs = [p for p in instrs if p.relative_to(AP / "slidesbench/examples").parts[0] == args.category]
    if args.shuffle:
        rng = random.Random(args.seed)
        rng.shuffle(instrs)
    instrs = instrs[args.offset : args.offset + args.n]
    print(f"AutoPresent x mimo({args.model}): {len(instrs)} tasks -> {out}")
    ok = 0
    records = []
    for i, ipath in enumerate(instrs):
        rel = ipath.relative_to(AP / "slidesbench/examples")
        tag = f"{rel.parts[0]}_{rel.parts[1]}"
        pptx_path = str(out / f"ap_{args.offset + i:03d}_{tag}.pptx")
        print(f"[{i+1}/{len(instrs)}] {tag}", flush=True)
        rec = {
            "index": args.offset + i,
            "tag": tag,
            "instruction": str(ipath),
            "pptx": pptx_path,
            "status": "pending",
        }
        if args.skip_existing and Path(pptx_path).exists():
            ok += 1
            rec["status"] = "existing"
            print("  EXISTS", flush=True)
            records.append(rec)
            continue
        try:
            if run_one(
                ipath.read_text(),
                pptx_path,
                library_content,
                args.model,
                lambda m: print(m, flush=True),
                attempts=args.attempts,
            ):
                ok += 1
                rec["status"] = "ok"
                print("  OK", flush=True)
            else:
                rec["status"] = "failed"
        except Exception as e:  # noqa: BLE001
            rec["status"] = "error"
            rec["error"] = f"{type(e).__name__}: {e}"
            print(f"  ERR {type(e).__name__}: {e}", flush=True)
        records.append(rec)
    print(f"\nGenerated {ok}/{len(instrs)} decks in {out}")
    if args.summary:
        summary = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "AutoPresent SlidesBench instruction_no_image",
            "model": args.model,
            "category": args.category or None,
            "offset": args.offset,
            "n_requested": args.n,
            "n_attempted": len(instrs),
            "n_success": ok,
            "records": records,
        }
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
