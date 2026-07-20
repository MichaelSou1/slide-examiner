# SPEC: Slide-Examiner — VLM 幻灯片质检的感知/推理归因、专用小模型修复与下游优化效用验证

**版本**: v0.3 (pre-registration draft)
**日期**: 2026-06-15
**状态**: 待评审 → 冻结后开始实验
**配套文档**: NOVELTY_analysis_2026-06.md(逐竞品切割,related work 截止 2026-06)
**硬件约束**: 4×RTX 3080 20GB (Ampere, PCIe, no NVLink) + 服务器推理 (Qwen3-VL 4B/8B/32B-dense/30B-A3B)
**方法论血缘**: VideoQA_PR_Decoupling_Plan.md(可控扰动 2×2 归因)、SUPPLEMENTARY_EXPERIMENT_SPEC.md(variance gating / power analysis)、orchestrator distillation(单卡 QLoRA 流程)

-----

## 0. 一句话定位

> VLM 做渲染文档(幻灯片)质检时,失败主要来自**感知保真度**而非**推理能力**;用**程序化缺陷注入**(零标注成本、精确标签)训练的小型专用 examiner 能在几何类检查上超过大型通用模型;且 examiner 质量可以转化为下游**技能空间优化**(SkillOpt 主 / GEPA 次)的效率——以**可验证 linter 选择 + 学习型 examiner 反思**的解耦反馈架构实现。

论文结构为三段式,共享一个 claim:**“质检信号的质量瓶颈在感知,而感知瓶颈可以被廉价地专门化修复,并且修复的价值可以在下游被外在地度量。”**

**模板坍缩洞察(本版核心增量)**: 工业幻灯片生成几乎总在企业模板(.potx 母版/版式/占位符)约束下进行。模板提供**结构参考但不提供内容参考**——它钉死排版骨架(对齐/字号继承/品牌色/边距),却完全不约束槽位内容是否准确、是否溢出、叙事是否连贯。因此引入模板后,可质检缺陷谱**向两端坍缩**:一端是模板兜不住的**纯感知缺陷**(溢出/重叠,因为文字长度由内容决定),另一端是模板管不着的**纯语义缺陷**(内容正确性/叙事),而中间”规模可解的版面推理”被模板吃掉。这一坍缩既是工程简化的依据(质检器只需实现两端),也让感知/语义二分在工业条件下更尖锐——模板成了归因协议的一个免费实验臂。

-----

## 0.5 Novelty 声明(三层,稳健度排序;详见 NOVELTY_analysis_2026-06.md)

|#     |Novelty                                                                    |稳健度               |最近邻竞品                                                               |切割要点                                          |
|------|---------------------------------------------------------------------------|------------------|--------------------------------------------------------------------|----------------------------------------------|
|**N1**|感知/推理归因首次用于**生成物质检**(而非输入理解),且 oracle 用**无损结构化几何表示**(而非有损 caption)         |高(方法已被邻域验证,但本域无人做)|“Your Reasoning Benchmark May Not Test Reasoning”(2512.21329, ARC 域)|任务族(质检 vs 理解)、oracle 形态(几何 vs caption)、是否闭环到下游|
|**N2**|**模板坍缩**:模板把可质检缺陷谱挤向”纯感知 + 纯语义”两端,中间版面推理被吸收;模板开关作为感知/推理 dissociation 的免费实验臂|高(**无直接竞品,竞品难平移**)|无                                                                   |唯一原创概念贡献,本工作护城河                               |
|**N3(已降级 2026-06-19;仅下游效用佐证,非重心)**|examiner 内在质量(Part1/2 度量)→ **下游 slide 生成改进**的效用佐证(**轻量**):self-refine(examiner 作 agent 反思信号)为主佐证 + GEPA skill-space 优化为**旁证**;解耦"可验证 linter 选择门 + 学习型 examiner 反思" + gold-vs-proxy 反作弊审计。**SkillOpt 第二载体移出主线**(上游 PyPI 包缺 prompt 资产/analyst 不调 optimizer、GitHub 不可达 → deferred,代码留 `skillopt_adapter.py`)|低-中(**依附 N1/N2,不独立成篇**)|Gao 2210.10760 / PRIME 2602.11570(verifier-质量→效率 已证);EvoPresent(self-refine 已占→仅 baseline);GEPA/SkillOpt(反馈固定)|贡献**既非"发现反馈质量重要"亦非"skill 优化论文"**;**论文重心是 N1/N2 的 VLM 诊断+专用 examiner**;slide 生成/下游优化均为测试床|

**最强单篇结构**: **这是一篇 VLM 论文** —— N2 概念核心 + N1 方法工具(感知/推理归因诊断 + 注入缺陷训练的专用 VLM examiner)为**重心**;N3 仅作外在效用的轻量佐证。资源优先级 **N2 > N1 ≫ N3**。

**三处必须主动防混淆的命名/任务撞车**(写作时在 related work 显式切割,见 §2.8):

- 2512.21329 同款 perception/reasoning 分离方法 → 切割任务族与 oracle 形态
- “VLM Judges Can Rank but Cannot Score”(2604.25235)的 **ranking-scoring decoupling** → 与本工作 perception/reasoning decoupling 正交,反过来引为 pairwise 设计背书
- **LED Benchmark**(2507.23295)的结构错误注入 → 引为方法先例,但强调 LED 自承”无法隔离识别 vs 推理失败”正是本工作所解决的

-----

## 1. 研究问题(预注册)

- **RQ1(诊断)**: VLM 在幻灯片缺陷检测上的失败,在多大程度上可归因于感知(看不见/看不准)vs 推理(看见了但判断不了)?该归因是否随缺陷类型(几何 vs 语义)、模型规模、输入分辨率系统性变化?
- **RQ2(修复)**: 在程序化注入的合成缺陷上 LoRA 微调的小型 VLM examiner(8B),能否在几何类检查上超过 zero-shot 的更大模型(27B/API 级),并泛化到真实人工制作的 deck 与公开 benchmark?
- **RQ3(下游,轻量佐证;非论文重心)**: examiner 质量(由 RQ1/RQ2 的内在指标度量)是否转化为**下游 slide 生成改进**的效率与最终质量?以**两条轻量载体**佐证(非"双优化器主张"):① **self-refine(主佐证)**——examiner 作 agent 的反思信号,generate→critique→revise;② **GEPA skill-space 优化(旁证)**。"选择信号(可验证 linter)+ 反思信号(VLM 批评)分离"是否优于任一单源?(注:verifier-质量→效率 在 RL/verifier 域已证[Gao 2210.10760、PRIME 2602.11570];本问只在 **design 域**做下游效用佐证,既不重新发现反馈质量、也**不是 skill 优化论文**。**SkillOpt 第二载体因上游包缺资产移出主线、deferred,见 §5。**)

-----

## 2. Related Work 地图与 Gap Statement

### 2.1 幻灯片/文档生成系统

|工作                                             |范式                                              |与本工作关系                                                                                          |
|-----------------------------------------------|------------------------------------------------|------------------------------------------------------------------------------------------------|
|PPTAgent (EMNLP 2025, arXiv 2501.03936)        |参考页编辑式生成 + PPTEval 三维评估                         |提供 Zenodo10K 数据集(真实 deck 素材源);其参数编辑不敏感问题是本工作的动机之一                                               |
|DeepPresenter (arXiv 2602.22839)               |环境接地反思,沙箱 + 20+ 工具                              |render-reflect loop 的 SOTA 系统;但其 reflector 是通用 VLM,正是 RQ1 要诊断的对象                                |
|AutoPresent + SlidesLib/SlidesBench (CVPR 2025)|NL→Python 程序→PPTX;高层函数库                         |提供 slide 级生成任务库与 reference-based 指标;证明 DSL 让小模型逼近大模型                                            |
|PreGenie (arXiv 2505.21660)                    |Slidev Markdown 中间表示                            |中间表示选型参考                                                                                        |
|Talk-to-your-slides + TSBench/TSBench-Hard     |结构化 JSON 操作 + 分层 planner/executor               |明确提出混合架构(结构操作为主、VLM 选择性验证),但未量化分工边界——本工作补这一刀                                                    |
|Learning to Present (arXiv 2603.16839)         |OpenEnv RL 环境,14 工具,inverse-specification reward|inverse-spec 思想纳入本工作的 examiner 信号消融之一                                                           |
|AeSlides (arXiv 2604.22840)                    |可验证美学奖励 RL                                      |关键先例:元评估证明 VLM 打分不可靠(GPT-5.2 过宽),并记录 reward hacking(overflow:hidden、纹理背景);本工作的”选择/反思信号分离”直接回应其发现|

### 2.2 幻灯片理解与评估 benchmark

- **VLM-SlideEval (arXiv 2510.22045)**: VLM 在像素级精确任务(bbox、字体属性、对齐)上弱、在语义角色/层级/叙事上强——本工作 RQ1 的假设来源,但其为观察性结论,未做因果归因。
- **PPTBench (arXiv 2512.02624)**: 检测/理解/修改/生成四任务;失败案例显示空间推理缺陷(表格移错方向、图压住文字)。用作 RQ2 的迁移评估集。
- **SlidesGen-Bench (arXiv 2601.09487)**: 计算美学 + V-E matrix。可选对标。

### 2.3 VLM 细粒度感知缺陷 + 感知/推理归因(诊断的理论基础)

**感知缺陷既存证据**:

- “VLMs are blind” / BlindTest (Rahmanzadehgervi et al., 2024):低层视觉系统性失败。
- MeasureBench (arXiv 2510.26865):**可控合成管线 + 精确标签 + 失败模式分析**的方法论先例;一致性失败模式为”指针定位”——能读文字但定不准位置,与幻灯片溢出检测失败同构。
- VLM-FO1 (arXiv 2509.25916):归因到架构——语言中心架构生成精确坐标是根本错配。
- On the Perception Bottleneck of VLMs for Chart Understanding (arXiv 2503.18435):把感知瓶颈再分解为 vision-encoder bottleneck + extraction bottleneck。与本工作”感知 vs 推理”二分**互补但在不同层**(它在感知内部细分);可作延伸方向。
- Hidden in plain sight (arXiv 2506.08008):LLM 利用视觉表示的能力是瓶颈——支撑”模态 B oracle 成功 ⇒ 感知信息在输入端缺失”的反事实逻辑。

**感知/推理归因方法论(N1 的直接邻居,须切割)**:

- **“Your Reasoning Benchmark May Not Test Reasoning”** (arXiv 2512.21329, 2026.01):两阶段显式分离感知/推理 + 四类错误归因 + same/stronger-model perception 双设定,在 ARC 系证明约 80% 失败源于感知。**与本工作 Part 1 方法论几乎同款**——既证明方法有效、降低发表风险,也意味着”通用视觉推理的感知归因”已被占。切割见 §2.8。
- Seeing without Looking (arXiv 2605.22903):用视觉扰动敏感性替代 top-1 accuracy。同思想,支撑分辨率消融。
- Ablate-to-Validate / TRT (arXiv 2605.21642):规范化 clean counterfactual 谱(zero/random/distribution-matched/oracle)——直接引为 oracle 反事实设计的方法学背书。

**潜在反驳预案 — “整合瓶颈”假说**: Caption This, Reason That (arXiv 2505.21538) 主张瓶颈既非纯感知也非纯推理,而在**视觉特征到推理的整合**。审稿人可能据此质疑本工作的二分法。**协议自带区分能力**:模态 B(结构化几何 oracle)旁路了整合通道——若模态 B 成功率高 ⇒ 整合非主瓶颈、感知才是;若模态 B 也失败 ⇒ 才轮到推理/整合。即本归因协议本身可证伪整合瓶颈假说,主动写进 discussion。

### 2.4 VLM critic/examiner 训练 + 缺陷注入 + judge 可靠性(修复的方法基础)

**critic 训练范式**:

- LLaVA-Critic (CVPR 2025):113k critic 指令数据训练开源多模态评估器,通用 VQA 域。
- VL-RewardBench (arXiv 2411.17451):critic training 使 pointwise 判断 +14.7%。
- LLaVA-Critic-R1 (arXiv 2509.00676):RL on critic data。
- **Gap**: 全部在自然图像 VQA 域;无渲染文档域专用 critic;无程序化缺陷注入(free exact label)训练范式。

**缺陷注入先例(N4 方法基础,须引)**:

- **LED Benchmark** (arXiv 2507.23295 / 2603.17265, 2026.03):**程序化注入 8 类结构错误,注入概率按真实 DLA 系统错误分布建模**;三粒度任务。本工作”按真实分布注入”设计的直接先例。**但**:LED 评的是 DLA 解析预测(parsing 质检),本工作评生成内容(generation 质检);且 LED 自承”现有指标难以隔离错误来自识别还是推理”——切割见 §2.8。
- (工业域)合成缺陷注入训练视觉检测器为成熟范式(ISP-AD 等):纯合成可达高性能、混入少量真实缺陷进一步提升——支撑本工作 sim2real 策略。

**VLM judge 可靠性元评估(支撑混合架构与 pairwise 设计)**:

- **“VLM Judges Can Rank but Cannot Score”** (arXiv 2604.25235, 2026.04):形式化 **ranking-scoring decoupling**——judge 能排序、不能可靠打分(MLLM-as-Judge 上仅 32–34% 与人类精确一致);操作准则:窄 conformal 区间→绝对分,宽区间→相对排序。**正式背书本工作 pairwise examiner 设计**;命名切割见 §2.8。
- 通用结论(Liu et al. 2025 等):VLM judge 普遍过度乐观、评分方差小;朴素集成可能劣于最强单 judge(不可靠 judge 注入噪声)——支撑本工作不做朴素集成、而做 linter+VLM 异质分工。
- EfficientPosterGen (arXiv 2603.00155):消融证明去掉精确违规检测模块布局分 3.71→2.91,即 MLLM 布局验证查不出溢出——直接支撑”几何检查交给 linter、语义交给 VLM”。

### 2.5 Prompt/技能进化与反馈工程(N3 基础)

- **SkillOpt(arXiv 2605.23904, Microsoft, 2026-05;本工作下游主载体)**:把技能优化重述为**可控 text-space 优化器**——独立 optimizer-model 反思 + held-out validation gate 选择 + bounded edit + rejected-edit buffer + slow/meta update;52/52 cell best-or-tied,**超过 GEPA/TextGrad/Trace2Skill/EvoSkill**。**关键**:它把反馈固定为 benchmark hard-score,且**结构上已把反思源(optimizer-model)与选择门(validation gate)解耦**——正是本工作解耦反馈架构的现成框架;但它**不把反馈源质量当自变量**。
- GEPA (ICLR 2026 Oral, arXiv 2507.19457;次载体):反思式 prompt 进化,文本反馈(ASI)为核心;Pareto 选择消融 +6.4~8.2%。**已核 PDF**:其 metric μ 与 feedback function μ_f 为**固定输入**(Alg.1 Require 项),从不把反馈源质量当实验变量——"反馈源质量未被检视"是**本工作的推断,非 GEPA 自述的 open problem**(全文无 "feedback engineering" 一词;原 spec 该归因有误,已更正)。两载体并用 → 结论 optimizer-agnostic,并消除"应用 GEPA 无新意"风险。
- **必须正面切割的已有原理(联网核查 + PDF 核验 2026-06-18)**: "评估器/奖励质量→优化效率/质量"在 **RL/verifier 域已被建立**——基础 = **RM-overoptimization gold-vs-proxy scaling law**([Gao 2210.10760];拟合函数式,非相关系数);verifier 准确率→RLVR policy 质量的强线性 = **PRIME [2602.11570] R²=0.937/0.920(Qwen3-8B/14B,数学/工程域,§5.3)**;**强度视用途而定**——BoN 强(RewardBench2 [2506.01937] r≈0.87)、RLHF/PPO 弱([2410.05584]:等准确率 RM 给出迥异 policy)。**故本工作不得宣称"发现反馈质量重要"**。N3 的确切空白 = 该原理尚未进入的**两个格的交集**:① text-space **skill/prompt 优化器**(GEPA μ/μ_f 固定、SkillOpt 反馈固定为 benchmark hard-score,**均不把反馈源质量当自变量**——已核 PDF;Decagon 2026.03 的 19+ GEPA 消融调超参非反馈源);② **design/multimodal 域**(无 scaling-law 类比)。本工作 = examiner 内在质量(Part 1/2 度量)→ 技能空间优化效率,在 design 域、以解耦可验证/学习反馈实现的受控传导 + **gold-vs-proxy 反作弊审计**(移植 Gao 协议;此处 gold=确定性可验证 linter,比 Gao 的 trained-gold-RM 更接近真值,是更紧的 Goodhart 实例)。

### 2.6 UI-to-code 与视觉精修(相邻领域:更成熟的同范式兄弟)

“代码→渲染→视觉反思”范式在前端域比幻灯片域早成熟约一年,演化三阶段值得参照:

- **Design2Code (NAACL 2025)**: 视觉自修订 prompting——参考图截图 + 自身渲染截图一并喂入,让模型修订实现以贴近目标。最朴素 render-reflect。
- **ReLook (2025)**: agentic 视觉接地 RL,多模态 LLM 当 critic 从渲染网页提供视觉反馈引导策略学习。
- **UI2Code^N (ICML 2026, arXiv 2511.08195)**: 将 UI-to-code 形式化为”交互式视觉优化”闭环(执行—视觉检查—迭代精修);提出 RVPO——因绝对视觉评估器有噪声,改为优化渲染候选间的**相对视觉排名**。
- **VisRefiner (arXiv 2602.05998)**: 差异对齐数据集,(目标图,当前渲染,差异)三元组训练修复;约 20K 实例。
- **METAL**: 图表复现中发现**批评时分离模态**带来强自我纠正与 test-time scaling 收益。

三处与本工作独立收敛的证据(抬高 spec 内设计决策的可信度):

1. **绝对打分不可靠、相对排序可靠**——UI2Code^N(RVPO)、Paper2Video(幻灯片)、AeSlides(美学)三域独立收敛 → 本工作 examiner 输出增设 pairwise 变体(见 §4.1)。
1. **批评时分离模态**(METAL)→ 呼应本工作 linter(符号通道)与 VLM(视觉通道)分离。
1. **现有视觉评估器对细粒度结构失明**——UI2Code^N 实测 CLIP 对 block/position 级布局差异不敏感(block/position 指标提升时 CLIP 不动),与 §2.3 的 VLM 细粒度感知缺陷同源。

**划界(本工作不可替代性的真正来源)**: 前端域是 **image-to-code 重建**——有参考截图,参考图同时钉死像素与内容,故 diff 本身即完备信号,无需独立 examiner。幻灯片域是 **spec-to-artifact**;即便有模板,模板只提供**结构参考、不提供内容参考**。因此 diff-based 信号(前端范式)在幻灯片域只能覆盖排版骨架,**内容保真度(溢出/语义)仍需独立 examiner**——这道”结构有参考、内容无参考”的缝隙是前端域不存在的,正是 examiner 不可替代的根因。(注:此处修正 v0.1 中”幻灯片无参考图”的过强表述——幻灯片有结构参考,但无内容参考。)

### 2.7 Gap Statement(三句话)

1. 没有工作对 VLM-as-document-checker 做过**感知/推理因果归因**——已有观察(VLM-SlideEval)与邻域方法(2512.21329 在 ARC),但无人在生成物质检域用无损几何 oracle 做归因。
1. 没有工作用**程序化缺陷注入**训练渲染文档域专用 examiner——LED 注入用于评 DLA 解析、critic training 全部依赖偏好标注或强模型蒸馏。
1. "评估器质量 → 优化效率"在 RL/verifier 域已有 scaling law,但**无人把它迁到 text-space skill/prompt 优化器(SkillOpt/GEPA 反馈固定)× design 域**,也无人用 VLM 视觉批评作其反思 ASI、以可验证 linter 作其选择门——这道 skill-space × design 的交集是本工作 N3 的空白。
1. (概念层,无任何竞品)没有工作刻画**模板对缺陷谱的坍缩效应**及其作为感知/推理 dissociation 实验杠杆的作用。

### 2.8 竞品切割(写作时直接植入 related work,防混淆)

本节针对三个最易被审稿人混淆的近邻给出正式切割。英文模板可直接用于 paper。

**(a) vs 2512.21329（同款 perception/reasoning 分离方法,ARC 域）**
三点差异:(i) 任务族——它做输入图理解,本工作做**生成物质检**(有缺陷分类学、严重度连续轴、可注入精确标签);(ii) oracle 形态——它用**有损自然语言 caption**,本工作用**无损结构化几何表示**,归因边界更干净(caption oracle 自身引入感知误差);(iii) 本工作闭环到 examiner 训练与生成优化,它止于诊断。

> *“Concurrent to our work, [2512.21329] separates perception and reasoning in abstract reasoning benchmarks via natural-language perception oracles. We differ in three ways: (i) our domain is quality inspection of generated artifacts rather than input understanding, admitting a controllable defect taxonomy with exact injected labels; (ii) our perception oracle is a lossless structured geometric representation rather than a lossy caption, yielding a cleaner attribution boundary; (iii) we close the loop from diagnosis to examiner training and downstream generation optimization.”*

**(b) vs 2604.25235（ranking-scoring decoupling 命名冲突）**
本工作的 perception/reasoning decoupling 与其 ranking-scoring decoupling **正交**:后者关乎 judge 的输出模式(排序 vs 打分),前者关乎失败的来源(感知 vs 推理)。并**反向利用**其结论为本工作 pairwise examiner 设计背书。

> *“Our ‘perception/reasoning decoupling’ is orthogonal to the ‘ranking-scoring decoupling’ of [2604.25235]: the latter concerns a judge’s output modes, ours the source of failure. We adopt their finding—relative judgments are more reliable than absolute scores—to motivate our pairwise examiner head (§4.1).”*

**(c) vs LED Benchmark 2507.23295（结构错误注入同范式）**
引为方法先例,但抓住其自承局限作为本工作 novelty 锚点:LED 评 DLA **解析预测**,本工作评**生成内容**;且 LED 明言现有指标无法隔离错误源于识别还是推理——而隔离二者正是本工作核心。

> *“LED [2507.23295] pioneers distribution-grounded structural-error injection for document layout analysis predictions. We extend injection to generated presentation content and, crucially, address the limitation LED explicitly notes—that existing metrics cannot isolate whether failures stem from recognition or reasoning—via a perception/reasoning attribution protocol.”*

-----

## 3. Part 1 — 诊断:SlideProbe 归因协议

### 3.0 协议修订(2026-06 pilot 实证;**优先于本节后文的预注册设计**,冲突处以本节为准)

下面 §3.1–§3.4 的预注册设计已用真实 VLM 在合成数据上实测:Qwen3-VL 4B/8B/30B-A3B,外加 Penguin-VL-8B / InternVL3.5-8B / Ovis2.5-9B / Kimi-VL-A3B 的**视觉编码器家族对照**。证据见 `reports/pilot_slideprobe.md`、`reports/part1_geometry_threshold.md`、`reports/part1_sgroup_30b.md`、`reports/part1_s6_manifest.md`、`reports/part1_encoder_geometry.md`、`reports/part1_resolution_forcedchoice.md`。

**(1) 三轨计分(按缺陷×方法分流,放弃"所有缺陷 × 所有模态 pointwise 铺满"的原矩阵)**
- **轨 L — linter**:G 组细几何(G2–G6:重叠/对齐/字号/色差/边距)由**符号 linter 主检测**,作 ground truth 与上界;VLM 对这些只作参照,不作主检测。
- **轨 E — examiner-pointwise**:S 组语义 **S1/S4/S5** 走 pointwise A/B/B′/C 归因——examiner 主场,也是感知/推理 decoupling 的真实信号。
- **轨 P — pairwise / forced-choice**:**G1 文字溢出、S6 图文矛盾、S3 术语不一致** 走 pairwise/2-AFC(`PairwiseResult`)+ 配对 clean。这些缺陷"能看见但不会绝对判断",pointwise 随机、forced-choice 满分。

**(2) 主指标:balanced accuracy + 配对 clean 控制;严禁只看 recall**
- 每个正样本必须有**同底图、仅缺陷不同**的配对 clean 负样本。pointwise 报 balanced accuracy / precision / recall;pairwise 报 2-AFC accuracy(双向序消位置偏置)。
- **pointwise VLM 几何检测不计入主结果**(实测全员在随机线:要么弃答、要么过报;只看 recall 会得出"假高检出")。

**(3) G 组结论(实测,替代"感知瓶颈主导"的原假设)**
- G1–G6 pointwise 在 4B/8B/30B 与 **5 个编码器家族**(SigLIP2 / LLM-based / InternViT / NaViT / MoonViT)上 balanced accuracy **全在 ~0.50**。
- 几何盲是**两种机制**:① **校准失败**(G1 溢出:能看见,forced-choice 8B 即 100%);② **感知阈值**(G3 对齐 + G4/G5/G6 细端:2–32px 级,forced-choice / 分辨率 / 规模都救不了)。
- 杠杆是**尺寸 / LLM 推理**(只有 30B-A3B 真破 G1 pointwise,bal-acc ~0.75),**不是视觉编码器、也不是分辨率** → 不要把预算花在换编码器/堆分辨率上。

**(4) B′ caption oracle = VLM 看图生成的自然语言描述**(不是扁平坐标 dump;`scripts/caption_images.py`)。几何上 B′ 是死通道;**deck 级语义上 B′ 反而最强**(S2 乱序 8/8)。

**(5) deck 模态**:多图已接通(`build_deck_messages` 全页),但 **C(图+结构,多图)对 deck 语义反而最差**,B/B′ 承载跨页推理。按"缺陷 × 通道"画像报告,不要默认 C 最好。

**(6) 模型矩阵**:保留**跨尺寸扫**(4B/8B/30B,用于定几何阈值);**编码器家族扫已完成且为负结果,不再进主矩阵预算**;30B-A3B 作几何上界参照。

**(7) 分辨率消融**:**收窄**。1536 vs 2048 对几何零差别 → 不再 768/1024/1536/2048 × 全缺陷铺满,只在非地板 cell(G1-overflow 的 pairwise、S1)上抽测。

**(8) H1-tpl 模板坍缩:解耦为两件事** — (a) 模板是否**吸收**几何缺陷,由 **linter 度量**(snap-to-master 已实现 `slide_examiner/template.py`,与模型无关);(b) VLM 检出是否下降,只在"能检出 freeform 几何"的 cell 才有意义(实测 4B/8B 几何本就 0,无从测量)。

**(9) 数据集冻结要求**:每正样本配对 clean、**带图 deck**(S6 可测)、**glossary 术语**(S3 可测)、held-out severity/defect;`template` 须**真实操纵**(snap-to-master),非元数据标签。

### 3.1 缺陷分类学(Defect Taxonomy)

每类缺陷由(类型, 严重度参数 θ, 精确标签)三元组定义,全部程序化注入,注入器作用于结构化 slide 表示(python-pptx / HTML DOM),再渲染成图。

**G 组 — 几何/感知类**(假设:感知瓶颈主导)
“模板覆盖”= 在企业模板(母版继承 + 占位符约束)下该缺陷是否被结构性消除:✅ 基本消除 / ⚠️ 部分残留 / ❌ 模板无能为力。

|ID|缺陷   |严重度参数 θ                      |注入方式     |模板覆盖              |
|--|-----|-----------------------------|---------|------------------|
|G1|文本溢出 |溢出像素 Δpx ∈ {4, 8, 16, 32, 64}|增字数或缩容器  |❌(文字长度由内容决定,模板兜不住)|
|G2|元素重叠 |IoU ∈ {0.05, 0.1, 0.2, 0.4}  |平移元素     |⚠️(静态布局✅,动态内容撑开仍会撞)|
|G3|对齐偏移 |偏移 Δpx ∈ {2, 4, 8, 16, 32}   |单元素偏移破坏栅格|✅(占位符锚定)          |
|G4|字号不一致|同级字号差 Δpt ∈ {1, 2, 4, 8}     |改单个同级元素字号|✅(母版字号继承)         |
|G5|品牌色违规|色差 ΔE ∈ {3, 6, 12, 24}       |替换主题色    |✅(主题色板)           |
|G6|边距违规 |出血 Δpx ∈ {4, 8, 16, 32}      |元素贴边/出界  |✅(版式边界)           |


> **坍缩预测**: 有模板时 G3–G6 缺陷率大幅下降并退出主要矛盾,残留几何难点坍缩到 G1/G2——而 G1/G2 恰是前述证据指认的纯感知瓶颈、规模不可解类。

**S 组 — 语义/推理类**(假设:推理瓶颈或两者均不构成瓶颈)

|ID|缺陷      |注入方式                 |模板覆盖|
|--|--------|---------------------|----|
|S1|标题-正文不匹配|跨页交换正文               |❌   |
|S2|叙事顺序破坏  |打乱页序(背景→痛点→方案链断裂)    |❌   |
|S3|术语口径不一致 |实体名跨页随机替换变体          |❌   |
|S4|密度违规    |字数超出场景规则(发布会页 >60 字等)|❌   |
|S5|逻辑缺段    |删除必要章节(如完整方案缺验收页)    |❌   |
|S6|图文矛盾    |架构图层级与正文描述不一致        |❌   |


> S 组**全部** ❌:模板对内容正确性零约束。这是”模板提供结构参考、不提供内容参考”的直接体现,也是 examiner 在工业条件下仍不可替代的根因。

素材源:Zenodo10K(PPTAgent 数据集)抽取干净 deck + 实习项目脱敏 deck;每缺陷 × 每严重度 ≥ 50 实例,留 20% held-out 缺陷参数(及 1–2 个完整 held-out 缺陷类型)做 OOD。

### 3.2 归因协议(模态 × 任务 × 模板,沿用 PR-Decoupling 设计)

**输入模态** × **任务**:

- 模态 A — 仅渲染图(标准 VLM 质检条件)
- 模态 B — 仅 oracle 结构化表示(元素列表 + 精确 bbox + 文本 + 样式;即”完美感知”反事实)
- 模态 C — 图 + oracle 表示(上界)
- 任务 T1 — 检测(该页是否存在缺陷 X,yes/no)
- 任务 T2 — 定位(指出缺陷元素)
- 任务 T3 — 修复建议(给出可执行修改;由 linter 复检修改是否消除缺陷)

**归因规则**(逐缺陷类型、逐模型):

- 模态 A 失败 ∧ 模态 B 成功 → **感知瓶颈**
- 模态 A 失败 ∧ 模态 B 失败 → **推理瓶颈**
- 模态 A 成功 ∧ T3 失败 → **执行瓶颈**(看得见、改不对;对应 Paper2Video 的参数不敏感观察)

**oracle 形态对照臂(切割 2512.21329 的实验证据)**: 模态 B 默认用**无损结构化几何表示**;另设模态 B′ — VLM 生成的**自然语言 caption**(2512.21329 的 oracle 形态)。预测 B ≥ B′,因 caption 自身引入感知损失。这一对照既量化”几何 oracle 比 caption oracle 干净多少”,也把本工作与 2512.21329 的方法差异落成可报告的数字证据,而非仅靠 related work 口头切割。

**整合瓶颈证伪(回应 Caption This, Reason That 的潜在反驳)**: 模态 B(结构化输入)旁路视觉→推理整合通道。若 G 组 B 成功率显著高于 A → 整合非主瓶颈、感知是;若 B 也低 → 才考虑推理/整合。写入 discussion。

**模板维度(免费第三臂,本版新增)**: 上述矩阵在两种条件下各跑一遍——

- 条件 ∅ — 无模板从零生成的 deck(缺陷谱完整,G3–G6 充分激活)
- 条件 ⊞ — 企业模板约束下生成的 deck(母版继承 + 占位符;G3–G6 应被结构性压制)

**预注册对照预测**(构成”模板解决版面推理、解决不了感知与语义”的因果证据):

- ⊞ 相对 ∅,G3–G6 的缺陷发生率与 examiner 漏检的**绝对损失**大幅下降(版面推理被模板吸收)
- ⊞ 相对 ∅,G1/G2 与整个 S 组的归因结论**几乎不变**(感知瓶颈与语义瓶颈不被模板触及)
- 若该 dissociation 成立 → 用一个工业杠杆(模板开关)二次验证感知/推理 decoupling,且证明”残差坍缩到两端”这一核心增量 claim

> 实现备注:条件 ⊞ 使用 python-pptx 加载 .potx,内容灌入占位符;G3–G6 注入需绕过模板约束(直接改 XML 几何)才能制造缺陷,这本身量化了”模板要被多大力度破坏才会失效”。

> **实证修订(§3.0)**:A-fail/B-success 归因规则**只在 balanced accuracy + 配对 clean 控制下**才成立(模型会过报/弃答,recall 会误导)。**G 组 pointwise 全员随机**,该规则对 G 组失效——G 组改走轨 L(linter)+ 轨 P(G1 的 pairwise)。该规则保留给**轨 E 的 S 组**(S1/S4/S5)。B′ 已落地为"VLM 看图 caption";模板维度按 §3.0(8) 解耦。

### 3.3 心理物理曲线(本 Part 的特色产出)

对 G 组每个缺陷,绘制**检测率 vs 严重度 θ** 曲线,拟合每个模型的”感知阈值”(50% 检测率对应的 θ)。预期产出:不同规模模型的阈值对比图——若 27B 与 8B 阈值无显著差异而语义任务有差异,即定量证实”scale 修推理不修感知”。

> **实证修订(§3.0)**:VLM 的 pointwise 几何检出**不是渐变的阈值曲线**,而是阶跃(要么随机、要么——仅 G1+30B——突然可检),且高分辨率/编码器都不移动它。心理物理阈值曲线**改在 linter 的连续几何量上画**(linter 有 θ 的连续读数);VLM 端只报"是否破随机 + 破在哪个尺寸/哪种缺陷"。G1 溢出的 forced-choice 复活(8B 即 100%)是这条线最干净的产出。

### 3.4 模型矩阵与消融

- Qwen3-VL: 4B / 8B / 32B-dense / 30B-A3B(服务器推理,权重已落本地 `/home/gpus/models`:4B/8B BF16、30B-A3B-AWQ、32B-dense **仅 AWQ**——全精度 BF16 版已于 2026-06-16 删除以腾磁盘,32B 档统一走 AWQ-INT4 + TP=2)
- Qwen3.6-27B(可选,已坐实为多模态 dense,Apache-2.0,2026-04-22 发布;原生 text+image+video,AWQ-INT4 ≈17GB 可单卡 或 TP=2,已有人在 vLLM v0.19 + Ampere 上跑通——与本机 vllm 0.19.0 一致,故不再预留大额趟坑预算,失败再降级 API)
- API 参考点 ×1(频控预算内)
- **GPU 拓扑约束(实测)**: 4×RTX 3080 20GB 为 PCIe 无 NVLink,且 `nvidia-smi topo -m` 显示 GPU0 与 GPU1/2/3 跨 NUMA(`SYS`),GPU1/2/3 互为 `NODE`(同 socket)。故 **TP 推理固定走 `CUDA_VISIBLE_DEVICES=1,2,3`**(避开 GPU0 跨 socket all-reduce 瓶颈),GPU0 留作微调/机动;所有 TP 加 `--disable-custom-all-reduce`;sm_86 无 FP8 硬件 → 大模型走 AWQ/GPTQ-INT4,KV cache 用 fp16/INT8,不用 fp8 KV
- **分辨率消融**: 输入图 {768, 1024, 1536, 2048} px 长边——感知瓶颈应对分辨率敏感、推理瓶颈不敏感,作为归因结论的第二证据线
- 每 (模型, 条件) 采样 k=3,报告均值 ± std;沿用 variance gating:效应量 < 2σ 不下结论

> **实证修订(§3.0)**:**编码器家族扫已完成且为负结果**(SigLIP2/LLM-based/InternViT/NaViT/MoonViT 在 8–9B 几何 bal-acc 全 ~0.50,只差 bias)——不进主矩阵预算。**分辨率消融收窄**(1536≡2048,几何零差别),只在非地板 cell 抽测,不再全缺陷 × 4 分辨率。模型矩阵保留跨尺寸(4B/8B/30B 定阈值);文档/OCR 专精模型(dots.ocr、PaddleOCR-VL)是**感知前端不是 examiner**(只 parse 版面,不判缺陷),如用只作 linter/reasoner 的输入。

-----

## 4. Part 2 — 修复:合成缺陷训练的专用 Examiner

### 4.1 训练配置

- 基座:Qwen3-VL-8B-Instruct;单卡 QLoRA(LLaMA Factory,gradient checkpointing,复用 orchestrator distillation 流程)
- 数据:G+S 全分类学合成注入,每实例输出结构化 JSON 批评(缺陷类型、定位元素、严重度估计、修复建议)——格式即下游优化器(SkillOpt optimizer-model / GEPA reflection)的 ASI 格式
- **输出双模式**(回应三域收敛的”相对优于绝对”结论,见 §2.6):
  - pointwise——单页打分 + 结构化批评(供 ASI 反思)
  - pairwise——同一内容两个渲染候选的相对优劣判断(供 §5 优化器选择门:SkillOpt validation gate / GEPA Pareto 与 RVPO 式相对排序;预期比 pointwise 更鲁棒)
- **成对训练格式**(VisRefiner 启发):同时喂 (clean, defective) 配对样本,让 examiner 显式对比学习缺陷边界,而非仅看单图二分类
- 数据量:~20–40K 实例(注入器免费生成,按训练曲线决定)
- 负样本:无缺陷页 ≥ 30%,抑制过报(precision 与 recall 同等报告)
- **模板条件标注**: 每训练样本标注 ∅/⊞ 来源,使 examiner 同时见到有/无模板分布,避免只在从零生成分布上过拟合

### 4.2 评估(三层)

1. **In-domain held-out**: 留出的严重度参数 + 留出缺陷类型(OOD 泛化)
1. **真实迁移**: 人工标注 ~100 页真实问题 deck —— **已延后至 §10(非必要)**;本轮以第三方 **SlideAudit** image-only 迁移替代(`reports/part2.md` Table 5)。PPTBench 经核为属性 QA、与缺陷 taxonomy 无重叠,不用。
1. **对手矩阵**: zero-shot {8B, 27B/Qwen3.6, API 强模型}、纯 linter(几何类上界参照)、finetuned-8B

### 4.3 预期结果形态

finetuned-8B 在 G 组逼近 linter、显著超过 zero-shot 27B/API;在 S 组与大模型持平或小幅落后——即”专用化修感知、规模修语义”的互补图景,直接支撑混合架构设计。

> **实证修订(§3.0)**:zero-shot VLM 的 G 组 **pointwise 几何检测不可达**(细几何是真感知阈值),所以 examiner 在 G 组的价值**不是 pointwise 检测逼近 linter**,而是:① **G1 溢出走 pairwise**(zero-shot 8B forced-choice 已 100%,微调强化);② 消费 **linter 喂入的几何标签**做交叉验证与修复建议;③ 主力放在 **S 组语义 + 一致性核查(pairwise)**。"finetuned-8B 在 G 组逼近 linter"的原表述改为"在 **overflow-pairwise** 上逼近 linter、其余细几何由 linter 承担";训练数据的 G2–G6 标签来自 linter,examiner 学的是"复述/兜底"而非"从像素重新检测"。

-----

## 5. Part 3 — 下游效用(轻量佐证):Examiner 质量 → 下游 slide 生成改进

> **降级 2026-06-19(本节相对 §5 后文的"双优化器载体/SkillOpt 主"措辞为准)**。决策与依据:
> 1. **重心回到 VLM**:本工作是**VLM 诊断(N1)+ 注入缺陷训练的专用 examiner(N2 配套)**论文,**不是 skill 优化论文**。Part 3 仅为"examiner 越准→下游 deck 改得越好"的**轻量外在效用佐证**,依附 N1/N2、不独立成篇(见 §0.5 N3)。
> 2. **载体降级为"self-refine 主佐证 + GEPA 旁证"**:① **self-refine**(examiner 作 agent 反思信号,generate→critique→revise)——零外部依赖、我们完全可控、最直接体现"examiner 质量→修订收益";按 §0.5 它是 EvoPresent 已占的范式,故**如实标 baseline-style 载体、不当独占头条**。② **GEPA** 作 skill-space 旁证(已真实跑通,见执行快照)。
> 3. **SkillOpt 移出主线(deferred,代码留存)**:上游 PyPI 包 0.1.0 **缺打包 prompt 资产**(`prompts/` 仅 `__init__.py`)、需未文档化 cfg、且其 analyst 在我们集成里**不真正调用 optimizer LLM**(轨迹文件契约不符,0 calls;后端隔离测试本身可调通),GitHub 不可达 → 忠实复现不可达。`slide_examiner/skillopt_adapter.py` 保留并标 deferred,不进主线。"optimizer-agnostic 双载体"从硬 claim 降为"换载体(GEPA vs self-refine)结论一致"的鲁棒性佐证。
> 4. 原"换 GEPA→SkillOpt 消除'应用优化器无新意'风险"的动机**作废**:既然不是优化器论文,该风险本就不适用;真正的护城河是 §0.5 的 N1/N2。
>
> **以下 §5.0–§5.4 与 §6 H3 的"SkillOpt 主/双载体 optimizer-agnostic"原措辞保留作历史,但以本 banner 为准。文献核查点(Gao/PRIME/AeSlides/EvoPresent/VLM-SlideEval 的切割)仍有效。**

> **重构 2026-06-18(载体换代 + 新颖性重定范围;原 §5"GEPA 单载体"作废)**。触发与依据:
> 1. **SkillOpt**(arXiv 2605.23904, Microsoft, 2026-05;github.com/microsoft/SkillOpt)把技能优化重述为**可控 text-space 优化器**(独立 optimizer-model 反思 + held-out validation gate 选择 + bounded edit + rejected-edit buffer + slow/meta update),在 6 benchmark × 7 模型 × 3 harness 的 **52/52 cell** 上 best-or-tied,**全面超过 GEPA/TextGrad/Trace2Skill/EvoSkill**。→ 把下游载体从 GEPA **换成 SkillOpt(主)+ GEPA(次)**,直接消除 §7 高概率风险"应用 GEPA 无新意"。
> 2. **联网核查 + PDF 核验纠正了一处会被拒稿的过强表述**:"反馈/评估器质量作受控自变量→优化效率"**并非空白**——RL/verifier 域已有:基础 [Gao 2210.10760](gold-vs-proxy 过优化 scaling)、量化 PRIME [2602.11570](verifier-acc→RLVR policy **R²=0.937/0.920**,数学/工程),强度视用途而定(BoN 强 r≈0.87 [2506.01937] / RLHF 弱 [2410.05584])。故本工作贡献**不是"发现反馈质量重要"**,而是把该已知原理**迁移到两个空白格的交集**:① **text-space skill/prompt 优化器**(GEPA 的 μ/μ_f 为固定输入、SkillOpt 反馈固定为 benchmark hard-score,**二者都不把反馈源质量当自变量**——已核 PDF);② **design/multimodal 域**(无 scaling-law 类比)。
> 3. **解耦反馈架构升为主线**:可验证 linter = 选择门(SkillOpt §3.5 validation gate / GEPA Pareto 选择),学习型 examiner = 反思源(SkillOpt optimizer-model / GEPA reflection)。这是 Part 1"相对/可验证 > 绝对/可幻觉"在下游的落点;SkillOpt 原文 *"plausible textual diagnoses can still hurt the actual target model"* 正是论据。AeSlides([2604.22840]:VLM 打分"prone to reward hacking"→改可验证度量)与 VLM-SlideEval([2510.22045]:呼吁"calibrated critic-in-the-loop selection gates")提供独立外部背书。
> 4. **slide 生成是测试床,不是 claim**。"用 design 反馈改进 slide 生成器"在 2026 已被**权重空间 RL** 占满且月度升温(AeSlides 4 月、EvoPresent/PresAesth [2510.05571] ICLR 2026、[2606.10334] 6 月、GLM-5),**正面竞争高危**;差异化必须落在 measurement/attribution + **skill-space**。`generate→critique→revise` self-refine 环(EvoPresent 已占 ICLR 2026)**降级为 baseline,不作 headline**。

### 5.0 新颖性范围(三交集,每个独立可辩护)

- **(i) skill-space**:把 verifier-质量→效率 从 RL/权重空间迁到 text-space skill/prompt 优化器(SkillOpt/GEPA);
- **(ii) design 域**:首条 examiner-内在质量 ↔ 下游优化效率曲线落在 **design/multimodal**(RL/verifier 工作全在 text/math/code);
- **(iii) 解耦可验证/学习反馈**:可验证 linter 选择门 + 学习型 VLM 反思,源自 Part 1 实证,恰配 SkillOpt 的 gate/optimizer 二分。
- **正确蹭的热度**:skills-as-trainable-state(SkillOpt/ACE/Trace2Skill)、verifier-quality(Gao 2210.10760 / PRIME 2602.11570)、verifiable-rewards-for-geometry(AeSlides 作背书非竞争);**不蹭** generate-critique-revise self-refine。

### 5.1 实验设计

- **被优化系统(测试床)**: 模块化 slide 生成 agent(场景识别 / 页面类型生成指令 / 组件库使用说明 / 质检 checklist 共 4 组 prompt/skill 模块;结构化内容 JSON → HTML+python-pptx 双渲染)——即实习交付系统本体,在 Part 3 中作为**评测载具**而非贡献本身
- **任务集**: SlidesBench 子集 + 实习场景任务包,train 10 / val 10 / test 10(deck 级)
- **下游载体(降级 2026-06-19,见 §5 banner;轻量佐证,非"双优化器主张")**:
1. **self-refine(主佐证)**: examiner 作 agent 的反思信号(generate→critique→revise),零外部依赖、完全可控;按 §0.5 是 EvoPresent 已占范式 → **如实标 baseline-style 载体,不作 headline**
1. **GEPA(旁证)**: skill-space 优化,reflection/optimizer LLM 冻结,已真实跑通
1. **~~SkillOpt~~(移出主线,deferred)**: 上游包缺资产、analyst 不调 optimizer → 忠实复现不可达;代码留 `skillopt_adapter.py`。"optimizer-agnostic" 降为"GEPA vs self-refine 两载体结论一致"的鲁棒性佐证
- **Examiner 质量梯度(真正的自变量,内在质量已由 Part 1/2 度量)**:
1. 纯 linter(只有可验证几何信号)
1. zero-shot 8B
1. zero-shot 30B(本机跨尺寸上界;API 强模型可选)
1. finetuned-8B(本工作)
1. **混合(解耦)**: 可验证 linter 作**选择门**(SkillOpt validation gate / GEPA Pareto)+ finetuned-8B 文本批评作**反思 ASI**(本工作主张的架构)
- **控制**: 相同优化器超参、相同 rollout 预算上限(每条件 × 每载体 ≤ 200 rollouts)、相同且**冻结的 reflection/optimizer LLM**、k=3 随机种子。**关键澄清**:examiner 是被替换的**反馈源**,不是优化器;优化器内核与超参在所有条件下同一,隔离出"反馈源质量"这一单一自变量

### 5.2 因变量

- **收敛效率**: 达到固定质量阈值所需 rollout 数(design 域首条 examiner-质量→效率 曲线)
- **最终质量**: held-out test 上的终评——评审采用与训练信号**不同源**的 panel(冻结 API judge 自动臂为主;**人工 3 名臂延后至 §10,非必要**),防 Goodhart 循环论证
- **Reward-hacking 审计(gold-vs-proxy,移植 [Gao 2210.10760] 协议到 design)**: 用 held-out **可验证 linter(gold)**检测 policy 是否在 game 学习型 examiner(proxy)——proxy 分升但 gold 分不升即过优化;逐项记录 AeSlides 式作弊(隐藏/越界文字、纹理背景遮挡、覆盖层、退化空页);混合条件(可验证选择门)预期最抗 hack

### 5.3 Token/成本预算

- rollout(deck 级,15 页): 生成 ~80K + examiner ~30K ≈ 110K token/次
- 5 examiner 条件 × 2 载体 × 200 rollouts × 3 seeds 为上限;**SkillOpt 的 edit-economy(全程 1–4 个 accepted edits、validation-gated)实际远低于该上限**,先跑页面级预实验估方差再定 deck 级预算
- 本地 8B/30B-A3B 承担 rollout(电费),API 仅 reflection(调用数在万次内,预算可控)
- 4×3080 分工:3 卡跑 examiner/generator 数据并行 worker,1 卡机动(训练期全部 4 卡轮转)

### 5.4 竞争窗口

design-reward 空间 2026 月度升温(AeSlides 4 月 → EvoPresent ICLR → 2606.10334 6 月)。本工作护城河是 **examiner-质量梯度 × skill-space × design 反作弊审计**的 measurement,不是又一个 slide 生成器改进法;**尽快产出页面级占位结果**以锁定 skill-space + measurement 角度。

-----

## 6. 预注册假设与证伪条件

|假设        |内容                                                                                |证伪条件(出现即如实报告,不调整假设)                                                    |
|----------|----------------------------------------------------------------------------------|-----------------------------------------------------------------------|
|**H1**    |G 组缺陷:模态 B(oracle)准确率 − 模态 A(图)准确率 ≥ 20pp,且该 gap 不随模型规模显著缩小;S 组 gap < 10pp 且随规模缩小 |若 27B/API 在模态 A 下 G 组接近天花板 → 感知瓶颈不成立,转向纯 examiner 工程论文或放弃              |
|**H1-tpl**|模板 dissociation:条件 ⊞ 相对 ∅,G3–G6 漏检绝对损失下降 ≥ 50%,而 G1/G2 与 S 组的感知/推理归因结论不变(差异 < 5pp)|若模板也显著改变 G1/G2 或 S 组归因 → “残差坍缩到两端”的核心增量 claim 不成立,模板维度降级为工程观察、不进主 claim|
|**H2**    |finetuned-8B 在 G 组检测 F1 超 zero-shot 最强对手 ≥ 10pp,且真实 deck 迁移 F1 ≥ 0.7              |若合成→真实迁移崩(F1 < 0.5)→ 报告 sim2real gap 为主要发现,H3 改用合成任务域                  |
|**H3(轻量佐证;降级 2026-06-19——载体为 self-refine 主 + GEPA 旁,非 SkillOpt 双载体)**|下游(self-refine / GEPA)中,examiner 内在质量越高 → 达固定质量阈值所需 rollout/迭代越少、终质量越高;混合(可验证选择门 + 学习反思)≥ 任一单源。RL/text 已有 verifier-质量→效率 先验,design 域出现是预期|若 design 域不单调/仅单一载体/混合不优 → 如实报 **design 域 feedback-transfer 反例**,单独成段(仍有价值,**且不动摇 N1/N2 重心**)。**执行快照(2026-06-19)**:GEPA 旁证已得**反例**(corr=+0.563;强 generator 地板 + proxy 饱和;0 reward-hacking);self-refine 主佐证待补|

辅助预测(不作为主 claim):P1 — G 组检测率对输入分辨率敏感、S 组不敏感;P2 — 严重度阈值曲线上,模型规模对 G 组阈值无显著影响。

> **预注册假设的实证修订(2026-06 pilot;以 balanced accuracy + 配对 clean 计)**:
> - **H1 重述**:不再是"模态 B − 模态 A ≥ 20pp"。实测 **G 组 pointwise 全员随机**(A/B/C 在 4B/8B/30B + 5 编码器家族 bal-acc ~0.50;B 的结构通道并不救 G 组)。修订后的 H1 = "**几何缺陷的 pointwise VLM 检测在 ≤30B 不可达,且不随编码器/分辨率改善;只有 G1 溢出在 forced-choice 下可达(8B 即 100%)**"。→ 主 claim 落在"G 归 linter、overflow 可 pairwise、细几何是真感知阈值",而非感知 vs 推理的连续 gap。
> - **H1-tpl 重述**:按 §3.0(8) **解耦**——模板吸收由 linter 度量(已证 snap-to-master 吸收 G2);"VLM 检出随模板下降"在 4B/8B 上无从测(几何本就 0),降级为 30B+overflow 上的可选观察。
> - **P1 证伪**:分辨率(1536 vs 2048)对几何**零影响** → P1(几何对分辨率敏感)**不成立**,删去。
> - **P2 部分成立**:规模确实不修细几何阈值(G3–G6),但**修 G1 溢出的可检性**(30B pointwise 破 G1、8B forced-choice 破 G1)→ P2 限定为"细几何(G3–G6)阈值与规模无关"。
> - **新增 H-rel(相对优于绝对)**:对"能感知但不会绝对判断"的缺陷(G1 溢出、S6 图文矛盾),**pairwise/2-AFC 显著优于 pointwise**(均从随机 → 满分)。这条已被 G1 与 S6 两组独立证据支持,提升为主 claim 之一。

-----

## 7. 风险与缓解

|风险                                                     |概率|缓解                                                                                     |
|-------------------------------------------------------|--|---------------------------------------------------------------------------------------|
|Qwen3.6-27B 在 Ampere 部署受阻                              |低 |已下调:Qwen3.6-27B 为多模态 dense,有公开实例在 vLLM v0.19(=本机版本)+ Ampere 跑通,AWQ-INT4 单卡/TP=2;预留 0.5 天而非 2 天,失败则 API 替代,不影响主矩阵(主矩阵基于已验证的 Qwen3-VL 系列)|
|合成缺陷与真实缺陷分布偏移                                          |中 |第三方 SlideAudit 做真实迁移(自建人工集延后至 §10);注入参数贴真实统计(先在 Zenodo10K 上测量真实缺陷分布)                                     |
|优化实验方差过大淹没条件差异                                      |中 |k=3 seeds + variance gating;先跑页面级(便宜)预实验估计方差再定 deck 级预算;SkillOpt validation-gate 使收敛轨迹更稳(edit-economy 1–4 accepted edits)|
|评审质疑”应用某优化器无新意”                                      |低 |**已降级 2026-06-19**:Part 3 不是优化器论文,是 VLM 诊断/examiner 论文的**轻量下游佐证**(self-refine 主 + GEPA 旁);该风险对"非优化器论文"本就不适用。重心是 N1/N2;切割 verifier-质量→效率(Gao/PRIME)|
|design-reward 空间被 RL-slides 抢发(AeSlides/EvoPresent/2606.10334 月度升温)|中高|差异化锁死在 **skill-space + measurement/attribution**(非又一个 slide 生成器改进);self-refine 环降级为 baseline;尽快产出页面级占位结果|
|与主线(PR-Decoupling)抢时间                                  |高 |硬性规则:本项目每周 ≤ 2.5 天;Part 1 注入器与 PR-Decoupling 扰动代码共享基建;若 Week 4 末 H1 未现端倪,降级为实习工程交付     |
|2512.21329 团队把同款方法推广到 document/slide 域(抢发)             |中 |抢时间窗;**N2 模板维度是护城河**(ARC 域无模板概念可平移),优先把 N2 做成可展示结果                                     |
|有人合并 LED 式注入 + 感知归因                                    |中低|N2 模板坍缩为独有概念;尽快产出 N2 结果占位                                                              |
|审稿人混淆 perception/reasoning 与 ranking-scoring decoupling|中 |§2.8(b) 已备正式切割措辞;模态 B′ caption 对照臂提供数字级区分证据                                            |
|某优化器(GEPA/SkillOpt)官方出 VLM-feedback 版本                |低 |不受影响:N3 已降级为轻量佐证、不独立成篇,重心是 N1/N2(VLM 诊断+专用 examiner),与优化器本身无关|
|SkillOpt 上游包不可用(缺 prompt 资产/analyst 不调 optimizer、GitHub 墙)|已发生|**移出主线、deferred**(代码留 `skillopt_adapter.py`);optimizer-agnostic 用 **self-refine vs GEPA** 两载体一致性替代|

-----

## 8. 时间线(8 周,每周 ≤ 2.5 天)

- **W1–2**: 注入器 + 渲染管线 + linter(与实习系统共建);Zenodo10K 清洗;真实缺陷分布测量
- **W3–4**: Part 1 全矩阵推理 + 归因分析 + 心理物理曲线;**Go/No-Go 检查点(H1)**
- **W5**: Part 2 训练 + 三层评估
- **W6–7**: Part 3 技能空间优化矩阵(SkillOpt 主 / GEPA 次;页面级预实验 → deck 级)
- **W8**: hacking 审计、补充消融、写作框架

-----

## 9. 交付物

1. **实习侧**: 可运行的 slide 生成 agent(双渲染 + 分层质检 + SkillOpt/GEPA 调优后的 Skill 文档)——mentor 的”不需要人改”系统。**工程简化(有归因实验背书)**: 在企业模板约束下,质检器只需实现 G1/G2 的几何 linter + S 组的 VLM examiner,可名正言顺砍掉 G3–G6 检查(母版已兜底)——此简化由 H1-tpl 的模板 dissociation 结果支撑,非经验偷懒,写进交付文档可向 mentor 论证。
1. **学术侧**: 论文草稿(目标:ACL/EMNLP 系或 CVPR/ICCV 系,视 H1/H2 哪条更强决定投向)+ SlideProbe 诊断集与注入器开源
1. **复用资产**: 缺陷注入器与归因协议代码,直接反哺 PR-Decoupling 主线的扰动基建

-----

## 10. 延后的人工标注工作（deferred；非主线，结论不依赖）

> **收尾决策(2026-06-18)**:全 spec 中一切依赖**人工标注**的环节集中到本节,统一定性为**非必要 / 非阻塞 / 待真正有空再锦上添花**。两条理由:① 本机无多人标注能力;② **自建真实 test set 有"自标自评"公正性嫌疑** —— 真实迁移的可信信号应来自**第三方**人工标注集,故采用第三方 **SlideAudit**(arXiv 2508.03630)做 image-only 真实迁移(`reports/part2.md` Table 5),不自建人工评测集进主线。各项均有已完成的**合成 / 第三方替代**,Part 1/2/3 的主结论与各 gate 判定**不依赖本节**。标注协议见 `docs/annotation_protocol.md`;`slide_examiner/panel.py` 已输出 inter-annotator agreement(κ/一致率)。

逐项归集(原出处 → 替代/现状):

1. **(原 §4.2 真实迁移 / §7 风险行) ~100 页真实问题 deck 人工标注** + 实习脱敏 deck 接入。
   - 替代:第三方 **SlideAudit** image-only 迁移已完成(Table 5,reframe 为 *out-of-design 下界*);`data_sources.py::internal_desensitized` 仅注册占位,无真实数据。
2. **(原 §4.2 / §6 H2) 带元素结构(模态 C)的真实迁移评测 + 语义真实标签**。
   - 现状:几何真实标签可由 linter 自动给,但**循环**且 examiner 本就设计弃答;语义真实标签需人工 → **阻塞**。**H2 的真实迁移合取项(F1≥0.7)按 §6 预登记证伪分支处理**:image-only 真实几何崩(<0.5)= sim2real gap 作为发现,已诚实记入报告;判别"缺结构 vs 缺能力"的模态 C 实验留本节。
3. **(原 §5.2 / §5.4 终评) Part 3 不同源人工 panel(3 名人工 + 冻结 API judge)**。
   - 替代:**冻结 API judge 自动臂** + 评测协议先行;人工 3 人臂延后。`gepa_eval` / `panel.py` 聚合就绪。

> 注:上述不改变 §6 各假设的**证伪口径**;H2 已落在其预登记的 sim2real-gap 分支,不因本节延后而"悬而未决"。