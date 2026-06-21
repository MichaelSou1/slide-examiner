"""C2 elicitation engine — synth-twin pairwise (A.4).

For a slide WITH structure, render a geometry-normalized counterfactual twin
(``snap_slide_to_master`` -> standard renderer): the snap absorbs declared
geometry defects (G1 declared overflow, G2/G3/G6) and re-draws the slide as the
master would lay it out. The VLM then judges, in BOTH orders (position-bias
control), whether the ORIGINAL is worse than its canonical re-render; agreement
in both orders => defect present.

Scope honesty: the twin is structure-derived, so C2 needs an IR. On real
image-only slides (no structure) C2 is N/A (returns failure -> dropped from
scoring). And by design the snap leaves render-level overflow with a *legal*
declared bbox (G7) largely unchanged in the IR, so C2 is expected to be weaker on
G7 than on declared-geometry classes — an honest, pre-registered prediction
(A.4: "C2 专攻感知-未校准类").

Playwright's sync API is not safe to call from pool worker threads, so twins are
batch-rendered ONCE in the main thread via :func:`prepare_twins` before the
threaded pairwise calls; the per-sample engine only issues network calls.
"""
from __future__ import annotations

import threading
from pathlib import Path

from .adapters import parse_examiner_json
from .elicit_common import chat_complete
from .examiner_contract import image_content_from_path
from .render import _RasterJob, _rasterize_jobs, slide_to_html
from .schemas import Slide
from .template import snap_slide_to_master

TWIN_DIR = Path(__file__).resolve().parents[1] / "data" / "part3" / "g7_twins"

_twins: dict[str, str] = {}          # slide_id -> twin png path
_lock = threading.Lock()

PAIR_SYSTEM = (
    "You compare two renderings of the same slide and judge presentation quality. "
    "Output ONLY a JSON object."
)
PAIR_PROMPT = (
    "Candidate A and Candidate B are two versions of the same slide. In ONE of "
    "them, some content may spill outside the box / card / frame that should "
    "contain it, or otherwise break the layout. Which candidate is WORSE? "
    'Output JSON: {"worse": "A" | "B" | "tie"}.'
)


def _image_path(rec: dict) -> str | None:
    return rec.get("image_path") or (rec.get("metadata") or {}).get("defective_image_path")


def prepare_twins(recs: list[dict], *, out_dir: Path = TWIN_DIR) -> dict[str, str]:
    """Batch-render the snap-to-master twin for every IR-bearing record, in the
    main thread. Idempotent (skips twins already on disk). Returns slide_id->path
    and also populates the module cache the engine reads."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs, planned = [], {}
    for rec in recs:
        slide_dict = rec.get("slide")
        if not slide_dict:
            continue
        slide = Slide.from_mapping(slide_dict)
        twin_png = out_dir / f"{slide.slide_id}_twin.png"
        planned[slide.slide_id] = str(twin_png)
        if not twin_png.exists():
            snapped = snap_slide_to_master(slide)
            jobs.append(_RasterJob(html=slide_to_html(snapped), output=twin_png,
                                   width=int(slide.width), height=int(slide.height)))
    if jobs:
        _rasterize_jobs(jobs)
    with _lock:
        _twins.update(planned)
    return planned


def _slide_id(rec: dict) -> str | None:
    sd = rec.get("slide")
    if sd:
        return str(sd.get("slide_id"))
    # clean-variant ids carry a __CLEAN suffix on the original sample id
    return str(rec.get("sample_id", "")).removesuffix("__CLEAN") or None


def _ask_worse(client, model, a_img, b_img, max_tokens):
    content = [image_content_from_path(a_img), image_content_from_path(b_img),
               {"type": "text", "text": PAIR_PROMPT}]
    messages = [{"role": "system", "content": PAIR_SYSTEM}, {"role": "user", "content": content}]
    try:
        raw = chat_complete(client, model, messages, max_tokens)
        w = str(parse_examiner_json(raw).get("worse", "")).strip().lower()
    except Exception:  # noqa: BLE001 - one bad call must not abort the sweep
        return None
    return w if w in {"a", "b", "tie"} else None


def run_pairwise_sample(client, model, rec, *, target_defect, max_tokens, blank):
    out = blank(rec)
    sid = _slide_id(rec)
    twin = None
    if sid:
        with _lock:
            twin = _twins.get(sid)
    if not twin or not Path(twin).exists():
        out["failure"] = True            # no IR/twin (e.g. real image) -> C2 N/A
        out["raw"] = "no-twin (C2 N/A)"
        return out
    orig = _image_path(rec)
    if not orig:
        out["failure"] = True
        return out

    # Both orders. order0: A=twin(clean) B=orig -> orig worse == "b".
    #              order1: A=orig B=twin(clean) -> orig worse == "a".
    n_orig_worse, n_valid = 0, 0
    for order in (0, 1):
        a, b, orig_worse = (twin, orig, "b") if order == 0 else (orig, twin, "a")
        pick = _ask_worse(client, model, a, b, max_tokens)
        if pick is None:
            continue
        n_valid += 1
        if pick == orig_worse:
            n_orig_worse += 1
    # Strict, position-bias-free: present only if BOTH orders call the original worse.
    present = n_valid == 2 and n_orig_worse == 2
    out["has_defect"] = present
    out["named_target"] = present
    out["predicted_types"] = [target_defect] if present else []
    out["locator"] = {"method": "snap_twin_pairwise", "orig_worse_orders": n_orig_worse,
                      "valid_orders": n_valid}
    if n_valid == 0:
        out["failure"] = True
    return out


def reset_cache() -> None:
    with _lock:
        _twins.clear()
