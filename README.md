# Slide-Examiner

面向 **VLM 幻灯片/文档质检** 的研究代码库，实现并执行了 [`specs/SPEC_slide_examiner_attribution.md`](specs/SPEC_slide_examiner_attribution.md) 中的 SlideProbe 归因方案，并汇总成一篇技术报告：**《It's the Elicitation, Not the Eyes: Diagnosing VLM Failures in Slide Quality Inspection and Routing a Symbolic–Neural Critic》**（[`paper/main.pdf`](paper/main.pdf)，17 页；当前**面向 AAAI-2027** 主技术轨投稿，7pp 压缩版为 R11 收尾步骤）。

> **一句话主张（重定位后的主线）。** **本工作的首要贡献是一套逐缺陷的归因协议**：它建立在**无损结构几何 oracle**（元素框 / 文本 / 样式，而非会重新注入感知误差的 model-written caption）之上，回答"VLM 漏检是**感知**（看不见）还是**校准/诱发**（看见了但不肯下判）"。诊断结论是**缺陷依赖**的，不是一句"VLM 像素盲"能概括。
> - **格式压制（旗舰类 G7 渲染溢出）**：bbox 合法但像素溢出。冻结模型在常规 `pointwise+rubric` 下弃答，**只把缺陷"命名"出来**就能检出，原子诱发在 **6 模型中 4 个**上救回并**迁移到人工标注的真实 slide**。G7 不是玩具——R5 在**真实 agent 生成的 deck** 里实测到它真实发生：**Zenodo10K 切片 81/93 deck**、**AutoPresent 切片 8/14 deck**。
> - **availability-of-reference（较弱）**：声明几何 **G1** 与图文矛盾 **S6** 的救回需要一张**配对 clean 参照**。
> - **真·感知地板（任何诱发都救不回）**：亚阈值 acuity 尾巴、OCR 受限术语一致性（S3）、以及 **G6 全局内容位移**。
>
> **诊断开出 critic，而非反过来。** 声明几何路由到符号 linter、格式压制类路由到一个再诱发的 VLM，把覆盖从 **2/9** 类（常规 pointwise VLM）抬到 **8/9**（bal-acc **0.86**），并与预注册的逐类路由 hybrid 持平——**混合 critic 是诊断的"推论"，不是我们主张的架构**。reward 侧审计（5 个公开 scorer + 1 个闭源前沿 VLM judge）复现同一裂痕：linter / 3B 文档 reward / 艺术美学头盲 G7，而两个通用多模态 reward + CLIP-IQA + VLM judge 抓得到——**G7 需要的是"渲染质量读出"而非"域标签 scorer"**。诊断在**真实 CC 版面**上复现（工具抽取无损 oracle，零标注）。**部署边界**：完整 hybrid 面向有 IR 的生成 agent；面对裸第三方像素，可部署的 critic 退化为那个再诱发的 VLM。注入缺陷微调的 8B examiner 在**域内**语义质检上超过 zs-30B（OOD 不迁移）。

与早期版本不同，本仓库**不再是 dry-run 脚手架**：Part 1 / Part 2 / Part 3 三段实验都已在本机（4×RTX 3080 20GB）用**真实 VLM 推理、真实 QLoRA 训练、真实下游优化**跑通并产出报告，经过一轮**面向顶会的加固复审**（todo_0623 的 E1–E8，含一次推翻自身早期结论的数据审计，见下），并已按一轮**模拟 AAAI 评审**做内容重定位（todo_0625 的 R0–R10：oracle-primary 重写、把摘要 scope 到 G7、量化 G7 在真实 deck 的发生率、隔离 null 结果）。受体积限制，权重、渲染图、原始 rollout JSONL 不入库（见 [可复现性与边界](#可复现性与边界)），但所有分析报告、脚本、论文源码、契约测试，以及一份 [Part 3 可复现 release bundle](#可复现性与边界) 都在仓库内。

-----

## 项目现状速览

| 阶段 | 内容 | 状态 | 头条结果 | 报告 |
|---|---|---|---|---|
| **Part 1 · 诊断** | 感知/推理归因（无损结构 oracle）+ 两种盲的拆分 | ✅ 真实跑通，Go/No-Go = **GO** | "看不见"拆成**亚感知 vs 格式压制**：改诱发即复活细对齐/色差（2-AFC 偏移 >0.8%w 饱和 1.0）；真盲只剩亚阈值尾巴 + **S3** + **G6 整页位移**；声明几何一律走 linter | [`reports/slideprobe.md`](reports/slideprobe.md)、`reports/_e8_*.md` 及 `reports/part1_*.md` |
| **Part 2 · 修复** | Qwen3-VL-8B QLoRA 专用 examiner（架构正确的路由） | ✅ 真实训练 + 评估 | 微调 8B 在 **S 组域内** pointwise bal-acc ≈**0.99–1.0** > zs-30B 0.785 > zs-8B 0.64；S4 密度 recall 1.0 vs zs-30B 0.65（p=4.5e-7）；几何 image-only 学会**弃答**（不幻觉几何）；**OOD 不迁移**（诚实记录） | [`reports/part2.md`](reports/part2.md) |
| **Part 3 · 下游效用（轻量佐证）** | examiner 质量 → 下游生成改进 | ✅ self-refine + GEPA + 真实 Hermes case + E6 unfloored | self-refine 方向为正 **+0.659** 但幅度 sub-1%；**E6**：换弱 generator 效应不是变大而是**消失**（+0.66→0.00）→ 头条 headroom 是**覆盖度**不在感知 critic 轴上；真实售前 PPT 占位符缺陷 **20→0** | [`reports/part3.md`](reports/part3.md) |
| **Part 3 · 混合批评臂** | 符号–神经混合 critic + G7 渲染溢出新类（真实 deck 实测发生）+ 多 RM 审计 + 开放世界 | ✅ 三协议跑通（6 模型 / 4 家族） | 诊断把覆盖从 **2/9（常规 pointwise VLM）抬到 8/9 @ 0.86**，与预注册逐类路由 hybrid 持平（混合是诊断的推论非主张）；**G7 检出取决于"渲染质量读出"而非"训练域标签"**（5 公开 reward + 1 闭源 VLM judge）；**G7 在真实 agent deck 真实发生**（Zenodo10K 81/93、AutoPresent 8/14）；开放世界（无 IR）→ critic 退化为 VLM-bound | [`reports/part3_hybrid.md`](reports/part3_hybrid.md) |

完整 **40 个测试文件**覆盖本地契约与冒烟管线（含 oracle 去泄漏回归）。诚实负例（域内强项不迁移 OOD、deck-scope 语义退化、sim2real gap、下游小效应）与本机算力降级在各报告与论文中均如实记录。

> **⚠ 一次推翻自身的修订（E8，2026-06）。** 早期 README/报告曾断言 "G3–G6 细几何 = 真·感知阈值，forced-choice 也救不回（恒 0.50）"。E8 的数据审计发现 G3/G5 的注入用了**不可见的外部参照**（绝对期望位置 / 品牌色板），使"对不对"在单图内**不可判定**——这才读成"亚感知"。**重做为内部对比**（一列里的某项相对其同列兄弟偏移/变色，单图内可判）后：G3 是**幅度门控的格式压制**（2-AFC 16px=0.83%w 饱和 1.0、原子 C3 在 48–64px 到 ≈0.90 平台），G5 内部色差 C3 在 ΔE40 到 0.99；真盲只剩亚阈值尾巴。**这套重做协议是可证伪的**：它没有救回一切——**G6 整页位移**在 6 模型上 2-AFC 仍恒处地板（真盲），**S6** 原 0.0 是"没渲染出图"的**数据 bug**（有效图语料上 2-AFC=1.00）。下文 Part 1 已按修订后口径叙述。

-----

## 研究问题

- **RQ1（诊断）**：VLM 质检失败在多大程度上归因于**感知**（看不准）vs **校准/诱发格式**（看见了但被 pointwise+rubric 压制）vs **推理**？该归因如何随缺陷类型（几何 vs 语义）、缺陷**幅度**、模型规模、输入分辨率系统性变化？
- **RQ2（修复）**：在合成缺陷上 LoRA 微调的小型 examiner（8B），能否逼近/超过 zero-shot 的更大模型，并泛化到真实 deck 与公开 benchmark？
- **RQ3（下游，轻量佐证；非论文重心）**：examiner 的内在质量是否转化为**下游 slide 生成改进**的效率与最终质量？以 **self-refine（主佐证）+ GEPA skill-space（旁证）** 两条载体验证，并检验"**可验证 linter 选择门 + 学习型 examiner 反思**"的解耦反馈是否优于单源信号。
  > 注：verifier 质量→效率在 RL/text 域已被证实（Gao 2210.10760、PRIME 2602.11570），本问只在 **design 域**做下游效用佐证，**既不重新发现"反馈质量重要"，也不是一篇 skill 优化论文**。E6 进一步把它收紧为：强 generator 把任务地板抬高、换弱 generator 后效应**消失**——下游头条是**覆盖度 headroom**（不在感知 critic 轴上）。SkillOpt 第二载体因上游包不可用已移出主线、deferred。

-----

## 核心发现（与论文 C1–C4 对应）

### Part 1 — 两种盲的拆分（[`reports/slideprobe.md`](reports/slideprobe.md) + `reports/_e8_*.md`）→ **C1/C2**

- **"看不见"是两种相反的失败**：① **格式压制**（看得见但被绝对打分埋掉）——**只改诱发方式，模型冻结**就能复活：G1 文字溢出 pointwise 0.50 → 2-AFC **1.00**；重做后的 **G3 对齐**是**幅度门控**（2-AFC 在 16px=0.83%w 饱和 **1.00**，原子 C3 在 48–64px 到 ≈**0.90** 平台）；**G5 内部色差** C3 在 ΔE40 到 **0.99**、2-AFC 在 ΔE12 到 1.00。② **真·感知地板**——只剩**亚阈值尾巴**（≤8px 偏移、≤6ΔE 近等亮度色差，side-by-side 也停在随机）、**OCR 受限的 S3 术语一致性**、以及 **G6 整页位移**（全局定位真盲）。
- **G6 是诚实的"真盲"旗舰**：整块内容偏向一边（内部对齐保持、边距不对称），6 模型 C3 bal-acc **0.504**、2-AFC **恒 tie**，绝对/不对称两种问法分别压垮 recall / specificity，直到内容被页边裁切才不再 tie。→ **linter 精确拥有它（0 FP），因为 VLM 真的看不见**，不是 linter 只是更便宜。这套重做协议**之所以可信，正因为它没救回 G6**。
- **声明几何一律走 linter——但理由被改写**：不是"VLM 像素盲"，而是"有结构化 IR 时 linter 更便宜、对声明几何精确、近 0 误报"。VLM 在超阈值的 C3/2-AFC 下其实能恢复（只是更低、且要过幅度门）。
- **编码器/分辨率不是杠杆**：换 **5 个视觉编码器家族**（SigLIP2 / LLM-based / InternViT / NaViT 原生分辨率 / MoonViT）pointwise 几何全停在随机线；1536↔2048 无差别。杠杆是**尺寸/诱发/幅度**。
- **S 组是 examiner 主场**：30B page 级 bal-acc 0.745；deck 级"VLM 看图 caption"（B′）是最强通道；**S3 移出 VLM**→ 确定性术语一致性 linter，bal-acc **1.000**（对比 VLM 30B 最佳 0.69）。
- 方法学：主指标一律 **balanced accuracy + 配对 clean**，严禁只看 recall。**逐类匹配诱发，无"全局最优 prompt"**——S1 标题/正文匹配是反例：原子 C3 在 recall 已饱和时反而拉高 FP（specificity 0.89→0.67），所以建议是"只对 recall 受限的类做原子分解"，不是"一律改 C3"（`reports/_s1_atomic_specificity_tradeoff.md`）。

### Part 2 — 专用 examiner 训练（[`reports/part2.md`](reports/part2.md)）→ **C4（支持性）**

- **架构正确的路由**（承 Part 1 结论）：S 组语义走 pointwise；**G2–G6 不做像素检测**，改"从结构复述（模态 B）+ image-only 弃答（模态 A）"；G1/S6 走 pairwise；S3 交给术语 linter。
- 微调 8B **S 组域内** pointwise bal-acc ≈**0.99–1.0** > zs-30B 0.785 > zs-8B 0.64；**S4 密度 recall 微调 8B 1.0 vs zs-30B 0.65**（two-proportion z **p=4.5e-7**）；OOD-severity 语义 0.917。
- 几何 image-only **学会弃答**（0 FPR，不从像素幻觉几何）；pairwise **v2** 修掉位置偏置后 G1 / S6 2-AFC 双双 **1.0**。
- **诚实负例**：① deck-scope 语义（S2/S5）pointwise 退化——SFT 缺 clean-deck 负样本导致恒报（已记 issue）；② 第三方 **SlideAudit**（2400 张真实标注 slide）image-only 迁移下，几何全模型 ≈0.5、合成强项不迁移 = **sim2real gap**，需 linter+结构。**ft 学到的是缺陷分布而非普适质量**，故域内强、OOD 弱。

### Part 3 — 下游效用 + 混合批评（[`reports/part3.md`](reports/part3.md) / [`reports/part3_hybrid.md`](reports/part3_hybrid.md)）→ **C3**

- **examiner 质量 → 下游增益**：self-refine 恢复**期望正向** corr **+0.659**，但幅度极小（gain 0.4–1.9%，强 generator 把任务地板抬高）；GEPA 效率 DV 给出 **+0.563** 反例（proxy 饱和 + running-best 伪迹）。**E6 把它收紧**：换**弱 generator（Qwen3-VL-4B）**让 first draft 不再 floored 后，效应不是变大而是**消失**（gain corr **−0.001**）——证明 headroom 是**覆盖度**（off the perception-critic axis），由 actionability A/B 坐实。
- **真实外部效度（Hermes 售前 PPT agent）**：真实 16 页 deck 上可验证缺陷 = 20 个未填模板占位符；**zs-30B 最强检测、微调 8B 在这个 OOD 缺陷上反而最弱** → 坐实"ft 学到缺陷分布而非普适质量"。examiner 批评驱动修订一轮后占位符 **20→0**。
- **符号–神经最小混合 critic**：**linter ⊕ 一个 C3 诱发的 VLM** 覆盖 **8/9 @ 0.896**，与预注册逐类路由 hybrid 持平（8/9 @ 0.885）≫ linter-only 5/9、VLM-C3 4/9、VLM-C0 2/9 → **关键是 linter⊕VLM-C3，不是繁复的逐类 prompt 调参**。
- **G7 渲染溢出新类**（本工作可证伪的扩展，且**在真实 deck 实测发生**）：bbox 合法但渲染溢出 ⇒ **几何 linter 结构上盲**。C3 把 G7 跨 6 模型/4 家族从 0.50 救到 0.93–1.0。**E5/R5 实测发生率**：一个"声明合法框 / 渲染像素溢出"检测器在**真实 agent 生成的 deck** 上抓到大量 G7——**Zenodo10K 切片 81/93 deck（857/3167 合法框，hard-G7 495 框）**、**AutoPresent 切片 8/14 deck（20/50 框）**，证明 G7 不是构造出来的玩具类。**多 RM 审计（5 个公开 reward + 1 闭源前沿 VLM judge，每类 ≥2）**：文档结构 reward（DocReward 0.48）与艺术美学头（0.57）盲，但**两个通用多模态 reward**（0.79 / 0.71，不同 backbone）+ 一个零样本感知质量探针（CLIP-IQA 0.83）+ VLM judge 能抓 → **G7 检出取决于"渲染质量读出"而非训练域标签**。另有 perturbation-fidelity 审计：**45% 注入几何缺陷根本没渲染出来**（任何用 IR 标签的 slide 数据集都会继承这个隐患）。
- **开放世界（E5）**：在无原生 IR 的真实 deck 上，用 PP-DocLayoutV2 从像素**recover 结构**再喂 linter——recovered 结构 ≠ native IR（只部分救回 G2、对细几何仍盲）→ critic 在开放世界**退化为 VLM-bound**（诚实边界，见 `slide_examiner/structure_recovery.py`）。

> **加固复审（todo_0623 E1–E8）一览。** E1 缺陷分解；E2/E3 顶会口径加固；**E4** 每类 ≥2 个 reward model 的多 RM G7 审计；**E5** 开放世界（像素→结构 recover）；**E6** unfloored 弱 generator 下游复核；E7 引用核验；**E8** G3/G5 重做 + S6 数据 bug 修复 + G6 整页位移 + reward 审计 + 真实 CC 版面复现。详见 [`specs/todo_0623.md`](specs/todo_0623.md) 与 `reports/_e1_*.md` / `reports/_e8_*.md`。

-----

## 安装

本项目用 conda 管理环境。在仓库根目录：

```bash
conda env create -f environment.yml   # 装可移植测试基线（-e .[dev]，纯 CPU、跨平台）
conda activate slide-examiner
pytest                                 # 应全绿（~221 passed, 2 skipped；GPU/网络无关）
```

环境以 `python=3.12` 为基底，依赖以 `pyproject.toml` 为单一来源、通过 pip 做可编辑安装，安装后提供命令行入口 `slide-examiner`。`slide_examiner/` 包在 import 时只依赖 `pydantic`，重依赖均在用到时**惰性导入**——故 `import slide_examiner` 与 CLI 永远可移植。

依赖分两层（详见 **[`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md)**）：

```bash
# —— 可移植层（跨平台 wheel、无 CUDA，任意机器可装）——
pip install -e ".[analysis]"  # numpy + scipy（诊断指标/统计）
pip install -e ".[render]"    # Playwright + python-pptx + pillow（栅格/PPTX）
pip install -e ".[data]"      # pyarrow（benchmark 适配）
pip install -e ".[api]"       # openai（在线模型适配器）
pip install -e ".[figures]"   # matplotlib（出图）
pip install -e ".[all]"       # 以上全部（CPU-only 全功能，不含 torch/vLLM）
playwright install chromium   # 渲染需一次性下载浏览器内核

# —— 机器相关 GPU 层（先按本机 CUDA 自装 torch，再装项目层）——
pip install torch --index-url https://download.pytorch.org/whl/cu124  # 示例：CUDA 12.4
pip install -e ".[vlm]"       # 本地 VLM 推理（transformers/accelerate/qwen-vl-utils/safetensors）
pip install -e ".[train]"     # QLoRA examiner 训练（peft/wandb；实训走 LLaMA-Factory）
```

> **可移植性要点**：`[all]` 故意**不含 `torch`/`vllm`**，所以在任何机器上都能装、装完即可跑 CLI 与全套测试（无需 GPU）。GPU 栈是独立一层，`torch`/`vllm` 的 wheel 必须匹配本机 CUDA（本机已验证组合：driver 570 / CUDA 12.4 / `torch 2.6.0+cu124` / RTX 3080 Ampere），vLLM serving 用独立 conda 环境承载。本地权重根目录由 `SLIDE_EXAMINER_MODELS_DIR` 覆盖、API 凭据走 `.env`（`OPENAI_*` / 按角色 `PART3_<ROLE>_*`），混合臂的 reward 审计需若干公开 reward model、开放世界的结构 recover 需 PP-DocLayoutV2。完整清单与 serving 踩坑见 **[`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md)**。

修改依赖后同步环境：

```bash
conda env update -f environment.yml --prune
```

-----

## 核心概念

- **中间表示（IR）**：`schemas.py` 定义 `BBox / Element / Slide / Deck / DefectLabel / ManifestSample`，所有注入与质检都作用在该结构化表示上，再渲染成图。
- **缺陷分类学**：`taxonomy.py` 定义两组共 12 类缺陷——
  - **G 组（几何/感知类）**：G1 文本溢出、G2 元素重叠、G3 对齐偏移、G4 字号不一致、G5 品牌色违规、G6 边距/整页位移，每类带严重度网格 θ。
  - **S 组（语义/推理类）**：S1 标题-正文不匹配、S2 叙事顺序破坏、S3 术语口径不一致、S4 密度违规、S5 逻辑缺段、S6 图文矛盾。
  - **G7 渲染容器溢出**（`defect_types.py` 中的扩展类，不改动冻结的 `taxonomy.py` enum）：声明 bbox 合法但渲染后内容溢出容器——**几何 linter 结构上盲，缺陷只在像素里可见**（可证伪的 linter-盲类）。
- **两种盲的拆分（论文中心，承 Part 1）**：诊断把 VLM 的"看不见"分成 **亚感知**（真·感知地板：亚阈值尾巴 + S3 + G6 整页位移）与 **格式压制**（看得见、但被 pointwise+rubric 埋掉，改诱发即复活）。**幅度**是连续变量：细几何在过了感知阈值后变成"格式压制可救回"，阈值以下才是真盲。
- **双 linter**：`geometry.py` 对 G1–G6 给符号化检测（G5 用 CIELAB ΔE 而非 RGB 距离）；`term_consistency.py` 对 S3 给确定性术语一致性检测（出现表 + 编辑距离聚类 ∪ text-LLM 漂移）。
- **架构正确的路由**（Part 1 实证结论 → Part 2/3 设计）：**声明几何归 linter**（有 IR 时更便宜、精确、近 0 FP）；可感知但被绝对打分压制的类（G1 溢出、S6、G7、超阈值 G3/G5）走 **pairwise / forced-choice / 换诱发的 VLM-C3**；语义类走 pointwise examiner；S3 走术语 linter。
- **归因协议**：在 模态 A（仅图）/ B（无损结构化 oracle）/ B′（VLM 看图 caption）/ C（图+oracle）× 任务 T1 检测 / T2 定位 / T3 修复 上跑同一组配对样本：
  - A 失败 ∧ B 成功 → **感知瓶颈**
  - A 失败 ∧ B 失败 → **推理瓶颈**
  - A 成功 ∧ T3 失败 → **执行瓶颈**

  做逐缺陷、逐模型的归因（`analysis.py`）。**关键方法学差异**：B 通道是**无损机器可读结构**，而非 model-written caption——后者会把要剔除的感知误差重新注入。
- **Oracle 去泄漏**：注入器会把 ground-truth 记号（`expected_bbox`、`narrative_order_broken` 等）写进 IR 元数据供 linter/repair 使用；构建模态 B/C 的 oracle 时由 `schemas.oracle_view()` 统一剥除这些键，避免把答案直接喂给模型而污染归因结论（`tests/test_oracle_leak.py` 回归保护）。
- **诱发协议（Part 3 混合臂）**：`elicit_*.py` 实现 C0 整张 taxonomy pointwise / C1 自由描述→分类 / C2 合成孪生 pairwise / C3 原子二分 + 强制证据，用来分离"格式压制 vs 能力缺失"；**C3-vs-C0 的对比正是"格式压制而非能力"的隔离器**。
- **结构 recover（开放世界）**：`structure_recovery.py` 用文档版面检测器（PP-DocLayoutV2）从像素恢复 IR 形状的元素框（类无关 NMS + 规范化坐标系），度量无原生 IR 时 linter 覆盖能救回多少。
- **多 RM 审计**：`reward_adapters.py` 对公开 reward model（pointwise / prompt-conditioned / pairwise 三种输入契约）做配对偏好审计，量化 G7 盲点是否跨 backbone/语料/契约存活。

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
- **Part 3（混合臂）** — `part3_build_g7.py`（G7 数据）→ `part3_p1_roster.py` / `part3_p1_sweep.sh`（诱发协议，6 模型/4 家族）→ `part3_p2_eval.py` / `part3_p2_summary.py`（混合 critic 覆盖）→ `part3_p3_reward_audit.py`（多 RM 审计）→ `part3_p2_figures.py`（图）。
- **Part 3（加固 E1–E8）** — `part3_e1_decomp.py`（E1 分解）；`part3_e5_recovered.py` / `part3_e5_figure.py`（E5 像素→结构 recover）；`part3_e6_parallel.py` / `part3_e6_actionability.py` / `part3_e6_unfloored_sweep.sh`（E6 unfloored）；`part3_regen_g3g5.py` / `part3_g3_relmisalign.py` / `part3_g5_internal.py` / `part3_e8_*.py`（E8 G3/G5 重做 + 饱和分层 + S6/G6 重测 + 真实 CC 复现 `part3_pc_real.py`）。
- **Part 3（R5 · G7 真实发生率）** — `part3_g7_gen_autopresent.py` / `part3_g7_gen_pptagent.py`（生成真实 agent deck）→ `part3_g7_prevalence.py`（"声明合法框 / 渲染像素溢出"检测器，量化 G7 在 Zenodo10K / AutoPresent 切片上的发生率）；`part3_real_inject.py`（真实版面 A/B/C 配对注入）。

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
  structure_recovery.py # 开放世界：像素 → IR 元素框 recover（PP-DocLayoutV2）
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
  downstream_regime.py                   # E6 floored-vs-unfloored 下游 regime 分析
  gepa_runner.py / gepa_eval.py          # GEPA 旁证（真实优化路径 + 混合反馈评估器）
  skillopt_adapter.py / part3_experiment.py  # SkillOpt（移出主线，留存）+ Part3 驱动
  part3_quality.py                       # model-free common-quality DV（gold）
  hybrid_critic.py                       # 符号–神经混合 critic（按缺陷路由）
  reward_adapters.py                     # 公开 reward model 多 RM 审计（pointwise/prompt/pairwise 契约）
  elicit_common.py / elicit_freeform.py / elicit_pairwise.py  # 诱发协议 C0–C3
  pptx_ingest.py                         # PPTX → Deck IR（Hermes case study）
  # —— 辅助 ——
  ingest.py / render.py / reports.py / distribution.py
  data_sources.py / data_prep.py / io.py / api_config.py / audit.py

paper/      # 技术报告 LaTeX 源码 + 图（main.tex / main.pdf 17pp / figs/fig1–fig11 / arxiv tarball）
scripts/    # 各 Part 的真实端到端实验驱动（part1_* / part2_* / part3_*（含 E1–E8）/ 渲染与拉取工具）
tests/      # 40 个测试文件：本地契约 + 冒烟管线 + oracle 去泄漏回归
specs/      # 研究 SPEC、novelty 分析、todo 执行清单（含 todo_0623 加固清单）
configs/    # Part 2 QLoRA / merge 配置
docs/       # 环境/可移植性（ENVIRONMENT.md）、实现状态、数据准备指南、Part 3 runbook、参考文献与图、spotcheck
data/  runs/  reports/   # 数据 / 渲染与 rollout 产物 / 分析报告（大产物 .gitignore）
```

-----

## 可复现性与边界

代码层面完整实现了 spec 的契约、linter、注入、训练与下游优化链路；Part 1/2/3 的真实实验**已在本机执行**并产出报告与论文。复现这些结论需要的外部资源：

- **GPU 与 serving**：4×RTX 3080 20GB（Ampere），vLLM 起 Qwen3-VL 4B/8B/30B 等本地服务（TP、AWQ/fp8 KV、`enable_thinking=false` 等配方见脚本与 `docs/`）。examiner 服务需 TP=2（单卡 KV OOM）。
- **模型权重**：Qwen3-VL 系列、2026 新 VLM（Gemma4 / InternVL3.5 / Ovis2.5 等，混合臂 6 模型/4 家族用）；多 RM 审计的**公开 reward model**（DocReward / Skywork-Reward / PickScore / LAION-aesthetic / CLIP-IQA）；开放世界结构 recover 的 **PP-DocLayoutV2**；微调产物 `runs/part2/examiner_lora_v2` / `examiner_merged_v2` 不入库（`scripts/push_adapter_hf.py` 可上传 HF）。
- **真实语料**：第三方 **SlideAudit**（真实迁移评估的可信信号，经镜像拉取）、Zenodo10K/PPTAgent、PPTBench、**AutoPresent**（slide-gen-with-feedback，R5 用于量化 G7 在真实生成 deck 的发生率）；**真实 CC 版面**（E8 用 41 篇真实 Zenodo deck 做诊断复现）；真实人工标注集**延后为非必要**（自标自评有公正性嫌疑，详见 `specs/todo.md §12`）。
- **生成器 / 优化器**：Part 3 generator+reflection 用在线 API 模型（强 generator 用 DashScope，E6 弱 generator 用本地 Qwen3-VL-4B）；GEPA 需 `pip install gepa`；SkillOpt 上游包缺资产已移出主线。

**Part 3 可复现 release bundle**（[`release/part3/`](release/part3/)）：随仓库提供**派生的配对图 manifest**（5 个：合成评测 / G7 渲染 / 真实版面 / G6 内部对比 / 覆盖度内部对比）与**逐项 rollout CSV**（Protocol-1 / McNemar 共 188 个 CSV / 28664 行 + 真实版面 A/B/C 4 个 CSV / 4008 行），每个产物附**重生成命令与 seed**（见 [`release/part3/index.md`](release/part3/index.md)）。权重、原始源语料等受 license 约束的上游件不入 bundle，仅释出派生产物。

测试套件验证的是**本地契约与冒烟管线**（含 oracle 去泄漏回归），**不是**经验性主张本身——经验结论以 `reports/` 下的报告与 `paper/main.pdf` 为准。实现状态对照见 [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)，执行清单见 [`specs/todo.md`](specs/todo.md)、[`specs/todo_0623.md`](specs/todo_0623.md) 与 [`specs/todo_0625.md`](specs/todo_0625.md)（AAAI-2027 重定位 backlog）。

**已知边界（如实记录）**：① 域内微调强项**不迁移 OOD**（SlideAudit / Hermes 占位符）；② deck-scope 语义（S2/S5）pointwise 退化；③ 合成饱和**不完全迁移**到真实杂乱版面（E8 真实 CC 上 G3 各通道近随机、specificity 崩）；④ 下游效用在强 generator 下 sub-1%、弱 generator 下消失（头条是覆盖度）；⑤ 45% 注入几何缺陷不渲染（IR 标签数据集通病）。

-----

## 报告索引

- **论文（canonical 综述）**：[`paper/main.pdf`](paper/main.pdf)（17pp）/ [`paper/main.tex`](paper/main.tex)，图见 `paper/figs/fig1–fig11`。
- **Part 1**：[`reports/slideprobe.md`](reports/slideprobe.md)（三轨汇总）；细分 `reports/part1_geometry_threshold.md` / `part1_encoder_geometry.md` / `part1_resolution_forcedchoice.md` / `part1_resolution_ablation.md` / `part1_sgroup_crosssize.md` / `part1_sgroup_30b.md` / `part1_s6_manifest.md` / `part1_term_consistency.md` / `part1_linter_track.md` / `part1_dataset_freeze.md`。
- **Part 2**：[`reports/part2.md`](reports/part2.md)（6 张表 + 真实迁移 + Wilson CI）。
- **Part 3（效用）**：[`reports/part3.md`](reports/part3.md)（含 E6 unfloored）+ `reports/part3_discussion.md` + `reports/part3_hacking.md` + `reports/part3_multiplicity.md`。
- **Part 3（混合臂）**：[`reports/part3_hybrid.md`](reports/part3_hybrid.md)（图见 `paper/figs/`）。
- **E8 修订（推翻早期 G3/G5、确立 G6 真盲 / S6 数据 bug）**：`reports/_e8_canonical_diagnosis.md`、`reports/_e8_corrected_summary.md`、`reports/_e8_g6_s6_results.md`、`reports/_e8_reward_g5.md`、`reports/_s1_atomic_specificity_tradeoff.md` 等 `reports/_e8_*.md`；E1 分解 `reports/_e1_decomp.md`；真实 CC `reports/_pc_real_tables.md`；R5 G7 真实发生率 `reports/part3/g7_autopresent_prevalence.jsonl` 等。
- **可复现 release bundle**：[`release/part3/index.md`](release/part3/index.md)（派生 manifest + 逐项 rollout CSV + 重生成命令/seed）。

-----

## 交付物

1. **学术侧**：技术报告《It's the Elicitation, Not the Eyes》——**首要贡献 C1 = 逐缺陷感知/推理归因协议**（无损结构 oracle，把"看不见"拆成亚感知 vs 格式压制）、C2 "格式压制而非能力"（改诱发即复活，4/6 模型/4 家族复现 + 迁移真实标注）、C3 由诊断推出的最小符号–神经混合 critic（2/9→8/9）+ 可证伪且**真实发生**的 G7 linter-盲类（Zenodo10K 81/93、AutoPresent 8/14）+ 多 RM 审计、C4 注入缺陷训练的专用 examiner + perturbation-fidelity 审计。
2. **工程侧**：缺陷注入器 + 无损 oracle 归因协议 + 诱发协议（C0–C3）+ 专用 examiner + 符号–神经混合质检 router + 像素→结构 recover + 多 RM 审计（可复用资产）。
3. **下游佐证**：examiner 质量→下游生成改进的外在效用度量（self-refine 主 + GEPA 旁 + E6 unfloored 复核），含 gold-vs-proxy 反作弊审计与真实 agent case-study。
</content>
</invoke>
