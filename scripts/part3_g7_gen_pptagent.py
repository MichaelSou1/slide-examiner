#!/usr/bin/env python
"""Drive PPTAgent's edit-based PPTX generator over mimo for R5 smoke data.

This intentionally uses the original `pptagent` package, its built-in template
and slide-editing API.  It does not invoke deeppresenter/html2pptx.  The script
uses a deterministic outline/content scaffold from Slide-Examiner Part-3 tasks,
then asks PPTAgent's edit-based coder agent (mimo) to apply XML-level edits to
the template slides and save real `.pptx` files.

The resulting decks are suitable for `scripts/part3_g7_prevalence.py`, but the
main R5 prevalence number should still prefer naturally generated decks
(AutoPresent/Zenodo) over this small wiring smoke.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import types
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

PPTAGENT = Path("/home/gpus/external_agents/PPTAgent")
REPO = Path(__file__).resolve().parents[1]


def _install_oaib_stub() -> None:
    """PPTAgent imports oaib for batch mode; R5 uses normal async calls only."""
    if "oaib" in sys.modules:
        return
    mod = types.ModuleType("oaib")

    class Auto:  # pragma: no cover - only guards accidental batch use
        def __init__(self, *args, **kwargs):
            pass

        async def add(self, *args, **kwargs):
            raise RuntimeError("oaib batch mode is not available in this local driver")

        async def run(self):
            raise RuntimeError("oaib batch mode is not available in this local driver")

    mod.Auto = Auto
    sys.modules["oaib"] = mod


def load_env(path: Path = REPO / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def endpoint_value(role_key: str, fallback_key: str, default: str = "") -> str:
    return os.environ.get(fallback_key) or os.environ.get(role_key) or default


def make_document(task: dict, image_dir: Path):
    from pptagent.document import Document
    from pptagent.document.element import Section, SubSection
    from pptagent.utils import Language

    required = task.get("rubric", {}).get("required_sections", [])
    topic = task.get("topic", "an AI product")
    audience = task.get("audience", "an executive audience")
    scenario = task.get("scenario", "proposal").replace("_", " ")
    sections = []
    for idx, section_name in enumerate(required[:4] or ["background", "problem", "solution", "next_steps"]):
        title = section_name.replace("_", " ").title()
        sections.append(
            Section(
                title=title,
                summary=f"{title} for {topic} aimed at {audience}.",
                content=[
                    SubSection(
                        title=f"{title} - message",
                        content=(
                            f"Create a {scenario} slide for {audience}. "
                            f"Explain {topic} through the lens of {title.lower()}. "
                            "Use concise business language, concrete claims, and avoid filler."
                        ),
                    ),
                    SubSection(
                        title=f"{title} - proof points",
                        content=(
                            "Include two to four compact points: operational impact, measurable outcome, "
                            "implementation path, and the next decision the audience should take."
                        ),
                    ),
                ],
            )
        )
    return Document(
        image_dir=str(image_dir),
        language=Language.english(),
        metadata={
            "title": task.get("brief", topic),
            "audience": audience,
            "topic": topic,
            "scenario": scenario,
        },
        sections=sections,
    )


class MimoAsyncLLMMixin:
    async def __call__(self, *args, **kwargs):
        kwargs.setdefault("temperature", 0.3)
        kwargs.setdefault("max_tokens", 4096)
        extra_body = kwargs.pop("extra_body", {}) or {}
        chat_kwargs = dict(extra_body.get("chat_template_kwargs", {}))
        chat_kwargs.setdefault("enable_thinking", False)
        extra_body["chat_template_kwargs"] = chat_kwargs
        kwargs["extra_body"] = extra_body
        return await super().__call__(*args, **kwargs)


async def generate_one(task: dict, out_path: Path, template: str, retry_times: int, max_slides: int):
    _install_oaib_stub()
    if str(PPTAGENT) not in sys.path:
        sys.path.insert(0, str(PPTAGENT))

    from pptagent.llms import AsyncLLM
    from pptagent.pptgen import PPTAgent
    from pptagent.presentation import Presentation
    from pptagent.response.pptgen import EditorOutput, SlideElement
    from pptagent.utils import Config

    class MimoAsyncLLM(MimoAsyncLLMMixin, AsyncLLM):
        pass

    base_url = endpoint_value("PART3_GEN_BASE_URL", "OPENAI_BASE_URL")
    api_key = endpoint_value("PART3_GEN_API_KEY", "OPENAI_API_KEY")
    text_model = os.environ.get("PPTAGENT_TEXT_MODEL") or os.environ.get("OPENAI_MODEL") or "mimo-v2.5-pro"
    vision_model = os.environ.get("PPTAGENT_VISION_MODEL", "mimo-v2.5")

    language_model = MimoAsyncLLM(text_model, base_url, api_key)
    vision_llm = MimoAsyncLLM(vision_model, base_url, api_key)

    template_dir = PPTAGENT / "pptagent" / "templates" / template
    config = Config(str(template_dir))
    presentation = Presentation.from_file(str(template_dir / "source.pptx"), config)
    slide_induction = json.loads((template_dir / "slide_induction.json").read_text(encoding="utf-8"))

    image_dir = out_path.parent / "_pptagent_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    doc = make_document(task, image_dir)

    agent = PPTAgent(language_model=language_model, vision_model=vision_llm, retry_times=retry_times)
    agent.set_reference(deepcopy(slide_induction), presentation, hide_small_pic_ratio=None)
    agent.source_doc = doc
    agent.dst_lang = doc.language
    agent.length_factor = 1.0
    agent.simple_outline = "\n".join(
        f"Slide {i + 1}: {section.title}" for i, section in enumerate(doc.sections[:max_slides])
    )

    layout_names = [name for name in agent.text_layouts if name in agent.layouts]
    if not layout_names:
        layout_names = [name for name in agent.layouts if name != "opening"]
    slides = []

    # Opening slide: deterministic content, edit-based coder still performs the XML edit.
    if "opening" in agent.layouts:
        layout = agent.layouts["opening"]
        elements = []
        for el in layout.elements:
            if "title" in el.name:
                data = [task.get("topic", "AI Product").title()]
            elif "subtitle" in el.name:
                data = [task.get("brief", "Generated by PPTAgent over mimo")]
            elif "presenter" in el.name:
                data = ["Slide-Examiner R5 / PPTAgent edit-based smoke"]
            else:
                data = [task.get("audience", "business audience")]
            elements.append(SlideElement(name=el.name, data=data))
        commands, template_id = agent._generate_commands(EditorOutput(elements=elements), layout)
        slide, _ = await agent._edit_slide(commands, template_id)
        slides.append(slide)

    for idx, section in enumerate(doc.sections[: max(1, max_slides - len(slides))]):
        layout = agent.layouts[layout_names[idx % len(layout_names)]]
        elements = []
        for el in layout.elements:
            if el.type != "text":
                continue
            if "title" in el.name:
                data = [section.title]
            else:
                pieces = [block.content for block in section.content if hasattr(block, "content")]
                if getattr(el, "default_quantity", 1) and getattr(el, "default_quantity", 1) > 1:
                    data = pieces[: getattr(el, "default_quantity", 1)]
                else:
                    data = [" ".join(pieces)]
            elements.append(SlideElement(name=el.name, data=data))
        if not elements:
            continue
        commands, template_id = agent._generate_commands(EditorOutput(elements=elements), layout)
        slide, _ = await agent._edit_slide(commands, template_id)
        slides.append(slide)

    agent.empty_prs.slides = slides
    out_path.parent.mkdir(parents=True, exist_ok=True)
    agent.empty_prs.save(str(out_path))
    return {"slides": len(slides), "model": text_model, "vision_model": vision_model}


async def amain() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(REPO / "data/part3/tasks/test.jsonl"))
    ap.add_argument("--out-dir", default=str(REPO / "data/part3/g7_pptagent"))
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--template", default="default")
    ap.add_argument("--retry-times", type=int, default=3)
    ap.add_argument("--max-slides", type=int, default=4)
    ap.add_argument("--summary", default="")
    args = ap.parse_args()

    load_env()
    tasks = [json.loads(line) for line in Path(args.tasks).read_text(encoding="utf-8").splitlines() if line.strip()]
    tasks = tasks[args.offset : args.offset + args.n]
    out_dir = Path(args.out_dir)
    records = []
    ok = 0
    for i, task in enumerate(tasks):
        out_path = out_dir / f"pptagent_{args.offset + i:03d}_{task['task_id']}.pptx"
        print(f"[{i + 1}/{len(tasks)}] {task['task_id']} -> {out_path}", flush=True)
        rec = {"task_id": task["task_id"], "pptx": str(out_path), "status": "pending"}
        try:
            meta = await generate_one(task, out_path, args.template, args.retry_times, args.max_slides)
            rec.update(meta)
            rec["status"] = "ok"
            ok += 1
            print(f"  OK slides={meta['slides']}", flush=True)
        except Exception as e:  # noqa: BLE001
            rec["status"] = "error"
            rec["error"] = f"{type(e).__name__}: {e}"
            print(f"  ERR {rec['error']}", flush=True)
        records.append(rec)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "PPTAgent edit-based generator over mimo",
        "template": args.template,
        "n_attempted": len(tasks),
        "n_success": ok,
        "records": records,
    }
    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    asyncio.run(amain())
