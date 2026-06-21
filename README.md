# Slide-Examiner

面向 **VLM 幻灯片质检** 的研究代码库，实现并执行了 [`specs/SPEC_slide_examiner_attribution.md`](specs/SPEC_slide_examiner_attribution.md) 中的 SlideProbe 方案。

> **这是一篇 VLM 论文。** 核心贡献是 **N1（感知/推理归因）** + **N2（模板坍缩）** 的诊断，以及用**程序化缺陷注入**（零标注成本、精确标签）训练出的专用 examiner。一句话主张：
>
> VLM 在渲染文档（幻灯片）质检上的失败，**主要来自感知/校准而非高层推理**；几何类缺陷在 4B→30B、5 个视觉编码器家族上**一致地无法靠 pointwise 像素判别**（应归符号 linter），而**相对判断（pairwise/forced-choice）远胜绝对打分**；用注入缺陷微调的小型 examiner 能在**语义类**质检上逼近/超过大得多的通用模型，其价值还能在下游被外在地度量。

与早期版本不同，本仓库**不再是 dry-run 脚手架**：Part 1 / Part 2 / Part 3 三段实验都已在本机（4×RTX 3080 20GB）用**真实 VLM 推理、真实 QLoRA 训练、真实下游优化**跑通并产出报告。受体积限制，权重、渲染图、原始 rollout JSONL 不入库（见 [可复现性与边界](#可复现性与边界)），但所有分析报告、脚本与契约测试都在仓库内。

-----

## 项目现状速览

| 阶段 | 内容 | 状态 | 头条结果 | 报告 |
|---|---|---|---|---|
| **Part 1 · 诊断** | 感知/推理归因 + 模板坍缩（SlideProbe 三轨矩阵） | ✅ 真实跑通，Go/No-Go = **GO** | 几何盲跨 4B/8B/30B + 5 编码器家族稳健 → **G 组归 linter**；**相对判断 >> 绝对打分**（G1/S6 forced-choice 0.50→1.0）；S 组是 examiner 主场 | [`reports/slideprobe.md`](reports/slideprobe.md) 及 `reports/part1_*.md` |
| **Part 2 · 修复** | Qwen3-VL-8B QLoRA 专用 examiner | ✅ 真实训练 + 评估 | **微调 8B 在 S 组 pointwise bal-acc ≈0.99–1.0 > zs-30B 0.785 > zs-8B 0.64**；S4 密度 recall 微调 8B 1.0 vs zs-30B 0.65（p=4.5e-7）；几何 image-only 学会**弃答**（0 FPR，不幻觉几何） | [`reports/part2.md`](reports/part2.md) |
| **Part 3 · 下游效用（轻量佐证）** | examiner 质量 → 下游生成改进 | ✅ self-refine + GEPA + 真实 Hermes case | self-refine corr **+0.659**（方向为正、幅度小）；GEPA **+0.563**（效率 DV 反例，已调和）；真实售前 PPT agent 占位符缺陷 **20→0** | [`reports/part3.md`](reports/part3.md) |
| **Part 3 · 混合批评臂** | 符号–神经混合 critic + G7 渲染溢出新类 | ✅ 三协议跑通（6 模型 / 4 家族） | **hybrid 8/9 覆盖 @ bal-acc 0.885** ≫ linter 5/9、VLM 2/9；**G7 仅 VLM-C3 抓得到**（linter 0.00 / 已发表 reward model DocReward 0.28，盲） | [`reports/part3_hybrid.md`](reports/part3_hybrid.md) |

完整 36 个测试文件覆盖本地契约与冒烟管线（含 oracle 去泄漏回归）。诚实负例与本机算力降级在各报告中均如实记录（见下）。

-----

## 研究问题

- **RQ1（诊断）**：VLM 质检失败在多大程度上归因于感知（看不准）vs 推理（看见了但判断不了）？该归因是否随缺陷类型（几何 vs 语义）、模型规模、输入分辨率系统性变化？
- **RQ2（修复）**：在合成缺陷上 LoRA 微调的小型 examiner（8B），能否逼近/超过 zero-shot 的更大模型，并泛化到真实 deck 与公开 benchmark？
- **RQ3（下游，轻量佐证；非论文重心）**：examiner 的内在质量是否转化为**下游 slide 生成改进**的效率与最终质量？以 **self-refine（主佐证）+ GEPA skill-space（旁证）** 两条载体验证，并检验"**可验证 linter 选择门 + 学习型 examiner 反思**"的解耦反馈是否优于单源信号。
  > 注：verifier 质量→效率在 RL/text 域已被证实（Gao 2210.10760、PRIME 2602.11570），本问只在 **design 域**做下游效用佐证，**既不重新发现"反馈质量重要"，也不是一篇 skill 优化论文**。SkillOpt 第二载体因上游包不可用已移出主线、deferred。

-----

## 核心发现

### Part 1 — 感知/推理归因（[`reports/slideprobe.md`](reports/slideprobe.md)）

- **几何盲是稳健现象，归符号 linter**：G1–G6 在 4B/8B 上 pointwise 全 0 检出；只有 30B 才勉强破最粗的 G1。换 **5 个视觉编码器家族**（SigLIP2 / LLM-based / InternViT / NaViT 原生分辨率 / MoonViT）全部停在随机线（差别只在弃答 vs 过报的 bias）；分辨率 1536↔2048 无差别。→ 杠杆是**尺寸/推理**，不是编码器或像素预算。
- **几何盲其实是两种失败**：G1 文字溢出 = **校准失败**，forced-choice **完全复活**（pointwise 0.50 → 2-AFC **1.00**）；G3–G6 = **真·感知阈值**，forced-choice 也救不回（恒 0.50）。
- **相对判断 >> 绝对打分（H-rel）**：G1 溢出与 S6 图文矛盾两组独立证据均 0.50→1.0。
- **S 组是 examiner 主场**：30B page 级 bal-acc 0.745；deck 级"VLM 看图 caption"（B′）是最强通道。
- **S3 术语一致性移出 VLM**：改用确定性**术语一致性 linter**，bal-acc **1.000**（对比 VLM 30B 最佳 0.69）。
- 方法学：主指标一律 **balanced accuracy + 配对 clean**，严禁只看 recall（一致性核查缺陷只看 recall 会误报"100% 检出"）。

### Part 2 — 专用 examiner 训练（[`reports/part2.md`](reports/part2.md)）

- **架构正确的路由**（承 Part 1 结论）：S 组语义走 pointwise；**G2–G6 不做像素检测**，改"从结构复述（模态 B）+ image-only 弃答（模态 A）"；G1/S6 走 pairwise；S3 交给术语 linter。
- 微调 8B **S 组 pointwise bal-acc ≈0.99–1.0 > zs-30B 0.785 > zs-8B 0.64**；**S4 密度 recall 微调 8B 1.0 vs zs-30B 0.65**（two-proportion z **p=4.5e-7**）；OOD-severity 语义 0.917。
- 几何 image-only **学会弃答**（0 FPR，不从像素幻觉几何）；pairwise **v2** 修掉位置偏置后 G1 / S6 2-AFC 双双 **1.0**。
- **诚实负例**：① deck-scope 语义（S2/S5）pointwise 退化——SFT 缺 clean-deck 负样本导致恒报（已记 issue）；② 第三方 **SlideAudit**（2400 张真实标注 slide）image-only 迁移下，几何全模型 ≈0.5、合成强项不迁移 = **sim2real gap**，需 linter+结构。

### Part 3 — 下游效用 + 混合批评（[`reports/part3.md`](reports/part3.md) / [`reports/part3_hybrid.md`](reports/part3_hybrid.md)）

- **examiner 质量 → 下游增益**：self-refine（直接改这一份 deck）恢复**期望正向** corr **+0.659**，但幅度极小（gain 0.4–1.9%，强 generator 把任务地板抬高）；GEPA 的效率 DV 给出 **+0.563** 的反例（proxy 饱和 + running-best 伪迹），两载体方向相反但在机制上调和。
- **真实外部效度（Hermes 售前 PPT agent）**：在真实 16 页 deck 上，可验证缺陷 = 20 个未填模板占位符；**zs-30B 最强检测、微调 8B 在这个 OOD 缺陷上反而最弱** → 坐实"ft 学到的是缺陷分布而非普适质量"。examiner 批评驱动修订一轮后占位符 **20→0**。
- **符号–神经混合 critic**：按缺陷瓶颈静态路由（细几何→linter、文本语义→LLM、可感知但被格式压制的渲染类→VLM+换诱发）。**hybrid 8/9 覆盖 @ 0.885** ≫ linter-only 5/9、VLM-only 2/9。
- **G7 渲染溢出新类**（本工作可证伪的扩展）：bbox 合法但渲染溢出 ⇒ **几何 linter 结构上盲**。改诱发协议（C3 原子二分 + 强制证据）后，**C3 把 G7 跨 Qwen 9B/27B/3.6 + Gemma4 + InternVL/Ovis（6 模型/4 家族）从 0.50 救到 0.93–1.0**；已发表的设计 reward model **DocReward 对 G7 偏好准确率仅 0.28**（低于随机，完全盲）。

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

> 复现真实实验还需：与本机 CUDA 匹配的 PyTorch、vLLM、Qwen3-VL 4B/8B/30B 等权重、QLoRA 训练栈（LLaMA-Factory）。本机实测的 vLLM/serving 踩坑配方见各报告与 `scripts/`。

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
  - **G7 渲染容器溢出**（`defect_types.py` 中的扩展类，不改动冻结的 `taxonomy.py` enum）：声明 bbox 合法但渲染后内容溢出容器——**几何 linter 结构上盲，缺陷只在像素里可见**。
- **双 linter**：`geometry.py` 对 G1–G6 给符号化检测（G5 用 CIELAB ΔE 而非 RGB 距离）；`term_consistency.py` 对 S3 给确定性术语一致性检测（出现表 + 编辑距离聚类 ∪ text-LLM 漂移）。
- **架构正确的路由**（Part 1 实证结论 → Part 2/3 设计）：细几何归 linter；可感知但被绝对打分压制的类（G1 溢出、S6、G7）走 **pairwise / forced-choice / 换诱发的 VLM**；语义类走 pointwise examiner；S3 走术语 linter。
- **归因协议**：在 模态 A（仅图）/ B（无损结构化 oracle）/ B′（VLM 看图 caption）/ C（图+oracle）× 任务 T1 检测 / T2 定位 / T3 修复 上跑同一组配对样本：
  - A 失败 ∧ B 成功 → **感知瓶颈**
  - A 失败 ∧ B 失败 → **推理瓶颈**
  - A 成功 ∧ T3 失败 → **执行瓶颈**

  做逐缺陷、逐模型的归因（`analysis.py`）。
- **Oracle 去泄漏**：注入器会把 ground-truth 记号（`expected_bbox`、`narrative_order_broken` 等）写进 IR 元数据供 linter/repair 使用；构建模态 B/C 的 oracle 时由 `schemas.oracle_view()` 统一剥除这些键，避免把答案直接喂给模型而污染归因结论（`tests/test_oracle_leak.py` 回归保护）。
- **诱发协议（Part 3 混合臂）**：`elicit_*.py` 实现 C0 整张 taxonomy pointwise / C1 自由描述→分类 / C2 合成孪生 pairwise / C3 原子二分 + 强制证据，用来分离"格式压制 vs 能力缺失"。

-----

## 命令行用法

`slide-examiner --help` 列出全部子命令。下面按流程分组（库级 CLI 用于单步契约操作；真实多步实验由 `scripts/` 驱动，见[复现实验](#复现实验scripts)）。

### 1. 数据构建（注入 + 渲染 + 数据集）

```bash
# 内容 JSON → deck HTML 脚手架 / 规整输入为 IR（JSON / 标注 HTML / PPTX 几何抽取）
slide-examiner generate content.json runs/generated_html
slide-examiner ingest deck.pptx data/deck_ir.json

# 注入单个缺陷并写 manifest / 按严重度网格批量构建（含 held-out 与负样本）
slide-examiner inject data/slide_ir.json G1_TEXT_OVERFLOW runs/injected data/manifest.jsonl --severity 16
slide-examiner build-synthetic runs/out data/manifest.jsonl data/slide_ir.json deck_ir.json

# 真实数据：目录约定 / 数据源登记下载 / 清洗 clean 语料 / benchmark 适配
slide-examiner init-data-layout
slide-examiner data-sources
slide-examiner prepare-clean-corpus pptagent_zenodo10k data/raw/zenodo10k \
  data/ir/zenodo10k_clean data/manifests/zenodo10k_clean_candidates.jsonl \
  --summary reports/data_prep/zenodo10k_cleaning_summary.json --include-slide-samples
slide-examiner benchmark-plan pptbench reports/data_prep/pptbench_plan.json
slide-examiner prepare-benchmark pptbench data/raw/pptbench/tasks.jsonl \
  data/manifests/pptbench_tasks.jsonl --ir-dir data/ir/pptbench

# 渲染：把 manifest 渲染成多分辨率 PNG 并写回 image_path / 渲染 PPTX
slide-examiner render-manifest data/manifest.jsonl --long-edge 1024
slide-examiner render-resolutions data/slide_ir.json runs/rendered/res
slide-examiner render-pptx deck.pptx runs/rendered/pptx_pages
```

### 2. 诊断（SlideProbe 矩阵 + 归因分析）

```bash
slide-examiner matrix configs/slideprobe_matrix.json                       # 写预注册矩阵
slide-examiner run-matrix data/manifest.jsonl configs/slideprobe_matrix.json \
  runs/probe/matrix.jsonl --adapter mock --limit 10                        # adapter: mock/replay/qwen-local/openai
slide-examiner probe data/manifest.jsonl runs/probe/mock.jsonl             # 单 adapter mock probe
slide-examiner analyze runs/probe/mock.jsonl -o runs/probe/summary.json    # 指标/归因/模板坍缩/心理物理/方差门控
slide-examiner distribution data/manifest.jsonl -o reports/distribution.json
slide-examiner hypotheses runs/probe/summary.json -o reports/hypotheses.json  # 预注册 Go/No-Go 门控
slide-examiner power 0.50 0.70                                             # 两比例样本量/功效
slide-examiner report runs/probe/summary.json reports/slideprobe.md        # 渲染 Markdown 报告
```

### 3. 质检 linter + 修复 + 反作弊审计

```bash
slide-examiner lint path/to/slide.json            # 几何 linter（G1–G6）
slide-examiner lint-deck path/to/deck.json        # 术语一致性 linter（S3）
slide-examiner repair path/to/slide.json runs/repaired_slide.json
slide-examiner hacking-audit path/to/slide.json -o reports/hacking.json
slide-examiner panel eval/panel_ratings.jsonl -o reports/panel_summary.json   # 含 κ inter-annotator agreement
```

### 4. Examiner 训练

```bash
# 导出 QwenVL 风格 SFT（pointwise / pairwise）
slide-examiner build-sft data/manifest.jsonl data/sft_pointwise.jsonl
slide-examiner build-sft data/manifest.jsonl data/sft_pairwise.jsonl --mode pairwise

# 写出 / 执行 LoRA 训练命令（--execute 才真正启动）
slide-examiner train-plan data/sft_pointwise.jsonl models/examiner --config configs/train_examiner.json
slide-examiner train-examiner data/sft_pointwise.jsonl models/examiner --execute
slide-examiner eval-examiner runs/probe/eval.jsonl -o runs/probe/eval_summary.json
```

> Part 2 实际训练走 LLaMA-Factory（`configs/part2_qlora*.yaml` + `scripts/part2_*.py`），CLI 的 train-plan/train-examiner 是契约级命令生成器。

### 5. 下游（skill-space 优化效用）

```bash
slide-examiner gepa-plan tasks/train.jsonl tasks/val.jsonl tasks/test.jsonl runs/gepa/plan.json
slide-examiner gepa-conditions tasks/train.jsonl tasks/val.jsonl tasks/test.jsonl runs/gepa/conditions.json
slide-examiner run-gepa ...        # 真实 GEPA 优化路径（需安装 gepa + 本地 generator/examiner 服务）
```

-----

## 复现实验（`scripts/`）

各 Part 的真实端到端流程在 `scripts/` 下（库级 CLI 之外的实验驱动）：

- **Part 1** — `part1_build_corpus.py` / `part1_build_dataset.py` / `part1_freeze_dataset.py`（冻结+sha256）；三轨：`part1_linter_track.py`（轨 L 几何）、`part1_sgroup_crosssize.py`（轨 E 语义跨尺寸）、`g13_forced_choice.py` / `s6_forced_choice.py` / `s3_forced_choice.py`（轨 P 相对判断）；`part1_encoder_report.py`（5 编码器对照）；`part1_synthesis.py`（三表 + 门控）。
- **Part 2** — `part2_build_corpus.py` → `part2_build_dataset.py` → `part2_build_sft.py`（架构正确的路由）→ LLaMA-Factory QLoRA → `part2_eval.py` / `part2_serve_and_eval.sh`（serve+eval）/ `part2_slideaudit_eval.py`（真实迁移）→ `part2_synthesis.py`（带 Wilson CI 的报告）。
- **Part 3（效用）** — `part3_build_tasks.py`（vague brief 任务集）→ `part3_self_refine_sweep.sh`（主佐证 5 档 × 3 seeds × 3 tasks）/ `part3_faithful_sweep.sh`（GEPA 旁证）→ `part3_hacking_audit.py`（gold-vs-proxy）→ `part3_synthesis.py`；真实 agent 臂 `part3_hermes_case_sweep.sh` + `part3_hermes_revise.py`。
- **Part 3（混合臂）** — `part3_build_g7.py`（G7 数据）→ `part3_p1_roster.py` / `part3_p1_sweep.sh`（诱发协议，6 模型/4 家族）→ `part3_p2_eval.py` / `part3_p2_summary.py`（混合 critic 覆盖）→ `part3_p3_reward_audit.py`（DocReward 审计）→ `part3_p2_figures.py`（图）。

> 多数 sweep 把 vLLM serve + rollout + teardown 放进**单个脚本**（本机 harness 会回收后台进程，不能让长驻 server 与独立 rollout 命令共存）。具体踩坑见 `docs/PART3_RUNBOOK.md` 与脚本内注释。

-----

## 目录结构

```
slide_examiner/
  # —— IR / 缺陷 / linter ——
  schemas.py          # IR + oracle_view 去泄漏
  taxonomy.py         # G1–G6 / S1–S6 缺陷定义与严重度网格
  defect_types.py     # G7 等扩展缺陷类（不动冻结 taxonomy enum）
  injection.py        # 程序化缺陷注入
  template.py         # snap-to-master 模板（实证吸收几何缺陷）
  experiment.py       # 注入分发 + 单 artifact → manifest
  dataset.py          # 注入结果 → ManifestSample / manifest JSONL
  synthetic.py        # 严重度网格批量构建（含 held-out / 负样本）
  geometry.py         # 几何 linter（CIELAB ΔE）
  term_consistency.py # 术语一致性 linter（S3）
  # —— 诊断（Part 1）——
  matrix.py / orchestrator.py / probe.py     # 预注册矩阵 / run-matrix 编排 / 模态×任务执行器
  adapters.py / model_adapters.py            # examiner 适配器（mock / replay / Qwen-VL 本地 / OpenAI）
  examiner_contract.py / runtime.py          # IO 契约（模态 A/B/B′/C）+ 运行时（默认模态 C）
  analysis.py / statistics.py / power.py / hypotheses.py  # 指标/归因 / CI/效应量 / 功效 / 假设门控
  # —— 修复 / 训练（Part 2）——
  repair.py / hacking.py     # G1–G6 确定性修复 + 反作弊审计
  sft.py / training.py       # SFT JSONL 导出 / LoRA 训练命令与配置
  panel.py                   # 人工/API 评审聚合（κ）
  # —— 下游效用 / 混合批评（Part 3）——
  generator.py / skill_doc.py            # 被优化的 slide generator + 可编辑 skill 模块
  feedback_sources.py / optim_runtime.py # 5 档反馈源 + 统一 rollout 引擎（唯一自变量=反馈源）
  self_refine.py                         # self-refine 主载体
  gepa_runner.py / gepa_eval.py          # GEPA 旁证（真实优化路径 + 混合反馈评估器）
  skillopt_adapter.py / part3_experiment.py  # SkillOpt（移出主线，留存）+ Part3 驱动
  part3_quality.py                       # model-free common-quality DV（gold）
  hybrid_critic.py                       # 符号–神经混合 critic（按缺陷路由）
  elicit_common.py / elicit_freeform.py / elicit_pairwise.py  # 诱发协议 C0–C3
  pptx_ingest.py                         # PPTX → Deck IR（Hermes case study）
  # —— 辅助 ——
  ingest.py / render.py / generator.py / reports.py / distribution.py
  data_sources.py / data_prep.py / io.py / api_config.py / audit.py

scripts/    # 各 Part 的真实端到端实验驱动（part1_* / part2_* / part3_* / 渲染与拉取工具）
tests/      # 36 个测试文件：本地契约 + 冒烟管线 + oracle 去泄漏回归
specs/      # 研究 SPEC、novelty 分析、todo 执行清单
configs/    # Part 2 QLoRA / merge 配置
docs/       # 实现状态、数据准备指南、Part 3 runbook、参考文献与图
data/  runs/  reports/   # 数据 / 渲染与 rollout 产物 / 分析报告（大产物 .gitignore）
```

-----

## 可复现性与边界

代码层面完整实现了 spec 的契约、linter、注入、训练与下游优化链路；Part 1/2/3 的真实实验**已在本机执行**并产出报告。复现这些结论需要的外部资源：

- **GPU 与 serving**：4×RTX 3080 20GB（Ampere），vLLM 起 Qwen3-VL 4B/8B/30B 等本地服务（TP、AWQ/fp8 KV、`enable_thinking=false` 等配方见脚本与 `docs/`）。
- **模型权重**：Qwen3-VL 系列、2026 新 VLM（Gemma4 / InternVL3.5 / Ovis2.5 等，混合臂用）、已发表 reward model（DocReward-3B）；微调产物 `runs/part2/examiner_lora_v2` / `examiner_merged_v2` 不入库（`scripts/push_adapter_hf.py` 可上传 HF）。
- **真实语料**：第三方 **SlideAudit**（真实迁移评估的可信信号，经镜像拉取）、Zenodo10K/PPTAgent、PPTBench；真实人工标注集**延后为非必要**（自标自评有公正性嫌疑，详见 `specs/todo.md §12`）。
- **生成器 / 优化器**：Part 3 generator+reflection 用在线 API 模型；GEPA 需 `pip install gepa`；SkillOpt 上游包缺资产已移出主线。

测试套件验证的是**本地契约与冒烟管线**（含 oracle 去泄漏回归），**不是**经验性主张本身——经验结论以 `reports/` 下的报告为准。实现状态对照见 [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)，执行清单见 [`specs/todo.md`](specs/todo.md)。

-----

## 报告索引

- **Part 1**：[`reports/slideprobe.md`](reports/slideprobe.md)（三轨汇总）；细分 `reports/part1_geometry_threshold.md` / `part1_encoder_geometry.md` / `part1_resolution_forcedchoice.md` / `part1_sgroup_crosssize.md` / `part1_s6_manifest.md` / `part1_term_consistency.md` / `part1_linter_track.md` / `part1_dataset_freeze.md`。
- **Part 2**：[`reports/part2.md`](reports/part2.md)（6 张表 + 真实迁移 + Wilson CI）。
- **Part 3（效用）**：[`reports/part3.md`](reports/part3.md) + `reports/part3_discussion.md` + `reports/part3_hacking.md`。
- **Part 3（混合臂）**：[`reports/part3_hybrid.md`](reports/part3_hybrid.md)（图见 `docs/figs/`）。

-----

## 交付物

1. **学术侧**：VLM 论文（N1 感知/推理归因 + N2 模板坍缩 + 注入缺陷训练的专用 examiner），含 SlideProbe 诊断集、双 linter、混合 critic 与 G7 可证伪类。
2. **工程侧**：缺陷注入器 + 归因协议 + 专用 examiner + 符号–神经混合质检 router（可复用资产）。
3. **下游佐证**：examiner 质量→下游生成改进的外在效用度量（self-refine 主 + GEPA 旁），含 gold-vs-proxy 反作弊审计与真实 agent case-study。
