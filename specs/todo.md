# Slide-Examiner TODO

状态快照: 2026-06-16
主参考: `specs/SPEC_slide_examiner_attribution.md`
接口参考: `specs/EXAMINER_IO_CONTRACT.md`

这份 TODO 是项目当前的执行清单。完成任务后要及时把 `[ ]` 改成 `[x]`；如果任务内容变了,也要同步更新这里,不要让 TODO 变成过期愿望清单。

## 0. TODO 维护规则

- [x] 建立项目级 TODO 文件: `specs/todo.md`。
- [x] 建立项目级记忆文件: `AGENTS.md`。
- [ ] 每次完成代码、实验、数据或文档任务后,同步更新本文件 checkbox。
- [ ] 如果中途发现任务拆分、合并、取消或优先级变化,同步改写本文件。
- [ ] 如果任务被阻塞,在对应条目后写清楚阻塞原因、日期和需要的外部资源。
- [ ] 不要只因为代码入口存在就勾选真实实验任务;必须有对应产物路径或结果文件。

## 1. 当前项目状态确认

- [x] 对照研究 spec 审查代码结构。
- [x] 确认当前仓库已有本地脚手架: IR、taxonomy、注入器、linter、probe、analysis、SFT、training plan、GEPA plan。
- [x] 跑通当前测试集: `88 passed`。
- [x] 明确当前边界: 本地契约和 mock/dry-run 流程已通,真实 VLM 推理、真实训练、真实 GEPA、人工 panel 尚未完成。
- [ ] 把 `docs/IMPLEMENTATION_STATUS.md` 更新成更口语化版本,区分“代码路径存在”和“真实实验已完成”。

## 2. 第一优先级: 接口和命名返修

目标: 在接真实模型和训练前,先把容易污染实验结果的接口缝补好。

- [x] 统一使用 `B_prime` 命名。
  - [x] 检查 `slide_examiner/adapters.py` 中的 `MODALITIES`。
  - [x] 检查 `slide_examiner/examiner_contract.py` 中的 `Modality.B_CAPTION_ONLY`。
  - [x] 检查 `slide_examiner/analysis.py` 中的 caption-oracle gap 统计。
  - [x] 检查 tests 中所有 modality 字符串。
  - [x] 选定稳定值 `B_prime`,并保证 manifest、probe records、analysis summary 中一致。

- [x] 统一 `DefectType` 的单一来源。
  - [x] 让 `taxonomy.py` 暴露 enum,让 `examiner_contract.py` import。
  - [x] 删除或减少重复硬编码,避免训练、serving、analysis 三处名字漂移。

- [x] 检查 page/deck scope 的全链路一致性。
  - [x] page 级只处理 G1-G6、S1、S4、S6。
  - [x] deck 级只处理 S2、S3、S5。
  - [x] S2/S3/S5 不再伪装成“第一页 page 样本”。

- [x] 检查运行时必须使用模态 C 的入口。
  - [x] runtime client 默认传图片 + 结构。
  - [x] 只有归因实验和训练采样才使用 A/B/B_prime。
  - [x] 文档里写清楚 runtime 和 attribution 的区别。

- [x] 补 parser 失败重试策略。
  - [x] 第一次解析失败时追加 “OUTPUT VALID JSON ONLY...” 重试。
  - [x] 最多重试 1-2 次。
  - [x] 仍失败时记录为 examiner failure,不要静默返回空结果。

- [x] 为接口返修补测试。
  - [x] modality 名称一致性测试。
  - [x] page/deck scope 拒绝错误缺陷类型的测试。
  - [x] parser 重试或失败记录测试。

## 3. 第二优先级: 训练数据契约补强

目标: 让训练样本真正符合 `EXAMINER_IO_CONTRACT.md`,避免 examiner 学偏。

- [ ] 实现训练采样中 A_IMAGE_ONLY >= 30%。
  - [ ] page 级样本至少 30% 只给图。
  - [ ] deck 级样本至少 30% 只给缩略图或页图序列。
  - [ ] B/C 样本比例可配置。
  - [ ] 导出时把实际 modality 写进 metadata。

- [ ] 让训练样本和运行时调用共用同一个 serializer。
  - [ ] pointwise page 使用 `build_page_messages`。
  - [ ] pointwise deck 使用 `build_deck_messages`。
  - [ ] pairwise 共用底层元素、render、image 序列化函数。
  - [ ] 不允许训练 prompt 和 runtime prompt 各写一套。

- [ ] 增加 evidence/fix_suggestion validator。
  - [ ] evidence 非空。
  - [ ] evidence 不能只复述缺陷名。
  - [ ] evidence 至少包含一个可见事实: 页号、元素、文本片段、术语、页面顺序或图文冲突点。
  - [ ] evidence 不包含 forbidden keys: `expected_*`、`defect_type`、`severity`、`repair_hint` 等。
  - [ ] fix_suggestion 非空且可执行。
  - [ ] 失败样本要重写或丢弃。

- [ ] 补 severity 三档映射测试。
  - [ ] G1 overflow: 4/8 minor,16/32 moderate,64 severe。
  - [ ] G2 IoU: 0.05 minor,0.1/0.2 moderate,0.4 severe。
  - [ ] G3 offset: 2/4 minor,8/16 moderate,32 severe。
  - [ ] G4 font delta: 1 minor,2/4 moderate,8 severe。
  - [ ] G5 delta E: 3 minor,6/12 moderate,24 severe。
  - [ ] G6 margin: 4/8 minor,16 moderate,32 severe。
  - [ ] S4 density 按超出比例定档。

- [ ] 让 SFT 导出产物能被 parser 逐条回读。
  - [ ] 导出 pointwise JSONL。
  - [ ] 导出 pairwise JSONL。
  - [ ] 对每条 assistant JSON 跑 `parse_page_result` / `parse_deck_result` / `PairwiseResult`。
  - [ ] 输出 parse failure 统计。

## 4. 第三优先级: 真实数据准备

目标: 从“玩具样本”进入能支持 Part 1 pilot 的真实 deck 数据。

- [ ] 建立数据目录约定。
  - [ ] `data/raw/` 放原始下载或脱敏文件。
  - [ ] `data/ir/` 放 Slide/Deck IR。
  - [ ] `data/manifests/` 放 manifest JSONL。
  - [ ] `runs/rendered/` 放渲染图片。
  - [ ] `runs/probe/` 放模型输出。
  - [ ] `reports/` 放分析报告。

- [ ] 接入 Zenodo10K / PPTAgent 数据。
  - [ ] 记录数据来源、下载命令和版本。
  - [ ] 清洗不可解析、损坏或空页 deck。
  - [ ] 抽取 clean slide/deck 候选。
  - [ ] 记录清洗统计。

- [ ] 接入 SlidesBench / PPTBench 评估数据。
  - [ ] 记录数据来源和版本。
  - [ ] 确认可用于迁移评估的任务子集。
  - [ ] 转成项目 IR 或建立适配器。

- [ ] 接入实习脱敏 deck。
  - [ ] 确认脱敏策略。
  - [ ] 移除客户名、敏感数字、内部项目名。
  - [ ] 记录可公开/不可公开边界。

- [ ] 建立真实问题 deck 人工标注计划。
  - [ ] 目标约 100 页。
  - [ ] 使用同一套 12 类缺陷 taxonomy。
  - [ ] severity 使用 minor/moderate/severe。
  - [ ] 至少双人抽样复核一部分标签。

## 5. 第四优先级: 真实渲染打通

目标: 保证图片、bbox、render spec 来自同一次渲染,否则 A/B 对比会失真。

- [ ] 安装并验证 Playwright 渲染。
  - [ ] 安装浏览器依赖。
  - [ ] 渲染一页 HTML slide 到 PNG。
  - [ ] 检查输出图片非空。
  - [ ] 检查图片尺寸和 `RenderSpec` 一致。

- [ ] 安装并验证 LibreOffice PPTX 渲染。
  - [ ] PPTX 转 PDF。
  - [ ] PDF 或页面图导出。
  - [ ] 检查多页 deck 顺序不乱。

- [ ] 实现或确认四个分辨率渲染。
  - [ ] 768 长边。
  - [ ] 1024 长边。
  - [ ] 1536 长边。
  - [ ] 2048 长边。
  - [ ] bbox 按相同 scale 转到像素坐标。

- [ ] 对渲染产物做质量检查。
  - [ ] 图片存在且可打开。
  - [ ] 文件大小合理。
  - [ ] bbox 没有明显全 0 或越界异常。
  - [ ] 文字元素和图片中位置基本一致。

- [ ] 将 `image_path` 和 `RenderSpec` 写入 manifest。
  - [ ] A/C 模态能够找到图片。
  - [ ] B/C 模态能够找到结构。
  - [ ] B_prime 模态能够找到 caption。

## 6. 第五优先级: Part 1 小规模 pilot

目标: 先用少量真实模型调用排雷,不要一上来烧完整矩阵。

- [ ] 选择 pilot 缺陷类型。
  - [ ] G1_TEXT_OVERFLOW。
  - [ ] G2_ELEMENT_OVERLAP。
  - [ ] S1_TITLE_BODY_MISMATCH。
  - [ ] 可选: S2_NARRATIVE_ORDER_BREAK。

- [ ] 为每类缺陷准备少量样本。
  - [ ] 每类至少 10-20 个样本。
  - [ ] 包含 clean negative。
  - [ ] 包含至少两个 severity 档位。
  - [ ] 包含 freeform 和 template metadata。

- [ ] 跑一个真实 VLM adapter。
  - [ ] 本地 Qwen3-VL 或 OpenAI-compatible API 二选一。
  - [ ] 跑 A、B、C。
  - [ ] 跑 B_prime。
  - [ ] 记录 parse failure rate。

- [ ] 分析 pilot 结果。
  - [ ] A vs B 是否出现感知 gap。
  - [ ] B vs B_prime 是否有 caption oracle 损失。
  - [ ] G 类和 S 类表现是否有差异。
  - [ ] 输出 `runs/probe/pilot_summary.json`。
  - [ ] 输出 `reports/pilot_slideprobe.md`。

- [ ] 根据 pilot 修改实验协议。
  - [ ] prompt 太长则压缩 serializer。
  - [ ] JSON 不稳定则加强 parser/retry。
  - [ ] 缺陷太容易或太难则调整 severity。
  - [ ] 图像尺寸不够则优先跑 resolution 消融。

## 7. 第六优先级: Part 1 全矩阵诊断

目标: 产出 H1 / H1-tpl / 心理物理曲线可报告结果。

- [ ] 冻结 Part 1 数据集。
  - [ ] 每缺陷 × 每 severity 至少达到 spec 目标或记录降级原因。
  - [ ] 留出 held-out severity。
  - [ ] 留出 1-2 个 held-out defect type。
  - [ ] clean negative 比例记录清楚。

- [ ] 冻结模型矩阵。
  - [ ] Qwen3-VL-4B。
  - [ ] Qwen3-VL-8B。
  - [ ] Qwen3-VL-32B dense 或可替代强模型。
  - [ ] Qwen3-VL-30B-A3B 或可替代强模型。
  - [ ] API 参考点。
  - [ ] 如果 27B 部署失败,记录失败原因和替代方案。

- [ ] 跑完整 attribution 矩阵。
  - [ ] A_IMAGE_ONLY。
  - [ ] B_STRUCT_ONLY。
  - [ ] B_prime caption oracle。
  - [ ] C_BOTH。
  - [ ] T1 检测。
  - [ ] T2 定位。
  - [ ] T3 修复建议。
  - [ ] k=3 seeds。

- [ ] 跑分辨率消融。
  - [ ] 768。
  - [ ] 1024。
  - [ ] 1536。
  - [ ] 2048。
  - [ ] 报告 G 组和 S 组对分辨率的敏感性差异。

- [ ] 跑模板维度实验。
  - [ ] freeform 条件。
  - [ ] template 条件。
  - [ ] G3-G6 是否被模板显著吸收。
  - [ ] G1/G2 和 S 组归因是否基本不变。

- [ ] 生成 Part 1 分析产物。
  - [ ] `runs/probe/full_matrix.jsonl`。
  - [ ] `runs/probe/summary.json`。
  - [ ] `reports/slideprobe.md`。
  - [ ] H1 gate 结果。
  - [ ] H1-tpl gate 结果。
  - [ ] 心理物理阈值表。
  - [ ] caption oracle gap 表。

- [ ] 做 Go/No-Go 判断。
  - [ ] 如果 H1 成立,进入 Part 2 训练。
  - [ ] 如果 H1 不成立,记录负结果并调整论文定位。
  - [ ] 如果 H1-tpl 不成立,模板坍缩降级为工程观察。

## 8. 第七优先级: Part 2 examiner 训练

目标: 训练一个专用 8B examiner,验证它是否能在几何类检查上超过更大 zero-shot 模型。

- [ ] 生成训练数据。
  - [ ] 20K-40K 合成样本。
  - [ ] 覆盖 G1-G6。
  - [ ] 覆盖 S1-S6。
  - [ ] negative >= 30%。
  - [ ] page/deck 都有 A-only 样本。
  - [ ] 标注 template/freeform 来源。

- [ ] 导出 SFT 数据。
  - [ ] pointwise JSONL。
  - [ ] pairwise JSONL。
  - [ ] LLaMA-Factory dataset_info。
  - [ ] parser 回读全部 target JSON。
  - [ ] 记录样本数、缺陷分布、modality 分布。

- [ ] 跑 QLoRA 训练。
  - [ ] 确认 GPU 环境。
  - [ ] 确认 Qwen3-VL-8B 权重路径。
  - [ ] 确认训练后 checkpoint 输出目录。
  - [ ] 记录训练命令。
  - [ ] 记录 loss 曲线或日志。

- [ ] 做 in-domain held-out 评估。
  - [ ] held-out severity。
  - [ ] held-out defect type。
  - [ ] precision、recall、F1。
  - [ ] 过报率。

- [ ] 做真实迁移评估。
  - [ ] 人工标注真实 deck。
  - [ ] VLM-SlideEval / PPTBench 可用子任务。
  - [ ] finetuned-8B vs zero-shot 8B。
  - [ ] finetuned-8B vs strong/API。
  - [ ] finetuned-8B vs linter。

- [ ] 生成 Part 2 报告。
  - [ ] G 组结果表。
  - [ ] S 组结果表。
  - [ ] 真实迁移结果表。
  - [ ] sim2real gap 讨论。

## 9. 第八优先级: Part 3 GEPA 下游效用

目标: 验证 examiner 质量是否能转化为 prompt 优化效率。

- [ ] 准备 GEPA 任务集。
  - [ ] train 10 decks。
  - [ ] val 10 decks。
  - [ ] test 10 decks。
  - [ ] 包含 SlidesBench 子集。
  - [ ] 包含实习场景任务包。

- [ ] 接真实 slide generator。
  - [ ] 场景识别 prompt。
  - [ ] 页面类型生成 prompt。
  - [ ] 组件库使用 prompt。
  - [ ] 质检 checklist prompt。
  - [ ] 结构化内容 JSON 到 HTML/PPTX 双渲染。

- [ ] 实现五个 GEPA feedback 条件。
  - [ ] 纯 linter。
  - [ ] zero-shot 8B。
  - [ ] zero-shot strong/API。
  - [ ] finetuned-8B。
  - [ ] hybrid: linter 做选择信号,finetuned-8B 做反思文本。

- [ ] 跑页面级预实验。
  - [ ] 小 rollout budget。
  - [ ] 估计方差。
  - [ ] 检查是否有明显 reward hacking。

- [ ] 跑 deck 级正式实验。
  - [ ] 每条件 rollout <= 200。
  - [ ] k=3 seeds。
  - [ ] 相同 GEPA 超参。
  - [ ] 相同 reflection 模型。

- [ ] 做终评。
  - [ ] 人工 3 名 panel。
  - [ ] 冻结 API judge。
  - [ ] 与训练反馈源不同源。
  - [ ] 汇总最终质量。
  - [ ] 汇总达到阈值所需 rollout 数。

- [ ] 做 hacking 审计。
  - [ ] overflow hidden。
  - [ ] hidden/tiny text。
  - [ ] off-canvas elements。
  - [ ] texture background。
  - [ ] covering overlays。
  - [ ] 人工抽查可疑样本。

- [ ] 生成 Part 3 报告。
  - [ ] 收敛曲线。
  - [ ] 最终质量表。
  - [ ] hacking 发生率。
  - [ ] examiner 内在质量与下游效率的相关性。

## 10. 写作与交付

- [ ] 更新 related work。
  - [ ] 明确切割 2512.21329。
  - [ ] 明确切割 VLM Judges ranking-scoring decoupling。
  - [ ] 明确切割 LED Benchmark。

- [ ] 写 Part 1 诊断章节。
  - [ ] 归因协议。
  - [ ] oracle 设计。
  - [ ] 模板坍缩实验。
  - [ ] 心理物理曲线。

- [ ] 写 Part 2 训练章节。
  - [ ] 合成缺陷训练。
  - [ ] pointwise/pairwise 输出。
  - [ ] in-domain 和真实迁移。

- [ ] 写 Part 3 下游章节。
  - [ ] feedback source 作为自变量。
  - [ ] hybrid 架构。
  - [ ] GEPA 收敛效率。
  - [ ] hacking 审计。

- [ ] 整理工程交付文档。
  - [ ] 如何生成数据。
  - [ ] 如何跑 probe。
  - [ ] 如何训练 examiner。
  - [ ] 如何跑 GEPA。
  - [ ] 哪些命令是真实执行,哪些仍是 dry-run。

- [ ] 整理开源资产。
  - [ ] SlideProbe 诊断集。
  - [ ] 缺陷注入器。
  - [ ] 分析脚本。
  - [ ] README 快速复现路径。

## 11. 近期建议执行顺序

建议先按这个顺序推进,不要直接跳到大规模实验:

- [x] 1. 修 `B_prime` 命名和 `DefectType` 单一来源。
- [ ] 2. 给 SFT 导出加 A>=30% 采样和 parser 回读。
- [ ] 3. 加 evidence validator。
- [ ] 4. 准备 2-3 类缺陷的 pilot manifest。
- [ ] 5. 打通真实渲染。
- [ ] 6. 跑一个真实 VLM 小 pilot。
- [ ] 7. 只有 pilot 稳定后,再扩大 Part 1 全矩阵。
