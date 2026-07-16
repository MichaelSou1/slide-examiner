# AAAI-27 修订 TODO — slide-examiner（Codex 执行版）

> **给执行 agent 的说明**：本文件自包含，不依赖任何对话上下文。遵守 `AGENTS.md` 的 TODO 维护规则（完成即勾 `[x]`；实验任务必须有产物路径才能勾）。用中文交流。
>
> **背景**：本论文收到一份模拟审稿（5/10 weak reject），主要打击点：① 因果措辞过强（"saw it all along"）② C0/C3 未做 compute 匹配 ③ 8/9 coverage 有选择偏差与定义漏洞 ④ 排版空引用+占位参考文献。修订策略：①③④ 靠写作，② 补一个纯 API 实验。

**硬截止（AoE = UTC-12）**：摘要 **2026-07-21** ｜ 正文 **2026-07-28** ｜ Supplement **2026-07-31**（OpenReview 提交）

## 审稿缩写索引

- **W = Weakness**（审稿意见里的主要弱点）
- **Q = Reviewer Question**（围绕某个 Weakness 的具体追问）

### Q1–Q8 映射

- **Q1–Q2** → **W2**（compute-matched C0 ablation；见 2.1–2.4）
- **Q3** → **W3 / 台账 L8**（frozen route vs data-driven correction；见 `revision_ledger_aaai27.md` L8，与 3.4 联动）
- **Q4–Q5** → **W3.4**（Table 3 covered 逐格审计 / coverage 定义与 per-cell supporting evidence）
- **Q6** → **W5.2**（SlideAudit 完整逐类表）
- **Q7** → **W5.1**（frozen-route held-out；现已并入 **W7.1/7.2**）
- **Q8** → **W3 / 台账 L9**（capable subset 的 selection-bias 声明；见 `revision_ledger_aaai27.md` L9）

## 关键环境事实（先读）

- **投稿版论文**：`AuthorKit27/submission/main.tex`（AAAI 格式，`\bibliography{refs}` + `refs.bib` + `aaai2027.bst`，build 用 `AuthorKit27/submission/build.sh`）。**所有正文修改以此文件为准。**
- `paper/main.tex` 是带作者署名的 tech-report/arXiv 版（manual thebibliography）。除非明确要求，不改它；若改了投稿版的科学内容（措辞/数字），结束前把同样修改同步过去一份。
- **空引用根因**：`AuthorKit27/submission/aaai2027.sty` L234 `\setcounter{secnumdepth}{0}` → 章节无编号 → 所有 `\ref{sec:*}` 展开为空，PDF 里渲染成 "(Sec. )"。main.aux 里 `\newlabel{sec:diag}{{}{3}...}` 第一个 field 为空可复证。
- **占位引用根因**：`refs.bib` 中 `chartbottleneck / hiddeninplainsight / reasoningbench / led / rankscore / aeslides / evopresent / vlmslideeval / slideaudit / docreward / skyworkvl / zenodo10k` 等 `@misc` 条目**没有 author 字段**，bst 回退用 citekey 缩写渲染成 "(cha 2025)"、"(hid 2025)" 等。
- **实验主机（重要变更，最终方案）**：原 GPU 主机不可用，H20 为组内共享排不到 → **W2 实验全部走在线 API**（Qwen3-VL API 版为主力——与论文 8B examiner 同家族；Gemini-2.5-flash、GPT-5.1-nothinking 为第二三 vendor，均具图像理解），渲染在 Mac 本地做（纯 CPU），详见 2.-1 节。elicitation harness：`scripts/part3_elicit.py`（ENGINES 字典约 L353：C0 / C0plus / C0_named / C3 / C1 / AFC / AFC_clean；`--base-url` 指向云端即可，先例见 `part3_r7_vlm_judge.py`）。已有结果：`data/part3/p1e1_{model}_{g7|geo}_{cond}.json`（metrics 已聚合；per-sample rows 在 `release/part3/rows/`）。
- **capable 4 模型**（论文口径，排除 internvl-8b / ovis-9b）：见 `part3_p1_roster.py` MODELS 列表与已有 `p1e1_*` 文件名（含 qwen35-9b、qwen36-27b、gemma4-31b 等）。
- 统计工具：`slide_examiner/statistics.py`（balanced_accuracy_ci、wilson_interval）；decomposition 分析：`scripts/part3_e1_decomp.py`。
- 检验族：正文称 "61-test family, Holm"。W2 新增检验后此数字必须更新。

---

## W1 排版与一致性修复 ｜ D1–2（07-14~15）｜ 无依赖，最先做

注意：本机“tex”这个conda环境有latex套件

### 1.1 修复空章节引用（Clarity 得分的主因）

- [x] 先读 `AuthorKit27/Instructions.txt` → Instructions L525 明确 AAAI-27 章节编号 **optional**（0→1 打开，最高 2）→ 采用**方案 A**。已在 main.tex `\frenchspacing` 后加 `\setcounter{secnumdepth}{2}`（深度 2 是必须的：`sec:g7`/`sec:elicit`/`sec:coverage` 是 subsection，深度 1 仍会空引用）。
- [x] 受影响位置全部随方案 A 自动解决；实际 `ref{sec:}` 共 15 处（不含 label 定义）全部出数字：Sec. 3/4/5/5.3/6/7、§4/§5.1/§7、范围引用 Sec. 4–5。
- [x] `supplement.tex` 对 main 的引用是**硬编码数字**（`\S3`/`\S5.3`/`Sec.~5` 等，非 `\ref`），逐条核对与方案 A 的编号**完全吻合**（§3=taxonomy、§5.3=G7、§5.1=capable-subset/elicit），方案 A 反而让这些跨文档引用第一次指向真实编号。无需改 supplement。
- [x] **验收（机器检查）**：`bash build.sh` 成功（8 页，bibtex rc=0）；`pdftotext main.pdf` 精确空引用模式（`Sec./Secs./§` 后无数字）**零命中**；log 无 undefined reference。

### 1.2 refs.bib 补 author 字段

- [x] 12 个条目全部经 arXiv API（`id_list` 批量查询）补全作者。所有 12 个返回标题与 bib 标题逐条吻合（id 核验无误）。作者以 `{Last, First}` 形式、` and ` 分隔写入 refs.bib，紧跟各条 citekey 开头行。
- [x] 未用 `and others`——本文件既有 `mmvp`（16 作者）即全列，为保持一致 12 条**全列作者**（docreward 20 位、skyworkvl 12 位等）。已重跑 bibtex+3 遍 pdflatex，**bibtex rc=0**（顺带修掉我在 bib 头注释里误写 `@misc` 触发的 1 个 BibTeX 解析错误——`.bib` 里 `@` 会被当条目起始，注释也不例外）。
- [x] **验收**：占位 citekey 引文（`(cha 20…)` 等）与参考文献表裸 citekey 条目**均零命中**；References 列表 12 条逐一显示真实作者（如 `Fu, S.; Bonnen, T.; …`、`Liu, J.; Zeng, W.; …`）。

### 1.3 S3 段自相矛盾句（审稿实锤）

- [x] 已按两通道分别归因重写（投稿版 main.tex + 已同步 paper/main.tex）：oracle 通道「两变体已显式在输入中 → 失败不可能是 OCR，而是跨页 term-matching 在该 yes/no framing 下不成立」；image 通道「与细粒度字形辨识一致」；两通道均不可靠 → 路由 terminology linter。**已删除原「bottleneck is OCR-from-pixels … not reasoning」单一机制断言**，不再声称是 reasoning。

---

## W2 compute-matched C0 ablation ｜ D1–5，与 W1 并行 ｜ 唯一补实验（GPU 主机跑）

> 回应审稿 Weakness 3 / Q1 / Q2：C3 每类一次调用 ≈ K 倍推理计算，需排除"提升来自更多 test-time compute"。已有线索有利：C0+（单调用+命名，`data/part3/p1e1_*_g7_C0plus.json`）specificity 崩至 55% 过报 → 指向格式而非算力。

### 2.-1 前置：本地渲染重建 + 在线 API 通道（**无 GPU 方案，最终版**）

> 决策历史：原 GPU 主机不可用 → 曾计划 2×H20 重配 → H20 为组内共享排不到 → **最终改为全部走在线 API**。本节取代一切 GPU/vLLM/roster 配置步骤——**不需要任何 GPU**。渲染是纯 CPU（playwright），在 Michael 的 Mac 上直接做。
>
> **可用 API 模型（已筛选，07-15 实测更新；公司付费但每日限额 → 执行要分批可续跑）**：
> - ✅ **qwen3-vl-plus**（¥3/30，256K，图像理解，**默认 RPM=20**）— 主力，E1 先在它上跑。与论文 8B examiner 底座（Qwen3-VL-8B）**同家族**，ablation 多一层"同家族更大模型复现同 pattern"的连续性。它是思考/非思考融合模型：**必须显式关 thinking**（`enable_thinking: false` / `PART3_DISABLE_THINKING=1`）。卡片有信安高风险标注，Michael 已确认按团队惯例使用（该标注不做阻断）
> - ✅ **Gemini-2.5-flash**（¥2.16/18，图像理解）— Google vendor；若冒烟不 capable 升级 Gemini-3.5-flash（¥10.8/64.8）
> - ✅ **gpt-5.1-nothinking**（¥9/72，图像理解）— OpenAI vendor，**实测可用**（dashboard 显示 rpm=0 是假象：5/5 文本+图像全通；gpt-5.4-mini 的 rpm=0 则是真封，每次 429）。无 thinking 版 compute 对照最干净。备胎：gpt-4.1-mini（¥2.88/11.52，非推理系，同样干净）
> - ⚠️ **平台 dashboard RPM 数字不可信**——只有实测算数。每个模型进 sweep 前先连发 5 次文本+1 次图像探可用性；实际限流以运行中的 429 频率为准动态调 workers
> - ❌ gpt-5.4-mini（实测真封）；gpt-4.1-nano（视觉最弱档恐不过 capable 门）；gpt-4o-mini（老+10-31 退役卡 rebuttal 后）
> - 可选④ Ernie-5.0-thinking-preview（¥6/24）：仅当想加"thinking 模型上 C3 仍胜出"的强化论据时跑 G7 单类
> - ❌ Qwen3.5-397B-A17B-Baidu（实测通道不可用）；MiniMax 系（无图像理解）；ERNIE-4.5-8K（上下文不够）；Gemini-3.1-flash-lite-preview（已下线）；GPT-4o 系（将退役且两代前）
>
> **RPM 约束（qwen3-vl-plus 默认 20 RPM）**：并发 workers 压到 **3**（VLM 响应 ~10s/条时贴着限额；出现 429 就再降），3400 调用 ≈ 2.8h/模型，挂后台+断点续跑即可；嫌慢可走平台"申请SOP"提额，非必需。其他两家 vendor 的 RPM 冒烟时实测后同法设置。
>
> **科学口径（写死）**：ablation 模型与论文 capable-4 不同批——这不是缺陷。审稿质疑是"C3 优势可能只是 compute"，compute-matched 控制在任何表现出 C0→C3 恢复的模型上做都成立；三 vendor（Alibaba/Google/OpenAI）强化外部效度，Qwen3-VL 与主实验模型家族同源提供连续性，且论文已有 API 先例（frontier judge 默认问法 G7=0.50、atomic=1.00，sec:g7）。新 ablation 自成一表，措辞："on three API-served models spanning distinct vendors, the compute-matched controls reproduce the recovery pattern"。旧 p1e1 数字原样保留。

#### (a) 本地环境（Mac，纯 CPU，半小时）

- [x] env `slide-examiner` 就绪；`pytest` = **221 passed, 2 skipped**（命中验收）；`.[all]` + `playwright install chromium` 完成。字体用 macOS 自带栈，无需装。
      **坑（07-15）**：本机 PyPI 直连仅 ~29KB/s，`conda env create` 的 pip 步骤卡死 20+ 分钟 → 改用国内镜像：`pip install -e ".[all]" -i https://mirrors.aliyun.com/pypi/simple`，chromium 走 `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright`。
- [x] `.env` 已配齐：美团 AIGC 端点 `https://aigc.sankuai.com/v1/openai/native` + key + `PART3_DISABLE_THINKING=1`。**重要更正**：`part3_elicit` 走的 thinking 关闭是 `PART3_CHAT_KWARGS`（extra_body），`PART3_DISABLE_THINKING` 只作用于 api_config 工厂、不影响 elicit 路径——冒烟/sweep 需 `export PART3_CHAT_KWARGS='{"enable_thinking":false}'`（云端 Qwen 顶层形式，端点已实测接受）。

#### (b) G7 语料重建 + fidelity 门槛（**过不了这道门不许跑实验**）

- [x] 生成器重跑完成：`data/part3/manifest_g7_rendered.jsonl`（90 对）+ **180 PNG** 落 `data/part3/g7_images/`，linter-blind 自检 **90/90=1.000**，per-variant 30/30/30。
- [x] **fidelity 三查 PASSED**——新写机器门 `scripts/part3_g7_fidelity_check.py`：① IR/labels 与 release 参考逐条 diff **90/90 完全一致**；② 渲染有效性（1280×720、def≠clean、非空）；③ 溢出定位 def_strip ink ≫ clean(=0)。另**人眼目检**三变体确认缺陷可见（bullet 溢卡底 / URL 冲出右边 / 图片越框）、clean 无溢出。
- [x] part2/G1 语料重建：`data/part2/manifest_eval_test_rendered.jsonl`（807 条）+ `runs/part2/rendered/`。**坑**：release 冻结 manifest 只内嵌缺陷 IR，clean 的 `clean_slide_path` 指死主机 `/home/gpus/...`；解法＝本地跑 `part2_build_dataset.py` 重生成 `runs/part2/build_freeform/<sid>/clean_slide.json`（sample_id 确定性匹配 735/735），改路径前缀后 `slide-examiner render-manifest`。产物：clean 双子 **735/735**、G1 **54/54** def+clean 齐，非 template 306 对全 def≠clean（≥10 对目检达标）。

#### (c) API 通道打通 + capable 冒烟门（每模型一道门）

- [x] 通道验证完成：`part3_elicit.py --base-url` + `.env`，带图请求确认 **base64 data-URL** 多模态入参兼容；OpenAI Python SDK 非流式路径不变。`part3_elicit.py` 客户端改为 `--timeout`（默认 120s）+ `--max-retries`（默认 5，SDK 指数退避）。
- [x] **capable 冒烟三家全 PASS**（判据 bal-acc≥0.70 且 precision≥0.70 且能指认溢出元素）。命令（以 qwen3-vl-plus 为例，其余同）：
      ```bash
      export PART3_CHAT_KWARGS='{"enable_thinking":false}'
      python scripts/part3_elicit.py --condition C3 --manifest data/part3/manifest_g7_rendered.jsonl \
        --base-url https://aigc.sankuai.com/v1/openai/native --model qwen3-vl-plus --style scoped \
        --defects G7_RENDER_CONTAINMENT_OVERFLOW --modalities A --max-per-defect 20 \
        --out data/part3/smoke_qwen3vlplus_g7_C3.json --resume --workers 3
      ```
      | 模型 | bal-acc | precision | recall | 产物 |
      |---|---|---|---|---|
      | qwen3-vl-plus | **0.950** | 1.000 | 0.900 | `data/part3/smoke_qwen3vlplus_g7_C3.json` |
      | gpt-5.1-nothinking | **0.900** | 1.000 | 0.800 | `data/part3/smoke_gpt51nothinking_g7_C3.json` |
      | gemini-2.5-flash | **0.933** | 1.000 | 0.867 | `data/part3/smoke_gemini25flash_g7_C3.json` |
      三家均过门 → Ernie/单模型/换方案的预案都不触发。C3 证据指认已核（示例点名溢出 bullet + region）。
- [x] thinking 处理已核：qwen3-vl-plus 该端点 **默认 reasoning_tokens=0**（三种关法都接受、都 0）；gpt-5.1-nothinking 天然干净；gemini-2.5-flash 需 `{"enable_thinking":false}` + 放大 `--max-tokens 768`，且**仍会花 ~59 reasoning tokens 并在约 5/20 探针返回 None content**（门不受影响，全量 sweep 时按预案单独报 reasoning tokens）。
- [x] **断点续跑 `--resume` 已实现**：增量写 `<out>.rows.jsonl`（每 sample flush）+ 启动**只跳成功行、重试失败行**（失败多为 429/限额，正是要续的）+ 结束聚合全量；非 resume 路径行为不变。实测：resume 精确「27 跳/13 重试」，配合退避 failures=0。
- [x] **限额下执行顺序**：① 三模型 capable 冒烟 **已完成**；② **qwen3-vl-plus G7 四条件全量已跑完**（含 C0_rep）→ report/cost-table 出（见 2.2/2.3）；③ G1 后台运行中；④ Gemini/GPT 复制、⑤ 可选 Ernie 为后续可续跑批次。
- [x] 并发与限流：`--max-retries=5` 指数退避（429「每分钟请求次数超过限制」按模型计、必现）；qwen3-vl-plus workers=3、gemini/gpt 冒烟用 workers=2；限额耗尽由 SDK 抛错、`--resume` 续跑。

#### (d) 成本预算（公司付费，约束是每日限额而非总价）

| 模型 | 全量四条件（G7+G1，≈3400 调用） | 备注 |
|---|---|---|
| qwen3-vl-plus | ≈¥66（¥3/30；2500 in+400 out/调用估） | 主力，先跑；RPM=20 → ≈2.8h/全量 |
| Gemini-2.5-flash | ≈¥45 | 升 3.5-flash 则 ≈¥180 |
| gpt-5.1-nothinking | ≈¥175 | 备胎 gpt-4.1-mini ≈¥40 |
| （可选）Ernie-5.0 G7 单类 | ≈¥60 | thinking 计费 |
| **合计** | **≈¥290–470** | 按 (c) 的顺序分日执行，断点续跑 |

#### (e) 可比性策略（写死，不再讨论）

- [x] p1e2 四条件已在同一 API 模型（qwen3-vl-plus）、同一批重渲染 G7 语料上同期跑，表内自洽（`reports/_e2_computematch.md` 单表）；与 p1e1（本地权重）不并表。C3 复现恢复效应（0.92，与冒烟 0.95 一致）作为与主实验的连续性证据。G1/其他 vendor 续跑中。

### 2.0 前置：token usage 日志

- [x] `slide_examiner/elicit_common.py` 的 `chat_complete` 现从 `response.usage` 累加（prompt/completion/**reasoning** tokens）到**线程本地**计数器（`reset_usage`/`pop_usage`），签名不变 → 完全向后兼容。`part3_elicit.py` 的 `work()`/`run_afc` 每 probe `reset→pop`，把 `usage` 写进每条 record；`usage_summary()` 汇总进结果 JSON 顶层 `usage`（旧 JSON/mock 无 usage 时该字段为 None）。测试见 `tests/test_part3_elicit.py`（usage 累加/缺失/summary 三例）。

### 2.1 新增两个 engine（`scripts/part3_elicit.py`，注册进 ENGINES 字典）

- [x] **`C0_rep`（E1）**：`engine_c0_rep`（part3_elicit.py）把 C0 调 K 次（默认 K=10 = 部署 router 每页 atomic-question 数 = 9 页级 frozen + G7；`--rep-k`/`--rep-temp` 覆盖），temperature 0.7 采样；C0/C0plus/C0_named/C3 原跑法温度不动（engine_c0 走 `_c0_call(...,temperature=0.0)`，字节等价）。**union**（任一 draw）与 **majority**（成功 draw 的严格多数）都写进 record（`has_defect`/`has_defect_maj` 等）并各自 paired-clean 计分（`score()` 见到 `has_defect_maj` 即额外产出 `detection_majority`/`named_majority` 格）；每个 draw 原始输出存 `reps`。
- [x] **`C0_full`（E2）**：`engine_c0_full` = C0plus 的 whole-taxonomy 单调用（含 G7）+ DEFINITIONS 块（每候选类附 `question_for` 的 C3 binary 问题）+ forced-evidence 门（`_finding_has_evidence`：无 element/evidence 指认的 finding 直接丢弃，与 C3 同门），仍 1 call/slide。差分：C0plus→C0_full = definitions+evidence；C0_full→C3 = decomposition。
- [x] **E3 budget 对照**：不新增 engine——报告 `part3_e2_computematch_report.py` 的 Budget 段直接用 2.0 usage 核算。**结论：C3 output=34.7 tok/slide < C0_full 134.6 < C0 121.6，且 C0_rep=1083.6（8.4× calls）**。C3 反而**最省** output tokens → 触发条件（C3>C0_full）不成立，**无需**加放宽 max_tokens 的 run。

### 2.2 执行

- [x] `scripts/run_e2_computematch.sh` + `scripts/run_e2_all_vendors.sh`（两 vendor 并行、每 vendor 2 passes=首跑+resume 补 429/None、bash-3.2 空数组 guard、.env source）。**三 vendor × G7+G1 × 四条件全量跑完 = 24 个 `data/part3/p1e2_{model}_{g7,g1}_{C0,C0_full,C3,C0_rep}.json`**（qwen3-vl-plus / gemini-2.5-flash / gpt-5.1-nothinking）。补 429 后残余 failure 2–8%。（可选 G3/G5 未做。）
- [x] mpd：G7 90 对（180 slides/cond）、G1 40 对（80 slides/cond），三 vendor 全跑完成。vendor 参数：gemini workers=2 max-tokens=2048（长 prompt 无视 enable_thinking、烧 ~1100 reasoning tok/调用，大 budget 防 None 截断）、gpt workers=2 768、qwen workers=3 768。
- [x] `scripts/part3_e2_computematch_report.py`：compute 对照 = **self-consistency（K=10 多数投票）**；主表 3 列只报 C0 / self-consistency / C3，**union 独立进 supplement 并保留在整族 Holm 里**；`reports/_e2_computematch.md` 与 `data/part3/p1e2_summary.json` 现按 **24 test / 14 拒绝** 对齐。**G7 三 vendor：C3 0.92/0.88/0.83 vs self-consistency 0.61/0.59/0.63，Δ+0.31/+0.29/+0.20 三家全 Holm 显著**；vs C0 0.64/0.61/0.70 亦三家显著（gpt 最弱格 holm_p=0.023）。**budget（E3）铁证**：C3 output tok=34.7/37.5/40.5 三家**最省**、1 call vs 8–10 calls（gemini 的 self-consistency 另烧 11631 reasoning tok/slide vs C3 的 402）→ 赢的条件最省算力，compute 解释三 vendor 均不成立。**C0_full（definition-matched 第二对照，supplement）**：qwen/gemini 仍 < C3 且显著、gpt≈C3（故正文不 headline "decomposition 是机制"）。**G1 = 负控**（qwen/gpt C3≤C0 标 N/A；gemini 全条件近 chance）。正文 "61-test family" → +24（`p1e2_summary.json` 的 `n_tests`）。

### 2.3 成本表（零实验成本）

- [x] `scripts/part3_cost_table.py` 已写：汇总 p1e1/p1e2 JSON 的 usage → 每 slide 调用数 / input+output tokens / total / 估算延迟，输出 `reports/cost_table.md`（+`data/part3/cost_table.json`）；另有 C0_rep-vs-C0 compute-multiplier 小表。旧 p1e1（本地权重，无 usage）如实标注为脚注省略数（64 run，GPU 不可用无法补测；p1e2 API run 全带 usage，现 24 run=3 vendor×G7+G1×4 cond）。**三 vendor G7：C3 out=34.7/37.5/40.5 tok 全场最省，C0_rep 8–10× calls；gemini C0_rep 另烧 11631 reasoning tok/slide（C3 仅 402）** → compute 预算与恢复方向相反（赢的条件反而最省 token）。

### 2.4 写入论文（`AuthorKit27/submission/main.tex` 的 elicitation 小节）

> **结果与定案（07-15 数据全出，07-16 口径定稿；三分支预案作废，落 "赢"）**：命中 **赢**。compute 对照正文只讲 self-consistency；**union 进 supplement 并配解释**（Michael 07-16 拍板——不隐瞒，防 selective-reporting 指控：union 是预设双聚合之一、rows/Holm 族里都有，删了反而授人以柄）。措辞走下面两条铁证：
> - **主文双铁证（三 vendor 全成立）**：① compute 对照 = **self-consistency（K=10 次 C0 采样多数投票）**——学界公认的"把 test-time compute 换成精度"的标准方法（引 Wang et al. self-consistency）；C3 在三 vendor 上全部 **Holm 显著**超过它（C3 0.92/0.88/0.83 vs self-consistency 0.61/0.59/0.63，Δ+0.31/+0.29/+0.20）。② **budget**：C3 恢复时 output tok=34.7/37.5/40.5 **三家最省**、1 call vs 8–10 calls → 赢的条件最省算力，compute 解释逻辑上不成立。
> - **Supplement 完整报**：union 全部数字（含 gpt Δ+0.05 n.s.）+ 一段解释：union（任一 draw 报警）是 OR 聚合＝等效放松判定阈值，对高保守模型（gpt spec≈1）白捡 recall，**本质是调门槛不是加算力**；majority 才是标准 self-consistency 口径，故为正文对照；且 C3 以 1 call 打平 union 8.5-call 的最好成绩。C0_full、G1 负控同进 supplement。**Holm 族按全部 24 test 报，不缩族**（缩族=事后重定义检验族，正撞审稿 Q4/Q5）。
> - **不 headline 的断言**：不说 "decomposition 是关键机制"（gpt 上 definition-matched 对照 C0_full≈C3，会被反杀）；正文不并列 union。改用三家兜得住的话："the whole-taxonomy pointwise format suppresses detection; breaking that format recovers it **without additional test-time compute**"。

- [x] 加一段（6–8 行）按"主文双铁证"口径 + supplement 表。措辞："on three API-served models spanning distinct vendors, a compute-matched self-consistency control fails to recover the suppressed detection, which the atomic elicitation restores at strictly lower cost."
- [x] **主表定版：只三列 C0 / self-consistency / C3 + budget 行**——已核 `p1e2_summary.json`（24-test 全族 Holm）：该三列隐含的 6 个格间对比（C3 vs C0、C3 vs self-consistency × 3 vendor）**全过 Holm、零 n.s.**（gpt 最弱格 C3 vs C0 holm_p=0.023）。supplement 放 union（any-vote，含解释段）+ C0_full（definition-matched 第二对照）+ 三 vendor 全格 + budget/reasoning-token 列。
- [x] 与 W3.2 联动：本段与"saw it all along"降级一致——只讲 format-suppression + 不靠算力，不声称内部表征。
- [x] **报告已对齐（07-16 定稿版）**：`reports/_e2_computematch.md` 主表 = C0 / self-consistency / C3 + Δ；**union 以独立 supplement 段回归**（含解释：OR 聚合=阈值放松非 compute scaling、majority 才是标准 self-consistency、C3 以 1 call 打平 union 8–10 calls 最好成绩）；C0_full 为 definition-matched supplement 段；**Holm 族恢复全部 24 test（14 拒绝），不缩族**——主表 6 格在 24-族下仍全显著。`p1e2_summary.json` 同步含全部四类 contrast。
- [x] **验收**：p1e2 JSON 产物存在（24 个 `data/part3/p1e2_*`）；report 落 `reports/_e2_computematch.md` + `reports/cost_table.md`；**E1（C0_rep）数字 07-15 已出（提前于 07-19 gate）**。✅ 正文段落与 supplement 表已落稿（走 W3 台账流程）。

---

## W3 措辞收缩 + Table 3 covered 审计 ｜ D3–6 ｜ 依赖 W2 的 E1 初步结果

> **工作流（防松散/防 AI 味，重要）**：W3/W4 的所有措辞与结构改动**先入台账 `revision_ledger_aaai27.md`，不直接改 tex**。台账已预填 L1–L15（原句摘录+拟改+理由），流程：Michael 逐条拍板 → 一次性整合写作 pass 落 tex（用论文原有声音重写受影响段落，禁止逐句补丁）→ 最后跑 Michael 的去 AI 味提示词做纯风格 pass（该 pass 不得再动 claim 强度）。硬规则：替换型新句不得长于原句；scope 声明全文只许两处（attribution 定义段 + Limitations）；追加型条目从严。W1 机械修复不过台账，直接落 tex。

全部改动最终落 `AuthorKit27/submission/main.tex`（完成后同步 paper/main.tex）。以下 3.1–3.6 与台账 L1–L12 一一对应，执行时以台账定案为准。

### 3.1 attribution 改操作性定义（回应 Weakness 1）

- [x] 在 attribution protocol 定义处（sec:setup 的 "Attribution modalities and metric" 段）加操作性定义："perception-bottlenecked（operational）＝ 同等信息以无损结构形式显式提供时任务可解"，并声明这是**干预层面的诊断而非表征层面的因果断言**。
- [x] 加一句 scope 辩护：oracle 同时改变表示与任务接口，但 routing 只需要"哪个引擎能解"，不需要"模型内部是否看见"——把混淆转述为设计边界。
- [x] B 失败 → "reasoning bottleneck" 的反向推断同样降级为"在该结构接口下亦不可解"（脚注 2 一并检查）。

### 3.2 "saw it all along" 降级（回应 Weakness 2）

- [x] 相关断言（Fig.1 caption、sec:elicit 的 "It is the format, not the eyes" 段、Conclusion）已统一改为 "targeted defect-specific elicitation recovers detection that the pointwise rubric suppresses" 风格。保留 C0/C0+/C0_named/C3 分解作为 format-vs-naming 证据链，但不断言 C0 下已形成等价内部表征。
- [x] Limitations 中已有的 "could in principle be reduced task difficulty" 段已与新措辞、W2 新结果对齐。

### 3.3 pairwise 剥离（回应 Weakness 4）

- [x] 全文统一三层术语并在首次出现处定义：**sub-perceptual**（G3 ≤8px 尾部、G6 page offset）/ **format-suppressed**（G7、supra-threshold G3、G5）/ **reference-assisted**（G1、S6，即 availability-of-reference）。
- [x] Abstract 与 Contributions 中已把 G1/S6 的 pairwise 恢复从 "not the eyes" 主叙事摘出为单独一句。
- [x] pairwise 的部署可得性已通过 intro / coverage / external 的 IR-owning scope 表述收束：clean reference 仅 IR-owning agent 内可得，third-party pixels 场景不适用。

### 3.4 Table 3 covered 逐格审计（回应 Weakness 5 / Q4 / Q5，**内部真雷，AC 自己会数**）

- [x] 已定位 coverage 表（sec:coverage）并按现定义（bal-acc **exceeds** 0.75 且 Wilson 下界 > 0.65）逐格核：
  - G6 linter = 0.75 [.67,.80]：不满足 "exceeds" → 严格不 covered；
  - linter+C3 列 S1 = 0.83 [**.63**,.92]：下界 < 0.65 → 严格不 covered；
  - 其余每格已按 reports/ 与 data/part3/ summary 口径复核。
- [x] 已采用决策 A：headline 换成 mean balanced accuracy 对比（hybrid 0.85–0.86 vs C0 0.59 vs linter 0.66），coverage 计数降为次要并按严格定义如实报；Abstract / Fig.1 caption / Conclusion 中的 8/9 已同步更新为严格口径。
- [x] S1 re-route 已透明化：frozen route（S1→text LLM，bal-acc 0.25 / precision 0.09）与 corrected route（S1→VLM-C0，0.94）两个数都已报；matching a pre-registered routed hybrid 的旧说法已删除或改写。
- [x] capable subset 已补 selection-bias 声明：selected on the same test items, so the subset is descriptive rather than confirmatory。

### 3.5 小样本降级 + 实验三分类（回应 Weakness 7）

- [x] 已复查 S1(n=18)、S6(n=12)、frontier judge(n=24) 只出现在 diagnostic/descriptive 语境；Abstract/Intro/Conclusion 不再引用这些数字做 confirmatory 主张。
- [x] 各实验节的口头定位已收束为：confirmatory（G7 主对比、G1，Holm 族内）/ diagnostic（routing 依据）/ exploratory（reward audit、real deck 案例）。

### 3.6 human spot-check 在新语料上重标（回应 Weakness 9 + 新语料 QA，台账 L16）｜ Michael 亲自标注

> 最新状态（2026-07-15 晚）：v1 标注已完成并证实当前普通 spot-check 的 **G3/G5 样本口径失效**——`docs/spotcheck/labels.json` 中 G3 7/7 = not visible、G5 7/7 = not visible，notes 直接指向“bullet 其实对齐”“只有粗细区别没有颜色区别”。这与 `reports/_e8_data_audit.md` / `specs/todo_0623.md` 的 E8 重口径一致：G3 应是 **同组 bullets 中一项相对错位**，G5 应是 **同组 bullets 中一项相对变色**，不能再用旧的 absolute/external 样本。

> 最新状态（2026-07-16 凌晨）：v2 已完成收口。`docs/spotcheck/manifest_v2.json` / `docs/spotcheck/labels_v2.json`、`reports/_e8_spotcheck_v2.md` / `data/part3/e8_spotcheck_v2.json`、`data/part3/e8_ir_faithfulness_v2.json` 与 `reports/_e8_spotcheck_v2_delta.md` 均已生成。结果是：**73/73 defect-visible、73/73 twin-clean、flagged pairs = 0；结构忠实性审计 55/55 present**。其中被替换之外的旧 55 对标签一条未变，变化仅限 corrected G3/G5（G3 `0/7 -> 8/8`，G5 `0/7 -> 10/10`），说明这次修复的是抽样口径，而不是整体人标漂移。

> 背景与真正动机：旧 spot-check（`reports/_e8_spotcheck.md`）当年不只是感知基线——**那轮人工标注是发现三个数据 bug 的唯一机制**（`reports/_e8_data_audit.md` 2026-06-25：①g3g5_internal 240 个 defective 共享同一张异 deck clean twin，2-AFC 被内容混淆；②template 渲染 snap 吸收 G3 offset 致 def==clean 像素相同却占每 stratum 50%；③`--freeform-only` 过滤器静默 no-op（匹配 `__template` 后缀 vs 实际 `/template/` 目录），根因，污染全部下游——修后 G3 linter 0.70→0.90）。自动 pipeline 三处全漏，人眼看 pair 直接露馅。**因此在 Mac 重渲染的新语料上重标 v2 = 感知基线刷新 + 对新语料执行同一道 QA**（07-15 Michael 决定）。旧结果不删，降级为对照。

- [x] **重标前的定向 bug 复查（对着旧 audit 的三条打）**：v1 人工标注已直接暴露当前普通 spot-check 的 G3/G5 口径漂移；并已核对 E8 权威记录，确认问题不是“人看不出来而已”，而是 **抽样仍在用旧定义**。同时已修 `scripts/part3_spotcheck_sample.py`：后续普通 spot-check 不再从 generic part-2 抽 G3/G5，而改用 `data/part3/g3_relmisalign.jsonl` / `data/part3/g5_chromatic.jsonl` 的 E8 纠正语料。
- [x] **replacement 抽样已完成**：为避免重刷 69 对，已生成只替换失效 G3/G5 的重标包——`docs/spotcheck/manifest_g3g5_replacement.json`（18 对：G3 8 + G5 10）与 `docs/spotcheck/annotate_g3g5_replacement_zh.html`。replacement 语料分别来自 `runs/part3/g3_rel/*`（relative misalignment）与 `runs/part3/g5_chroma/*`（chromatic hue swap）。
- [x] **补标 replacement（现只剩 G5）**：G3 的 8 对已在 `docs/spotcheck/labels_g3_only_replacement.json` 中保留为有效人标；Michael 已在 `docs/spotcheck/annotate_current_g5_only_replacement_zh.html` 上完成 corrected G5 的 10 对重标，并导出 `docs/spotcheck/labels_g5_only_replacement_v2.json`。若能拉到第二标注者（同学），同样走 G5-only 页再标一份；否则仍可保留 Michael + Claude 交叉核验。
- [x] **出报告**：已用 `part3_spotcheck_report.py` 生成 `reports/_e8_spotcheck_v2.md` + `data/part3/e8_spotcheck_v2.json`；并将 `part3_spotcheck_irdiff.py` 升级为可审计 replacement G3/G5 的 v2 版本，产出 `data/part3/e8_ir_faithfulness_v2.json`。结果：**73/73 defect-visible、73/73 twin-clean、flagged pairs = 0；结构忠实性审计 55/55 present**。
- [x] **新旧对照**：已用 `scripts/part3_spotcheck_merge_v2.py` 合并旧 labels + G3-only replacement + G5-only replacement，得到 `docs/spotcheck/manifest_v2.json` / `docs/spotcheck/labels_v2.json`；并落盘 `reports/_e8_spotcheck_v2_delta.md`。结果：**被替换之外的旧 55 对一条未变**，G3 从 `0/7 -> 8/8`，G5 从 `0/7 -> 10/10`，说明 v2 修复的是抽样口径而非整体人标漂移。
- [x] 落稿（配合台账 L16）：正文 3–4 句引用 v2 数字，完整表进 supplement；Limitations "No human-inspector reference point" 句改写；v2 若揪出新语料 bug，修复记录进 supplement 的 perturbation-fidelity 部分（与 45% snapping 发现同一叙事线）。
- [ ] 时间盒：bug 复查 + 抽样 + 标注 ≈ 3–4 小时，安排在 W2 跨模型跑批等待窗口；**07-24 前完成**。

**验收**：无表征级因果断言残留（grep 复查）；coverage headline 数字与表格逐格一致；三层术语无混用。

---

## W4 结构收缩 + 摘要锁死 ｜ D5–7，**07-21 AoE 摘要截止** ｜ 依赖 W3 方向

- [x] **动笔前先清点 `reports/`（半小时，重要）**：reports/ 里是当年压 7 页时砍掉的材料（例：human spot-check 被砍导致审稿 W9 整条 weakness，见 3.6/台账 L16——删减代价已被审稿标价）。逐个 report 对照审稿 9 weakness + 8 questions 列一张"审稿点 ↔ 现成材料"配对表：能用 3–4 句正文 + supplement 表买回来的，优先于新写任何内容；特别核对 Q6（SlideAudit 逐类表）、Q5（per-cell precision 是否真在 supplement）。产出：配对清单落 `specs/`，供 W4 分配篇幅时用。已落：`specs/review_material_map_20260716.md`。

- [x] sec:g7 的 reward audit 压至 ~半页：主文现只保留 CLIP-IQA/LAION 同 backbone dissociation + perturbation-fidelity 45% 两点；per-scorer 表与其余讨论已移交 Technical Supplement/补充材料承接。
- [x] sec:examiner 压缩：主文现只保留 in-distribution 超 30B、abstain 行为、sim-to-real 负结果三点；训练细节与细表改由 supplement 承接。
- [x] 释放篇幅给 W2 ablation 段与 W3 scope 声明；主线现为 Intro → setup → diag → elicit（含 ablation）→ coverage → g7 → examiner(压缩) → external → limits。
- [ ] **07-21 前重新锁定 Abstract**：2026-07-16 主线由 LTT 切换为 Diagnose→Distill→Defer（D3），原 W4 摘要不再视为锁定。只有完成 **W7.0–W7.4 的“摘要锁定门”** 后，才可锁定方法性摘要；此时只写已经实现并通过 smoke test 的方法，不提前写 D3 优于 baseline 的结果数字。最终结果性措辞须等 W7.7 untouched test 后再更新。
- [ ] **07-21 前**：将通过 W7 摘要锁定门后的标题与 Abstract 提交 OpenReview。待完成（2026-07-16）：投稿人将在截止日前自行填写并保存；提交成功后再勾选，不以本地改稿代替。
- [x] 备选标题已拟好（仅 E1 结果不利时启用）："Diagnose Before You Route: Sub-Perceptual, Format-Suppressed, and Reference-Assisted Failures in VLM Slide Inspection"。
- [x] 页数检查：`AuthorKit27/submission/main.pdf` 当前总计 8 页，但第 8 页为 references 延续；`pdftotext -f 7 -l 7 main.pdf -` 可见 References 已在物理第 7 页底部开始，满足 AAAI-27 正文 7 页页限。

---

## W5 机动项 ｜ D8–12 ｜ 仅 W2–W4 收工后

- [x] **5.1 frozen-route held-out**（回应 Q7）：已用新 seed/新模板生成 9 类各 150 positive + 150 unique clean twin，并通过全类 fidelity gate；corrected frozen route 一次性评估 macro bal-acc .957、严格覆盖 8/9，\g{S6} 因 clean FP 为唯一未覆盖类。产物：`release/part3/w5/heldout_fidelity.json`、`heldout_routed.json`、`heldout_routed_rows.jsonl`，正文一句 + supplement 表（2026-07-16）。这批数据及结果已经看过，后续仅作为 D3 的 frozen-route baseline / validation，不得充当 untouched final test。
- [x] **5.2 SlideAudit 完整逐类表**（回应 Q6）：已从冻结的 `data/part3/p2_slideaudit.json` 整理全部 7 个映射类的 C0/C3 per-class bal-acc、precision、有效 n 与 95% Wilson CI，并加入完整 C0/C3 prompt template 及逐类 C3 问句；同时补齐正文 coverage 表逐格 precision companion。产物：`AuthorKit27/submission/supplement.tex` / `AuthorKit27/submission/supplement.pdf`（2026-07-16）。
- [x] 5.3：G6 page-offset 极端 magnitude（整体左移 144px、越界 48px）补测完成；C0/C3 detection 均为 .958（11/12 positive，12/12 clean，precision 1.0），C0 named 仍为 0、C3 named 为 11/12。结论据此改为 **moderate-magnitude blind spot / clipping boundary**，不再声称跨 magnitude 的普遍 blind spot。产物：`release/part3/w5/g6_extreme_C0.json`、`g6_extreme_C3.json`（2026-07-16）。

---

## W7 新主线：Diagnose → Distill → Defer（D3 Critic）｜ 取代 LTT ｜ 依赖 Part 1/2 与 W5

> **决策（2026-07-16）**：撤销 LTT 作为正文方法主线。LTT 原本是在不能重训、需要快速补足算法内容时，对人工 frozen route 加有限样本认证的权衡；它认证既有配置，但不让模型从诊断中学习。现在改为完整 D3：把 Part 1 的 recoverability 诊断转成 teacher/action supervision，蒸馏 targeted elicitation 与 pairwise 能力，并训练模型在证据不足时请求结构、参考或拒答。**不创建 LTT 预注册、不跑原计划 5,400 次/模型认证调用、不实现 `part3_ltt_certify.py`，正文不再声称 `m/9 certified`。**
>
> **主张边界**：“模型自身学会质检”不是让裸像素 VLM 强行解决全部缺陷，而是学会三件事：① 对可恢复缺陷直接检测并给出 evidence；② 对 reference-/structure-dependent 缺陷选择正确工具或上下文；③ 对 sub-perceptual / 证据不足样本校准地 defer。G2–G6 的 detector of record 仍是 linter，不能把复述 linter 标签写成视觉能力。
>
> **新方法一句话**：对样本 $x_i$ 与缺陷 $k$，在训练/开发数据上比较 $e\in\{\mathrm{C0},\mathrm{C3},\mathrm{pairwise},\mathrm{linter},\mathrm{defer}\}$ 的正确性、paired-clean FPR、evidence 与成本，得到 teacher action $e^*_{ik}$；再训练统一 student 同时预测 finding 与动作 $a\in\{\texttt{ANSWER},\texttt{CALL\_LINTER},\texttt{REQUEST\_REFERENCE},\texttt{REQUEST\_DECK},\texttt{DEFER}\}$。测试时 student 只接 generic inspection instruction，不再靠逐类 prompt 才成立。

### 7.0 冻结科学问题、成功标准与旧资产角色

- [x] 锁死三个 RQ，后续不得看 final test 后改口径（冻结于 `release/part3/d3/freeze.json`，2026-07-16）：
  - **RQ-D（Distill）**：C3 teacher 的 G7 recovery 能否在 student 的 generic single-call inference 下保留，同时不抬高 clean FPR？
  - **RQ-R（Route）**：learned action 是否优于人工 frozen route / 单一 C3，在相同或更低平均调用成本下提高 macro bal-acc？
  - **RQ-F（Defer）**：student 能否把 G2–G6 image-only 等不可可靠判断样本送往 linter/defer，而不是制造 false positive？
- [x] 冻结 primary metrics：macro balanced accuracy、paired-clean FPR、named localization/evidence validity、correct-action accuracy、average model calls、token/latency cost、selective risk–coverage；`covered m/9` 仅作 descriptive companion，阈值不得再当算法 headline（`release/part3/d3/freeze.json`）。
- [x] 冻结关键成功门槛：D3 generic-prompt G7 优于当前 vanilla Part 2 FT 的 generic prompt；G2–G6 image-only FPR 不高于当前 FT；相对 learned baseline 在 accuracy–cost Pareto 上非劣；所有结论同时给 per-class 数字与 CI，不用 micro average 掩盖 S6/S2（`release/part3/d3/freeze.json`）。
- [x] 旧本地 6 模型、W2 compute-matched 结果、Part 2 v2 权重与 `release/part3/rows/` 全部冻结，只做 baseline，不重写历史结果。
- [x] W5 novel-template 2,700 图及已看过的 .957 / 8-of-9 结果降格为 **validation + frozen handcrafted-route baseline**；不得作为 D3 untouched final test。
- [x] 为当前 checkout 打 D3 起点 commit/tag，记录代码、数据 manifest、Part 2 adapter 与现有结果哈希；后续每个训练 run 都记录 parent commit、config、seed、数据 hash 与模型 hash。已建 annotated tag `d3-start-20260716`（commit `10c121f`），冻结哈希与“本机无 adapter checkpoint”事实见 `release/part3/d3/freeze.json`（2026-07-16；未 push）。

### 7.1 数据切分与防泄漏协议（先冻结，再生成 final test）

- [x] 建立四层数据角色并在 manifest metadata 中显式写 `split`、`source_deck`、`template_id`、`content_cluster`（`data/part3/d3/split_manifest.jsonl`、`final_test_{image,deck}.jsonl`）：
  - `train`：生成 teacher traces、SFT/ranking/action records；
  - `dev`：选择 utility 权重、loss 权重、route/defer threshold 与 checkpoint；
  - `validation`：使用已看过的 W5 novel-template 集，只做消融与 frozen-route 对照；
  - `final_test`：新 seed + 新模板 + source/content 去重，方法冻结后只运行一次。
- [x] 按 **source deck / template / near-duplicate content cluster** 分组切分，禁止同源 clean/defective twin 跨 split；clean twin、severity chain、pairwise 两顺序必须整体留在同一 split。实现与测试：`slide_examiner/d3_data.py`、`tests/test_d3_data.py`；审计：`release/part3/d3/split_audit.json`。
- [x] 在生成 `final_test` 前锁死生成 seed、每类 n、severity 比例、模板池、fidelity gate、primary comparisons、统计检验族与失败处理；生成后先只跑 fidelity，不调用 student、不查看类别结果。冻结顺序与 `student_invoked=false` 见 `release/part3/d3/{freeze,final_test_fidelity,final_test_deck_fidelity}.json`。
- [x] `final_test` 至少覆盖当前 9 个 image-level 类，每类正/负 paired clean 数量预先等额；额外保留 deck-scope S2/S5 独立 split，不能和 page-level macro 混报。已生成 image 9 类各 30 pair（270 pair）及 S2/S5 各 20 pair + 40 clean deck；manifest 在 `data/part3/d3/`，可提交 fidelity 在 `release/part3/d3/`。
- [x] 修复 Part 2 已知数据缺口：补 clean-deck negatives；S2/S5 加 paired/reference arm；所有 pairwise 样本继续随机 A/B 且要求双顺序一致；NO_DEFECT page/deck 分开统计。产物：`split_manifest.jsonl`、`pairwise_orders.jsonl`、`final_test_deck.jsonl`、`split_audit.json`。
- [x] 增加同底图 severity chain，供 monotonic loss；增加 image-only / image+structure / reference-available / deck-context-available 四种 availability condition，供 action supervision。产物：`data/part3/d3/{split_manifest,availability_records}.jsonl`。
- [x] 每次导出后跑 parser round-trip、重复/泄漏检查、modality/action/class composition、paired-clean 完整性和 A/B 平衡检查，产物写入现有 `runs/` / `data/` 路径，不以“脚本能跑”代替 artifact。`release/part3/d3/split_audit.json` 与两份 fidelity 均 `passed=true`（2026-07-16）。

### 7.2 归因结果 → teacher/action supervision

- [x] 定义 expert/action 空间与可用性约束（`slide_examiner/d3_data.py`、`release/part3/d3/freeze.json`）：
  - `C0_GENERIC`：普通全局质检；
  - `C3_ATOMIC`：逐类 targeted + forced evidence teacher；
  - `PAIRWISE_REFERENCE`：clean/reference twin 双顺序一致判断；
  - `LINTER`：有 IR 时的确定性结构检测；
  - `DEFER`：无可靠证据或所需输入不可用。
- [x] 为 train/dev 样本汇总每个 expert 的 correctness、paired-clean FP、named localization/evidence validity、calls、tokens、latency 与 availability，形成 sample × expert reward matrix；不得用 validation/final_test 选择 teacher。`release/part3/d3/teacher_reward_matrix.jsonl` 为 5,394 samples × 5 experts = 26,970 rows。
- [x] 冻结 utility 形式并在 dev 上选择系数：$U_i(e)=R_i(e)-\lambda_c C_i(e)-\lambda_{fp}FP_i(e)+\lambda_v V_i(e)$；保存每个 $e^*_i=\arg\max_e U_i(e)$、次优 margin、teacher disagreement 与不可用原因。dev-only 81 点 grid 与所选系数见 `utility_selection.json`；逐样本结果见 `d3_records.jsonl`、`teacher_summary.json`。
- [x] 对 teacher tie / disagreement 设确定规则：优先低成本、低 FPR、可验证 evidence；margin 低于阈值则标 `DEFER` 或降低蒸馏权重，不用人工逐条挑“好看输出”。见 `teacher_summary.json` 与逐样本 `d3_records.jsonl`。
- [x] 构建五类训练目标（`release/part3/d3/training_targets.jsonl`）：
  - G7：C3 teacher → **generic single-call student** 的 detection + location + evidence distillation；
  - G1/S6：clean-defective twin ranking + `REQUEST_REFERENCE`；
  - G2–G6：有 IR 时 `CALL_LINTER`/解释 linter evidence，image-only 时 `DEFER`，禁止伪视觉正例；
  - S1/S4：direct answer；S2/S5：补 clean-deck 后 direct/deck-context 或 pairwise；
  - clean / clean-clean：`NO_DEFECT` / tie，专门约束 false positive 与 forced-pick bias。
- [x] 对 API teacher trace 做缓存、hash、重试和 parser validation；teacher 失败不能默认为 negative，必须标 failure 并排除或降权。现有 CSV 作为 immutable cache，索引/哈希/parser/retry policy 在 `release/part3/d3/teacher_trace_cache.json`；1 条 failure 在 matrix 中 `available=false`，未转成 negative。

### 7.3 D3 模型、输出契约与联合损失

- [x] 扩展现有 examiner 输出而不破坏旧 parser：已在 `PageExamResult` / `DeckExamResult` 加入 `action`、`confidence`、`requested_context`、`evidence_source`，旧字段保留默认值；一致性 validator 强制非 `ANSWER` 动作无 finding 且 `evidence_source=none`。实现与回归测试见 `slide_examiner/examiner_contract.py`、`tests/test_examiner_contract.py`（2026-07-16）。
- [x] student 推理入口只接受一个 frozen generic inspection instruction；`scripts/part3_d3_infer.py` 仅使用训练记录首条 generic user message，C3/pairwise/linter 仅用于 teacher 或一次升级动作，不向首轮 student 暴露 defect-name oracle（2026-07-16）。
- [x] 实现联合目标并逐项可开关消融（`scripts/part3_d3_train.py`、`slide_examiner/d3_training.py`；六项 loss 均有独立 `--loss-*` 权重，2026-07-16）：
  - $\mathcal L_{detect}$：结构化 finding / NO_DEFECT；
  - $\mathcal L_{distill}$：teacher label、evidence、location 与可选 soft confidence；
  - $\mathcal L_{pair}$：Bradley–Terry 或 margin ranking，含 clean-clean tie；
  - $\mathcal L_{severity}$：同源 severity 单调性；
  - $\mathcal L_{route}$：teacher action 分类；
  - $\mathcal L_{select}$：confidence/defer 的 selective-risk 目标。
- [ ] 先以 Qwen3-VL-8B + QLoRA 延续 Part 2 v2 配置，建立 `vanilla-v2 continue-train` 与 `from-base D3` 两条可比 run，防止收益仅来自更多训练 step；固定总 records/steps 的 compute-matched baseline。
- [x] 明确 router 形态并至少实现两级：`class_router.json` 是仅用 train split 拟合的 multinomial logistic regression（dev accuracy 0.7387，`manual_route_used=false`）；D3 heads 是 sample-level action prediction，并由 generic inference 执行至多一次 escalation。实现见 `fit_class_router` / `D3Heads`，不是人工 defect→action 字典（2026-07-16）。
- [x] 正式 run 保存逐 step train loss、完整 dev joint/sub-loss、action confusion/recall、G7 generic answer recall、G2–G6 image-only unsafe-answer rate、config、数据 hash 与 dev-only selection basis；artifact 见 150：`runs/part3/d3_formal/train_seed{17,73}/` 及三项消融目录。注意这些 head 指标只用于 dev 选择，finding/FPR 最终数仍须由 W7.6/7.7 端到端 scoring 给出（2026-07-16）。

### 7.4 端到端 smoke test 与“摘要锁定门”

- [ ] 用每类小样本跑通完整链路：manifest → teacher reward matrix → D3 records → QLoRA → merge/serve → generic inference → action escalation → scoring；产出可复现 run artifact。
- [ ] smoke test 必须证明实现语义正确，而非追求最终数字：
  - generic prompt 下 G7 student 能输出合法 finding/evidence；
  - G2–G6 image-only 能输出 `CALL_LINTER` 或 `DEFER`，且不伪造 finding；
  - G1/S6 能请求 reference 并在获得 reference 后完成双顺序一致判断；
  - S2 clean deck 不再因缺负样本而恒报；
  - parser failure、teacher failure、action loop 均有显式计数。
- [ ] **摘要锁定门（做到这里即可锁定并提交方法性 Abstract）**：W7.0 的 RQ/metrics/成功标准已冻结；W7.1 split 与防泄漏脚本通过；W7.2 teacher/action 数据有真实 artifact；W7.3 联合损失与统一 generic inference 已实现；W7.4 端到端 smoke test 全通过。此时摘要可写“we introduce attribution-guided distillation and selective tool/defer learning”，但**不得写性能提升、成本下降、覆盖数或‘模型已学会’等结果性结论**。
- [ ] 摘要锁定后，除非方法失败导致 claim 不成立，只允许在 W7.7 后填入预先声明的 final-test 数字；禁止根据 validation 调换 primary endpoint。

### 7.5 正式训练与 dev-only 模型选择

- [ ] 运行至少 3 个固定 seed；每个 seed 保存 base model、adapter、merged model、config、数据 hash、训练日志和推理版本。**进度（2026-07-16）**：seed 42/17/73 均已完成 768-step QLoRA 并保存 adapter、heads、config、hash 与日志；seed17/73 已跑完整 2,151 条 dev（joint loss 0.2332/0.2685），seed42 旧 run 仅评估前 320 条，且三 seed 尚未逐一 merge + 固化 inference artifact，故本项暂不勾选。
- [ ] 只在 dev 上调：loss 权重、utility cost、teacher margin、confidence/defer threshold、最大 escalation 次数；W5 validation 用于对照和消融，不用于继续追 final-test 类别。
- [ ] 冻结最终 D3 checkpoint 与 inference policy：generic first-pass → action → 最多一次工具/reference escalation → final finding/defer；记录最坏调用上限，防止成本无限增长。
- [ ] 在碰 `final_test` 前生成 model card 式 run summary（放现有 report/run artifact，不新建无关文档）：选择原因、失败类别、threshold、预期主表列、代码/data/model hash。

### 7.6 必做 baseline 与消融

- [ ] Baselines：zero-shot 8B、zero-shot 30B、当前 vanilla Part 2 FT、fixed C0、uniform C3、人工 frozen route、compute-matched vanilla FT（相同数据量/step）。
- [ ] Router 对照：人工 fixed route、learned class-level route、learned sample-level route、sample-level + escalation/defer。
- [ ] Loss 消融：去 `distill`、去 `pair`、去 `severity`、去 `route`、去 `select/defer`；如果篇幅不足，正文保留前三个最能回答 RQ 的，其余进 supplement。**进度（2026-07-16）**：同 seed、同 768 steps、同完整 2,151 dev 的去 `distill` / 去 `pair` / 去 `route` 已完成，artifact 为 150 的 `runs/part3/d3_formal/ablation_no_{distill,pair,route}_seed42/`；其中去 route 导致 `CALL_LINTER`/`REQUEST_DECK`/`DEFER` recall 全为 0、G7 answer recall 仅 0.25。去 `severity` 与去 `select/defer` 尚未运行，三项已有消融也仍待统一端到端 scoring，故不提前勾选。
- [ ] Teacher 消融：C3 labels 直接 SFT vs attribution-selected teacher；证明收益不是“多收一批 C3 输出再微调”。
- [ ] Prompt 内化对照：teacher-C3、vanilla-FT+generic、D3+generic、D3+C3；主结果必须是 D3+generic，D3+C3 只用于测残余 elicitation gap。
- [ ] Availability/OOD：去掉 IR、去掉 reference、novel template、held-out severity；检查动作是否随可用证据改变，而不是只背 defect type。
- [ ] Deck 负例专项：S2/S5 在补 clean-deck 前后对照，分别报告 recall 与 specificity，禁止用 balanced aggregate 掩盖恒报。

### 7.7 冻结评测、统计与最终摘要数字

- [ ] 方法、checkpoint、threshold、primary comparisons 和表格模板全部冻结并 commit 后，才解锁 `final_test`；只运行一次，失败重跑仅限有日志可证的系统/解析错误，不能因结果差换 checkpoint。
- [ ] 主表逐类报告 balanced accuracy、precision/recall/specificity、paired-clean FPR、Wilson CI、named localization；另表报告 action accuracy、defer/coverage、calls、tokens、latency。
- [ ] 画 risk–coverage 与 accuracy–cost Pareto；固定 coverage 点比较 selective risk，并报告工具不可用时的 graceful degradation。
- [ ] 预先定义并执行最小检验族：D3-generic vs vanilla-FT-generic（G7 与 macro）、learned route vs frozen route（macro/cost）、D3 defer vs no-defer（G2–G6 FPR/risk）；Holm 校正，探索性 per-class 检验单列，不把所有表格数字塞进一个族。
- [ ] 外部真实迁移继续使用 SlideAudit，并明确其无 IR/reference 的输入边界；若 D3 仍 sim-to-real 失败，作为核心 negative 如实保留，不用合成 final test 覆盖。
- [ ] **只有完成本节后，才可在 Abstract/Conclusion 填最终结果性数字**：优先写 generic-prompt G7 recovery、macro bal-acc、paired-clean FPR 与平均调用成本；`m/9 covered` 不再作为 headline，更不得写 `certified`。
- [ ] 若 full D3 未达到预设成功门槛：保留诊断与 honest negative；按消融定位是 teacher 不可蒸馏、router 不泛化还是 defer 过度，不回退到事后 LTT 包装负结果。

### 7.8 论文重构与验收

- [ ] 重写贡献顺序为：① recoverability diagnosis；② attribution-guided elicitation/pairwise distillation；③ selective tool/defer critic；C0/C2/C3 降为 teacher/action conditions，不再作为方法标题中心。
- [ ] Method 给出 reward matrix、teacher selection、联合损失与 inference policy 伪代码；公式必须对应真实实现，不能只为“显得算法”增加符号。
- [ ] Results 按 RQ-D/RQ-R/RQ-F 组织：能力内化、学习路由、能力边界；旧 reward audit 与 external validity 继续压缩/放 supplement，避免主线再次分叉。
- [ ] 更新 Fig.1：diagnosis → teacher selection → student distillation → answer/tool/reference/defer；删除任何 LTT/certification 图示或文字。
- [ ] 更新 Limitations：teacher/API 依赖、合成到真实迁移、IR/reference availability、selective coverage 代价；明确 linter-owned geometry 不是 student pixel perception。
- [ ] 全文清理 `LTT`、`Learn-then-Test`、`certified m/9`、旧“摘要已锁死”与人工 route 被称作算法的残留；保留统计上必要的 CI/Holm，不删除严谨评估。
- [ ] 同步 `AuthorKit27/submission/main.tex`、`supplement.tex`、tech-report 版及 refs；跑构建、页限、空引用、匿名、数字一致性检查。
- [ ] **W7 验收**：真实 teacher/action artifact、至少一个完整 D3 checkpoint、untouched final-test manifest/fidelity/result、baseline+ablation、risk–coverage/accuracy–cost、论文方法与结果均存在；未产生对应 artifact 的实验不得勾选。

---

## W6 全文终校 + 提交 ｜ D13–14（07-27~28）

- [ ] 逐条对照审稿 9 条 weakness + 8 个 question，确认每条：已修复 / Limitations 有明示 scope。
- [ ] W1 的机器检查重跑（空引用、占位引用均零命中）。
- [ ] 数字一致性：Abstract / Fig.1 caption / Table 3 / Conclusion 的 coverage 与 bal-acc 数字互相一致（W3.4 改动后极易漏）。
- [ ] Holm/BH 检验族数字更新（"61-test family" → 实际新数；W2 与 D3 的预先定义检验族分开列，见 7.7），清除旧 W7 LTT 家族口径。
- [ ] 匿名检查（投稿版无作者信息、无 acknowledgment、self-citation 匿名化）；`grep -i "surh6\|Ruihan\|Sun Yat-sen" AuthorKit27/submission/main.tex` 零命中。
- [ ] paper/main.tex（tech-report 版）同步所有科学内容改动。
- [ ] **07-28 AoE 提交正文**；**07-31 AoE 提交 supplement**（含 W2 表、W5.2 表、per-cell precision、S1 双路由数、cost table）。

---
