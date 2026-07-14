# AAAI-27 修订 TODO — slide-examiner（Codex 执行版）

> **给执行 agent 的说明**：本文件自包含，不依赖任何对话上下文。遵守 `AGENTS.md` 的 TODO 维护规则（完成即勾 `[x]`；实验任务必须有产物路径才能勾）。用中文交流。
>
> **背景**：本论文收到一份模拟审稿（5/10 weak reject），主要打击点：① 因果措辞过强（"saw it all along"）② C0/C3 未做 compute 匹配 ③ 8/9 coverage 有选择偏差与定义漏洞 ④ 排版空引用+占位参考文献。修订策略：①③④ 靠写作，② 补一个纯 API 实验。

**硬截止（AoE = UTC-12）**：摘要 **2026-07-21** ｜ 正文 **2026-07-28** ｜ Supplement **2026-07-31**（OpenReview 提交）

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
- [ ] **限额下执行顺序**：① 三模型 capable 冒烟 **已完成**（见上）；②–⑤（E1 C0_rep 全量 → C0/C3/C0_full G7+G1 → Gemini/GPT 复制 → 可选 Ernie）属 2.1/2.2 sweep，未开始。
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

- [ ] p1e2 四条件全部在同一 API 模型、同一批重渲染语料上同期跑，表内完全自洽；与 p1e1（本地权重）不并表、不互相引用数字。正文一句话交代模型来源与语料重渲染，冒烟 C3 结果（应复现恢复效应）作为与主实验的连续性证据。

### 2.0 前置：token usage 日志

- [ ] `slide_examiner/elicit_common.py` 的 `chat_complete` 目前**不记录 usage**。改为从 OpenAI 兼容响应中取 `response.usage`（prompt_tokens / completion_tokens），随每条 record 写入输出 JSON。保持向后兼容（旧 JSON 无 usage 字段）。

### 2.1 新增两个 engine（`scripts/part3_elicit.py`，注册进 ENGINES 字典）

- [ ] **`C0_rep`（E1，最优先——结果决定 07-21 摘要措辞）**：把 engine_c0 调 K 次（K = C3 在该 sweep 中的调用数，即被查询的 defect type 数；命令行 `--rep-k` 可覆盖），temperature 0.7 采样（确认 chat_complete 支持传温度；C3/C0 原跑法的温度设置保持不动作为对照），聚合报 **union** 和 **majority** 两种，分别按 paired-clean balanced accuracy 计分。每次重复的原始输出都存进 record 便于复核。
- [ ] **`C0_full`（E2）**：单次调用 = C0plus 的 catalog（含 G7）+ 每类附 C3 用的 binary 问题文本作为 definitions（复用 part3_elicit.py L63 起的 per-type questions 字典）+ forced evidence（每个报出的 defect 必须给 element 指认，无指认则不计入）。与 C0plus 的差 = definitions+evidence 的贡献；与 C3 的差 = decomposition 的贡献。
- [ ] **E3 budget 对照**：不新增 engine——用 2.0 的 usage 日志核算 C0/C0_rep/C0_full/C3 的实际 token 消耗，若 C3 总 output tokens 明显高于 C0_full，加一组 C0_full 放宽 max_tokens 的 run 确认差距不随 budget 消失。

### 2.2 执行

- [ ] 范围：**G7 + G1 +（时间允许）G3 supra-threshold、G5**；模型 = 过了 capable 冒烟门的 API 模型（1–2 个，见 2.-1(c)）。不走 roster（那是 vLLM serve 用的）——直接写 `scripts/run_e2_computematch.sh` 循环调 `part3_elicit.py --base-url <API>`，四条件 × 模型 × tag，产物 `data/part3/p1e2_{model}_{tag}_{cond}.json`。
- [ ] mpd（每类样本数）：G7 90 对全跑（API 便宜），G1 40 对全跑。
- [ ] 计分：沿用 part3_elicit.py 的 paired-clean bal-acc / precision / Wilson CI；新对比（C3 vs C0_rep、C3 vs C0_full，至少 G7+G1 × 4 模型）纳入检验族重跑 Holm，更新正文 "61-test family" 数字。分析脚本仿照 `part3_e1_decomp.py` 写 `scripts/part3_e2_computematch_report.py`，产物落 `reports/`。

### 2.3 成本表（零实验成本）

- [ ] 写 `scripts/part3_cost_table.py`：汇总 p1e1/p1e2 JSON 的 usage → 每 slide 的调用数 / input+output tokens / 估算延迟，输出 markdown 表到 `reports/cost_table.md`，进 supplement。旧 JSON 无 usage 的，跑一小批补测或按 prompt 长度估算并标注。

### 2.4 写入论文（`AuthorKit27/submission/main.tex` 的 elicitation 小节）

- [ ] 加一段（6–8 行）+ supplement 完整表。三种结果的措辞预案：
  - **赢**（C0_rep 不涨或 specificity 崩、C0_full 部分涨但 < C3、budget 不解释差距）→ "compute-matched 与 definition-matched 对照下 C3 仍显著占优，排除 test-time compute 解释"。
  - **混合**（C0_full ≈ C3）→ 主张改为"suppressor 是 whole-taxonomy 单调用多标签格式，decomposition 是关键成分"（routing 结论不变，弱化 atomic 的特殊性）。
  - **输**（C0_rep 追平 C3）→ 核心主张改写为"repeated sampling 或 decomposition 均可恢复，pointwise single-call rubric 是共同失败模式"，**标题与摘要须同步改**（见 W4 备选标题）。
- [ ] **验收**：p1e2 JSON 产物存在；report 落 reports/；正文段落与 supplement 表完成；**07-19 前 E1（C0_rep）初步数字必须出来**。

---

## W3 措辞收缩 + Table 3 covered 审计 ｜ D3–6 ｜ 依赖 W2 的 E1 初步结果

> **工作流（防松散/防 AI 味，重要）**：W3/W4 的所有措辞与结构改动**先入台账 `revision_ledger_aaai27.md`，不直接改 tex**。台账已预填 L1–L15（原句摘录+拟改+理由），流程：Michael 逐条拍板 → 一次性整合写作 pass 落 tex（用论文原有声音重写受影响段落，禁止逐句补丁）→ 最后跑 Michael 的去 AI 味提示词做纯风格 pass（该 pass 不得再动 claim 强度）。硬规则：替换型新句不得长于原句；scope 声明全文只许两处（attribution 定义段 + Limitations）；追加型条目从严。W1 机械修复不过台账，直接落 tex。

全部改动最终落 `AuthorKit27/submission/main.tex`（完成后同步 paper/main.tex）。以下 3.1–3.6 与台账 L1–L12 一一对应，执行时以台账定案为准。

### 3.1 attribution 改操作性定义（回应 Weakness 1）

- [ ] 在 attribution protocol 定义处（sec:setup 的 "Attribution modalities and metric" 段）加操作性定义："perception-bottlenecked（operational）＝ 同等信息以无损结构形式显式提供时任务可解"，并声明这是**干预层面的诊断而非表征层面的因果断言**。
- [ ] 加一句 scope 辩护：oracle 同时改变表示与任务接口，但 routing 只需要"哪个引擎能解"，不需要"模型内部是否看见"——把混淆转述为设计边界。
- [ ] B 失败 → "reasoning bottleneck" 的反向推断同样降级为"在该结构接口下亦不可解"（脚注 2 一并检查）。

### 3.2 "saw it all along" 降级（回应 Weakness 2）

- [ ] grep `saw the overflow all along` 及同类断言（Fig.1 caption、sec:elicit 的 "It is the format, not the eyes" 段、Conclusion），统一改为 "targeted defect-specific elicitation recovers detection that the pointwise rubric suppresses" 风格。保留 C0/C0+/C0_named/C3 分解作为 format-vs-naming 证据链，但不断言 C0 下已形成等价内部表征。
- [ ] Limitations 中已有的 "could in principle be reduced task difficulty" 段与新措辞、W2 新结果对齐。

### 3.3 pairwise 剥离（回应 Weakness 4）

- [ ] 全文统一三层术语并在首次出现处定义：**sub-perceptual**（G3 ≤8px 尾部、G6 page offset）/ **format-suppressed**（G7、supra-threshold G3、G5）/ **reference-assisted**（G1、S6，即 availability-of-reference）。
- [ ] Abstract 与 Contributions 中把 G1/S6 的 pairwise 恢复从 "not the eyes" 主叙事摘出为单独一句。
- [ ] 在 pairwise（C2/2-AFC）首次出现处声明部署可得性：clean reference 仅 IR-owning agent 内可得（synthetic twin re-render），third-party pixels 场景不适用。

### 3.4 Table 3 covered 逐格审计（回应 Weakness 5 / Q4 / Q5，**内部真雷，AC 自己会数**）

- [ ] 定位 coverage 表（sec:coverage）。按现定义（bal-acc **exceeds** 0.75 且 Wilson 下界 > 0.65）逐格核：
  - G6 linter = 0.75 [.67,.80]：不满足 "exceeds" → 严格不 covered；
  - linter+C3 列 S1 = 0.83 [**.63**,.92]：下界 < 0.65 → 严格不 covered；
  - 其余每格复核（原始数字在 reports/ 与 data/part3/ 的 summary 里，勿手抄论文数）。
- [ ] 决策（倾向 A）：**A** = headline 换成 mean balanced accuracy 对比（hybrid 0.85–0.86 vs C0 0.59 vs linter 0.66），coverage 计数降为次要并按严格定义如实报；**B** = 定义改 "≥0.75" 且下界规则逐格执行、如实报数（linter+C3 可能 6/9）。Abstract / Fig.1 caption / Conclusion 中所有 "8/9" 同步更新。
- [ ] S1 re-route 透明化：frozen route（S1→text LLM，bal-acc 0.25 / precision 0.09）与 corrected route（S1→VLM-C0，0.94）**两个数都报**；删除或限定 "matching a pre-registered routed hybrid" 中被 S1 违反的部分。
- [ ] "capable subset" 由同一测试集 C3 表现定义 → 加 selection-bias 声明一句（或绑定到独立样本，若 W5.1 做了就引用它）。

### 3.5 小样本降级 + 实验三分类（回应 Weakness 7）

- [ ] 复查 S1(n=18)、S6(n=12)、frontier judge(n=24) 只出现在 diagnostic/descriptive 语境；Abstract/Intro/Conclusion 不引用这些数字做 confirmatory 主张。
- [ ] 各实验节口头标注类型：confirmatory（G7 主对比、G1，Holm 族内）/ diagnostic（routing 依据）/ exploratory（reward audit、real deck 案例）。

### 3.6 "sub-perceptual" 限定（human baseline 的零成本替代，回应 Weakness 9）

- [ ] 全文 grep `sub-perceptual`，在首次出现处限定为 "below the tested models' effective threshold under this protocol"，Abstract/Intro/Table 1 caption 同步；Limitations 保留 no-human-baseline 声明。

**验收**：无表征级因果断言残留（grep 复查）；coverage headline 数字与表格逐格一致；三层术语无混用。

---

## W4 结构收缩 + 摘要锁死 ｜ D5–7，**07-21 AoE 摘要截止** ｜ 依赖 W3 方向

- [ ] sec:g7 的 reward audit 压至 ~半页：保留 CLIP-IQA/LAION 同 backbone dissociation + perturbation-fidelity 45% 两个点，Table 4 细节与其余讨论移 Technical Supplement。
- [ ] sec:examiner 压缩：保留 in-distribution 超 30B、abstain 行为、sim-to-real 负结果三点，训练细节移 supplement。
- [ ] 释放篇幅给 W2 ablation 段与 W3 scope 声明；检查主线接力：Intro → setup → diag → elicit（含 ablation）→ coverage → g7 → examiner(压缩) → external → limits。
- [ ] **07-21 前**：Abstract 定稿并在 OpenReview 提交。措辞范围必须与 W2 E1 结果方向一致。
- [ ] 备选标题想好一个（仅 E1 结果不利时启用），风格如 "Diagnose Before You Route: Sub-Perceptual, Format-Suppressed, and Reference-Assisted Failures in VLM Slide Inspection"。
- [ ] 页数检查：正文（不含 references）满足 AAAI-27 页限（见 Instructions.txt）。

---

## W5 机动项 ｜ D8–12 ｜ 仅 W2–W4 收工后

- [ ] **5.1 frozen-route held-out**（回应 Q7，最值）：换随机种子+换模板重新注入一批 defect instance（复用 `part3_e8_regen_corpus.py` / part1/part2 注入 pipeline），路由**冻结**（含 S1 corrected route，作为声明过的 final route），一次性评估，报 coverage/mean bal-acc → 正文一句 + supplement 一表。产物：新 manifest + run JSON + report。
- [ ] **5.2 SlideAudit 完整逐类表**（回应 Q6）：从 `part3_p2_slideaudit.py` / `part2_slideaudit_eval.py` 已有 runs 整理 per-class bal-acc + n + Wilson CI + 完整 prompt 文本 → `supplement.tex`（07-31 截止，不占正文窗口）。
- [ ] 5.3（可选）：G6 page-offset 补一档更极端 magnitude，巩固 "genuine blind spot"。

---

## W6 全文终校 + 提交 ｜ D13–14（07-27~28）

- [ ] 逐条对照审稿 9 条 weakness + 8 个 question，确认每条：已修复 / Limitations 有明示 scope。
- [ ] W1 的机器检查重跑（空引用、占位引用均零命中）。
- [ ] 数字一致性：Abstract / Fig.1 caption / Table 3 / Conclusion 的 coverage 与 bal-acc 数字互相一致（W3.4 改动后极易漏）。
- [ ] Holm/BH 检验族数字更新（"61-test family" → 实际新数）。
- [ ] 匿名检查（投稿版无作者信息、无 acknowledgment、self-citation 匿名化）；`grep -i "surh6\|Ruihan\|Sun Yat-sen" AuthorKit27/submission/main.tex` 零命中。
- [ ] paper/main.tex（tech-report 版）同步所有科学内容改动。
- [ ] **07-28 AoE 提交正文**；**07-31 AoE 提交 supplement**（含 W2 表、W5.2 表、per-cell precision、S1 双路由数、cost table）。

---

## 每日检查点

| 日期 | 应完成 |
|---|---|
| 07-15 | ✅ W1 全部（机器检查通过）；✅ 2.-1(a)(b)：Mac 本地环境 + G7 语料重建过 fidelity 门槛（另 part2/G1 也重建完） |
| 07-16 | ✅ 2.-1(c)：API 通道通、**三**模型 capable 冒烟全过（提前于计划，见 2.-1(c) 表）；⬜ 2.0/2.1 代码（未开始） |
| 07-17 | E1（C0_rep）初步数字出炉 → 决定摘要方向 |
| 07-19 | W2 四条件齐 + report；W3.1–3.3 台账拍板完毕 |
| 07-21 | **摘要提交 OpenReview**；W3.4 表格审计定稿 |
| 07-24 | W4 完成，正文可通读 |
| 07-26 | W5 冻结（做多少算多少） |
| 07-28 | **正文提交** |
| 07-31 | **supplement 提交** |
