"""Reward-model adapters for the Part-3 Protocol-3 multi-RM blind-spot audit.

The audit asks one falsifiable question of each *published* reward model:

    given a (clean, defective) slide pair, does the model prefer the clean one,
    i.e. is ``reward(clean) > reward(defective)``?

Per defect class we report the paired preference accuracy and the mean reward
gap. ``0.5`` = blind; ``1.0`` = always prefers the clean slide; ``<0.5`` =
inverted (it prefers the broken slide). The whole point is to show the G7
render-containment blind spot is **model-agnostic**: it survives a swap of
backbone, training corpus and input contract.

Reward models differ in their input contract; we expose three:

  * ``POINTWISE``           — score a single image with a fixed instruction; the
                             scalar IS the reward (DocReward, aesthetic predictors).
  * ``PROMPT_CONDITIONED``  — score a (question, positive-answer) chat grounded in
                             the image, so the per-image scalar reflects how well
                             the model grounds that (true-for-clean,
                             false-for-defective) answer in the pixels (Skywork-VL,
                             IXC-2.5). Two elicitation regimes (``ELICITATIONS``):
                             ``generic`` (deployment-realistic, no defect names —
                             the PRIMARY measurement, matching DocReward's fixed
                             neutral doc prompt) and ``probe`` (names containment/
                             overflow — the best-case recoverability check; the
                             generic->probe delta mirrors Result-1's C0->C3).
  * ``PAIRWISE_BT``         — a Bradley-Terry latent: the pointwise scalar is the
                             BT strength, so ``P(clean≻defective)`` reduces to
                             ``gap > 0``. DocReward is BT-trained but used
                             pointwise, so this collapses into POINTWISE here.

Every adapter ultimately exposes ``score(image_path, variant=...) -> float`` and
the audit harness computes the SAME paired metric over all of them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

# ---- input contracts -------------------------------------------------------
POINTWISE = "pointwise"
PROMPT_CONDITIONED = "prompt_conditioned"
PAIRWISE_BT = "pairwise_bt"

# ---- elicitation for PROMPT_CONDITIONED reward models ----------------------
# Two regimes, both a (question, positive-answer) chat. The answer is TRUE for the
# clean slide and FALSE for the defective one, so a reward that perceives the
# defect rewards the clean slide more.
#
#   GENERIC = the deployment-realistic regime (PRIMARY). A reward model in
#   RLHF/best-of-N scores generic quality; it is NOT told which defect to look
#   for. This matches DocReward's own fixed neutral doc prompt, so the cross-RM
#   comparison is apples-to-apples. "Is the reward, asked generically about
#   quality, blind to G7?"
#
#   PROBE = the best-case recoverability regime (SENSITIVITY). The prompt
#   explicitly names containment/overflow — the reward's latent VLM is handed the
#   examiner's elicitation. The GENERIC->PROBE delta is the reward-side mirror of
#   Result-1's C0->C3 recovery: perception present but elicitation-gated.
ELICITATIONS = {
    "generic": (
        "Rate the overall visual quality, layout and professionalism of this "
        "presentation slide.",
        "This is a high-quality, well-designed, professional slide with a clean, "
        "polished layout.",
    ),
    # symmetric with generic (same positive-assertion polarity); differs ONLY in
    # naming containment/overflow, so the generic->probe delta isolates "directing
    # attention to the defect dimension" rather than answer polarity.
    "probe": (
        "Assess whether every element on this presentation slide is fully contained "
        "within its box, with no text overflow, cut-off, or content spilling outside "
        "its container.",
        "This is a high-quality, professional slide: every element is fully contained "
        "within its box, with no text overflow, cut-off, or content spilling outside "
        "its container.",
    ),
}
DEFAULT_VARIANT = "generic"


def _resolve(image_path: str, repo: Path | None) -> str:
    p = Path(image_path)
    if p.is_absolute() or repo is None:
        return str(p)
    return str(repo / p)


class RewardAdapter(ABC):
    """One published reward model behind a uniform ``score`` interface."""

    key: str = "abstract"
    display_name: str = "abstract"
    category: str = "unknown"          # document | general_mm | design | aesthetic
    contract: str = POINTWISE
    backbone: str = "unknown"
    trained_reward: bool = True        # False only for heuristic aesthetic scorers

    def __init__(self, path: str, repo: Path | None = None, max_pixels: int = 1_003_520):
        self.path = path
        self.repo = repo
        self.max_pixels = max_pixels

    @abstractmethod
    def load(self) -> "RewardAdapter":
        """Load weights onto the current CUDA device. Returns self."""

    @abstractmethod
    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        """Reward scalar for one image. ``variant`` selects the elicitation regime
        ("generic" / "probe") for PROMPT_CONDITIONED models; it is ignored by
        POINTWISE / image-only models, whose elicitation is fixed by construction."""

    def meta(self) -> dict:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "category": self.category,
            "contract": self.contract,
            "backbone": self.backbone,
            "trained_reward": self.trained_reward,
            "model_path": self.path,
        }


# ===========================================================================
# DocReward-3B — Qwen2.5-VL-3B + Bradley-Terry value head (document structure)
# ===========================================================================
class DocRewardAdapter(RewardAdapter):
    """jeepliu/DocReward-3B. Pointwise document structure/style reward. The image
    IS the assistant's "document"; a fixed doc-creation instruction is the user
    turn and an appended ``<|regression|>`` token carries the value head."""

    key = "docreward"
    display_name = "DocReward-3B"
    category = "document"
    contract = PAIRWISE_BT  # BT-trained, read pointwise -> gap>0 is the preference
    backbone = "Qwen2.5-VL-3B"

    DOC_PROMPT = "You need to create a professional document page(s). "
    REG_TOKEN = "<|regression|>"

    def load(self):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        self.torch = torch
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.path, dtype=torch.bfloat16, attn_implementation="sdpa", device_map="cuda")
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(
            self.path, trust_remote_code=True, max_pixels=min(self.max_pixels, 300000))
        vh = torch.load(Path(self.path) / "value_head.bin", map_location="cpu")
        self.w = vh["v_head.summary.weight"].to("cuda", torch.float32)   # [1, 2048]
        self.b = vh["v_head.summary.bias"].to("cuda", torch.float32)     # [1]
        self.reg_id = self.processor.tokenizer.convert_tokens_to_ids(self.REG_TOKEN)
        assert self.reg_id is not None and self.reg_id >= 0, "no <|regression|> token"
        return self

    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        from PIL import Image
        torch = self.torch
        messages = [
            {"role": "user", "content": [{"type": "text", "text": self.DOC_PROMPT}]},
            {"role": "assistant", "content": [{"type": "image"}]},
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False,
                                                  add_generation_prompt=False)
        text = text + self.REG_TOKEN
        img = Image.open(_resolve(image_path, self.repo)).convert("RGB")
        inputs = self.processor(text=[text], images=[img], return_tensors="pt", padding=True)
        assert int(inputs["input_ids"][0, -1]) == self.reg_id, "regression token not last"
        inputs = {k: (v.to("cuda") if hasattr(v, "to") else v) for k, v in inputs.items()}
        with torch.no_grad():
            out = self.model(**inputs, output_hidden_states=True, return_dict=True, use_cache=False)
        h = out.hidden_states[-1][0, -1].to(torch.float32)               # [2048]
        return float((h @ self.w.squeeze(0)) + self.b.squeeze(0))


# ===========================================================================
# Skywork-VL-Reward-7B — Qwen2.5-VL-7B + trl ValueHead (general multimodal RM)
# ===========================================================================
class SkyworkVLAdapter(RewardAdapter):
    """Skywork/Skywork-VL-Reward-7B. A general multimodal reward model
    (Qwen2.5-VL-7B-Instruct + a trl value head). We reimplement the value-head
    read from the model card WITHOUT trl: forward with output_hidden_states and
    apply the linear head at the last non-pad token (== card's
    ``values.gather(attention_mask.sum-1)``)."""

    key = "skywork-vl"
    display_name = "Skywork-VL-Reward-7B"
    category = "general_mm"
    contract = PROMPT_CONDITIONED
    backbone = "Qwen2.5-VL-7B"

    def load(self):
        import torch
        from safetensors.torch import load_file
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        self.torch = torch
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.path, dtype=torch.bfloat16, attn_implementation="sdpa", device_map="cuda")
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(
            self.path, trust_remote_code=True, max_pixels=self.max_pixels)
        vh = load_file(str(Path(self.path) / "value_head.safetensors"))
        wkey = next(k for k in vh if k.endswith("summary.weight"))
        bkey = next(k for k in vh if k.endswith("summary.bias"))
        self.w = vh[wkey].to("cuda", torch.float32)   # [1, 3584]
        self.b = vh[bkey].to("cuda", torch.float32)   # [1]
        return self

    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        torch = self.torch
        question, ans = ELICITATIONS[variant]
        messages = [
            {"role": "user", "content": [
                {"type": "image", "image": _resolve(image_path, self.repo)},
                {"type": "text", "text": question}]},
            {"role": "assistant", "content": ans},
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False,
                                                  add_generation_prompt=False)
        from PIL import Image
        img = Image.open(_resolve(image_path, self.repo)).convert("RGB")
        inputs = self.processor(text=[text], images=[img], return_tensors="pt", padding=True)
        inputs = {k: (v.to("cuda") if hasattr(v, "to") else v) for k, v in inputs.items()}
        with torch.no_grad():
            out = self.model(**inputs, output_hidden_states=True, return_dict=True, use_cache=False)
        last = int(inputs["attention_mask"][0].sum().item()) - 1
        h = out.hidden_states[-1][0, last].to(torch.float32)             # [3584]
        return float((h @ self.w.squeeze(0)) + self.b.squeeze(0))


# ===========================================================================
# IXC-2.5-Reward-7B — InternLM-XComposer2.5 + reward head (general multimodal RM)
# ===========================================================================
class IXCRewardAdapter(RewardAdapter):
    """internlm/internlm-xcomposer2d5-7b-reward. Different family (InternLM2 LLM +
    InternViT). Uses the model's own ``get_score(chat, [image], hd_num)`` API."""

    key = "ixc-2.5"
    display_name = "IXC-2.5-Reward-7B"
    category = "general_mm"
    contract = PROMPT_CONDITIONED
    backbone = "InternLM2-7B"

    def __init__(self, *a, hd_num: int = 1, **k):
        super().__init__(*a, **k)
        # hd_num tiles the image into sub-images -> a long visual sequence. With
        # only EAGER attention available (no flash/sdpa on this Ampere box), the
        # L x L score matrix is materialised in fp32, so the card default hd_num=9
        # (and even 4) OOMs a 20GB GPU. hd_num=1 keeps the slide a single tile.
        self.hd_num = hd_num

    def load(self):
        import torch
        from transformers import AutoConfig, AutoModel, AutoTokenizer
        self.torch = torch
        # config defaults to flash_attention_2 (flash_attn not installed on this
        # Ampere box) -> force the self-contained eager attention path.
        cfg = AutoConfig.from_pretrained(self.path, trust_remote_code=True)
        cfg.attn_implementation = "eager"
        # transformers>=5 drops generation attrs (max_length) from PretrainedConfig;
        # the IXC modeling reads config.max_length at init -> re-add it.
        if not hasattr(cfg, "max_length"):
            cfg.max_length = 16384
        # The model (~20GB fp16) does not fit one 20GB Ampere card with the forward
        # activations, so we shard across GPUs. device_map="auto" splits modules the
        # custom apply_chat_template later cats together (text embeds + vision embeds
        # land on different GPUs -> device-mismatch). So we hand-build a device_map
        # that CO-LOCATES every module the embedding assembly touches
        # (tok_embeddings, vit, vision_proj, norm, score, plora norms) on GPU0 and
        # spreads only the transformer layers across the remaining GPUs; accelerate
        # hooks move the hidden state between layer devices. (Viable only because
        # build_mlp was patched to build the vision tower from CONFIG, not a nested
        # from_pretrained, which made device_map's meta-init crash before.)
        ng = torch.cuda.device_count()
        if ng > 1:
            n = cfg.num_hidden_layers
            device_map = {m: 0 for m in ("vit", "vision_proj", "model.tok_embeddings",
                                         "model.norm", "score", "plora_glb_GN", "plora_sub_GN")}
            for i in range(n):  # layers on GPUs 1..ng-1, GPU0 reserved for assembly
                device_map[f"model.layers.{i}"] = 1 + (i * (ng - 1)) // n
        else:
            device_map = {"": 0}
        self.model = AutoModel.from_pretrained(
            self.path, config=cfg, torch_dtype=torch.float16, device_map=device_map,
            trust_remote_code=True)
        self.model = self.model.eval()
        tok = AutoTokenizer.from_pretrained(self.path, trust_remote_code=True)
        self.model.tokenizer = tok
        return self

    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        torch = self.torch
        question, ans = ELICITATIONS[variant]
        chat = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": ans},
        ]
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            s = self.model.get_score(chat, [_resolve(image_path, self.repo)], hd_num=self.hd_num)
        return float(s)


# ===========================================================================
# PickScore-v1 — CLIP-H/14 fine-tuned on Pick-a-Pic (general preference reward)
# ===========================================================================
class PickScoreAdapter(RewardAdapter):
    """yuvalkirstain/PickScore_v1. A *second* general-multimodal preference reward,
    deliberately a DIFFERENT architecture from Skywork: a CONTRASTIVE CLIP-H/14
    fine-tuned on 500K human pairwise choices (Pick-a-Pic), not a generative VLM
    with a value head. The reward is the CLIP logit between the slide and a generic
    'high-quality professional slide' caption (== the PROMPT_CONDITIONED positive
    assertion), so the clean twin should match that caption more than the defective
    one. Having two general rewards on *unrelated backbones* is what lets the G7
    finding speak at the category level rather than per instance."""

    key = "pickscore"
    display_name = "PickScore-v1"
    category = "general_mm"
    contract = PROMPT_CONDITIONED
    backbone = "CLIP-H/14"

    def load(self):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(self.path)
        self.model = AutoModel.from_pretrained(self.path, dtype=torch.float32).to("cuda").eval()
        return self

    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        from PIL import Image
        torch = self.torch
        # the positive assertion is a self-contained 'good slide' caption; generic vs
        # probe differs only in naming containment/overflow (mirrors C0->C3 / Skywork).
        _q, caption = ELICITATIONS[variant]
        img = Image.open(_resolve(image_path, self.repo)).convert("RGB")
        # logits_per_image == logit_scale * normalize(img_emb) . normalize(txt_emb), i.e.
        # exactly the PickScore reward. (get_image_features returns an output object on
        # transformers 5.x, so go through the full forward — same path as CLIP-IQA.)
        inputs = self.processor(text=[caption], images=img, padding=True, truncation=True,
                                max_length=77, return_tensors="pt").to("cuda")
        with torch.no_grad():
            score = self.model(**inputs).logits_per_image[0, 0]
        return float(score)


# ===========================================================================
# CLIP-IQA — antonym-prompt zero-shot perceptual quality on CLIP ViT-L/14
# ===========================================================================
class CLIPIQAAdapter(RewardAdapter):
    """CLIP-IQA-style zero-shot perceptual-quality scorer (Wang et al., 'Exploring
    CLIP for Assessing the Look and Feel of Images', AAAI'23). Antonym-prompt
    method: P('Good photo.') under softmax over {'Good photo.', 'Bad photo.'} from
    the CLIP image-text logits — NO trained head. A *second* aesthetic/perceptual
    foil whose METHOD differs from the LAION linear MSE head (it shares the CLIP
    ViT-L/14 backbone, an honest caveat: the two aesthetic scorers are
    method-diverse, not backbone-diverse). Pure perception, zero layout/document
    supervision — shows a second aesthetic-class scorer also misses render-overflow."""

    key = "clip-iqa"
    display_name = "CLIP-IQA (ViT-L/14)"
    category = "aesthetic"
    contract = POINTWISE
    backbone = "CLIP ViT-L/14"
    trained_reward = False  # zero-shot antonym-prompt heuristic, not a preference RM

    POS = "Good photo."
    NEG = "Bad photo."

    def load(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.model = CLIPModel.from_pretrained(self.path).to("cuda").eval()
        self.processor = CLIPProcessor.from_pretrained(self.path)
        return self

    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        from PIL import Image
        torch = self.torch
        img = Image.open(_resolve(image_path, self.repo)).convert("RGB")
        inputs = self.processor(text=[self.POS, self.NEG], images=img,
                                return_tensors="pt", padding=True).to("cuda")
        with torch.no_grad():
            out = self.model(**inputs)
            probs = out.logits_per_image.softmax(dim=-1)  # [1, 2]
        return float(probs[0, 0])                          # P('Good photo.')


# ===========================================================================
# Aesthetic predictor — CLIP ViT-L/14 + LAION linear aesthetic head (pure aesthetic)
# ===========================================================================
class AestheticAdapter(RewardAdapter):
    """LAION aesthetic predictor: a linear/MLP head on frozen CLIP ViT-L/14 image
    features (the "improved-aesthetic-predictor" weights). Pure visual aesthetics,
    no document/layout supervision at all — the foil that shows even an aesthetic
    reward misses render-containment overflow."""

    key = "aesthetic"
    display_name = "LAION-Aesthetic (CLIP-L/14)"
    category = "aesthetic"
    contract = POINTWISE
    backbone = "CLIP ViT-L/14"
    trained_reward = False  # heuristic aesthetic head, not a preference-trained RM

    def __init__(self, path: str, *a,
                 clip_path: str = "/home/gpus/models/clip-vit-large-patch14", **k):
        super().__init__(path, *a, **k)
        self.clip_path = clip_path

    def load(self):
        import torch
        import torch.nn as nn
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        # openai CLIP ViT-L/14 in transformers form; get_image_features == the
        # 768-d projected image embedding the LAION head was fit on.
        self.clip = CLIPModel.from_pretrained(self.clip_path).to("cuda").eval()
        self.processor = CLIPProcessor.from_pretrained(self.clip_path)

        class _MLP(nn.Module):
            def __init__(self, d=768):
                super().__init__()
                self.layers = nn.Sequential(
                    nn.Linear(d, 1024), nn.Dropout(0.2), nn.Linear(1024, 128),
                    nn.Dropout(0.2), nn.Linear(128, 64), nn.Dropout(0.1),
                    nn.Linear(64, 16), nn.Linear(16, 1))

            def forward(self, x):
                return self.layers(x)

        self.head = _MLP(768).to("cuda")
        sd = torch.load(self.path, map_location="cpu")
        self.head.load_state_dict(sd)
        self.head.eval()
        return self

    def score(self, image_path: str, *, variant: str = DEFAULT_VARIANT) -> float:
        from PIL import Image
        torch = self.torch
        img = Image.open(_resolve(image_path, self.repo)).convert("RGB")
        inputs = self.processor(images=img, return_tensors="pt").to("cuda")
        with torch.no_grad():
            # the 768-d projected CLIP image embedding (== openai clip
            # encode_image), computed explicitly: get_image_features returns the
            # vision output object on transformers 5.x, so go via the projection.
            vis = self.clip.vision_model(pixel_values=inputs["pixel_values"])
            feat = self.clip.visual_projection(vis.pooler_output)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            val = self.head(feat.float())
        return float(val.item())


# ---- registry --------------------------------------------------------------
ADAPTERS: dict[str, type[RewardAdapter]] = {
    DocRewardAdapter.key: DocRewardAdapter,
    SkyworkVLAdapter.key: SkyworkVLAdapter,
    IXCRewardAdapter.key: IXCRewardAdapter,
    PickScoreAdapter.key: PickScoreAdapter,
    AestheticAdapter.key: AestheticAdapter,
    CLIPIQAAdapter.key: CLIPIQAAdapter,
}

DEFAULT_PATHS: dict[str, str] = {
    "docreward": "/home/gpus/models/DocReward-3B",
    "skywork-vl": "/home/gpus/models/Skywork-VL-Reward-7B",
    "ixc-2.5": "/home/gpus/models/IXC-2.5-Reward-7B",
    "pickscore": "/home/gpus/models/PickScore_v1",
    "aesthetic": "/home/gpus/models/aesthetic/sac+logos+ava1-l14-linearMSE.pth",
    "clip-iqa": "/home/gpus/models/clip-vit-large-patch14",
}


def build(key: str, path: str | None = None, repo: Path | None = None, **kw) -> RewardAdapter:
    cls = ADAPTERS[key]
    return cls(path or DEFAULT_PATHS[key], repo=repo, **kw)
