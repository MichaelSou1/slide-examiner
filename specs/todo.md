# Slide-Examiner TODO

状态快照: 2026-06-17
主参考: `specs/SPEC_slide_examiner_attribution.md`(Part 1 执行设计已按 pilot 实证固化为三轨,见 SPEC §3.0)
接口参考: `specs/EXAMINER_IO_CONTRACT.md`

> **Part 1 实证总纲(贯穿 §7–§10,与 SPEC §3.0 一致)**:G2–G6 细几何归 **linter**(VLM pointwise 几何不计分,跨 4B/8B/30B + 5 编码器家族全随机);S1/S4/S5 走 **examiner-pointwise A/B/B′/C 归因**(balanced accuracy + 配对 clean,B′=VLM 看图 caption);G1 溢出 / S6 / S3 走 **pairwise/2-AFC**(相对判断 >> 绝对打分)。主指标一律 balanced accuracy + 配对 clean,**严禁只看 recall**。

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
- [x] 跑通当前测试集: `126 passed`。
- [x] 明确当前边界: 本地契约 + 真实 VLM pilot/几何阈值/编码器对照/S 组/S6 forced-choice 已完成(见 §6/§7);真实训练(Part 2)、真实下游技能空间优化(SkillOpt/GEPA)、人工 panel 尚未完成。**注:Part 3(§9)非"代码已在、只差跑",而是 greenfield —— 真实 generator / SkillOpt 接入 / rollout 链路均未实现,仅有 GEPA dry-run 计划脚手架,见 §9 代码状态。**
- [x] 把 `docs/IMPLEMENTATION_STATUS.md` 更新成更口语化版本,区分“代码路径存在”和“真实实验已完成”。(已含全部 pilot 实证记录)

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

- [x] 实现训练采样中 A_IMAGE_ONLY >= 30%。
  - [x] page 级样本至少 30% 只给图。
  - [x] deck 级样本至少 30% 只给缩略图或页图序列。
  - [x] B/C 样本比例可配置。
  - [x] 导出时把实际 modality 写进 metadata。

- [x] 让训练样本和运行时调用共用同一个 serializer。
  - [x] pointwise page 使用 `build_page_messages`。
  - [x] pointwise deck 使用 `build_deck_messages`。
  - [x] pairwise 共用底层元素、render、image 序列化函数。
  - [x] 不允许训练 prompt 和 runtime prompt 各写一套。

- [x] 增加 evidence/fix_suggestion validator。
  - [x] evidence 非空。
  - [x] evidence 不能只复述缺陷名。
  - [x] evidence 至少包含一个可见事实: 页号、元素、文本片段、术语、页面顺序或图文冲突点。
  - [x] evidence 不包含 forbidden keys: `expected_*`、`defect_type`、`severity`、`repair_hint` 等。
  - [x] fix_suggestion 非空且可执行。
  - [x] 失败样本要重写或丢弃。

- [x] 补 severity 三档映射测试。
  - [x] G1 overflow: 4/8 minor,16/32 moderate,64 severe。
  - [x] G2 IoU: 0.05 minor,0.1/0.2 moderate,0.4 severe。
  - [x] G3 offset: 2/4 minor,8/16 moderate,32 severe。
  - [x] G4 font delta: 1 minor,2/4 moderate,8 severe。
  - [x] G5 delta E: 3 minor,6/12 moderate,24 severe。
  - [x] G6 margin: 4/8 minor,16 moderate,32 severe。
  - [x] S4 density 按超出比例定档。

- [x] 让 SFT 导出产物能被 parser 逐条回读。
  - [x] 导出 pointwise JSONL。
  - [x] 导出 pairwise JSONL。
  - [x] 对每条 assistant JSON 跑 `parse_page_result` / `parse_deck_result` / `PairwiseResult`。
  - [x] 输出 parse failure 统计。

## 4. 第三优先级: 真实数据准备

目标: 从“玩具样本”进入能支持 Part 1 pilot 的真实 deck 数据。

- [x] 建立数据目录约定。
  - [x] `data/raw/` 放原始下载或脱敏文件。
  - [x] `data/ir/` 放 Slide/Deck IR。
  - [x] `data/manifests/` 放 manifest JSONL。
  - [x] `runs/rendered/` 放渲染图片。
  - [x] `runs/probe/` 放模型输出。
  - [x] `reports/` 放分析报告。
  - [x] 写入 `data/README.md`、`.gitkeep` 和 `.gitignore`,避免真实语料误入库。

- [x] 建立真实数据准备命令和文档。
  - [x] 新增 `slide-examiner init-data-layout`。
  - [x] 新增 `slide-examiner prepare-clean-corpus`。
  - [x] 新增 `slide-examiner benchmark-plan`。
  - [x] 新增 `slide-examiner prepare-benchmark`。
  - [x] 写入人工执行指南: `docs/REAL_DATA_PREP.md`。
  - [x] 补数据准备单元测试: `tests/test_data_prep.py`。

- [ ] 接入 Zenodo10K / PPTAgent 数据。
  - [x] 记录公开入口和本地 manifest 覆盖机制: `slide_examiner/data_sources.py`, `docs/REAL_DATA_PREP.md`。
  - [x] 记录下载/镜像命令模板: `docs/REAL_DATA_PREP.md`。
  - [x] 实现清洗不可解析、损坏或空页 deck 的工具。
  - [x] 实现抽取 clean slide/deck 候选 manifest 的工具。
  - [x] 实现清洗统计输出: `reports/data_prep/*_cleaning_summary.json`。
  - [x] 下载 Zenodo10K/PPTAgent pilot 子集并记录固定版本/revision。
    - 2026-06-16: ModelScope 未找到 `Forceless/Zenodo10K`/`PPTAgent/Zenodo10K`;fallback 到 hf-mirror。
    - artifact: `reports/data_prep/source_acquisition.json`。
    - raw: `data/raw/zenodo10k_hfmirror_pilot/`,revision `e59bf3ec11f7518a6c84dc145d83c0675d412522`,50 个 PPTX。
  - [x] 产出 pilot 清洗统计 artifact。
    - artifact: `reports/data_prep/zenodo10k_hfmirror_pilot_cleaning_summary.json`。
    - result: scanned 50, accepted decks 2, accepted slide samples 4, manifest records 6。
  - [ ] 扩大 Zenodo10K/PPTAgent 下载规模,直到 clean 候选足够支持 Part 1 pilot。
    - 阻塞 2026-06-16: 当前磁盘剩余约 94GB;全量 10448 个 PPTX 可能超过本机余量,需外部存储或分批策略。

- [x] 接入 PPTBench Detection/Understanding 评估数据。
  - [x] 记录可用子集计划命令: `slide-examiner benchmark-plan`。
  - [x] 确认本轮只接入迁移评估必需子集: PPTBench detection/understanding。
  - [x] 联网搜索并排序 ModelScope/HF 候选数据集。
    - artifact: `reports/data_prep/dataset_search_2026-06-16.md`。
    - 结论: 本轮只下载 ModelScope `tyrionhuu/PPTBench-Detection` 和 `tyrionhuu/PPTBench-Understanding`;SlidesBench、Slides-Align、PPTBench generation/modification、Zenodo10K full 仅保留在搜索报告中,不进入当前执行清单。
  - [x] 建立任务 JSON/JSONL 适配器: `slide-examiner prepare-benchmark`。
  - [x] 下载 ModelScope PPTBench Detection/Understanding 真实任务数据,并记录固定版本/release。
    - 建议版本: Detection `bf3310bd011bd2a4b2316646efc260243f0b95a8`;Understanding `d26501d5fb9a7e0daf68b3331aa14b4f1b699592`。
    - artifact: `reports/data_prep/pptbench_modelscope_acquisition.json`。
    - raw: `data/raw/pptbench_detection_modelscope/` 和 `data/raw/pptbench_understanding_modelscope/`。
    - result: Detection 1200 examples, Understanding 1037 examples;本地 Arrow schema 已用 `pyarrow` 验证可读。
  - [x] 将 PPTBench Arrow 转成 `prepare-benchmark` 可读的 JSON/JSONL adapter input。
    - 新增命令: `python -m slide_examiner.cli convert-pptbench-arrow ...`。
    - artifacts: `data/raw/pptbench_detection_modelscope_adapter_input.jsonl`, `data/raw/pptbench_understanding_modelscope_adapter_input.jsonl`。
    - rendered inputs: `runs/rendered/pptbench_detection_modelscope/`, `runs/rendered/pptbench_understanding_modelscope/`。
    - result: image records 2237, structure parse failures 0。
  - [x] 产出真实 adapter summary。
    - artifact: `reports/data_prep/pptbench_adapter_summary.json`。
    - outputs: `data/manifests/pptbench_detection_tasks.jsonl`, `data/manifests/pptbench_understanding_tasks.jsonl`。
    - handoff: task records 已包含 `task.image_path` 和 `task.structure`,可接后续真实模型 probing / 渲染质量核查。

<!-- - [ ] 接入实习脱敏 deck。
  - [ ] 确认脱敏策略。
  - [ ] 移除客户名、敏感数字、内部项目名。
  - [ ] 记录可公开/不可公开边界。 -->

- [x] 建立真实问题 deck 人工标注计划。
  - [x] 目标约 100 页。
  - [x] 使用同一套 12 类缺陷 taxonomy。
  - [x] severity 使用 minor/moderate/severe。
  - [x] 至少双人抽样复核一部分标签。
  - [x] 计划写入 `docs/REAL_DATA_PREP.md`;真实标签 JSONL 和 summary 仍需后续人工采集后产出。

## 5. 第四优先级: 真实渲染打通

目标: 保证图片、bbox、render spec 来自同一次渲染,否则 A/B 对比会失真。

实现: `slide_examiner/render.py`(多分辨率 + RenderSpec + 质量检查 + PPTX 路径),
CLI `render-manifest --long-edge` / `render-resolutions` / `render-pptx`,
测试 `tests/test_render_wiring.py`。

- [x] 安装并验证 Playwright 渲染。
  - [x] 安装浏览器依赖。
    - slide-examiner conda 环境已装 playwright;bundled chromium 缺失时 `_launch_chromium` 回退系统 `google-chrome`(`/usr/bin/google-chrome`)。
  - [x] 渲染一页 HTML slide 到 PNG。
  - [x] 检查输出图片非空。
  - [x] 检查图片尺寸和 `RenderSpec` 一致。
    - `check_render_artifact` 的 `dims_match_spec` 校验;真实产物 768x432/1024x576/1536x864/2048x1152 全部一致。

- [x] 安装并验证 LibreOffice PPTX 渲染。
  - [x] PPTX 转 PDF。
    - `render_pptx_to_pdf`(`--invisible --nodefault --nolockcheck --nologo --norestore`);真实产物 `runs/rendered/pptx_pages/pilot_deck_*/*.pdf`。
  - [x] PDF 或页面图导出。
    - `render_pdf_to_pngs`(poppler `pdftoppm`)。
  - [x] 检查多页 deck 顺序不乱。
    - 6 页真实 deck(State of Infrastructure 2023):pdf_pages=6,rendered=6,页号连续 1-6。artifact: `reports/render/pptx_render_summary.json`。
    - 沙箱备注 2026-06-16: 本机 LibreOffice 为 AppImage;当前 Claude Code 沙箱里**经 Python subprocess 启动 soffice 会被静默 kill**(直接在 shell 跑正常),故 PDF 由 shell 直接生成、PNG 由 `render_pdf_to_pngs` 生成。生产环境无此限制;并新增 `SLIDE_EXAMINER_SOFFICE` 覆盖,可指向解包后的 `.../program/soffice`。

- [x] 实现或确认四个分辨率渲染。
  - [x] 768 长边。
  - [x] 1024 长边。
  - [x] 1536 长边。
  - [x] 2048 长边。
  - [x] bbox 按相同 scale 转到像素坐标。
    - `render_slide_multi_resolution` 用坐标缩放 HTML 做真实重渲染(2048 也清晰,非位图上采样);`build_render_spec` 记录 `scale_x/scale_y`,`bbox_to_pixels` 用同一 scale。
    - artifact: `runs/rendered/zenodo10k_pilot_resolutions/{768,1024,1536,2048}/`。

- [x] 对渲染产物做质量检查。
  - [x] 图片存在且可打开。
  - [x] 文件大小合理。
  - [x] bbox 没有明显全 0 或越界异常。
  - [x] 文字元素和图片中位置基本一致。
    - `check_render_artifact`(存在/可打开/字节数/dims/zero-area/out-of-bounds/text-has-ink);真实 pilot 6 records × 4 分辨率 = 24 张全部通过。
    - artifact: `reports/render/zenodo10k_pilot_resolution_quality.json`。

- [x] 将 `image_path` 和 `RenderSpec` 写入 manifest。
  - [x] A/C 模态能够找到图片。
  - [x] B/C 模态能够找到结构。
  - [x] B_prime 模态能够找到 caption。
    - `render_manifest` 写 `image_path` + `metadata.render`;round-trip 用 `request_from_sample` 验证 A=图、B=结构、C=图+结构、B_prime=caption(slide + deck 两类样本均通过)。
    - per-resolution manifest: `runs/rendered/zenodo10k_pilot_resolutions/<res>/manifest.jsonl`。

## 6. 第五优先级: Part 1 小规模 pilot

目标: 先用少量真实模型调用排雷,不要一上来烧完整矩阵。

完成快照 2026-06-16: 用 Qwen3-VL-4B(vLLM, GPU0)跑通 84 样本 × 4 模态 × 3 任务 = 1008 次真实调用。
- 数据: base deck `data/pilot/decks/`(`scripts/pilot_build_corpus.py`),manifest `data/pilot/manifest.jsonl` / 渲染后 `data/pilot/manifest_rendered.jsonl`(`scripts/pilot_subset.py`,1024 长边)。
- 驱动/分析: `scripts/run_pilot.py`、`scripts/pilot_report.py`。
- 产物: `runs/probe/pilot_probe.jsonl`、`runs/probe/pilot_summary.json`、`runs/probe/pilot_analysis.json`、`reports/pilot_slideprobe.md`。

全矩阵前 blocker 返修 + 8B 确认 pilot 2026-06-16(第三轮): 修完 4 个会污染全矩阵的硬问题,在 Qwen3-VL-8B(vLLM TP=2 @ GPU1,2)上确认。
- Blocker 1 B′:改用 VLM 看图生成 caption(`scripts/caption_images.py` + 契约 serializer 新增 `caption` 字段/B_prime 分支),不再是坐标 dump。B′ 现在忠实承载文本类信号(S1 标题被转写),但 captioner 自己看不见几何重叠 → B′ 不带 G 信号(合理)。
- Blocker 2 deck 多图:`render-manifest` 渲染 deck 全页 + 写 `page_image_paths`,契约 deck serializer 每页一图(实测 5 页 deck = 5 图)。但 S2 在 A/C 仍 0、B=10/12 → 模型仍无法从页面像素读叙事顺序,且图像把 C 拖到 B 以下(真实发现,非基建问题)。
- Blocker 3 模板:`slide_examiner/template.py` snap-to-master 真正吸收几何缺陷(肉眼核验 template G2 无重叠);H1-tpl 坍缩信号需要"能检出 freeform 几何"的模型才会出现。
- Blocker 4 serializer 对齐:probe 走 `build_messages_from_sample`(全矩阵同款路径),findings 格式,0% parse failure。
- 头条结论(4B→8B):G1/G2 在 8B 上**仍全 0**(几何阈值非 4B 独有);S1 图像感知被唤醒(A 0%→50%);S2 结构检出 B 58%→83%。几何仍归 linter。
- 产物:`runs/probe/pilot_probe.jsonl`(8B)、`runs/probe/pilot_summary.json`、`reports/pilot_slideprobe.md`(新增"Confirmation pilot"小节)。
- 单测:126 passed(新增 `tests/test_template.py`,改 deck 渲染测试)。

返修快照 2026-06-16(第二轮): 修复 G1/G2"注入不可见"后重跑。
- 改 `inject_text_overflow`:把缺陷框收窄到文字宽度,filler 真正溢出(单测仍过)。
- 改 `render.slide_to_html`:内容块渲染成可见卡片(`white-space:nowrap` + 半透明边框盒),溢出/重叠肉眼可辨(已逐张核验 θ=64 / IoU=0.4 渲染图)。
- 结论翻转:即便缺陷已清晰可见、且 B/C 的 oracle 直接给出 `rendered_text_width_px`,4B 仍 0 检出;自由描述探针(`scripts/pilot_geometry_diag.py`)确认它"看不见"中等档几何缺陷,但能认出极端档 → 这是**模型几何检测阈值过高**的真实发现(不是数据 bug),更坚实地支持"G 类归 linter"。诊断产物 `runs/pilot/sanity/{sanity_results,geometry_threshold}.json`。

- [x] 选择 pilot 缺陷类型。
  - [x] G1_TEXT_OVERFLOW。
  - [x] G2_ELEMENT_OVERLAP。
  - [x] S1_TITLE_BODY_MISMATCH。
  - [x] 可选: S2_NARRATIVE_ORDER_BREAK。(已纳入,deck 级)

- [x] 为每类缺陷准备少量样本。
  - [x] 每类至少 10-20 个样本。(G1=20, G2=16, S1=12, S2=12, neg=24)
  - [x] 包含 clean negative。(24 个,FP=0)
  - [x] 包含至少两个 severity 档位。(G1 5 档 / G2 4 档;S1/S2 注入器单档,符合其设计)
  - [x] 包含 freeform 和 template metadata。(注:当前 template/freeform 仅为元数据标签、底图相同,真正模板操纵需在全矩阵前接入,见报告 caveat)

- [x] 跑一个真实 VLM adapter。
  - [x] 本地 Qwen3-VL 或 OpenAI-compatible API 二选一。(Qwen3-VL-4B 本地 vLLM,OpenAI 兼容端点)
  - [x] 跑 A、B、C。
  - [x] 跑 B_prime。
  - [x] 记录 parse failure rate。(0/1008 = 0%)

- [x] 分析 pilot 结果。
  - [x] A vs B 是否出现感知 gap。(S1 B−A=+0.67, S2 B−A=+0.58,语义类感知瓶颈明显)
  - [x] B vs B_prime 是否有 caption oracle 损失。(B′ 全 0;扁平 caption 是死通道,B−B′ 损失最大)
  - [x] G 类和 S 类表现是否有差异。(G 类近乎不可检 G1 1/80、G2 0/64;S 类信号集中在结构通道)
  - [x] 输出 `runs/probe/pilot_summary.json`。
  - [x] 输出 `reports/pilot_slideprobe.md`。

- [x] 根据 pilot 修改实验协议。(协议调整清单写入 `reports/pilot_slideprobe.md`)
  - [x] prompt 太长则压缩 serializer。(已改为 scope+schema 感知 prompt;deck 级 C/A 需改走 `build_deck_messages` 多图)
  - [x] JSON 不稳定则加强 parser/retry。(0% parse failure,scope+schema prompt + 1 次 JSON retry 足够,暂不需语法约束解码)
  - [x] 缺陷太容易或太难则调整 severity。(已修:G1 收窄框真正溢出、渲染卡片化使 G1/G2 肉眼可辨;但 4B 仍 0 检出——根因是模型几何阈值过高,非数据,见返修快照)
  - [x] 图像尺寸不够则优先跑 resolution 消融。(本轮 1024 长边;G 类在结构/图像两通道都为 0,先解决"注入可见性"再做分辨率消融)

## 7. 第六优先级: Part 1 全矩阵诊断

目标: 产出 H1 / H1-tpl / 心理物理曲线可报告结果。

数据集扩充快照 2026-06-16: 扩到 12 个 base deck(`scripts/part1_build_corpus.py`),全 12 类缺陷 + 完整 severity 网格 + held-out severity(80)+ held-out defect(40: G4/S5)+ freeform/template,共 352 样本。
- 产物: `data/part1/decks/`、`data/part1/manifest.jsonl` / 渲染后 `data/part1/manifest_rendered.jsonl`、几何子集 `data/part1/manifest_geometry.jsonl`(288)。
- 构建脚本: `scripts/part1_build_dataset.py`。负样本 22.7%(略低于 30%,如需可调 negative_ratio)。

几何阈值跨尺寸确认 2026-06-16(4B / 8B / 30B-A3B-AWQ,几何子集 288 × A/B/C × T1,0% parse failure):
- **4B、8B 对 G1–G6 全部 0 检出**(图像/图像+结构两通道都为 0,即便缺陷清晰可见)。
- **阈值在 30B-A3B 才首次突破,且只对最粗的"文字溢出"G1**(A=20/40=50%);细几何(G3 对齐、G5 色差)即便 30B 仍 0,G2/G4/G6 在 1–2/32 噪声内。
- 结构 oracle **反而拖累**几何感知(30B G1:A=20/40 vs C=4/40);检出的溢出几乎不随 severity 分级;三个尺寸 0 误报。
- 结论:**G1–G6 归符号 linter** 得到跨尺寸强证据;VLM 顶多在最大模型上做"溢出"兜底交叉验证。报告 `reports/part1_geometry_threshold.md`,汇总 `runs/probe/part1_geometry_summary.json`,脚本 `scripts/part1_geometry_report.py`,原始 `runs/probe/part1_geom_{4b,8b,30b}.jsonl`。
- 部署备注:30B-A3B-AWQ(17G 权重)单卡 20G 放不下 KV,改 TP=2(GPU1,2)+ `--disable-custom-all-reduce` 跑通。

S 组 30B 验证 2026-06-16(S1–S6 + 40 负样本,A/B/B′/C × T1,B′ 用 30B 看图 caption,0% parse failure):**语义类是 examiner 的主场,与几何完全相反**。
- 30B 对 S 组检出 50–100%:S1 标题/正文 A=8/8(图像直读)、S5 缺段 ~88%、S4 密度 ~70%。
- **deck 级语义里自然语言 caption(B′)是最强通道**(deck-S B′=20/24=83%,C=11/24):S2 乱序 B′=8/8、S3 术语 B′ 最好 → 坐实 B′-via-VLM-caption 修复有效(几何里 B′ 是死通道,语义里 B′ 反而最强)。
- 多图堆叠(C)对 deck 语义反而最差(C<B′),与几何一致:堆 5 张页图分散注意力。
- S6 图文矛盾在原合成语料全 0(无图像元素,不可见)。负样本 FP:A=3/40,B/B′/C=0。
- 报告 `reports/part1_sgroup_30b.md`,汇总 `runs/probe/part1_sgroup_summary.json`,原始 `runs/probe/part1_sgroup_30b.jsonl`。

S6 补带图 deck 后重测 2026-06-16(`scripts/part1_image_corpus.py`:figure 元素画 ▲/▼ + claim;`diagram_claim/false_claim/trend` 从 oracle 剥离,只在像素里可见):**S6 现在真正可测,但结果是负结果**。
- 缺陷已真实可见(肉眼 + caption 都确认:绿色↑"revenue rose" vs 正文"revenue fell")——原 S6=0 是数据不可见的伪问题,已修。
- **但 30B 做不了 S6**:图像通道(A/C)对**每张**带图幻灯片都报矛盾——真 S6 24/24、一致的 clean 也 24/24 → precision 0.50、**balanced accuracy 0.50 = 纯随机**。100% "recall" 是无脑过报。
- 结构 B 精确但盲(0 FP / 3-24 recall,因 figure claim 被 oracle 剥离);B′ caption 仅略高于随机(bal_acc 0.58,15/24 FP)。
- **方法论警告**:S6 这类"一致性核查"缺陷必须用配对 clean 控制 + balanced accuracy/precision 评,**绝不能只看 recall**(只看 recall 会误报"100% 检出")。scope prompt 点名 S6 可能助长过报,公平的后续是 open-scope 或二选一强制选择评测。
- 报告 `reports/part1_s6_manifest.md`,汇总 `runs/probe/part1_s6_summary.json`,原始 `runs/probe/part1_s6_30b.jsonl`。

S6 二选一(2-AFC)强制选择复评 2026-06-16(`scripts/s6_forced_choice.py`,12 个同图 clean/S6 配对 × 双向序):**模型其实会做,只是不会"绝对判断"**。
- 把矛盾页和其一致 clean 页(同图、只正文不同)并排,问"哪一页有图文矛盾":**2-AFC 准确率 100%(24/24),双向序都对 12/12,pick 分布 {A:12,B:12} 无位置偏置**。
- 即 pointwise 随机(0.50)、forced-choice 满分(1.00):失败的是"孤立地给绝对 yes/no",不是感知。给了对比就完美区分。
- **协议建议**:S6(以及大概率 S3)这类一致性核查用契约已定义的 pairwise/forced-choice 臂(`PairwiseResult`)评,别用 pointwise —— 这是目前"相对判断优于绝对打分"最干净的证据。
- 产物:`runs/probe/part1_s6_forced_choice_30b.json`(+ 已并入 `reports/part1_s6_manifest.md`)。

视觉编码器全家桶对照 2026-06-17(假设:几何盲是 SigLIP/对比编码器的锅,换非 SigLIP 或原生分辨率应能破):**假设不成立**。
- 同 ~8–9B、同 288 几何样本、A/B/C/T1,**5 个编码器家族**,主指标 **balanced accuracy**(配对 clean,recall 会被过报骗):
  - Qwen3-VL-8B(SigLIP2):弃答(0 FP),bal-acc 0.50
  - Penguin-VL-8B(LLM-based 非对比):弃答(0 FP),0.50
  - InternVL3.5-8B(InternViT):**过报**(G1 recall 53% 但 FPR 54% → 0.49,纯随机)
  - Ovis2.5-9B(NaViT 原生分辨率):轻微过报(27/160 FP,12% 解析失败),0.49
  - Kimi-VL-A3B(MoonViT 原生分辨率):弃答(0 FP),0.50
  - (尺寸参照)Qwen3-VL-30B-A3B:G1 bal-acc ~0.65(A 单通道 0.75,0 FP)——唯一真破 G1 的
- 结论:**所有 8–9B 模型几何判别都在随机线**,差别只在 bias(弃答 vs 过报),不是感知。recall-only 会误判 InternVL"最好",配对 clean 一看就是过报。
- 真正的杠杆是**尺寸/LLM 推理**(只有 30B 真破 G1),不是编码器家族,**原生分辨率也没用**。
- 感知不是瓶颈、**几何推理才是**:文档专精 dots.ocr 把溢出标题逐字读出("…real XXXXX")并给出每个框坐标(像素/文字完全可读),却照样说不出"这段文字溢出了/这两个框重叠了"。
- **`G1–G6 归符号 linter` 现在是 Part 1 压力测试最充分的结论**:扛过尺寸扫(4B/8B/30B)+ 5 个编码器家族扫(SigLIP2/LLM-based/InternViT/NaViT/MoonViT)。文档/OCR 专精模型(dots.ocr、PaddleOCR-VL)是感知前端、不是 examiner(只 parse 不判缺陷),宜喂给 linter/reasoner 而非替代。
- 边界:1024px、pointwise、每家一个实例;更高分辨率 + forced-choice 未测。
- 产物:`reports/part1_encoder_geometry.md`、`runs/probe/part1_encoder_summary.json`、`runs/probe/part1_geom_{8b,penguin,internvl,ovis,kimi,30b}.jsonl`;脚本 `scripts/part1_encoder_report.py`、`penguin_geom_offline.py`、`penguin_sanity.py`。
- 部署:InternVL3.5-8B / Ovis2.5-9B / Kimi-VL-A3B 都在 **vllm-qwen(0.19)主线支持**(从 ModelScope 拉,`vllm serve` + OpenAI 端点直接用 run_pilot)。Penguin-VL 需专用 0.11 env + 离线 LLM(见上一条)。

分辨率 + forced-choice 复活实验 2026-06-17(只在最有信号的 G1/G3 上,24 对/缺陷,1536+2048,Qwen3-VL-8B 与 30B-A3B):**几何盲其实是两种不同的失败**。
- **G1 文字溢出 = 校准失败,forced-choice 完全复活**:pointwise 随机(8B 0.50 / 30B 0.65),2-AFC **100%**(48/48,pick 平衡 {A:24,B:24},双向序都对)——8B、30B、两分辨率全 100%。溢出一直能看见,只是给不出"绝对 yes/no"。→ **pairwise/forced-choice examiner 能做溢出**。
- **G3 对齐偏移 = 真·感知阈值,啥都救不了**:2-AFC **50% 且全选一边**(分不出两张图);1536/2048、8B/30B 全一样。2–32px 的位移就是在 VLM 感知阈值之下。
- **分辨率(1536 vs 2048)毫无差别**——不是像素预算问题。
- 结论(精炼 Part 1 分工):**细几何(对齐/字号/色差/小边距)归 linter(不可替代)**;**文字溢出可用 pairwise VLM 兜底**;**pointwise VLM 几何检测根本不该计分**。这跟 S6 一致:相对判断 >> 绝对打分。
- 产物:`reports/part1_resolution_forcedchoice.md`、`runs/probe/part1_fc_summary.json`、`runs/probe/fc_{8b,30b}_{G1,G3}_{1536,2048}.json`;脚本 `scripts/g13_fc_build.py`、`g13_forced_choice.py`、`g13_fc_report.py`;数据 `data/part1_fc/`。
- Penguin-VL-8B 部署配方(踩坑实录):hf-mirror 下载(ModelScope 无,`tencent-community/Penguin-VL-8B` 是社区镜像);专用 env `penguin-vl`(vllm==0.11.0,**transformers 降到 4.56.2**,vllm 默认拉的 5.x 删了 `all_special_tokens_extended`);插件补丁(`projector.py` 的 `TRANSFORMERS_CACHE` 回退、ViT 无 flash-attn 时回退 `TORCH_SDPA`、`tokenizer_class→Qwen2TokenizerFast`、`config.vision_encoder` 指向本地 `/home/gpus/models/Penguin-Encoder`);**插件 OpenAI HTTP server 与 pip vllm 0.11 漂移严重,改用离线 `LLM.chat`**(传 `chat_template_kwargs={"image_token":"<image>"}`);`HF_HUB_OFFLINE=1` + **从 /tmp 运行**(避开 triton 调 gcc 读 `./specs` 目录的老问题)。

**执行设计已按 pilot 实证固化为三轨(见 `specs/SPEC...md` §3.0)。原"所有缺陷×所有模态 pointwise 铺满"作废。**

全矩阵三轨完成快照 2026-06-17:数据集已冻结(sha256),三轨全跑通,三张主表 + 四道 gate + Go/No-Go=**GO**。产物索引见各条目;汇总 `reports/slideprobe.md` / `runs/probe/part1_gates.json`(`scripts/part1_synthesis.py`),126 passed。

- [x] 冻结 Part 1 数据集(**配对优先**)。`scripts/part1_freeze_dataset.py` → `reports/part1_dataset_freeze.md` / `runs/probe/part1_dataset_freeze.json`(sha256 锁定)。
  - [x] **每个正样本配一个同底图、仅缺陷不同的 clean 负样本**。page 级 328/352 配对;deck 级 S2/S3/S5 按 deck 粒度配对。
  - [x] 每缺陷 × 每 severity 达 spec 目标或记降级原因;clean negative 比例记录清楚。负样本 22.7%(<30%,记为降级)。
  - [x] 留出 held-out severity(`ood_severity`=80)+ held-out defect(`ood_defect`=G4/S5=40)。
  - [x] **带图 deck**(S6:`data/part1_img`)、**glossary 术语**(S3 deck 级 canonical/variant 已在 sgroup manifest);`template`=真实 snap-to-master(linter 实证吸收=1.0)。

- [x] 冻结模型矩阵(**跨尺寸即可,编码器扫已完成不再做**)。
  - [x] Qwen3-VL-4B(单卡 GPU0)/ 8B(TP=2)、30B-A3B-AWQ(TP=2,fp8 KV,enforce-eager)。三轨全部用此矩阵。
  - [x] 可选 API 参考点 ×1 —— 不做(本机跨尺寸已足够定阈值)。
  - [x] TP `--disable-custom-all-reduce` + 从 /tmp 启动避 gcc;8B BF16 单卡 20G 放不下(weights 16.6G)→ TP=2。
  - [x] (不做)编码器家族扫——已完成且为负结果,见 `reports/part1_encoder_geometry.md`。

- [x] 轨 L — G 组(G2–G6)由 **linter 主检测**。`scripts/part1_linter_track.py` → `reports/part1_linter_track.md` / `runs/probe/part1_linter_summary.json`。
  - [x] linter 跑全 G 组,产连续几何量(overflow_px/iou/offset_px/delta_pt/delta_e/bleed_px),作 ground truth 与上界。freeform recall G1/G4/G5/G6=1.0,G2/G3 仅受 linter 自身阈值地板限制,全 80 clean **0 FP**。
  - [x] VLM 对 G2–G6 只作稀疏交叉验证,**pointwise 不计入主结果**(只标"破/没破随机",见 Table 3)。

- [x] 轨 E — S 组语义(S1/S4/S5)pointwise A/B/B′/C 归因。`scripts/part1_sgroup_crosssize.py` → `reports/part1_sgroup_crosssize.md` / `runs/probe/part1_sgroup_crosssize_summary.json`。
  - [x] A/B/B′/C × T1。temperature=0 确定性输出,k=3 seeds 退化为单次(无随机性);T2/T3 暂不需要。
  - [x] **B′ = VLM 看图 caption**(跨尺寸固定用 30B caption,隔离"对固定 caption 的推理"与 caption 质量)。
  - [x] 主指标 **balanced accuracy**(配对 clean,含补齐的 deck-clean 负样本)。page 4B 0.50→8B 0.58→**30B 0.745**;deck 30B B′=0.639 强通道。

- [x] 轨 P — pairwise/2-AFC(**G1 溢出、S6 图文矛盾、S3 术语**)。
  - [x] `PairwiseResult`/forced-choice,配对 clean,双向序消位置偏置;报 2-AFC accuracy。G1/G3 见 `runs/probe/part1_fc_summary.json`,S6 `part1_s6_forced_choice_30b.json`,S3 `scripts/s3_forced_choice.py`→`part1_s3_forced_choice_30b.json`。
  - [x] 验证"相对优于绝对":G1 溢出 0.50→1.0 robust、S6 0.50→1.0;**S3 是诚实反例(62%、B 偏置、robust 2/8,未复活)**。
  - [x] **S3 决策:移出 VLM examiner**。B 结构通道已喂全文(两变体都在)但仍 0.56 → 瓶颈是 OCR-from-pixels + pointwise yes/no,不是推理。改走**文字抽取模块**(抽 deck 文字 → 术语-出现表 → 符号编辑距离聚类[干净变体] ∪ text-LLM[真实模糊漂移如 K8s/Kubernetes],免图像)。
  - [x] **模块已落地**:`slide_examiner/term_consistency.py`(`lint_deck` / `detect_terminology_inconsistency` / `build_term_occurrences`,支持 `--glossary`),CLI `slide-examiner lint-deck`,测试 `tests/test_term_consistency.py`(7 例)。冻结 S3 子集 head-to-head:**recall 1.00 / FP 0/40 / bal-acc 1.000**(对比 VLM 30B 最佳 0.69)。`scripts/part1_term_consistency_eval.py` → `reports/part1_term_consistency.md` / `runs/probe/part1_term_consistency_summary.json`。133 passed。

- [x] 分辨率消融(**收窄**):只测非地板 cell。`reports/part1_resolution_ablation.md`(+ `runs/probe/part1_s1_res_1536_30b.jsonl`)。结论"分辨率不是杠杆":G3 地板恒地板、G1/S1 天花板恒天花板(S1 1024→1536 bal-acc 0.96→0.97),1536≡2048。

- [x] 模板坍缩(**解耦**):(a) 吸收量由 **linter** 度量——snap-to-master 对 G1/G2/G3/G6 **吸收=1.0**、对 G4/G5 **不吸收**(并入 `part1_linter_track.md`);(b) "VLM 检出随模板下降"在 4B/8B 几何本就地板无从测,留 30B+overflow 可选观察。

- [x] 生成 Part 1 分析产物。
  - [x] `runs/probe/*` 原始 + `reports/slideprobe.md` 汇总(三轨骨架)。
  - [x] 三张主表:轨 E S 组通道画像(balanced acc)、轨 P 2-AFC 对照、轨 L linter 几何 + VLM 阈值。
  - [x] H1/H1-tpl/H-rel gate 结果(`runs/probe/part1_gates.json`):三者全 **SUPPORTED**(H-rel 带 S3 边界)。

- [x] 做 Go/No-Go 判断 → **GO to Part 2**。
  - [x] H-rel(相对优于绝对)+ S 组 examiner 有效(30B page 0.745)→ 进 Part 2(训 8B examiner,pointwise S1/S4/S5 + pairwise G1-overflow/S6 双输出,G 标签来自 linter,**S3 移出 examiner → 文字抽取+术语一致性模块**)。
  - [x] G 组结论(归 linter)已稳,直接写进 Part 2/3 的混合架构设计。

## 8. 第七优先级: Part 2 examiner 训练

目标(按 Part 1 实证修订,见 SPEC §4.3 实证修订):训练专用 8B examiner,主力放在 **S 组语义 + 一致性核查(pairwise)**;**几何不靠 pointwise 检测**——G1 溢出走 pairwise(zero-shot 8B forced-choice 已 100%,微调强化),G2–G6 标签来自 **linter** 喂入,examiner 学"复述/兜底/修复建议"而非"从像素重新检测"。验证点:能否在 S 组逼近/超过更大 zero-shot 模型,并把 overflow-pairwise 做到逼近 linter。

完成快照 2026-06-18:Part 2 全链路跑通(数据→渲染→SFT→QLoRA→eval→报告)。脚本 `scripts/part2_*.py`;配置 `configs/part2_qlora*.yaml`;报告 `reports/part2.md` / 汇总 `runs/probe/part2_summary.json`;wandb project `slide-examiner-part2`。**头条:finetuned 8B 在 S 组 pointwise(modality A)bal-acc ~0.99,胜过 zero-shot 8B(0.64)与 zero-shot 30B(0.785);几何在 image-only 下学会弃答(0 FPR,不从像素幻觉几何)。** 规模按用户决定取 ~5-8K(非 20-40K)。

- [x] 生成训练数据。(`scripts/part2_build_corpus.py`+`part2_build_dataset.py`+`part2_build_sft.py`;5304 样本 manifest / 2142 SFT records)
  - [ ] 20K-40K 合成样本。(**降级**:本轮按用户决定取 ~5-8K → 5304 manifest 样本 / 2142 训练 records;渲染 11568 PNG)
  - [x] G2–G6:标签来自 **linter**,examiner 学**复述(modality B)+ 弃答(modality A,不做 pixel-level 检测目标)**。
  - [x] G1 溢出 + S6:**pairwise/配对样本**(clean vs defective 同底图);**S3 移出 examiner → 术语一致性 linter**(承 Part 1 Go/No-Go)。
  - [x] S1/S4:pointwise 结构化批评(S5 作 held-out defect 留 OOD 评估,不进训练)。
  - [x] negative >= 30%(train 40.5% NO_DEFECT + 几何弃答负样本),**每正样本配对同底图 clean**;page/deck 都有 A-only。
  - [x] 标注 template/freeform 来源(template=真实 snap-to-master)。

- [x] 导出 SFT 数据。(`scripts/part2_build_sft.py` → `data/part2/sft/`)
  - [x] pointwise JSONL(S1/S4 + G 复述/弃答)。
  - [x] **pairwise JSONL(G1/S6;v1 序固定有位置偏置 → v2 已随机化 A/B,答案均衡)**。
  - [x] LLaMA-Factory dataset_info(`data/part2/sft/dataset_info.json`,sharegpt)。
  - [x] parser 回读全部 target JSON(**0 parse failures**)。
  - [x] 记录样本数/缺陷/modality/pointwise:pairwise 比例(`data/part2/sft/composition.json`)。

- [x] 跑 QLoRA 训练。(`configs/part2_qlora.yaml`,LLaMA-Factory `qwen3_vl_nothink`,4-bit rank16 2ep)
  - [x] 确认 GPU 环境。(单卡 GPU0 训练;TP 推理走 GPU1/2/3)
  - [x] 确认 Qwen3-VL-8B 权重路径。(`/home/gpus/models/Qwen3-VL-8B-Instruct`)
  - [x] checkpoint 输出目录。(`runs/part2/examiner_lora`,merged `runs/part2/examiner_merged`)
  - [x] 记录训练命令。(`runs/part2/train.log`;config 入库)
  - [x] 记录 loss 曲线。(wandb + `runs/part2/examiner_lora/training_eval_loss.png`;**eval_loss 0.099→0.018 单调降后平台,无过拟合/坍塌**)

- [x] 做 in-domain held-out 评估。(`scripts/part2_eval.py` + `part2_serve_and_eval.sh`)
  - [x] held-out severity。(`data/part2/manifest_eval_ood_severity_rendered.jsonl`,ft-8b 语义 C=0.917)
  - [x] held-out defect type。(G4/S5,`..._ood_defect_...`;G4 image-only 弃答 0 FPR)
  - [x] **balanced accuracy + precision/recall/F1(配对 clean);pairwise 报 2-AFC**。(`runs/probe/part2_eval/`)
  - [x] 过报率(FPR on 配对 clean)。(ft-8b geometry image-only FPR=0;语义 page FPR≈0)

- [ ] 做真实迁移评估。
  - [ ] 人工标注真实 deck + 带结构(模态 C)真实迁移。**已归入 §12(延后人工标注,非必要)**;image-only 第三方迁移用 SlideAudit 已完成(Table 5)。
  - [x] 真实公开数据迁移(替代 PPTBench)。PPTBench detection 实为属性 QA(字号差/最大元素 bbox/标题文本),**无缺陷 taxonomy 重叠**,不适合;改用 **SlideAudit**(arXiv 2508.03630,2400 真实人工标注 slide,19 维设计缺陷,经 kkgithub 镜像拉取——ModelScope/hf-mirror 均无、GitHub 直连被墙)。7 维映射到我方 taxonomy(G1-G6+S4),`scripts/slideaudit_fetch.py` + `part2_slideaudit_eval.py`,image-only 迁移评,见 `reports/part2.md` Table 5。**结论:真实 image-only 下几何全模型≈0.5(需 linter+结构);S4 仅 zero-shot 30B 有信号(0.70),ft 合成强项不迁移=sim2real gap**。
  - [x] finetuned-8B vs zero-shot 8B。(S 组 0.99 vs 0.64)
  - [x] finetuned-8B vs strong(zero-shot 30B)。(0.99 vs 0.785;**未接 API 强模型**)
  - [x] finetuned-8B vs linter。(几何:linter 主检测;ft 弃答/复述,见 Table 2)

- [x] 生成 Part 2 报告。(`reports/part2.md` / `runs/probe/part2_summary.json`,`scripts/part2_synthesis.py`)
  - [x] G 组表:linter vs ft(复述-B / 弃答-A);不报 pointwise G 检测。
  - [x] S 组表:pointwise channel 画像(balanced acc)+ G1/S6 pairwise 2-AFC。
  - [x] finetuned-8B vs zero-shot(8B/30B)vs linter;**pointwise vs pairwise** 对照(pairwise v1 位置偏置已记录,v2 修复)。
  - [x] 真实迁移结果表 + sim2real gap 讨论。(`reports/part2.md` Table 5 + "Real-data transfer reading":SlideAudit image-only;**人工标注 + 带结构的真实评估见 §12**)

- [x] **收尾返修(2026-06-18,指引 `specs/PART2_FINALIZE_GUIDE_for_CC.md`;不重训,权重冻结)**。
  - [x] **P1-1 统计严谨性**:`statistics.py` 加 Wilson CI / balanced-accuracy CI / two-proportion z(+测试);`part2_synthesis.py` 所有 bal-acc/2-AFC 单元格改为 `value [lo–hi] n=…`,n<10 标 †,headline 带 p 值。报告无裸点估计。
  - [x] **P2-1 deck S2/S5 配对 clean**:`part2_render_clean_decks.py` 渲染 192 个同底图 clean deck;`part2_eval.py` 加 `--deck-clean/--deck-only/--only-defects`;Table 1/4 deck 格回填真实 n/CI。
    - **诚实负例(记 issue,本轮不动)**:deck-scope 语义 pointwise 不成立 —— **ft-8b 在 S2 退化(recall 1.0/spec 0.0,恒报)**,根因是**训练集无 clean-deck 负样本**(84 条 deck 训练记录全是 S2 正样本,600 个 NO_DEFECT 均为 page 级);S5 为 held-out 故弃答;zero-shot 也过报(spec≈0.35,与 Part 1"pointwise 对一致性缺陷过报"一致)。**后续**:SFT 加 clean-deck 负样本 +/或 S2/S5 pairwise 头后重训。
  - [x] **P1-2 prompt 对称性**:zero-shot 在 ft trained format 重跑 → **崩到 ~0.50**(zs-30b 0.83 scoped→0.50 trained),证明 ft 优势非 prompt 偏好(`reports/part2.md` Table 6)。
  - [x] **P0-1/P0-2 reframe**:Table 5 改述为 out-of-design 下界、H2 落预登记 sim2real 分支;`docs/annotation_protocol.md` 写就;`panel.py` 加 inter-annotator agreement(κ)。人工标注全部归 §12。

## 9. 第八优先级: Part 3 下游效用(**轻量佐证,非重心**) — Examiner 质量 → 下游 slide 生成改进

> **降级 2026-06-19(本节以此 banner 为准,见 SPEC §5 降级 banner)**:本工作**重心是 VLM(N1 诊断 + N2 模板 + 注入缺陷训练的专用 examiner)**,**不是 skill 优化论文**。Part 3 仅为"examiner 越准→下游 deck 改得越好"的**轻量外在效用佐证**。
> - **载体降级为"self-refine 主佐证 + GEPA 旁证"**:① self-refine(examiner 作 agent 反思信号,generate→critique→revise;零外部依赖、最直接;按 EvoPresent 已占范式,标 baseline-style、不当 headline)= **主佐证(待建,见 P10)**;② GEPA skill-space(旁证,已真实跑通)。
> - **SkillOpt 移出主线、deferred**:上游 PyPI 包缺 prompt 资产、analyst 不真正调 optimizer(轨迹文件契约不符,0 calls;后端隔离测试本身可调通)、GitHub 不可达 → 忠实复现不可达。代码留 `slide_examiner/skillopt_adapter.py`,不进主线。"optimizer-agnostic" 降为"self-refine vs GEPA 两载体结论一致"的鲁棒性佐证。
> - P0–P9 的"SkillOpt 主/双载体"原措辞保留作历史,以本 banner 为准。

目标(降级 2026-06-19): 轻量验证 examiner 内在质量(Part 1/2 度量)是否转化为**下游生成改进**的效率与最终质量(self-refine 主 + GEPA 旁),并验证**可验证 linter 选择门 + 学习型 examiner 反思**的解耦反馈是否优于单源。**结论无论正负都不动摇 N1/N2 重心。**

> **新颖性范围(三交集,勿越界宣称)**: 贡献 = 把"verifier-质量→效率"原理从 RL/text **迁到 text-space skill 优化(SkillOpt/GEPA)× design 域**的交集 + 解耦可验证/学习反馈 + design 反作弊审计。**不得宣称"发现反馈质量重要"**(RL 域已有:Gao 2210.10760 gold-vs-proxy、PRIME 2602.11570 verifier-acc→RLVR policy R²≈0.92-0.94)。slide 生成是**测试床不是 claim**;`generate→critique→revise` self-refine 环(EvoPresent ICLR2026 已占)**仅作 baseline**。换载体(GEPA→SkillOpt 主)直接消除"应用 GEPA 无新意"风险。**PDF 核验记录(2026-06-18,papers 在 `docs/refs/`)**: SkillOpt 2605.23904 gate/reflection 解耦+beats GEPA 52/52 已核;Gao 2210.10760 gold-vs-proxy 协议可忠实移植(本工作 gold=确定性 linter,更紧);**GEPA 2507.19457 全文无 "feedback engineering",μ/μ_f 为固定输入——原 spec 该归因已更正**;AeSlides 2604.22840(GRPO 权重空间 + "VLM 不适合作 reward source")/ EvoPresent 2510.05571(GRPO critic + self-refine)/ Visual-SDPO 2606.10334(权重空间自蒸馏,覆盖 slides)/ VLM-SlideEval 2510.22045(eval-only)**四个近邻均为不同范畴,新颖性边界(skill-space × design-reward)经直接核验仍成立**。

> **代码状态(2026-06-18 核对;诚实标注 per §0 规则):本节绝大多数是 greenfield —— 不是"代码路径已在、只差跑实验",而是"真实链路尚未实现"。下面每条 `[ ]` 默认从零写,勿因 `gepa_runner` 存在就误判已接好。**
> - **现有 = 仅 dry-run 规划脚手架**:`slide_examiner/gepa_runner.py`(`GEPARunConfig` + `FEEDBACK_CONDITIONS` 五条件字符串表 + `build_gepa_condition_plan` + `run_gepa_experiment(dry_run=True)` 只回计划字典;**非 dry-run 路径直接 `raise RuntimeError("Install GEPA...")`,且依赖尚不存在的 `generator/linter_fn/examiner_fn`**)、`slide_examiner/gepa_eval.py`(`evaluate_hybrid_feedback`:hybrid 分数合成 + ASI 文本,**作用于已算好的分数,无 rollout**)、`tests/test_gepa_eval.py`。line 23 所列"GEPA plan"= 这些 dry-run 计划器。
> - **不存在(从零实现)**:① **真实 slide generator agent(被优化系统本体:4 prompt-skill 模块 + JSON→HTML/PPTX 双渲染)—— 最大缺口**;② SkillOpt 接入(microsoft/SkillOpt + adapter,主载体,全新);③ 真实 GEPA 链路(把 dry-run 接到真实 generator 的 rollout / metric);④ 任务集(SlidesBench 子集)接线;⑤ 任何 rollout 产物 / 报告(`runs/probe/part3*`、`reports/part3*` 均空)。
> - **换载体影响**:现有 GEPA dry-run 脚手架降为**次载体参考**(其真实路径本就未实现);**SkillOpt 主载体完全 greenfield**。

> **执行完成快照(2026-06-19,本会话)**: Part 3 **真实链路全部跑通**,产出真实 artifacts + H3 判定。
> - **被优化系统**: `generator.generate_deck`(brief→content JSON→IR,结构化,4 个可编辑 `PromptModules`)。
> - **真实 sweep 配置(`scripts/part3_faithful_sweep.sh`)**: generator + 冻结 reflection LLM = 在线 API `mimo-v2.5-pro`(reasoning 模型,`PART3_DISABLE_THINKING=1` 否则空 content),**对所有条件同一**;examiner 梯度用**真实 Part1/2 模型本地起服**(Qwen3-VL-8B / 30B-A3B / ft-8B),让 H3 横轴=实际 examiner。
> - **关键实证修正(本会话发现,详见 `docs/PART3_PREP.md` / `reports/part3_discussion.md`)**: 强 generator 在**漏题 brief**下即便空 skill 也拿 ~1.0 → skill-opt 无可优化(测得);故改 **vague brief**(rubric 仅入 metadata)+ **WEAK 种子** + **独立可验证 common-quality DV**(`part3_quality`:coverage/conciseness/terms/geometry,model-free;= SPEC §5.2 固定阈值 DV + Gao gold)。
> - **GEPA 真实 deck 级结果(4 条件 × 3 seeds;linter/zs8b/ft/hybrid)**: **rollouts→阈值不随 examiner 质量单调下降(corr=+0.563,反而略升;ft 因真去 mutate 付探索代价)→ H3 = design 域 feedback-transfer 反例(如实报告,合 SPEC §6 证伪分支)**。机制:强 generator 把任务地板抬到近阈值 + 饱和 proxy(linter 几何/zs8b 宽松均≈1.0→GEPA 不 mutate→"靠不探索"平凡收敛)。
> - **诚实降级(本机算力/时间约束)**: zero_shot_30b(第 5 档)与 SkillOpt 第二载体(optimizer-agnostic 臂)**因 30B+逐页 examiner 调用极慢而延后**;主结论(反例)在 4 条件下已稳健。每条件 ≤12 rollouts(非 200;API 延迟)。examiner 走 modality B(结构,`--no-render`,省磁盘)。
> - 产物: `runs/probe/part3/{main,pilot_main}.jsonl`、`runs/part3/best_skill_deck_A/`、`reports/part3{,_pilot,_hacking,_discussion}.md`、`runs/probe/part3/{summary,feedback_iv,hacking,final_eval}.json`;**165 单测通过**(+7 `tests/test_part3_quality.py`)。详见记忆 `part3-impl-and-serving`。

**实现路线图(P0→P9,按依赖排序;greenfield,每条标了复用 vs 新建 + 产物路径,产物未落不得勾选 per §0)。关键路径:P1 generator → P2 反馈接口 → P4 优化器载体 → P5 占位。P3 任务集可与 P1/P2 并行。**

- [x] **P0 — 脚手架与复用盘点(便宜,先做)**。
  - [x] 建 `data/part3/`、`runs/probe/part3/`、`runs/part3/`、`reports/` 子约定 + `.gitignore` 防真实语料/大产物入库。
  - [x] 盘点可复用资产写进 `docs/PART3_PREP.md`:`render.py`(双渲染)、geometry linter、`term_consistency.py`(S3)、ft-8B examiner(`runs/part2/examiner_merged`)、contract serializer、vLLM serving(Part1/2 配方,见记忆 `vllm-serving-gotchas`)、`gepa_eval.evaluate_hybrid_feedback`、`gepa_runner`(dry-run 桩)。**+ `docs/PART3_RUNBOOK.md`(real vs dry-run 命令图)。**
  - [x] 定 best_skill / skill-doc 文本格式(SkillOpt 与 GEPA 共用同一可 add/delete/replace 的 skill 工件)。`slide_examiner/skill_doc.py`。

- [x] **P1 — 被优化系统(slide generator agent)本体(最大缺口,核心前置)**。`slide_examiner/generator.py` + `scripts/part3_generator_smoke.py`。
  - [x] 定义 task brief → 结构化内容 JSON(贴 Slide/Deck IR)的输入/输出 schema。
  - [x] 实现 4 组**可编辑** prompt/skill 模块:场景识别 / 页面类型生成指令 / 组件库使用说明 / 质检 checklist(每个模块文本即优化器编辑对象)。
  - [x] generator 调用链:task →(4 模块)→ 内容 JSON → render(`--no-render` 时结构-only;`render.py` 双渲染可用)→ 渲染图 + 结构。
  - [x] 最小端到端 smoke:1 task → 结构、无崩溃。
  - [x] 单测:generator wiring + round-trip(`tests/test_part3_generator.py`)。

- [x] **P2 — 评分/反馈接口(选择信号 vs 反思信号 解耦)**。`slide_examiner/feedback_sources.py`。
  - [x] 定义 `FeedbackSource` 抽象:渲染产物 → `(selection_score∈[0,1], reflection_text)`。
  - [x] 实现 5 档反馈源(**自变量 = 反馈源质量**,内在质量已由 Part1/2 度量,IV 登进 `feedback_iv.json`):
    - [x] linter-only(可验证几何/术语违规归一 → selection;reflection = 违规列表)。
    - [x] zero-shot 8B(本地 vLLM Qwen3-VL-8B)。
    - [x] zero-shot 30B(本地 vLLM 30B-A3B;**真实 sweep 延后,见快照**)。
    - [x] finetuned-8B(`runs/part2/examiner_merged`)。
    - [x] hybrid 解耦:linter 作 selection 门 + ft-8B 文本批评作 reflection ASI。
  - [x] 单测:每档返回合法 `(score, text)`(`tests/test_feedback_sources.py`)。

- [x] **P3 — 任务集 train/val/test(deck 级,split 固定;可与 P1/P2 并行)**。`scripts/part3_build_tasks.py`。
  - [x] SlidesBench 不可达(GitHub 墙)→ 用 in-house scenario pack(记录在 freeze 与 `reports/data_prep/part3_optimizer_install.json`)。
  - [x] 切 train 10 / val 10 / test 10,固定 `split_seed`;**test 锁到最终报告才用**。优化用小子集 `tasks_opt`(train6/val4)控 API 延迟。
  - [x] 每 task:**vague brief**(rubric 仅入 metadata 防漏题)+ 评测 rubric;产物 `data/part3/tasks/{train,val,test}.jsonl` + freeze(sha256)。
<!--  - [ ] 含实习场景任务包。 -->

- [x] **P4 — 下游载体(GEPA 旁证真实跑通;SkillOpt 移出主线 deferred;self-refine 主佐证见 P10)**。
  - [x] **SkillOpt:移出主线、deferred(降级 2026-06-19)**。`slide_examiner/skillopt_adapter.py` 保留(`EnvAdapter`+`ReflACTTrainer`,offline 单测过),但**上游包缺 prompt 资产 + analyst 不真正调 optimizer(0 calls,后端隔离可调通)+ GitHub 不可达 → 忠实复现不可达**。不进主线;optimizer-agnostic 改用 self-refine vs GEPA。
  - [x] GEPA:`gepa_runner` 非 dry-run 路径接真实 generator + `FeedbackSource`(metric=`selection_score`,feedback=`reflection_text`);桩已删。
  - [x] 两载体共用同一 generator / 任务集 / 评分管线,**唯一变量 = FeedbackSource**(`OptimizerRunConfig.control_signature`)。
  - [x] 真实最小 run:GEPA 真实优化(非 dry-run)在 deck 级 4 条件 × 3 seeds 全跑通(skill 真被 mutate、score/gold 真回读)。
  - [x] 单测:adapter 注入/回读 + 跨载体配置一致性(`tests/test_part3_optimizers.py`)。

- [x] **P5 — 页面级预实验(占位里程碑)**。`scripts/part3_pilot.py`。
  - [x] 5 档(GEPA 载体)小 budget(页面级);产物 `pilot_main.jsonl`。
  - [x] 估计方差 → 定 deck 级预算。**注:页面级(2 页)结构上达不到 deck rubric(coverage≤0.6)→ 用降低阈值 q=0.55 估方差;deck 级才是主结果。**
  - [x] reward-hacking 初探针(并入 P7 审计)。
  - [x] 产物:`reports/part3_pilot.md` / `runs/probe/part3/pilot_summary.json`。

- [x] **P6 — deck 级正式实验**。`scripts/part3_run.py` + `scripts/part3_faithful_sweep.sh`。
  - [x] GEPA 载体 × 4 条件(linter/zs8b/ft/hybrid)× k=3 seeds。**降级:每条件 ≤12 rollouts(非 200,API 延迟);zs30b 第 5 档 + SkillOpt 第二载体延后(见快照)。**
  - [x] 相同优化器超参 + 冻结 reflection/optimizer LLM(隔离单一自变量;generator+reflection = mimo-v2.5-pro API 同一)。
  - [x] 记录收敛曲线(达固定 common-quality 阈值所需 rollout 数)+ 每条件 best_skill。
  - [x] 产物:`runs/probe/part3/main.jsonl` + `runs/part3/best_skill_deck_A/<condition>__gepa__seed<k>.md`。

- [x] **P7 — gold-vs-proxy reward-hacking 审计(移植 Gao 2210.10760 到 design)**。`scripts/part3_hacking_audit.py`。
  - [x] held-out **可验证 common-quality 作 gold**(`part3_quality.gold_quality`,model-free;+ 严格几何 gold);对每条件最优 skill 产物比 proxy vs gold。
  - [x] AeSlides 式作弊清单逐项:隐藏/极小文字、越界元素、覆盖层、退化空页(+ 超大字号)。
  - [x] 按条件比较:**0 作弊(全条件全项=0)**;proxy(1.0)−gold(~0.69-0.71)gap 存在但为**泛化 gap 非 hack**(linter gap 最小);**人工抽查归 §12**。
  - [x] 产物:`reports/part3_hacking.md` / `runs/probe/part3/hacking.json`。

- [x] **P8 — 终评(防 Goodhart,不同源)**。
  - [x] 冻结 API judge 自动臂(mimo,与 examiner 不同源)汇总 held-out test 最终质量(linter 0.75/zs8b 0.82/ft 0.72/hybrid 0.80,**与 examiner 质量无单调关系**,合反例);+ held-out 可验证 gold(P7)作第二自动臂。`runs/probe/part3/final_eval.json`。
  - [x] 不同源**人工 3 人 panel**:**归入 §12(延后人工标注,非必要)**;`panel.py` κ 聚合已就绪,自动臂占位。

- [x] **P9 — Part 3 报告 + H3 判定**。`scripts/part3_synthesis.py` → `reports/part3.md`(+ `reports/part3_discussion.md`)/ `runs/probe/part3/summary.json`。
  - [x] 收敛曲线(examiner 质量 × GEPA 载体)。
  - [x] 最终质量表 + hacking 发生率(P7/P8 自动臂)。
  - [x] **examiner 内在质量 ↔ 下游效率相关性(design 域首条曲线)—— 核心结果:corr=+0.563(非负→不单调)。**
  - [x] 载体一致性(robustness):**self-refine vs GEPA 两载体方向相反但可调和**(见 P10 + `reports/part3.md §3`):GEPA 的效率 DV 因 proxy 饱和 + running-best 伪迹给出反例(+0.563);self-refine 直接编辑 DV 去掉两个混淆后**恢复期望正向**(+0.659 / best_gain +0.558),两者在"强 generator 地板→headroom 小"机制上一致。替代原 SkillOpt 双载体。
  - [x] **H3 gate 判定**(SPEC §6):**反例** —— 收敛 rollout 数不随 examiner 质量单调下降(强 generator 地板 + proxy 饱和),混合 ≥ 任一单源成立但整体证伪 → 如实报 design 域 feedback-transfer 反例(SPEC 预登记分支,仍有价值)。

- [x] **P10 — self-refine 轻量载体(降级后的主佐证)。代码 + full 梯度 run + 并入报告均完成(2026-06-20)**。
  - [x] 循环:deck=generate → 批评=examiner.score → deck=generate(prompt+批评) → 重复 N 轮。`slide_examiner/self_refine.py`(`run_self_refine`/`refinement_summary`)+ `scripts/part3_self_refine.py`;**零外部依赖、不碰 SkillOpt**;复用 `generate_deck`(加了 `revise` 参数)/`FeedbackSource`/`part3_quality`。单测 `tests/test_part3_self_refine.py`(2 例)。
  - [x] **live 验证(linter,API gen,无 GPU)**:循环跑通,gain≈0(linter 几何批评对 coverage 无可操作信息→平,符合预期下界)。
  - [x] **full 5 档 × 3 seeds × 3 tasks = 45 run**(2-phase 起服 8B@8108 + ft@8101 → linter/zs8b/ft/hybrid;再 30B@8130 → zs30b;`scripts/part3_self_refine_sweep.sh`)。**结果:`examiner_quality_vs_gain_corr=+0.659`、`best_gain corr=+0.558`、`final corr=-0.147`** —— 方向为正(期望号),但幅度极小(gain 0.4%–1.9%,强 generator 地板);仅 zs30b/hybrid 两个强语义 examiner 偶尔把欠阈 deck 顶过 0.85(11%),linter/zs8b/ft 从不(0%)。聚合加了鲁棒的 `mean_best_gain`/`frac_improved`(final−initial 受 iter-2 回退噪声影响)。
  - [x] 产物:`runs/probe/part3/self_refine{,_summary}.json` + `self_refine.jsonl`(45 records);已并入 `reports/part3.md §1`(主佐证),**如实标 baseline-style(EvoPresent 已占),非 headline**;GEPA 降为 §2 旁证 + §3 调和。

- [x] **P11 — 真实 Hermes agent case-study(外部效度臂,2026-06-20)**。用户指出 toy 任务太软 → 在**真实 Hermes 售前 PPT agent**(其 `powerpoint` Agent Skill)产出的真实 deck(`SYC盛原成_智能制造售前方案.pptx`,16 页)上跑同一 examiner 梯度。
  - [x] 渲染:AppImage soffice 在 harness 里 hang(FUSE);改用 `unsquashfs -o 193728` 解包后的 ELF 直接渲染(`scripts/render_pptx_extracted.sh`)→ pdf → pdftoppm。
  - [x] `slide_examiner/pptx_ingest.py`(pptx→Deck IR + `placeholder_stats` 可验证 DV)+ `scripts/part3_hermes_case.py`(5 档检测探针)+ `scripts/part3_hermes_case_sweep.sh`(2-phase 起服)。单测 `tests/test_pptx_ingest.py`。
  - [x] **可验证缺陷 = 未填模板占位符(添加标题/添加内文)20 个 / 7 页**(几何 linter 结构上看不见)。**检测结果**:zs30b 最强(recall 1.0、显式点名 4/7、占位页打分 0.03 vs 干净 0.64);**ft(Part2 内在质量第一,q=1.0)对这个 OOD 缺陷反而最弱(显式点名 0/7、区分度最小)** —— 排序按通用 VLM 能力而非 Part2 内在质量,**佐证"ft 学到的是缺陷分布而非普适质量"的 VLM 论点**。linter 0.86"recall"是几何噪声假象(0 点名 + 44% 假阳)。
  - [x] **examiner-critique→修订一轮**:`scripts/part3_hermes_revise.py` 用 **mimo-v2.5-pro(Hermes 自配生成器,非 qwen,按用户要求)** 填占位符 → 重渲 → **20→0 占位符**(填 25 个 shape,内容连贯切题)。
  - [x] 产物:`runs/probe/part3/hermes_case.json` + `hermes_revise.json` + `data/part3/hermes_case/{slides,revised}/`;并入 `reports/part3.md §6`(case-study/外部效度,非受控梯度)。

## 10. 写作与交付

- [ ] 更新 related work  （联网调研，截止至2026.6.18）。
  - [ ] 明确切割 2512.21329。
  - [ ] 明确切割 VLM Judges ranking-scoring decoupling。
  - [ ] 明确切割 LED Benchmark。
  - [ ] 明确切割 SkillOpt(2605.23904): 引为 skills-as-trainable-state 相关工作(gate/optimizer 解耦框架)。**注:已从下游载体移出主线(降级 2026-06-19,上游包不可用);本工作非 skill 优化论文,Part 3 用 self-refine 主 + GEPA 旁。**
  - [ ] 明确切割 Gao 2210.10760(基础 gold-vs-proxy 过优化)+ PRIME 2602.11570(R²≈0.92-0.94 verifier→policy,数学)+ BoN/RLHF 强度差异(RewardBench2 2506.01937 r≈0.87 vs 2410.05584 弱相关): 反馈质量→效率 在 RL/text 已证;本工作贡献是迁到 skill-space × design,非重新发现。
  - [ ] 明确切割 AeSlides(2604.22840) / EvoPresent-PresAesth(2510.05571): RL-slides + self-refine 已占;本工作落在 skill-space measurement,self-refine 仅作 baseline。AeSlides "VLM 打分 prone to reward hacking" + VLM-SlideEval(2510.22045) "calibrated selection gates" 反引为背书。

- [ ] 写 Part 1 诊断章节(按实证三轨叙事)。
  - [ ] 三轨归因协议(linter / examiner-pointwise / pairwise)+ balanced accuracy + 配对 clean 方法学。
  - [ ] oracle 设计(B′=VLM 看图 caption;deck 按通道画像,C 多图未必最好)。
  - [ ] **几何盲两机制**:校准失败(G1 溢出,forced-choice 复活)vs 感知阈值(G3–G6,啥都救不了)。
  - [ ] **编码器/分辨率负结果**:5 编码器家族 + 1536/2048 都不破几何 → 杠杆是尺寸/推理。
  - [ ] **H-rel(相对优于绝对)**:G1 + S6 两组独立证据。
  - [ ] 心理物理曲线**画在 linter 连续几何量上**;VLM 端只标"破/没破随机"。
  - [ ] 模板坍缩:linter 度量吸收量(与模型解耦)。

- [ ] 写 Part 2 训练章节。
  - [ ] 合成缺陷训练。
  - [ ] pointwise/pairwise 输出。
  - [ ] in-domain 和真实迁移。

- [ ] 写 Part 3 下游章节(**轻量,1 节;非论文重心,见降级 banner**)。
  - [ ] 定位:examiner 内在质量 → 下游 slide 生成改进的外在效用佐证;**明确不宣称"发现反馈质量重要"、也不是 skill 优化论文**。
  - [ ] feedback source 质量作为受控自变量(generator/反思 LLM 冻结)。
  - [ ] hybrid 解耦架构(可验证 linter 选择门 + 学习 examiner 反思)。
  - [ ] 载体:**self-refine(主佐证,标 baseline-style)+ GEPA skill-space(旁证)**;两载体一致性。**SkillOpt 移出主线,如实记上游包不可用。**
  - [ ] gold-vs-proxy reward-hacking 审计(0 作弊;proxy-gold gap=泛化 gap)。
  - [ ] 诚实记 GEPA 旁证的 design 域 feedback-transfer 反例(corr=+0.563;强 generator 地板 + proxy 饱和)。

- [ ] 整理工程交付文档。
  - [ ] 如何生成数据。
  - [ ] 如何跑 probe。
  - [ ] 如何训练 examiner。
  - [ ] 如何跑下游佐证(self-refine 主 + GEPA 旁;SkillOpt 移出主线/deferred)。
  - [ ] 哪些命令是真实执行,哪些仍是 dry-run。

- [ ] 整理开源资产。
  - [ ] SlideProbe 诊断集。
  - [ ] 缺陷注入器。
  - [ ] 分析脚本。
  - [x] 大模型 API 配置示例: `.env.example`(仅 API 路由,不含本机路径/密钥)。
  - [ ] README 快速复现路径。

## 11. 近期建议执行顺序

建议先按这个顺序推进,不要直接跳到大规模实验:

- [x] 1. 修 `B_prime` 命名和 `DefectType` 单一来源。
- [x] 2. 给 SFT 导出加 A>=30% 采样和 parser 回读。(见 §3)
- [x] 3. 加 evidence validator。(见 §3)
- [x] 4. 准备 2-3 类缺陷的 pilot manifest。(见 §6 pilot)
- [x] 5. 打通真实渲染。
- [x] 6. 跑一个真实 VLM 小 pilot。(Qwen3-VL-4B/8B/30B + 编码器对照,见 §6/§7 与 `reports/`)
- [x] 7. pilot 稳定后把全矩阵**重设计成三轨**(见 §7 与 SPEC §3.0),放弃 pointwise 铺满。
- [x] 8. 按三轨**冻结数据集(配对优先)+ 跑全矩阵**,产出 Part 1 三张主表。(2026-06-17,Go/No-Go=GO;见 §7 完成快照)
- [x] 9. H-rel + S 组 examiner 成立 → 进 Part 2(8B examiner,pointwise+pairwise 双输出,G 标签来自 linter)。(2026-06-18 完成:见 §8 完成快照与 `reports/part2.md`;头条 finetuned 8B S 组 0.99 > zero-shot 30B 0.785)
- [x] 10. Part 2 完成 → **Part 3 下游效用真实跑通**(§9 完成快照 2026-06-19)。真实 generator + 5 档反馈源(faithful 本地 examiner) + GEPA 真实优化 + common-quality DV + gold-vs-proxy 审计 + 自动臂终评。**核心结果 = H3 design 域 feedback-transfer 反例**(收敛 rollout 不随 examiner 质量单调下降,corr=+0.563;强 generator 地板 + proxy 饱和;0 reward-hacking)。**诚实降级**:zero_shot_30b 第 5 档 + SkillOpt 第二载体(optimizer-agnostic 臂)延后(算力/时间),反例在 4 条件下稳健。新颖性限定"交集迁移 + 解耦反馈",未宣称"发现反馈质量重要"。详见 §9 与 `reports/part3{,_discussion,_hacking,_pilot}.md`。
  - **再降级 2026-06-19(见 §9 banner)**:Part 3 正式定为**轻量下游佐证、非论文重心**(重心=VLM 的 N1/N2);载体改为 **self-refine 主佐证(待建,P10)+ GEPA 旁证**;**SkillOpt 移出主线、deferred**(上游包缺资产/analyst 不调 optimizer/GitHub 不可达,代码留存)。
  - **§9 全部完成(2026-06-20)**:P10 self-refine full 梯度跑通(5 档 × 3 seeds × 3 tasks = 45)。**self-refine 主佐证 corr=+0.659(gain)/+0.558(best_gain)= 期望正向但幅度极小**(强 generator 地板);GEPA 旁证 corr=+0.563(效率 DV 反例)。两载体方向相反但在 `reports/part3.md §3` 调和(GEPA 反例≈效率 DV 的 proxy 饱和/running-best 伪迹,非 examiner 无用)。zs30b 第 5 档在 self-refine 已补齐;GEPA 的 zs30b + SkillOpt 第二载体仍 deferred。报告以 self-refine 为 §1 主、GEPA 为 §2 旁、§3 调和、§4 反作弊审计重构完毕。

## 12. 延后的人工标注工作（非必要 / 锦上添花 — 全部阻塞于本机无人工标注）

> **定位（2026-06-18 收尾决策）**:本项目所有依赖人工标注的任务**集中归到这一节**,统一标为**非必要、非阻塞、待真正有空再锦上添花**。理由有二:① 本机不具备多人标注能力(同 SPEC §10);② **自造真实 test set 反而有"自标自评"的公正性嫌疑** —— 可信的真实迁移信号应来自**第三方**人工标注集。因此当前真实迁移评测以第三方 **SlideAudit**(`reports/part2.md` Table 5)为准,自建人工集不进主线。各条目对应的合成/第三方替代品**已完成**,Part 2/3 的结论**不依赖**本节。标注协议已写好(`docs/annotation_protocol.md`),数据一到即可跑;`slide_examiner/panel.py` 已能输出 inter-annotator agreement(κ/一致率)。

- [ ] (源 §4) 真实问题 deck 人工标注集落地(目标 ~100 页,12 类 taxonomy,minor/moderate/severe,双人复核)。
  - 替代/现状:计划与协议已在 `docs/REAL_DATA_PREP.md` + `docs/annotation_protocol.md`;真实标签 JSONL / summary 待人工采集。**非阻塞**。
  - (源 §4 注释块) 实习脱敏 deck 接入(脱敏策略 / 去客户名/敏感数字/内部项目名 / 公开边界)—— `data_sources.py::internal_desensitized` 仅为注册占位,无真实数据。
- [ ] (源 §8 真实迁移评估) **带结构(模态 C)的真实迁移 + 语义真实标注**。
  - 替代/现状:image-only 第三方迁移已用 **SlideAudit** 完成(`reports/part2.md` Table 5,reframe 为 out-of-design 下界);几何真实标签可由 linter 自动给,但**循环**(linter 既是标注又是 examiner 复述对象),语义真实标签需人工 → **阻塞**。H2 的真实迁移合取项已触发 SPEC 预登记证伪分支(sim2real gap 已诚实记入报告)。
- [ ] (源 §9 P8) Part 3 终评的**不同源人工 panel**(3 名人工 + 冻结 API judge,与训练反馈源不同源,防 Goodhart)。
  - 替代/现状:先备**冻结 API judge 自动臂** + 评测协议;人工 3 人臂 **阻塞**,待有空补。`panel.py` 聚合 + κ 已就绪。
- [ ] (源 §10 写作) related work / 章节里凡引用"人工 panel 终评"处,统一指向本节口径(自动臂为主、人工臂为延后锦上添花)。
