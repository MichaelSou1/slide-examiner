"""Part 3 Protocol-3 (a) — audit a published design/document reward model.

We do NOT retrain a reward model (expensive, derivative). Instead we take a
*published* one — **DocReward** (jeepliu/DocReward-3B, a Qwen2.5-VL-3B + a
Bradley-Terry value head, trained to score document **structure & style**,
textual-quality-agnostic; arXiv 2510.11391) — and ask a falsifiable question:

    Does it penalise a slide whose content visibly **overflows its container**
    (our G7 render-containment class), i.e. does reward(clean) > reward(defective)?

A structure/style reward that is blind to render-containment overflow assigns the
defective slide a reward no lower than its clean twin -> paired preference
accuracy ~= chance (0.5). We measure that paired preference accuracy per defect
class on the SAME paired-clean slides used by Protocols 1-2, with:

  * **freeform** renders (the defect actually renders) — the real sensitivity test;
  * **template** renders (snap-to-master absorbs the geometry defect, Protocol-3c)
    — where the "defective" image is pixel-identical to clean, so even a perfect
    reward model is structurally unable to react. This ties the reward-model blind
    spot to the perturbation-fidelity hazard: ~45% of injected geometry labels
    never render, so a reward model trained on snap-rendered pairs gets no signal.

Reward = value_head(last_hidden_state at an appended ``<|regression|>`` token),
reimplemented from the model card's demo_inference.py with plain transformers
(no trl / llamafactory dependency). value_head.bin = Linear(2048 -> 1).

Run on one GPU:  CUDA_VISIBLE_DEVICES=2 python scripts/part3_p3_reward_audit.py
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO))
from slide_examiner.statistics import wilson_interval  # noqa: E402

DOC_PROMPT = "You need to create a professional document page(s). "
REG_TOKEN = "<|regression|>"


class DocRewardScorer:
    def __init__(self, path: str, max_pixels: int = 300000):
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            path, dtype=torch.bfloat16, attn_implementation="sdpa", device_map="cuda")
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(path, trust_remote_code=True,
                                                       max_pixels=max_pixels)
        vh = torch.load(Path(path) / "value_head.bin", map_location="cpu")
        self.w = vh["v_head.summary.weight"].to("cuda", torch.float32)   # [1, 2048]
        self.b = vh["v_head.summary.bias"].to("cuda", torch.float32)     # [1]
        self.reg_id = self.processor.tokenizer.convert_tokens_to_ids(REG_TOKEN)
        assert self.reg_id is not None and self.reg_id >= 0, "no <|regression|> token"

    @torch.no_grad()
    def score(self, image_path: str) -> float:
        messages = [
            {"role": "user", "content": [{"type": "text", "text": DOC_PROMPT}]},
            {"role": "assistant", "content": [{"type": "image"}]},
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False,
                                                  add_generation_prompt=False)
        # Append the regression token to the TEXT (not post-tokenization) so the
        # sequence / attention_mask / 3D-rope position ids stay consistent under
        # newer transformers. The value head is read at this last token.
        text = text + REG_TOKEN
        img = Image.open(image_path).convert("RGB")
        inputs = self.processor(text=[text], images=[img], return_tensors="pt", padding=True)
        assert int(inputs["input_ids"][0, -1]) == self.reg_id, "regression token not last"
        inputs = {k: (v.to("cuda") if hasattr(v, "to") else v) for k, v in inputs.items()}
        out = self.model(**inputs, output_hidden_states=True, return_dict=True, use_cache=False)
        h = out.hidden_states[-1][0, -1].to(torch.float32)               # [2048]
        return float((h @ self.w.squeeze(0)) + self.b.squeeze(0))


def defect_of(rec: dict) -> str:
    return rec["labels"][0]["type"] if rec.get("labels") else "NO_DEFECT"


def variant_paths(rec: dict, variant: str):
    """(defective_img, clean_img) for the requested render variant."""
    dp = rec.get("image_path")
    cp = (rec.get("pair") or {}).get("clean_image_path")
    if not dp or not cp:
        return None, None
    if variant == "template":
        dp, cp = dp.replace("__freeform", "__template"), cp.replace("__freeform", "__template")
    for p in (dp, cp):
        if not Path(p if Path(p).is_absolute() else REPO / p).exists():
            return None, None
    return dp, cp


def run_class(scorer, recs, defect, variant, max_n):
    # keep freeform synth records (drop interleaved __template ones) AND the G7
    # records (whose paths carry neither suffix — they are freeform by construction).
    pos = [r for r in recs if defect_of(r) == defect and "__template" not in (r.get("image_path") or "")][:max_n]
    gaps, clean_pref = [], 0
    n = 0
    for r in pos:
        dp, cp = variant_paths(r, variant)
        if not dp:
            continue
        rd = scorer.score(dp if Path(dp).is_absolute() else str(REPO / dp))
        rc = scorer.score(cp if Path(cp).is_absolute() else str(REPO / cp))
        gap = rc - rd          # >0 means the reward correctly prefers the clean slide
        gaps.append(gap)
        clean_pref += int(gap > 0)
        n += 1
    if not n:
        return None
    ci = wilson_interval(clean_pref, n)
    mean_gap = sum(gaps) / n
    return {
        "defect": defect, "variant": variant, "n": n,
        "preference_accuracy": round(clean_pref / n, 3),
        "preference_ci": [round(ci.low, 3), round(ci.high, 3)],
        "mean_reward_gap_clean_minus_def": round(mean_gap, 4),
        "median_gap": round(sorted(gaps)[n // 2], 4),
        "n_clean_preferred": clean_pref,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/home/gpus/models/DocReward-3B")
    ap.add_argument("--model-name", default="DocReward-3B")
    ap.add_argument("--synth", default="data/part2/manifest_eval_test_rendered.jsonl")
    ap.add_argument("--g7", default="data/part3/manifest_g7_rendered.jsonl")
    ap.add_argument("--max-per-defect", type=int, default=40)
    ap.add_argument("--out", default="data/part3/p3_audit.json")
    args = ap.parse_args()

    print(f"loading {args.model} ...", flush=True)
    scorer = DocRewardScorer(args.model)
    print("loaded.", flush=True)

    synth = [json.loads(l) for l in Path(args.synth).open() if l.strip()]
    g7 = [json.loads(l) for l in Path(args.g7).open() if l.strip()]

    results = []
    # A) freeform sensitivity: does the reward penalise the VISIBLE defect?
    for d in ["G7_RENDER_CONTAINMENT_OVERFLOW", "G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP",
              "G5_BRAND_COLOR_VIOLATION", "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION"]:
        recs = g7 if d == "G7_RENDER_CONTAINMENT_OVERFLOW" else synth
        r = run_class(scorer, recs, d, "freeform", args.max_per_defect)
        if r:
            results.append(r)
            print(f"  [freeform] {d:32s} pref_acc={r['preference_accuracy']} "
                  f"gap={r['mean_reward_gap_clean_minus_def']} n={r['n']}", flush=True)
    # C) template (snap-absorbed) — perturbation-fidelity tie-in (defect erased).
    for d in ["G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET", "G6_MARGIN_VIOLATION"]:
        r = run_class(scorer, synth, d, "template", args.max_per_defect)
        if r:
            results.append(r)
            print(f"  [template] {d:32s} pref_acc={r['preference_accuracy']} "
                  f"gap={r['mean_reward_gap_clean_minus_def']} n={r['n']}", flush=True)

    out = {"model": args.model_name, "model_path": args.model,
           "metric": "paired preference accuracy = P(reward(clean) > reward(defective)); "
                     "0.5 = blind, 1.0 = always prefers the clean slide",
           "results": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", args.out)


if __name__ == "__main__":
    main()
