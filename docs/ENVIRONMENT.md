# 环境与可移植性（ENVIRONMENT）

本文档说明如何在一台新机器上**可移植地**复现本项目的运行环境，以及哪些部分是机器无关（portable）、哪些部分天然依赖本机 GPU/CUDA。

依赖以 [`pyproject.toml`](../pyproject.toml) 为**单一来源**，[`environment.yml`](../environment.yml) 只负责建 conda 壳并做可编辑安装。`slide_examiner/` 包在 import 时只依赖 `pydantic`，所有重依赖都在用到它的函数内**惰性导入**——所以 `import slide_examiner` 与 CLI 本身永远可移植，缺哪个 extra 只在真正调用对应功能时才报错。

-----

## 1. 分层依赖模型

| 层 | extra | 引入的依赖 | 可移植性 | 用途 |
|---|---|---|---|---|
| **core** | （默认） | `pydantic` | ✅ 任意 OS / 无 GPU | IR、注入、契约、CLI 骨架 |
| analysis | `[analysis]` | `numpy` `scipy` | ✅ | 诊断指标 / 统计 / 功效 |
| render | `[render]` | `playwright` `python-pptx` `pillow` | ✅（浏览器另装，见 §4） | 栅格渲染 + PPTX 几何抽取 |
| data | `[data]` | `pyarrow` | ✅ | benchmark arrow/parquet 适配 |
| api | `[api]` | `openai` | ✅ | 调用 OpenAI 兼容在线模型 |
| figures | `[figures]` | `matplotlib` | ✅ | 报告/论文出图 |
| **test** | `[test]` | 上面 analysis+render+data + `pytest` | ✅ | **自包含测试基线**：fresh clone 即 `pytest` 全绿 |
| **dev** | `[dev]` | `[test]` + `ruff` | ✅ | 开发（lint + test） |
| **all** | `[all]` | `[dev]` + api + figures | ✅ **CPU-only 全功能** | 全部可移植能力，无需 GPU |
| vlm | `[vlm]` | `transformers` `accelerate` `qwen-vl-utils` `safetensors`（+render+api） | ⚠️ 需 GPU + 自装 torch | 本地 VLM 推理 |
| train | `[train]` | `transformers` `accelerate` `peft` `wandb` | ⚠️ 需 GPU | QLoRA examiner 训练 |
| optim | `[optim]` | `gepa` | ✅（运行需本地服务） | GEPA 下游优化 |

> **关键不变量**：`[all]` 是**纯 CPU、跨平台**的——它**不**含 `torch` / `vllm`，所以在任何机器上 `pip install -e ".[all]"` 都不会因为 CUDA 不匹配而失败。GPU 栈是独立的一层（§3），需要手动按本机 CUDA 安装。

-----

## 2. 快速开始（可移植基线，无需 GPU）

```bash
# 1) 建壳 + 装可移植测试基线（environment.yml 里是 -e .[dev]）
conda env create -f environment.yml
conda activate slide-examiner

# 2) 验证：一行命令应全绿（GPU/网络无关；skillopt/gepa 等缺失自动 skip）
pytest                       # 期望 ~221 passed, 2 skipped

# 3) 需要渲染/出图/在线模型时，装满可移植层
pip install -e ".[all]"
playwright install chromium  # 渲染需要一次性下载浏览器内核，见 §4
```

CLI 入口 `slide-examiner --help`；单步契约操作走 CLI，多步真实实验走 `scripts/`（见 [README](../README.md) 与 `docs/PART3_RUNBOOK.md`）。

-----

## 3. GPU / CUDA 层（机器相关，不可移植，需手装）

真实 VLM 推理、QLoRA 训练、reward 审计需要 GPU。`torch` / `vllm` **故意不写进 `pyproject.toml`**，因为它们的 wheel 必须匹配本机 CUDA——写死任何一个版本都会在别的机器上装坏。

**本机已验证的已知好组合**（4×RTX 3080 20GB，Ampere `sm_86`）：

| 组件 | 版本 | 备注 |
|---|---|---|
| NVIDIA 驱动 | 570.211.01 | |
| CUDA toolkit | 12.4 | `nvcc 12.4` |
| PyTorch | `2.6.0+cu124` | `torch.cuda.is_available() == True` |
| transformers | 5.x（`>=4.50`） | examiner / reward 适配器 |
| vLLM | 见独立 conda 环境 | serving，TP；配方见脚本 |

安装顺序（在别的机器上请把 `cu124` 换成本机 CUDA 对应的索引）：

```bash
# 先按本机 CUDA 装 torch（示例：CUDA 12.4）
pip install torch --index-url https://download.pytorch.org/whl/cu124
# 再装项目的推理/训练层
pip install -e ".[vlm]"      # 本地 VLM 推理（transformers/accelerate/qwen-vl-utils/safetensors）
pip install -e ".[train]"    # QLoRA 训练（peft/wandb；实际训练走 LLaMA-Factory）
# vLLM 按本机 CUDA 单独装；本仓库用独立 conda 环境承载（见下）
```

**serving 注意**（本机实测，见 `memory/vllm-serving-gotchas` 与脚本内注释）：
- vLLM serve 用**独立 conda 环境**（如 `vllm-latest` / `vllm-qwen`），不与本环境混装，避免 ABI 冲突。
- examiner（8B/merged）serve 需 **TP=2**，单卡会 KV-cache OOM。
- 多数 sweep 把 `serve + rollout + teardown` 放进**单个脚本**：本机 harness 会回收后台进程，不能让长驻 server 与独立 rollout 命令共存。
- 不要用宽匹配 `pkill` 杀 `VLLM::EngineCore`（会误伤）；用脚本自带的 teardown。

-----

## 4. 渲染浏览器内核（Playwright）

`[render]` 只装 playwright 的 **python 包**；HTML→PNG 栅格还需要一个浏览器内核，二选一：

```bash
playwright install chromium          # 推荐：下载 playwright 自带 chromium
# 或复用系统 Chrome/Chromium，并通过环境变量指路：
export SLIDE_EXAMINER_CHROME=/usr/bin/chromium
```

渲染逻辑 `slide_examiner/render.py` 会依次尝试 bundled chromium → system chrome/chromium。PPTX 渲染可另设 `SLIDE_EXAMINER_SOFFICE` 指向 LibreOffice。

-----

## 5. 环境变量（`.env` 驱动，便于跨机器配置）

API 访问与本机权重路径**全部走环境变量**，可移植性的核心。项目自带零依赖的 `.env` 加载器（`slide_examiner/api_config.py:load_dotenv`，真实环境变量优先）。在仓库根放一个 `.env`：

```bash
# —— 在线模型（OpenAI 兼容；DashScope/vLLM 等都可）——
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PART3_API_STYLE=chat                 # chat | responses
PART3_DISABLE_THINKING=1             # 推理模型禁 thinking，避免空 content

# —— 按角色独立配服务（可选，留空则回落到上面的 OPENAI_*）——
# 角色 ∈ {GENERATOR, OPTIMIZER, JUDGE, EXAMINER}，各自 MODEL/BASE_URL/API_KEY/API_STYLE
PART3_GENERATOR_MODEL=qwen3.6-flash
PART3_GENERATOR_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PART3_GENERATOR_API_KEY=sk-...
PART3_EXAMINER_MODEL=qwen-vl-max     # 例：E8 复核走 DashScope qwen-vl-max

# —— 本机权重根目录（reward / 本地 VLM）——
SLIDE_EXAMINER_MODELS_DIR=/path/to/your/models

# —— 渲染器覆盖（可选）——
SLIDE_EXAMINER_CHROME=/usr/bin/chromium
SLIDE_EXAMINER_SOFFICE=/usr/bin/soffice
```

> `.env` 已在 `.gitignore` 中，不会带密钥入库。角色解析顺序：`PART3_<ROLE>_*` → 可选 fallback 角色 → 共享 `OPENAI_*`（详见 `api_config.resolve_role`）。

-----

## 6. 本地模型权重约定（不入库）

权重体积大、不重分发。本项目用 `SLIDE_EXAMINER_MODELS_DIR`（默认 `/home/gpus/models`，可被环境变量覆盖）作为根目录，reward 适配器按固定子目录名查找：

```
$SLIDE_EXAMINER_MODELS_DIR/
  Qwen3-VL-8B-Instruct/            # 训练/推理底座
  DocReward-3B/  Skywork-VL-Reward-7B/  PickScore_v1/  clip-vit-large-patch14/   # reward 审计
  aesthetic/sac+logos+ava1-l14-linearMSE.pth                                      # 美学头
  IXC-2.5-Reward-7B/               # 延后项
```

开放世界结构 recover 需 **PP-DocLayoutV2**（transformers-native，经 hf-mirror 拉取）。微调产物 `runs/part2/examiner_lora_v2` / `examiner_merged_v2` 不入库（`scripts/push_adapter_hf.py` 可上传 HF）。

> **LLaMA-Factory 训练配置**（`configs/part2_*.yaml`）含写死的绝对路径（`model_name_or_path` / `dataset_dir` / `output_dir`）。在新机器上训练前需把这些路径改成本机实际位置——它们天然机器相关，不做模板化以保持训练复现的精确性。

-----

## 7. 论文构建（TeX）

`paper/main.tex` 用**本机原生 TeX Live 2026** 构建（`paper/build_paper.sh`）。conda 的 `texlive` 环境是**坏的桩**，勿用（见 `memory/paper-build-texlive`）。

-----

## 8. 可复现性边界

- 测试套件验证的是**本地契约与冒烟管线**（含 oracle 去泄漏回归），**不是**经验主张本身——结论以 `reports/` 与 `paper/main.pdf` 为准。
- 不入库的外部资源：模型权重、渲染 PNG、原始 rollout JSONL、真实语料（SlideAudit / Zenodo10K / PPTBench，经各自来源/镜像拉取）。
- `pyproject.toml` 给的是**下界版本**而非锁定版本，以保证跨平台可装；如需逐位复现，在目标机 `pip freeze > requirements.lock` 自行锁定。

-----

## 9. 维护

```bash
conda env update -f environment.yml --prune   # 改依赖后同步
ruff check slide_examiner scripts             # lint（dev extra）
pytest -q                                     # 回归（应全绿）
```

改了依赖只需动 `pyproject.toml`（单一来源）；`environment.yml` 一般不用动。
</content>
