"""E5 — recover IR-shaped element boxes from rendered slide pixels (open-world hybrid).

The symbolic linter (:mod:`slide_examiner.geometry`) reasons over **declared**
element bboxes — the native IR a ``.pptx`` / python-pptx export carries. Third-party
decks exported as PDF/PNG ship no IR, so on bare pixels the hybrid critic degrades
to its VLM engine (see ``scripts/part3_pc_real.py`` and the paper's Limitations).
This module asks the open-world question R3-W1/EIC-W1 raised: *how much of the
linter's coverage survives if element structure is **recovered from the pixels**
with a document-layout detector?*

Pipeline
--------
1. A learned, transformers-native detector (PP-DocLayoutV2 by default) returns
   region boxes on the rendered image.
2. **Class-agnostic NMS** — the detector emits duplicate boxes across its label set
   (e.g. ``doc_title`` and ``paragraph_title`` on the identical region); left in,
   those would manufacture phantom element overlaps and make G2 meaningless.
3. The surviving boxes are **normalised into a canonical IR frame** (width 960,
   aspect preserved) so the linter's absolute thresholds (``margin_px=32`` etc.,
   tuned on the synthetic 960×720 IR) map to the same fractional thresholds across
   datasets of different resolution.
4. They are shaped into a ``Slide`` dict the linter consumes **verbatim** — drop it
   into ``rec["slide"]`` and ``slide_examiner.hybrid_critic.linter_types`` runs
   unchanged.

Only **box-geometry** defects survive a pixel→box projection: G2 overlap
(box-vs-box IoU) and G6 margin (box-vs-edge). G1 overflow needs text capacity, G3
alignment needs declared/expected positions, G4 font needs point sizes, G5 colour
needs the brand palette — none are carried by a recovered box, so the recovered
linter is **silent on them by construction**. That is the pre-registered E5
falsification branch: open-world recovery rescues coarse geometry, not fine
geometry, confirming the linter's near-zero-FP advantage requires true IR.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "PaddlePaddle/PP-DocLayoutV2_safetensors"
#: canonical IR width the recovered boxes are normalised to (matches the synthetic
#: real-layout IR the linter thresholds were tuned on; height follows the image
#: aspect ratio).
NORM_WIDTH = 960

#: detector labels that denote a non-text graphic element. Everything else maps to
#: a text element. The IR ``type`` only matters to the linter via the overlap
#: ignore-set ({"background", "canvas"}); neither bucket is ignored, so every
#: recovered box participates in overlap/margin geometry exactly as intended.
_IMAGE_LABELS = {"image", "figure", "chart", "table", "seal", "formula"}


# --------------------------------------------------------------------------- #
# Geometry helpers (xyxy pixel boxes)
# --------------------------------------------------------------------------- #
def _iou_xyxy(a: list[float], b: list[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def nms_class_agnostic(dets: list[dict], iou_thr: float) -> list[dict]:
    """Greedy class-agnostic NMS over ``[{bbox_xyxy, score, label}]`` (desc score).

    Removes the detector's cross-class duplicate boxes so the only residual
    box-pairs the linter sees are genuine element collisions.
    """
    order = sorted(dets, key=lambda d: -d["score"])
    kept: list[dict] = []
    for d in order:
        if all(_iou_xyxy(d["bbox_xyxy"], k["bbox_xyxy"]) < iou_thr for k in kept):
            kept.append(d)
    return kept


# --------------------------------------------------------------------------- #
# Learned layout detector (lazy-loaded, optional disk cache)
# --------------------------------------------------------------------------- #
class LayoutDetector:
    """PP-DocLayoutV2 (or any ``AutoModelForObjectDetection``) wrapped to emit
    NMS'd region boxes in image-pixel space. The model is loaded lazily so the
    module imports cheaply (the eval scripts and unit tests do not need a GPU)."""

    def __init__(self, model_id: str = DEFAULT_MODEL, *, device: str | None = None,
                 score_thr: float = 0.4, nms_iou: float = 0.7):
        self.model_id = model_id
        self.score_thr = score_thr
        self.nms_iou = nms_iou
        self._device = device
        self._proc = None
        self._model = None

    def _ensure(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        if self._device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._proc = AutoImageProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForObjectDetection.from_pretrained(self.model_id).eval().to(self._device)

    def detect(self, image_path: str | Path) -> dict:
        """Run the detector on one image. Returns
        ``{"img_w", "img_h", "dets": [{"bbox_xyxy", "label", "score"}]}`` with
        class-agnostic NMS already applied."""
        import torch
        from PIL import Image

        self._ensure()
        im = Image.open(image_path).convert("RGB")
        inp = self._proc(images=im, return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self._model(**inp)
        target = torch.tensor([im.size[::-1]]).to(self._device)
        post = self._proc.post_process_object_detection(out, target_sizes=target,
                                                        threshold=self.score_thr)[0]
        id2label = self._model.config.id2label
        dets = [{"bbox_xyxy": [float(x) for x in box], "score": float(sc),
                 "label": id2label[int(lb)]}
                for box, sc, lb in zip(post["boxes"].tolist(), post["scores"].tolist(),
                                       post["labels"].tolist())]
        dets = nms_class_agnostic(dets, self.nms_iou)
        return {"img_w": im.size[0], "img_h": im.size[1], "dets": dets}


# --------------------------------------------------------------------------- #
# Detection cache (detector inference is the expensive step; cache per image)
# --------------------------------------------------------------------------- #
class DetectionCache:
    """Append-only jsonl cache keyed by image path. Lets a sweep re-run scoring /
    threshold choices without re-invoking the detector."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.store: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.open():
                if line.strip():
                    rec = json.loads(line)
                    self.store[rec["image_path"]] = rec["det"]

    def get_or_compute(self, detector: LayoutDetector, image_path: str) -> dict:
        if image_path in self.store:
            return self.store[image_path]
        det = detector.detect(image_path)
        self.store[image_path] = det
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps({"image_path": image_path, "det": det},
                                ensure_ascii=False) + "\n")
        return det


# --------------------------------------------------------------------------- #
# Pixel boxes -> IR-shaped Slide dict
# --------------------------------------------------------------------------- #
def _label_to_type(label: str) -> str:
    return "image" if any(k in label for k in _IMAGE_LABELS) else "text"


def recover_slide(det: dict, *, norm_width: int = NORM_WIDTH,
                  slide_id: str = "recovered") -> dict:
    """Build a linter-ready ``Slide`` dict from a cached detection.

    Boxes are scaled by ``norm_width / img_w`` into a canonical frame (height
    follows the image aspect ratio) and converted from xyxy pixel boxes to the IR
    ``{x, y, width, height}`` bbox. Synthetic ``element_id``s are assigned.
    """
    img_w, img_h = det["img_w"], det["img_h"]
    s = norm_width / float(img_w)
    height = int(round(img_h * s))
    elements = []
    for i, d in enumerate(det["dets"]):
        x0, y0, x1, y1 = d["bbox_xyxy"]
        elements.append({
            "element_id": f"rec_{i}",
            "type": _label_to_type(d["label"]),
            "bbox": {"x": x0 * s, "y": y0 * s,
                     "width": max(0.0, (x1 - x0) * s), "height": max(0.0, (y1 - y0) * s)},
            "text": "",
            "style": {},
            "z": 0,
            "placeholder_id": None,
            "metadata": {"recovered_label": d["label"], "det_score": round(d["score"], 4)},
        })
    return {"slide_id": slide_id, "width": norm_width, "height": height,
            "elements": elements, "metadata": {"structure_recovered": True}}


# --------------------------------------------------------------------------- #
# Recovery fidelity — recovered boxes vs ground-truth IR boxes (synthetic only)
# --------------------------------------------------------------------------- #
def _gt_boxes_xyxy(gt_slide: dict) -> list[list[float]]:
    out = []
    for el in gt_slide.get("elements", []):
        b = el.get("bbox") or {}
        x, y, w, h = b.get("x", 0.0), b.get("y", 0.0), b.get("width", 0.0), b.get("height", 0.0)
        out.append([x, y, x + w, y + h])
    return out


def _rec_boxes_xyxy(rec_slide: dict) -> list[list[float]]:
    out = []
    for el in rec_slide.get("elements", []):
        b = el["bbox"]
        out.append([b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]])
    return out


def recovery_fidelity(rec_slide: dict, gt_slide: dict, *, match_iou: float = 0.5) -> dict:
    """Hungarian-match recovered boxes to GT IR boxes (both already in the same
    normalised frame) and report fidelity: mean IoU over matched pairs, the
    fraction of GT boxes recovered at ``match_iou``, and detector precision/recall.

    The GT slide must be pre-scaled into the recovered frame by the caller (the
    eval normalises GT 960×720 and recovered both to width=960)."""
    from scipy.optimize import linear_sum_assignment
    import numpy as np

    gt = _gt_boxes_xyxy(gt_slide)
    rec = _rec_boxes_xyxy(rec_slide)
    n_gt, n_rec = len(gt), len(rec)
    if n_gt == 0 or n_rec == 0:
        return {"mean_iou_matched": 0.0, "recall_at_iou": 0.0, "precision_at_iou": 0.0,
                "n_matched": 0, "n_gt": n_gt, "n_rec": n_rec}
    iou = np.zeros((n_gt, n_rec))
    for i, g in enumerate(gt):
        for j, r in enumerate(rec):
            iou[i, j] = _iou_xyxy(g, r)
    rows, cols = linear_sum_assignment(-iou)
    pairs = [(i, j, iou[i, j]) for i, j in zip(rows, cols)]
    matched = [p for p in pairs if p[2] >= match_iou]
    n_match = len(matched)
    mean_iou = float(np.mean([p[2] for p in matched])) if matched else 0.0
    return {
        "mean_iou_matched": round(mean_iou, 3),
        "recall_at_iou": round(n_match / n_gt, 3),
        "precision_at_iou": round(n_match / n_rec, 3),
        "n_matched": n_match, "n_gt": n_gt, "n_rec": n_rec,
    }


def normalize_gt_slide(gt_slide: dict, *, norm_width: int = NORM_WIDTH) -> dict:
    """Scale a ground-truth IR slide into the recovered frame (width=``norm_width``)
    so fidelity IoU is computed in one coordinate space."""
    w = float(gt_slide.get("width", norm_width))
    s = norm_width / w
    out: dict[str, Any] = {"slide_id": gt_slide.get("slide_id", "gt"),
                           "width": norm_width,
                           "height": int(round(float(gt_slide.get("height", w)) * s)),
                           "elements": [], "metadata": {}}
    for el in gt_slide.get("elements", []):
        b = el.get("bbox") or {}
        out["elements"].append({
            "element_id": el.get("element_id", ""), "type": el.get("type", "shape"),
            "bbox": {"x": b.get("x", 0.0) * s, "y": b.get("y", 0.0) * s,
                     "width": b.get("width", 0.0) * s, "height": b.get("height", 0.0) * s},
            "text": el.get("text", ""), "style": {}, "z": 0,
            "placeholder_id": None, "metadata": {},
        })
    return out
