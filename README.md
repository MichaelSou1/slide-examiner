# Slide-Examiner

面向 **VLM 幻灯片质检** 的研究工具集，实现 [`specs/SPEC_slide_examiner_attribution.md`](specs/SPEC_slide_examiner_attribution.md) 中的 SlideProbe 方案。

> 核心主张：VLM 在渲染文档（幻灯片）质检上的失败，主要来自**感知保真度**而非**推理能力**；用**程序化缺陷注入**（零标注成本、精确标签）训练的小型专用 examiner，能在几何类检查上超过大型通用模型；并且 examiner 的质量可以在下游（GEPA prompt 进化）被外在地度量。

本仓库目前是一套**可运行的脚手架（v0）**：完整打通了数据构建 → 诊断 → 修复 → 训练 → 下游优化的本地契约与 dry-run 流程，真实的栅格渲染、VLM 推理、QLoRA 训练与 GEPA 优化需要额外的外部依赖、模型权重、GPU 与数据集（见[当前边界](#当前边界)）。

-----

## 研究问题

- **RQ1（诊断）**：VLM 的质检失败在多大程度上归因于感知（看不准）vs 推理（看见了但判断不了）？该归因是否随缺陷类型（几何 vs 语义）、模型规模、输入分辨率系统性变化？
- **RQ2（修复）**：在合成缺陷上 LoRA 微调的小型 examiner（8B），能否在几何类检查上超过 zero-shot 的更大模型，并泛化到真实 deck？
- **RQ3（下游）**：examiner 的内在质量是否单调地转化为 GEPA prompt 进化的收敛效率与最终质量？“可验证 linter（选择信号）+ VLM 文本批评（反思信号）分离”是否优于任一单源信号？

-----

## 安装

本项目用 conda 管理环境。在仓库根目录：

```bash
conda env create -f environment.yml
conda activate slide-examiner
pytest
```

环境以 `python=3.12` 为基底，依赖以 `pyproject.toml` 为单一来源、通过 pip 做可编辑安装，安装后提供命令行入口 `slide-examiner`。

需要真实渲染 / VLM 推理 / 训练能力时再装可选 extras：

```bash
pip install -e ".[render]"   # Playwright + python-pptx
pip install -e ".[vlm]"      # transformers + accelerate + pillow
pip install -e ".[all]"      # 全部
```

> VLM 推理 / QLoRA 训练需要与本机 CUDA 匹配的 PyTorch；extras 默认拉取 CPU 版，建议按 PyTorch 官方指引单独安装 GPU 版。

修改依赖后同步环境：

```bash
conda env update -f environment.yml --prune
```

-----

## 核心概念

- **中间表示（IR）**：`schemas.py` 定义 `BBox / Element / Slide / Deck / DefectLabel / ManifestSample`，所有注入与质检都作用在该结构化表示上，再渲染成图。
- **缺陷分类学**：`taxonomy.py` 定义两组共 12 类缺陷——
  - **G 组（几何/感知类）**：G1 文本溢出、G2 元素重叠、G3 对齐偏移、G4 字号不一致、G5 品牌色违规、G6 边距违规，每类带严重度网格 θ。
  - **S 组（语义/推理类）**：S1 标题-正文不匹配、S2 叙事顺序破坏、S3 术语口径不一致、S4 密度违规、S5 逻辑缺段、S6 图文矛盾。
- **几何 linter**：`geometry.py` 对 G1–G6 给出符号化检测（G5 使用 CIELAB ΔE，而非 RGB 距离）。
- **归因协议**：在 模态 A（仅图）/ B（无损结构化 oracle）/ B′（caption oracle）/ C（图+oracle）× 任务 T1 检测 / T2 定位 / T3 修复 上跑同一组样本，按
  - A 失败 ∧ B 成功 → **感知瓶颈**
  - A 失败 ∧ B 失败 → **推理瓶颈**
  - A 成功 ∧ T3 失败 → **执行瓶颈**

  做逐缺陷、逐模型的归因（`analysis.py`）。
- **Oracle 去泄漏**：注入器会把 ground-truth 记号（`expected_bbox`、`narrative_order_broken` 等）写进 IR 元数据供 linter/repair 使用；构建模态 B/C 的 oracle 时由 `schemas.oracle_view()` 统一剥除这些键，避免把答案直接喂给模型而污染归因结论。

-----

## 命令行用法

### 1. 数据构建（注入 + 渲染 + 数据集）

```bash
# 把结构化内容 JSON 生成为 deck 的 HTML 脚手架
slide-examiner generate content.json runs/generated_html

# 规整输入为 IR（JSON / 标注 HTML / PPTX 几何抽取）
slide-examiner ingest deck.pptx data/deck_ir.json
slide-examiner ingest annotated_slide.html data/slide_ir.json

# 注入单个缺陷并写出 manifest
slide-examiner inject data/slide_ir.json G1_TEXT_OVERFLOW runs/injected data/manifest.jsonl --severity 16

# 按严重度网格批量构建合成 manifest（含 held-out 与负样本）
slide-examiner build-synthetic runs/out data/manifest.jsonl data/slide_ir.json deck_ir.json

# 数据源登记与下载
slide-examiner data-sources
slide-examiner download-source internal_desensitized data/internal.zip --url file:///path/to/internal.zip
```

### 2. 诊断（SlideProbe 矩阵 + 归因分析）

```bash
# 写出预注册的实验矩阵（模型 × 模态 × 任务 × 模板 × 分辨率 × seed）
slide-examiner matrix configs/slideprobe_matrix.json

# 在矩阵上运行质检（adapter: mock / replay / qwen-local / openai）
slide-examiner run-matrix data/manifest.jsonl configs/slideprobe_matrix.json runs/probe/matrix.jsonl --adapter mock --limit 10

# 单 adapter 跑 mock SlideProbe
slide-examiner probe data/manifest.jsonl runs/probe/mock.jsonl

# 汇总检测指标、A/B 归因、模板坍缩、心理物理阈值、方差门控
slide-examiner analyze runs/probe/mock.jsonl -o runs/probe/summary.json
slide-examiner distribution data/manifest.jsonl -o reports/distribution.json

# 预注册 Go/No-Go 假设门控
slide-examiner hypotheses runs/probe/summary.json -o reports/hypotheses.json

# 两比例样本量/功效估计
slide-examiner power 0.50 0.70

# 渲染 Markdown 报告
slide-examiner report runs/probe/summary.json reports/slideprobe.md
```

### 3. 修复（linter 闭环 + 反作弊审计）

```bash
slide-examiner lint path/to/slide.json
slide-examiner repair path/to/slide.json runs/repaired_slide.json
slide-examiner hacking-audit path/to/slide.json -o reports/hacking.json
slide-examiner panel eval/panel_ratings.jsonl -o reports/panel_summary.json
```

### 4. Examiner 训练

```bash
# 导出 QwenVL 风格 SFT（pointwise / pairwise）
slide-examiner build-sft data/manifest.jsonl data/sft_pointwise.jsonl
slide-examiner build-sft data/manifest.jsonl data/sft_pairwise.jsonl --mode pairwise

# 写出 / 执行 Qwen-VL LoRA 训练命令（--execute 才真正启动）
slide-examiner train-plan data/sft_pointwise.jsonl models/examiner --config configs/train_examiner.json
slide-examiner train-examiner data/sft_pointwise.jsonl models/examiner --execute
```

### 5. 下游（GEPA prompt 进化效用）

```bash
# 单条件 dry-run 计划
slide-examiner gepa-plan tasks/train.jsonl tasks/val.jsonl tasks/test.jsonl runs/gepa/plan.json

# Part 3 全部反馈条件（linter / zero-shot 8B / zero-shot strong / finetuned-8B / hybrid）
slide-examiner gepa-conditions tasks/train.jsonl tasks/val.jsonl tasks/test.jsonl runs/gepa/conditions.json
```

### 实用工具

```bash
# 仅检查代码入口面（import 是否可用、符号是否暴露；不做任何行为/经验验证）
slide-examiner audit
```

-----

## 目录结构

```
slide_examiner/
  schemas.py        # IR + oracle_view 去泄漏
  taxonomy.py       # G1–G6 / S1–S6 缺陷定义与严重度网格
  geometry.py       # 几何 linter（CIELAB ΔE）
  injection.py      # 程序化缺陷注入
  experiment.py     # 注入分发 + 单 artifact → manifest
  dataset.py        # 注入结果 → ManifestSample / manifest JSONL
  synthetic.py      # 严重度网格批量构建（含 held-out / 负样本）
  matrix.py         # 预注册实验矩阵
  adapters.py       # ExaminerAdapter 基类 + MockAdapter + payload 构建
  model_adapters.py # replay / Qwen-VL 本地 / OpenAI 兼容 适配器
  probe.py          # ProbeRunner（模态 × 任务 执行器）
  orchestrator.py   # run-matrix 编排
  analysis.py       # 指标 / 归因 / 模板坍缩 / 心理物理 / 方差门控
  statistics.py     # 方差门控效应量
  power.py          # 两比例样本量估计
  hypotheses.py     # 预注册假设门控
  repair.py         # G1–G6 确定性修复 + linter 复检
  hacking.py        # 反作弊审计
  panel.py          # 人工/API 评审聚合
  sft.py            # SFT JSONL 导出
  training.py       # LoRA 训练命令/配置
  gepa_eval.py      # 混合反馈评估器（linter + examiner ASI）
  gepa_runner.py    # GEPA 运行计划/条件矩阵
  generator.py      # 内容 JSON → Deck IR/HTML
  ingest.py         # JSON/HTML/PPTX → IR，及 caption 生成
  render.py         # HTML/PPTX 渲染脚手架
  reports.py        # 分析摘要 → Markdown
  distribution.py   # manifest/linter 缺陷分布
  data_sources.py   # 数据源登记/下载
tests/              # 本地契约与冒烟管线测试
specs/              # 研究 spec 与 novelty 分析
docs/               # 实现状态对照
```

-----

## 当前边界

代码层面打通了完整 spec 的本地契约与可执行 dry-run 脚手架。以下环节需要外部资源才能产出真实的研究结论：

- **真实 deck 语料**：Zenodo10K/PPTAgent、SlidesBench/PPTBench、脱敏实习 deck。
- **真实栅格渲染**：安装 Playwright 浏览器和/或 LibreOffice 后渲染样本。
- **真实 VLM 推理**：安装模型依赖并提供 Qwen3-VL / API 模型访问。
- **真实 8B QLoRA 训练**：在目标 GPU 上执行生成的训练命令。
- **真实 GEPA 优化**：安装 GEPA 并以真实 generator/linter/examiner 跑非 dry-run rollout。
- **人工/Panel 评审**：收集 Part 3 所需的外部评审标签。

当前测试套件验证的是本地契约与冒烟管线（含 oracle 去泄漏回归测试），**不是**经验性主张本身。详见 [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)。

-----

## 交付物

1. **工程侧**：可运行的幻灯片生成 agent（双渲染 + 分层质检 + GEPA 调优后的 Skill prompt）。
2. **学术侧**：论文草稿 + SlideProbe 诊断集与注入器开源。
3. **复用资产**：缺陷注入器与归因协议代码。
