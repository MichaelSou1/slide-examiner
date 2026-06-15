# Novelty 分析(related work 调研截止 2026-06)

配套 SPEC_slide_examiner_attribution.md v0.2。目的:逐个定位最接近的竞品,明确”它做了什么 / 没做什么”,给出可直接写进 paper 的差异化措辞与防混淆切割。

-----

## 0. 结论先行:三层 novelty,稳健度排序

|#     |Novelty claim                                             |稳健度|最大威胁                                 |状态                                       |
|------|----------------------------------------------------------|---|-------------------------------------|-----------------------------------------|
|**N1**|**感知/推理归因从”理解型任务”迁移到”生成质检型任务”,且 oracle 用结构化几何表示(非自然语言描述)**|高  |2512.21329(ARC 同款方法)、69 号(chart 感知瓶颈)|方法论已被验证有效,但无人在”生成物质检”域做过 → 安全            |
|**N2**|**模板维度作为感知/推理 dissociation 的免费实验臂;残差缺陷谱向”纯感知+纯语义”两端坍缩**   |高  |无直接竞品                                |完全空白,这是本工作最独特的概念贡献                       |
|**N3**|**examiner 反馈信号质量 → GEPA 收敛效率的受控传导研究(VLM 视觉批评首次作 ASI)**   |中  |GEPA 应用清单(全文本域)、Decagon 配置消融         |feedback-source 作自变量无人做 → 安全;但需防”应用无新意”质疑|

辅助贡献(非主 claim,但增强完整性):程序化缺陷注入训练渲染文档域专用 examiner(N4);8B 专用 examiner 在几何检查上 > 大模型(N5)。

-----

## 1. 最危险的竞品:逐个切割

### 1.1 ⚠️ 头号近邻 — “Your Reasoning Benchmark May Not Test Reasoning”(arXiv 2512.21329, 2026.01)

**它做了什么**: 两阶段 pipeline 显式分离感知与推理——感知阶段把每张图独立转成自然语言描述,推理阶段用描述做规则归纳;在 Mini-ARC/ACRE/Bongard-LOGO 上证明约 80% 失败源于感知;含”四类错误归因”+ same-model/stronger-model perception 双设定。

**与你高度重合处**: 核心方法论(oracle 反事实分离感知/推理 + 错误归因)几乎同款;结论方向一致(感知是主瓶颈)。

**你的差异化(必须在 related work 显式写出)**:

1. **任务族不同**: 它在抽象视觉推理基准(ARC 系),你在**生成物质检**(slide deck QA)。前者是”理解输入图”,后者是”评判生成图是否有缺陷”——质检任务有缺陷类型分类学、有严重度连续轴、有可程序化注入的精确标签,ARC 没有。
1. **oracle 形态不同**: 它的 perception oracle 是**自然语言 caption**(有损、依赖描述者能力);你的 oracle 是**结构化几何表示**(元素 bbox + 文本 + 样式,无损、机器精确)。这让你的归因边界更干净——caption oracle 自身会引入感知误差,几何 oracle 不会。
1. **下游闭环**: 它止于诊断;你把归因结论接到 examiner 训练(N4)与生成系统优化(N3),证明诊断有外在效用。

> **写作模板**: “Concurrent to our work, [2512.21329] separates perception and reasoning in abstract reasoning benchmarks via natural-language perception oracles. We differ in three ways: (i) our domain is *quality inspection of generated artifacts* rather than input understanding, admitting a controllable defect taxonomy with exact injected labels; (ii) our perception oracle is a *lossless structured geometric representation* rather than a lossy caption, yielding a cleaner attribution boundary; (iii) we close the loop from diagnosis to examiner training and downstream generation optimization.”

### 1.2 ⚠️ 命名冲突 — “VLM Judges Can Rank but Cannot Score”(arXiv 2604.25235, 2026.04)

**它做了什么**: 用 conformal prediction 给 VLM judge 的分数配校准区间;发现 **ranking-scoring decoupling**(能排序、不能可靠打分),失败模式由任务结构与标注质量(非模型)主导;操作准则:窄区间→绝对打分,宽区间→相对排序/成对。

**威胁**: “decoupling” 命名 + “相对优于绝对”结论,会让审稿人把你的 perception/reasoning decoupling 与它混淆。

**切割**:

- 它 decouple 的是 **judge 的两种输出模式**(ranking vs scoring);你 decouple 的是**失败的两种归因来源**(perception vs reasoning)。正交概念。
- **反过来用它**: 它正好给你 §4.1 的 pairwise examiner 设计提供正式背书——“既然绝对分不可靠、相对排序可靠,examiner 与 GEPA 选择信号应优先用 pairwise”。把它从威胁转成 supporting citation。

> **写作模板**: “Note our ‘perception/reasoning decoupling’ is orthogonal to the ‘ranking-scoring decoupling’ of [2604.25235]: the latter concerns a judge’s *output modes*, ours concerns the *source of failure*. We adopt their finding (relative judgments are more reliable than absolute scores) to motivate our pairwise examiner head (§4.1).”

### 1.3 ⚠️ 同名任务、不同对象 — LED Benchmark(arXiv 2507.23295 / 2603.17265, 2026.03)

**它做了什么**: Layout Error Detection——**程序化注入 8 类结构错误**(Missing/Hallucination/Size/Split/Merge/Overlap/Duplicate/Misclassification),注入概率按真实 DLA 系统的错误分布建模;三任务(文档级检测/类型分类/元素级分类)。

**与你重合**: 程序化缺陷注入 + 按真实分布建模注入概率 + 缺陷分类学 + 多粒度任务——这是你 Part 1 数据构造的近亲,**必须引为方法论先例**(也佐证你”按真实分布注入”的设计不是空想)。

**你的差异化**:

1. **评估对象不同**: LED 评的是 **DLA 模型的解析预测**(把扫描文档切成区域,看切得对不对);你评的是**生成系统产出的 deck 内容质量**(看做出来的 PPT 好不好)。一个是 parsing 质检,一个是 generation 质检。
1. **关键反转**: LED 自承局限——“现有指标难以隔离错误来自识别还是推理失败 (hard to isolate whether errors stem from recognition or reasoning failures)”。**LED 把这当未解决的局限,而隔离感知 vs 推理正是你的核心方法。** 这是教科书级的 novelty 抓手:你解决了你最近邻明确承认没解决的问题。
1. LED 无生成、无 examiner 训练、无下游优化、无严重度连续轴、无模板维度。

> **写作模板**: “LED [2507.23295] pioneers distribution-grounded structural-error injection for *document layout analysis predictions*. We extend injection to *generated presentation content* and, crucially, address the limitation LED explicitly notes—that existing metrics cannot isolate whether failures stem from recognition or reasoning—by introducing a perception/reasoning attribution protocol.”

-----

## 2. 中等距离:范式相邻,需引用不需担心被抢

### 2.1 感知瓶颈系列(支撑 N1 的理论基础,全部应引)

- **On the Perception Bottleneck of VLMs for Chart Understanding**(arXiv 2503.18435): 把感知瓶颈分解为 vision-encoder bottleneck + extraction bottleneck。与你的”感知 vs 推理”二分**互补但不同层**——它在感知内部再分两层,你在感知 vs 推理之间画线。可引为”感知瓶颈可被进一步分解”的延伸方向。
- **Hidden in plain sight: VLMs overlook their visual representations**(arXiv 2506.08008): LLM 利用视觉表示的能力是瓶颈;视觉信息在表示里但没被用上。支撑你”模态 B oracle 成功 = 感知信息缺失”的反事实逻辑。
- **Caption This, Reason That**(arXiv 2505.21538): 主张瓶颈在**视觉特征到推理的整合**,既非纯感知也非纯推理。这是对你二分法的潜在反驳——审稿人可能问”会不会是整合瓶颈”。**预案**: 你的几何 oracle(模态 B)恰好旁路了整合问题(直接给结构化输入),若模态 B 成功率高 → 整合不是主瓶颈、感知才是;若模态 B 也失败 → 才轮到推理/整合。即你的协议本身能区分这两种假说,主动写进 discussion。
- **Ablate-to-Validate / TRT**(arXiv 2605.21642): 提供 clean counterfactual 谱(zero/random/distribution-matched/oracle)的方法学规范。直接引为你 oracle 反事实设计的方法论背书。
- **Seeing without Looking**(arXiv 2605.22903): 主张用视觉扰动敏感性替代 top-1 accuracy。同思想。

### 2.2 slide 生成与评估(N2/N3 的领域背景)

- **AeSlides**(arXiv 2604.22840): **最重要的领域级背书**。明说 agentic 迭代精修”对严重布局损坏有效,但受限于有限的视觉感知能力,常无法处理细粒度美学问题”;且记录 reward hacking(overflow:hidden、纹理背景);连 Claude-Sonnet-4.5/GPT-5.2 都频繁产出美学问题。→ 它**承认了感知瓶颈的存在**但当作既定事实绕过(转向规则化奖励),**没有归因、没有量化、没有 examiner 修复**。你填的正是这个空。
- **SlidesGen-Bench**(arXiv 2601.09487): 三维(Content/Aesthetics/Editability)计算式评估,visual-domain agnostic。可作为你 examiner 评估的对标 benchmark 之一;但它是 benchmark 不是归因研究。
- **EfficientPosterGen**(arXiv 2603.00155): 消融证明”去掉精确违规检测模块,布局分 3.71→2.91”,即 MLLM 布局验证不可靠、查不出溢出。→ 直接支撑你”linter(符号)优于 VLM(视觉)做几何检查”的混合架构。
- **DeepPresenter / Learning to Present / Talk-to-your-slides**: 系统侧 SOTA,其 reflector/critic 都是通用 VLM,即你 RQ1 要诊断的对象。

### 2.3 critic 训练(N4/N5 方法基础)

- **LLaVA-Critic / VL-RewardBench / LLaVA-Critic-R1**: critic training 范式成熟,但全在自然图像 VQA 域,无渲染文档域、无程序化注入 free-label。你的差异化已在 SPEC §2.4 写明。
- **VisRefiner**(arXiv 2602.05998): (clean, defective) 成对训练修复能力(前端域)。你借其成对格式,但训 examiner 检测而非 generator 修复 → 互补。

### 2.4 GEPA / feedback engineering(N3 基础)

- **GEPA**(ICLR 2026 Oral): ASI = 文本反馈作梯度类比;论文自列 feedback engineering 为 future work。Pareto 选择消融 +6.4~8.2%。
- **GEPA 应用清单**(github, 2026.04): 医疗 NER、临床 RoB、深度研究多智能体、医学影像 prompt triage、客服 supervisor——**全部文本/标量反馈,无一用 VLM 视觉批评作 ASI,无一以”反馈源质量”为自变量**。
- **Decagon 生产实践**(2026.03): 19+ GEPA 配置消融,但对象是文本监督模型,调的是超参不是反馈源。
- → **N3 的确切空白**: 把”examiner 内在质量(由 N1/N2 度量的感知/语义准确度梯度)“作为自变量、“GEPA 收敛效率与泛化”作为因变量的受控研究,在 GEPA 谱系中不存在。且”用 VLM 结构化视觉批评作 ASI”是 first。

-----

## 3. 给三层 novelty 的最终定位句(可直接进 abstract/intro)

**N1**: We present the first perception/reasoning attribution protocol for *quality inspection of generated documents*, using lossless structured-geometry oracles rather than lossy captions, and show the perception/reasoning boundary in rendered-document QA collapses differently than in input-understanding tasks.

**N2(最独特)**: We identify a *template-collapse* effect: under enterprise template constraints, the inspectable defect spectrum collapses toward two poles—pure-perception defects (overflow/overlap, uncontrollable by templates because text length is content-determined) and pure-semantic defects (content/narrative, unconstrained by templates)—while the regime of “scale-solvable layout reasoning” is absorbed by the template. We use the template switch as a free experimental arm to causally re-validate the perception/reasoning dissociation.

**N3**: We provide the first controlled study of *feedback-source quality* in reflective prompt evolution (GEPA), instantiating VLM structured visual critique as actionable side information, and demonstrate that examiner perceptual quality (measured intrinsically in N1/N2) transfers monotonically to downstream generation-optimization efficiency.

-----

## 4. 风险:可能被”抢发”的窗口与应对

|风险                                           |评估                    |应对                                                |
|---------------------------------------------|----------------------|--------------------------------------------------|
|2512.21329 的团队把同款方法推广到 document/slide 域      |中(他们在 ARC,转域需重建数据,非平凡)|抢时间窗;且你的模板维度(N2)他们无法平移过来,作为护城河                    |
|有人把 LED 式注入 + 感知归因合并                         |中低                    |N2 模板坍缩是你独有概念;尽快把 N2 做成可展示结果                      |
|GEPA 团队官方出 VLM-feedback 版本                   |低中                    |N3 单独不强,务必绑定 N1/N2 作为 examiner 质量梯度的来源——别让 N3 独立成篇|
|“perception/reasoning decoupling” 在视频域(你主线)被抢|见主线 spec              |本项目与主线共享方法论,互为时间对冲                                |

**核心建议**: 把资源优先压在 **N2(模板坍缩)** 上——它是唯一无直接竞品、且竞品难平移的概念贡献。N1 方法论虽稳但已被邻域验证(意味着既安全也拥挤),N3 必须依附 N1/N2。最强的单篇故事 = N2 为概念核心 + N1 为方法工具 + N3 为外在效用证明。