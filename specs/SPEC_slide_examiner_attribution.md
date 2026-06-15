# SPEC: Slide-Examiner — VLM 幻灯片质检的感知/推理归因、专用小模型修复与下游优化效用验证

**版本**: v0.3 (pre-registration draft)
**日期**: 2026-06-15
**状态**: 待评审 → 冻结后开始实验
**配套文档**: NOVELTY_analysis_2026-06.md(逐竞品切割,related work 截止 2026-06)
**硬件约束**: 4×RTX 3080 20GB (Ampere, PCIe, no NVLink) + 服务器推理 (Qwen3-VL 4B/8B/32B-dense/30B-A3B)
**方法论血缘**: VideoQA_PR_Decoupling_Plan.md(可控扰动 2×2 归因)、SUPPLEMENTARY_EXPERIMENT_SPEC.md(variance gating / power analysis)、orchestrator distillation(单卡 QLoRA 流程)

-----

## 0. 一句话定位

> VLM 做渲染文档(幻灯片)质检时,失败主要来自**感知保真度**而非**推理能力**;用**程序化缺陷注入**(零标注成本、精确标签)训练的小型专用 examiner 能在几何类检查上超过大型通用模型;且 examiner 质量可以直接转化为下游 prompt 进化(GEPA)的优化效率。

论文结构为三段式,共享一个 claim:**“质检信号的质量瓶颈在感知,而感知瓶颈可以被廉价地专门化修复,并且修复的价值可以在下游被外在地度量。”**

**模板坍缩洞察(本版核心增量)**: 工业幻灯片生成几乎总在企业模板(.potx 母版/版式/占位符)约束下进行。模板提供**结构参考但不提供内容参考**——它钉死排版骨架(对齐/字号继承/品牌色/边距),却完全不约束槽位内容是否准确、是否溢出、叙事是否连贯。因此引入模板后,可质检缺陷谱**向两端坍缩**:一端是模板兜不住的**纯感知缺陷**(溢出/重叠,因为文字长度由内容决定),另一端是模板管不着的**纯语义缺陷**(内容正确性/叙事),而中间”规模可解的版面推理”被模板吃掉。这一坍缩既是工程简化的依据(质检器只需实现两端),也让感知/语义二分在工业条件下更尖锐——模板成了归因协议的一个免费实验臂。

-----

## 0.5 Novelty 声明(三层,稳健度排序;详见 NOVELTY_analysis_2026-06.md)

|#     |Novelty                                                                    |稳健度               |最近邻竞品                                                               |切割要点                                          |
|------|---------------------------------------------------------------------------|------------------|--------------------------------------------------------------------|----------------------------------------------|
|**N1**|感知/推理归因首次用于**生成物质检**(而非输入理解),且 oracle 用**无损结构化几何表示**(而非有损 caption)         |高(方法已被邻域验证,但本域无人做)|“Your Reasoning Benchmark May Not Test Reasoning”(2512.21329, ARC 域)|任务族(质检 vs 理解)、oracle 形态(几何 vs caption)、是否闭环到下游|
|**N2**|**模板坍缩**:模板把可质检缺陷谱挤向”纯感知 + 纯语义”两端,中间版面推理被吸收;模板开关作为感知/推理 dissociation 的免费实验臂|高(**无直接竞品,竞品难平移**)|无                                                                   |唯一原创概念贡献,本工作护城河                               |
|**N3**|首次以 **examiner 反馈源质量为自变量**研究 GEPA 收敛效率;首次用 **VLM 结构化视觉批评作 ASI**            |中(须依附 N1/N2)      |GEPA 应用清单(全文本/标量反馈域)                                                |feedback-source 作受控自变量无人做;但不可独立成篇             |

**最强单篇结构**: N2 为概念核心 + N1 为方法工具 + N3 为外在效用证明。资源优先级 N2 > N1 > N3。

**三处必须主动防混淆的命名/任务撞车**(写作时在 related work 显式切割,见 §2.8):

- 2512.21329 同款 perception/reasoning 分离方法 → 切割任务族与 oracle 形态
- “VLM Judges Can Rank but Cannot Score”(2604.25235)的 **ranking-scoring decoupling** → 与本工作 perception/reasoning decoupling 正交,反过来引为 pairwise 设计背书
- **LED Benchmark**(2507.23295)的结构错误注入 → 引为方法先例,但强调 LED 自承”无法隔离识别 vs 推理失败”正是本工作所解决的

-----

## 1. 研究问题(预注册)

- **RQ1(诊断)**: VLM 在幻灯片缺陷检测上的失败,在多大程度上可归因于感知(看不见/看不准)vs 推理(看见了但判断不了)?该归因是否随缺陷类型(几何 vs 语义)、模型规模、输入分辨率系统性变化?
- **RQ2(修复)**: 在程序化注入的合成缺陷上 LoRA 微调的小型 VLM examiner(8B),能否在几何类检查上超过 zero-shot 的更大模型(27B/API 级),并泛化到真实人工制作的 deck 与公开 benchmark?
- **RQ3(下游)**: examiner 质量(由 RQ1/RQ2 的内在指标度量)是否单调地转化为 GEPA prompt 进化的收敛效率与最终生成质量?“选择信号(可验证 linter)与反思信号(VLM 文本批评)分离”是否优于任一单源信号?

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

### 2.5 Prompt 进化与反馈工程(N3 基础)

- GEPA (ICLR 2026 Oral, arXiv 2507.19457):反思式 prompt 进化,文本反馈(ASI)为核心;Pareto 选择消融 +6.4~8.2%;论文自列 “feedback engineering” 为未来方向——RQ3 即是对该方向的系统回答。
- gepa-ai optimize_anything:整个 agent 脚手架作为文本工件进化;工程载体。
- **GEPA 应用清单实证空白(坐实 N3)**: 截至 2026.04 的公开应用——医疗 NER、临床风险偏倚评估、深度研究多智能体、医学影像 prompt triage、客服 supervisor、低资源语言——**全部基于文本/标量反馈,无一以 VLM 视觉批评作 ASI,无一以”反馈源质量”为受控自变量**。Decagon 生产实践(2026.03)做了 19+ GEPA 配置消融但对象是文本监督模型、调的是超参而非反馈源。→ 本工作 N3 的确切空白:examiner 感知/语义质量(由 Part 1/2 内在度量)→ GEPA 收敛效率的受控传导。

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
1. 没有工作量化 **examiner 质量 → prompt 优化效率**的传导链,也无人用 VLM 视觉批评作 GEPA 的 ASI——feedback engineering 被列为 open problem 但无受控研究。
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

### 3.3 心理物理曲线(本 Part 的特色产出)

对 G 组每个缺陷,绘制**检测率 vs 严重度 θ** 曲线,拟合每个模型的”感知阈值”(50% 检测率对应的 θ)。预期产出:不同规模模型的阈值对比图——若 27B 与 8B 阈值无显著差异而语义任务有差异,即定量证实”scale 修推理不修感知”。

### 3.4 模型矩阵与消融

- Qwen3-VL: 4B / 8B / 32B-dense / 30B-A3B(服务器推理,已有)
- Qwen3.6-27B(可选,4×3080 BF16 TP=4;注意 Ampere 上混合 DeltaNet kernel 成熟度,预留 2 天趟坑预算,趟不通则降级为 API 调用)
- API 参考点 ×1(频控预算内)
- **分辨率消融**: 输入图 {768, 1024, 1536, 2048} px 长边——感知瓶颈应对分辨率敏感、推理瓶颈不敏感,作为归因结论的第二证据线
- 每 (模型, 条件) 采样 k=3,报告均值 ± std;沿用 variance gating:效应量 < 2σ 不下结论

-----

## 4. Part 2 — 修复:合成缺陷训练的专用 Examiner

### 4.1 训练配置

- 基座:Qwen3-VL-8B-Instruct;单卡 QLoRA(LLaMA Factory,gradient checkpointing,复用 orchestrator distillation 流程)
- 数据:G+S 全分类学合成注入,每实例输出结构化 JSON 批评(缺陷类型、定位元素、严重度估计、修复建议)——格式即下游 GEPA ASI 格式
- **输出双模式**(回应三域收敛的”相对优于绝对”结论,见 §2.6):
  - pointwise——单页打分 + 结构化批评(供 ASI 反思)
  - pairwise——同一内容两个渲染候选的相对优劣判断(供 §5 GEPA 的 Pareto 选择与 RVPO 式相对排序;预期比 pointwise 更鲁棒)
- **成对训练格式**(VisRefiner 启发):同时喂 (clean, defective) 配对样本,让 examiner 显式对比学习缺陷边界,而非仅看单图二分类
- 数据量:~20–40K 实例(注入器免费生成,按训练曲线决定)
- 负样本:无缺陷页 ≥ 30%,抑制过报(precision 与 recall 同等报告)
- **模板条件标注**: 每训练样本标注 ∅/⊞ 来源,使 examiner 同时见到有/无模板分布,避免只在从零生成分布上过拟合

### 4.2 评估(三层)

1. **In-domain held-out**: 留出的严重度参数 + 留出缺陷类型(OOD 泛化)
1. **真实迁移**: 人工标注 ~100 页真实问题 deck(实习场景脱敏 + Zenodo10K 人工筛查);VLM-SlideEval / PPTBench 检测与理解子任务直接报数
1. **对手矩阵**: zero-shot {8B, 27B/Qwen3.6, API 强模型}、纯 linter(几何类上界参照)、finetuned-8B

### 4.3 预期结果形态

finetuned-8B 在 G 组逼近 linter、显著超过 zero-shot 27B/API;在 S 组与大模型持平或小幅落后——即”专用化修感知、规模修语义”的互补图景,直接支撑混合架构设计。

-----

## 5. Part 3 — 下游效用:Examiner 质量 → GEPA 优化效率

### 5.1 实验设计

- **被优化系统**: 模块化 slide 生成 agent(场景识别 / 页面类型生成指令 / 组件库使用说明 / 质检 checklist 共 4 组 prompt 模块;结构化内容 JSON → HTML+python-pptx 双渲染)——即实习交付系统本体
- **任务集**: SlidesBench 子集 + 实习场景任务包,train 10 / val 10 / test 10(deck 级)
- **Examiner 梯度**(自变量,内在质量已由 Part 1/2 度量):
1. 纯 linter(只有几何信号)
1. zero-shot 8B
1. zero-shot 27B 或 API
1. finetuned-8B(本工作)
1. **混合**: linter 分数驱动 Pareto 选择 + finetuned-8B 文本批评作 ASI 驱动反思(本工作主张的架构)
- **控制**: 相同 GEPA 超参、相同 rollout 预算上限(每条件 ≤ 200 rollouts)、相同 reflection 模型(API,冻结)、k=3 随机种子

### 5.2 因变量

- **收敛效率**: 达到固定质量阈值所需 rollout 数
- **最终质量**: held-out test 上的终评——评审采用与训练信号**不同源**的 panel(人工 3 名 + 冻结 API judge),防 Goodhart 循环论证
- **Hacking 审计**: 对最优 prompt 的产物跑全量 linter + 人工抽查,记录 AeSlides 式作弊模式发生率

### 5.3 Token/成本预算

- rollout(deck 级,15 页): 生成 ~80K + examiner ~30K ≈ 110K token/次
- 5 条件 × 200 rollouts × 3 seeds ≈ 330M token → 本地 8B/30B-A3B 承担 rollout(电费),API 仅 reflection(~600 次调用 × 5 条件 × 3 seeds ≈ 1 万次内,预算可控)
- 4×3080 分工:3 卡跑 examiner/generator 数据并行 worker,1 卡机动(训练期全部 4 卡轮转)

-----

## 6. 预注册假设与证伪条件

|假设        |内容                                                                                |证伪条件(出现即如实报告,不调整假设)                                                    |
|----------|----------------------------------------------------------------------------------|-----------------------------------------------------------------------|
|**H1**    |G 组缺陷:模态 B(oracle)准确率 − 模态 A(图)准确率 ≥ 20pp,且该 gap 不随模型规模显著缩小;S 组 gap < 10pp 且随规模缩小 |若 27B/API 在模态 A 下 G 组接近天花板 → 感知瓶颈不成立,转向纯 examiner 工程论文或放弃              |
|**H1-tpl**|模板 dissociation:条件 ⊞ 相对 ∅,G3–G6 漏检绝对损失下降 ≥ 50%,而 G1/G2 与 S 组的感知/推理归因结论不变(差异 < 5pp)|若模板也显著改变 G1/G2 或 S 组归因 → “残差坍缩到两端”的核心增量 claim 不成立,模板维度降级为工程观察、不进主 claim|
|**H2**    |finetuned-8B 在 G 组检测 F1 超 zero-shot 最强对手 ≥ 10pp,且真实 deck 迁移 F1 ≥ 0.7              |若合成→真实迁移崩(F1 < 0.5)→ 报告 sim2real gap 为主要发现,H3 改用合成任务域                  |
|**H3**    |GEPA 收敛 rollout 数随 examiner 内在质量单调下降;混合条件 ≥ 任一单源条件                                |若收敛对 examiner 质量不敏感 → 本身是有价值的负结果(“GEPA 对反馈噪声鲁棒”),单独成段报告                |

辅助预测(不作为主 claim):P1 — G 组检测率对输入分辨率敏感、S 组不敏感;P2 — 严重度阈值曲线上,模型规模对 G 组阈值无显著影响。

-----

## 7. 风险与缓解

|风险                                                     |概率|缓解                                                                                     |
|-------------------------------------------------------|--|---------------------------------------------------------------------------------------|
|Qwen3.6-27B 在 Ampere 部署受阻                              |中 |预算 2 天;失败则 API 替代,不影响主矩阵(主矩阵基于已验证的 Qwen3-VL 系列)                                        |
|合成缺陷与真实缺陷分布偏移                                          |中 |真实 deck 人工标注集提前建;注入参数贴真实统计(先在 Zenodo10K 上测量真实缺陷分布)                                     |
|GEPA 实验方差过大淹没条件差异                                      |中 |k=3 seeds + variance gating;先跑页面级(便宜)预实验估计方差再定 deck 级预算                                |
|评审质疑”应用 GEPA 无新意”                                      |高 |写作上 GEPA 仅为 extrinsic evaluation 载体,主 claim 落在 H1/H2;RQ3 表述为 feedback engineering 的受控研究|
|与主线(PR-Decoupling)抢时间                                  |高 |硬性规则:本项目每周 ≤ 2.5 天;Part 1 注入器与 PR-Decoupling 扰动代码共享基建;若 Week 4 末 H1 未现端倪,降级为实习工程交付     |
|2512.21329 团队把同款方法推广到 document/slide 域(抢发)             |中 |抢时间窗;**N2 模板维度是护城河**(ARC 域无模板概念可平移),优先把 N2 做成可展示结果                                     |
|有人合并 LED 式注入 + 感知归因                                    |中低|N2 模板坍缩为独有概念;尽快产出 N2 结果占位                                                              |
|审稿人混淆 perception/reasoning 与 ranking-scoring decoupling|中 |§2.8(b) 已备正式切割措辞;模态 B′ caption 对照臂提供数字级区分证据                                            |
|GEPA 官方出 VLM-feedback 版本                               |低中|N3 不独立成篇,务必绑定 N1/N2 作 examiner 质量梯度来源                                                  |

-----

## 8. 时间线(8 周,每周 ≤ 2.5 天)

- **W1–2**: 注入器 + 渲染管线 + linter(与实习系统共建);Zenodo10K 清洗;真实缺陷分布测量
- **W3–4**: Part 1 全矩阵推理 + 归因分析 + 心理物理曲线;**Go/No-Go 检查点(H1)**
- **W5**: Part 2 训练 + 三层评估
- **W6–7**: Part 3 GEPA 矩阵(页面级预实验 → deck 级)
- **W8**: hacking 审计、补充消融、写作框架

-----

## 9. 交付物

1. **实习侧**: 可运行的 slide 生成 agent(双渲染 + 分层质检 + GEPA 调优后的 Skill prompt)——mentor 的”不需要人改”系统。**工程简化(有归因实验背书)**: 在企业模板约束下,质检器只需实现 G1/G2 的几何 linter + S 组的 VLM examiner,可名正言顺砍掉 G3–G6 检查(母版已兜底)——此简化由 H1-tpl 的模板 dissociation 结果支撑,非经验偷懒,写进交付文档可向 mentor 论证。
1. **学术侧**: 论文草稿(目标:ACL/EMNLP 系或 CVPR/ICCV 系,视 H1/H2 哪条更强决定投向)+ SlideProbe 诊断集与注入器开源
1. **复用资产**: 缺陷注入器与归因协议代码,直接反哺 PR-Decoupling 主线的扰动基建