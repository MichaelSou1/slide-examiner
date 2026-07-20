# Slide-Examiner 面试 Cheatsheet

## 一句话版本

我研究的是：**当视觉语言模型漏掉幻灯片缺陷时，如何判断它究竟是“看不见”、“提问方式不对”，还是“缺少参照信息”，并用这个诊断结果设计一个确定性的符号—神经混合质检器。**

---

## 一、五分钟项目介绍

下面可以直接照着讲，正常语速约 4–5 分钟。

### 0:00–0:40｜背景与问题

我做的项目叫 **Slide-Examiner**，目标是给自动生成幻灯片的 AI agent 增加一个可靠的质量检查模块。

最直接的做法，是把渲染后的幻灯片交给视觉语言模型，也就是 VLM，让它按照一份 rubric 检查溢出、重叠、对齐、语义矛盾等问题。但我发现，VLM 输出“没有缺陷”时，这个结果本身并不能告诉我们为什么失败。

例如，一段文字溢出了文本框，模型可能是真的无法分辨这个视觉细节，也可能其实看到了，但因为一次 prompt 同时要求检查十几类问题，目标信号被压制了。这两种失败需要完全不同的解决方案：前者应该使用结构化信息或符号规则，后者只需要改变提问方式。

所以，这个项目的核心问题不是简单地问“VLM 准不准”，而是：

> **能否对 VLM 的质检失败进行归因，并让归因结果指导我们选择正确的检查方法？**

### 0:40–1:45｜失败归因方法

为了回答这个问题，我设计了一个受控的归因协议。

数据上，我为每个缺陷构造一对共享同一底稿的 defective slide 和 clean twin，只改变一个目标缺陷。然后用四种输入形式测试模型：

1. 只给渲染图像；
2. 只给结构化几何 oracle；
3. 给图像的 VLM caption；
4. 同时给图像和结构化 oracle。

这里的 geometry oracle 来自生成过程中的原生中间表示，也就是元素的 bounding box、文本和样式，不需要人工标注。

再把这些输入与 detection、localization 和 repair 三类任务交叉测试。这样就能区分三类主要失败：

- **Sub-perceptual failure**：图像输入失败，但结构化几何可以解决，说明目标低于当前模型和协议的有效视觉阈值。
- **Format-suppressed failure**：whole-rubric prompt 失败，但针对单个缺陷的 atomic query 成功，说明问题主要出在 elicitation format。
- **Reference-assisted failure**：单张图无论如何提问都不可靠，但提供 clean twin 做相对比较后可以识别，说明缺少的是参照信息。

此外，我们还构造了一个叫 **G7 render-containment overflow** 的缺陷：声明的文本框本身完全合法，但实际渲染出的像素越过了边界。因为 defective 和 clean slide 的声明几何相同，所以纯结构化 linter 按构造就看不到它，必须检查渲染结果。

### 1:45–2:50｜关键发现

实验得到三个关键结论。

第一，**有些视觉失败确实是感知阈值问题**。例如几像素的对齐偏移和很小的字号差异，即使改变分辨率、prompt 或同时提供图像与结构信息，VLM 也不稳定。对于这类声明几何明确的问题，符号 linter 更可靠。

第二，**有些失败不是模型看不见，而是 whole-rubric prompt 抑制了信号**。对于 G7，一次只询问一个缺陷、并要求给出定位证据的 C3 atomic query，明显优于一次检查全部 rubric 的 C0。

为了排除“atomic query 只是用了更多计算量”这个替代解释，我又做了三家 API 模型的 repeated-C0 对照：用十次 whole-rubric sampling 做 majority vote，而 C3 只调用一次。即使 repeated C0 获得更大的推理预算，C3 的 balanced accuracy 仍然高出 **0.20 到 0.31**，而且调用次数和输出 token 更少。

第三，**atomic query 不是万能的**。例如普通文本溢出和图文矛盾，在单张 slide 上仍可能不可靠，但给出 clean twin 做 forced choice 后，准确率可以达到约 **0.97 到 1.00**。这说明它们属于 reference-assisted，而不是简单的 prompt suppression。

### 2:50–3:50｜系统设计

根据归因结果，我设计了一个**手工指定、确定性的 symbolic–neural critic**，而不是训练一个黑盒 router：

- 原生 IR 中可精确定义的几何和术语问题，交给 symbolic linter；
- 只存在于渲染像素中的 format-suppressed 问题，交给 atomic VLM query；
- 需要上下文理解的内容问题，交给 neural semantic examiner；
- 单张图证据不足的问题，请求 clean reference 后再比较。

这个设计的重要点是：**路由规则来自失败机制，而不是哪个模型在开发集上分数最高。**

在开发阶段的 held-out validation 上，这个组合达到 **0.957 macro balanced accuracy**。但这批结果参与了方法选择，所以我没有把它包装成最终测试。

在方法冻结后，我们又生成了一个无交集的九类 image arm，每类 30 个 positive 和 30 个 clean control。冻结 critic 的 macro balanced accuracy 是 **0.826**。其中四个有可信原生 IR 的类别全部达到 **1.000 balanced accuracy**；主要损失来自 neural transfer 和 reference request 没有被 executor 完整闭环。

这里我特别区分了开发结果和冻结结果，没有用 0.957 代替真正的 disjoint evaluation。

### 3:50–4:35｜外部有效性与边界

为了避免结论只成立于合成模板，我还做了两类外部验证。

第一类使用真实 CC 授权 PPTX。我们从 26 个真实 deck 中提取原生 XML，在 PPTX 空间注入单一缺陷，再用相同 renderer 生成 clean/defective pair。结果显示粗粒度缺陷可以直接从图像识别，margin 类问题能被结构 oracle 改善，而细微对齐在真实复杂布局中仍接近随机。

第二类是只有 PDF 或 PNG、没有原生 IR 的 open-world 场景。我们尝试用 PP-DocLayoutV2 从像素恢复结构，再把恢复出的 box 交给同一个 linter。但结构恢复存在过分割，IoU ≥ 0.5 的 recall 只有约 **0.30–0.39**，无法恢复 native-IR linter 的保证。

因此，这个系统不是 universal pixel-only slide critic。它最适合拥有可信中间表示的生成 pipeline；在 open-world 输入中，性能仍受 VLM 能力限制。

### 4:35–5:00｜总结与个人贡献

这个项目的核心贡献不是提出了一个更大的模型，而是把“VLM 漏检”从单一准确率问题拆成了可干预的失败机制，并证明这种诊断能够指导系统设计。

我的主要工作包括：

- 设计缺陷 taxonomy、paired-clean 数据和归因协议；
- 实现几何与术语 linter、缺陷注入器、VLM elicitation harness 和 deterministic critic；
- 设计 compute-control、外部验证和统计分析；
- 建立从 manifest、逐样本 rollout 到论文表格的可复现流水线。

如果用一句话总结：

> **先诊断模型为什么失败，再决定应该改 prompt、加 reference，还是直接换成确定性工具。**

---

## 二、必须记住的数字

| 项目 | 数字 | 面试口径 |
|---|---:|---|
| 三厂商 C3 对 repeated C0 的提升 | **+0.20～+0.31 BA** | repeated C0 最多 10 calls，C3 仅 1 call |
| 开发期 held-out validation | **0.957 macro BA** | 参与方法选择，不能称最终测试 |
| 冻结九类 image arm | **0.826 macro BA** | 每类 30 positive + 30 clean |
| Native-IR 四类 | **1.000 BA** | 冻结测试中最强证据 |
| Direct-neural 三类平均 | **0.811 BA** | 存在 transfer boundary |
| Reference-assisted forced choice | **约 0.97～1.00** | 诊断证据，不代表 executor 已闭环 |
| 真实布局实验 | **209 pairs，5 类，3 VLM families** | 来自 26 个真实 deck |
| 像素恢复结构 recall | **0.30～0.39 at IoU ≥ 0.5** | 无法恢复 native IR 保证 |
| 模板 snapping 吸收缺陷 | **45%** | 模板特定；真实自由布局约 7% |
| G6 极端偏移 stress test | **0.958 BA** | 说明盲点受幅度约束，并非绝对能力缺失 |
| 全局多重检验 | **85 tests** | Holm：35；BH：47 |

---

## 三、10 道拷打题与参考答案

### 1. 你怎么证明是 prompt suppression，而不是模型随机性或额外算力？

我没有只比较一次 C0 和一次 C3，而是加入了 repeated-C0 control。对三家 API 模型，我们给 whole-rubric C0 最多十次独立采样，再做 majority-vote self-consistency；C3 只有一次调用。

即使 C0 使用约 8–10 倍调用和更多 token，C3 在 G7 上仍提高 0.20–0.31 balanced accuracy，三个差异在 24-test E2 family 的 Holm 校正后都显著。因此结果不能简单解释成 test-time compute 增加。

但我不会声称已经证明唯一因果机制。因为 C3 同时改变了问题粒度、输出约束和所需证据。更准确的结论是：**额外 sampling 不能解释恢复，query format 是必要干预因素之一。**

### 2. 为什么不用一个更强的端到端 VLM，非要做复杂的 hybrid system？

因为不同缺陷需要的证据类型不同，而且端到端模型的失败模式不一致。

对原生 IR 已经明确给出的几何关系，用 VLM 判断不仅成本更高，还会把确定性问题变成概率性问题。冻结测试里四个 trusted-native-IR 类全部达到 1.000 balanced accuracy，而 neural 分支存在明显迁移下降。

另一方面，G7 只存在于渲染像素中，结构 linter 按构造无法检测；语义问题也不能靠几何规则解决。因此没有一个单一模块在所有类别上都合适。

Hybrid design 的价值不是堆模块，而是根据可观测信息选择最小且可靠的检查器。

### 3. 你的 geometry oracle 会不会造成不公平？现实里哪来的 oracle？

它有两个角色，需要区分。

第一，在诊断实验里，oracle 是一种受控干预，用于区分视觉感知失败和后续推理失败。它不一定代表所有部署输入都拥有该信息。

第二，在目标部署场景——程序化生成 slide 的 agent——系统本身拥有元素位置、文本、样式和层级，所以 native IR 并不是额外人工标注，而是生成过程已经存在的数据。

我们也显式测试了没有 native IR 的 PDF/PNG 场景。用 layout parser 从像素恢复 box 后，recall 只有约 0.30–0.39，并且过分割严重，无法恢复原生 linter 的保证。所以论文明确把适用范围限制在 **IR-owning generation pipelines**。

### 4. 为什么 frozen evaluation 只有 0.826，而开发集有 0.957？是不是过拟合？

这正是我们严格区分两套数字的原因。

0.957 来自 template-held-out validation，但这批结果被查看并用于确定方法映射，所以它只能作为 development evidence。之后的 0.826 来自方法冻结后生成的 disjoint image arm，样本在 seed、ID、内容实例、路径和 image hash 上都与开发集无交集。

下降主要来自两点：

1. G7 的 neural transfer 从开发阶段的 0.937 降到冻结集的 0.567；
2. G1 和 S6 的 reference request 虽然被正确触发，但原始 executor 没有完成 reference → comparison → terminal verdict 的闭环，因此按 miss 计分。

所以 0.826 暴露了真实的迁移和系统集成边界。若只报告 0.957，反而会夸大系统效果。

### 5. 你的数据主要是合成缺陷，怎么证明结论能迁移到真实场景？

我们没有声称合成数据等同于自然缺陷，而是做了两层外部验证。

第一，在 26 个真实 CC-licensed PPTX deck 上直接修改原生 XML，构造 209 个 paired slides。真实背景、排版和内容都保留，只注入一个目标缺陷。粗粒度缺陷、margin perception bottleneck 和 fine-alignment failure 都在真实布局中重现。

第二，我们在第三方 image-only SlideAudit 上评估，没有使用自己的 IR。Atomic elicitation 对多个映射类别仍优于 whole-rubric prompt，但 symbolic linter 无法运行。

不过 real-layout 数据仍然是“真实布局上的受控注入”，不是自然发生缺陷的完整部署分布，因此论文把这一点列为 limitation，而没有声称完成了 full in-the-wild validation。

### 6. 你所谓的“感知失败”和“推理失败”真的能被实验严格区分吗？

不能把它解释成模型内部机制的严格因果分解。我们的定义是 operational attribution。

如果图像输入失败，但包含同一目标事实的 lossless structured oracle 成功，我们把它定义为 tested interface 下的 perception bottleneck。如果图像和 oracle 都失败，则说明仅改变输入表示不足以解决问题，但这并不能证明模型内部到底是 reasoning、attention 还是任务理解出了问题。

因此我们刻意使用“sub-perceptual under the tested protocol”“format-suppressed”和“reference-assisted”这些可观测、可复现实验定义，而不是声称定位了神经网络内部模块。

### 7. Balanced accuracy 为什么是主指标？为什么不用普通 accuracy 或 F1？

每个主要实验都使用 defective/clean paired design，因此我们同时关心 recall 和 clean specificity。Balanced accuracy 等于两者平均：

\[
\mathrm{BA}=\frac{\mathrm{Recall}+\mathrm{Specificity}}{2}.
\]

它可以避免 always-positive 或 always-negative 策略因为类别比例获得虚高分数。Precision 也单独报告，用来检查模型是否通过过度报警换 recall；coverage 的判定同时要求 BA 和 precision 不低于 0.70。

F1 不显式计入 true negative，在质检系统中会弱化 clean false alarm 的影响，因此不适合作为唯一主指标。

### 8. 为什么不训练一个 router 自动决定调用哪个工具？

我们早期考虑过 learned router，但最终没有把它作为论文贡献，原因有三个。

第一，研究问题是“失败归因能否指导方法选择”，手工冻结的 correspondence 更直接检验这个假设。

第二，类别数量和独立测试规模不足以支持一个具有可信泛化结论的 learned router。

第三，learned router 会把“诊断是否正确”和“router 是否训练好”混在一起，削弱可解释性。

因此最终系统使用确定性规则：如果谓词能由可信 IR 完整定义，就使用 linter；如果是 render-only 且 whole-rubric suppressed，就使用 atomic VLM；如果单张图证据不足，就请求 reference；语义类交给 neural examiner。

未来可以在更大规模部署日志上学习 router，但需要独立评估 calibration、abstention 和 domain shift。

### 9. G7 是不是为了让你的方法获胜而人为设计的特殊缺陷？

G7 确实是一个针对系统边界设计的 stress-test class，但不是任意构造。

它对应真实渲染系统中的常见问题：CSS-like layout、字体替换、unbreakable string、object-fit 或渲染器差异可能使像素越界，而声明 box 仍然合法。我们在 93 个 Zenodo10K deck 和 AutoPresent 样本中检查了类似 declared-legal/render-overflow 现象，说明它有现实基础。

更重要的是，我们没有只报告 G7。G1、G3、G6、S3、S6 等负结果都保留了；G1 还是 compute-control 的负控。G7 的作用是展示一个结构 linter 按构造不可见、但 render-aware inspection 必须处理的明确边界。

### 10. 如果让你重新做一次，最想改进什么？

我会优先改进三个方面。

第一，**在冻结前把 reference executor 做成真正的闭环状态机**，并为每个阶段定义 contract test。当前原始系统能请求 reference，却未必产生 terminal verdict，这是冻结评测下降的重要原因。

第二，**增加自然发生缺陷的人工标注部署集**。当前 real-layout 实验是受控注入，优点是有精确 ground truth，但不能完全覆盖自然缺陷的共现和分布。

第三，**做 deck/template-clustered uncertainty estimation**。目前每类区间是 component-wise Wilson-derived interval，没有对模板和 deck 的聚类相关性估计 system-level macro uncertainty。更完善的方案会使用 cluster bootstrap 或 hierarchical model。

如果资源允许，我还会加入 cost-sensitive routing，让系统在准确率、误报率和 API 成本之间给出可校准的 Pareto frontier。

---

## 四、可能被继续追问的短答

### 这个项目最难的地方是什么？

不是调用 VLM，而是**建立有效的因果对照**：保证 clean/defective pair 只差一个缺陷、确认缺陷在渲染后确实存在，并区分 IR 标签和实际像素。我们发现模板 snapping 会吸收 45% 的几何注入；如果不做 render-fidelity gate，实验会把“缺陷根本没渲染出来”误判成模型看不见。

### 你个人最有价值的工程贡献是什么？

建立端到端可复现链路：缺陷注入 → 渲染 fidelity 检查 → manifest 冻结 → 多模型调用 → schema normalization → paired statistics → Holm/BH correction → 论文表格和逐样本 release。

### 你个人最有价值的研究贡献是什么？

把笼统的“VLM 不行”拆成三种**对应不同干预措施**的 operational failure classes，并用负控和 compute-control 验证这种划分确实能指导工具选择。

### 项目有没有失败？

有。像素恢复结构没有恢复 linter；S3 即使给出文本 oracle 也不可靠；冻结 G7 发生明显迁移下降；原始 reference executor 没有闭环。这些失败最终帮助我们限定了系统的适用范围。

### 项目有没有真实业务价值？

适合接入拥有结构化生成状态的 slide agent：生成时即运行 linter，渲染后只对 linter 看不到的像素问题调用 VLM，从而降低 API 成本和误报，并输出可定位的修复证据。

---

## 五、面试表达注意事项

### 推荐说法

- “operationally identifies a perception bottleneck”
- “diagnosis-informed deterministic composition”
- “development validation 与 disjoint frozen evaluation 严格分开”
- “适用于 IR-owning generation pipelines”
- “结果排除了额外 sampling budget，但不声称识别了唯一内部机制”
- “负结果帮助界定部署边界”

### 避免说法

- 不要说“证明了模型其实看得见”；
- 不要说“0.957 是最终测试结果”；
- 不要说“我们解决了所有幻灯片质检问题”；
- 不要说“结构 oracle 可以从任何 PDF 无损恢复”；
- 不要说“pairwise/atomic prompt 总是更好”；
- 不要把 0.778 的三类 confirmation 描述成九类系统结果；
- 不要把 deterministic critic 说成 learned router。

### 结束项目介绍时的落点

> 这个项目让我形成的研究方法是：面对模型失败，不先堆更大的模型，而是先用受控干预判断失败发生在哪种信息条件下，再选择最简单、可验证的解决方案。
