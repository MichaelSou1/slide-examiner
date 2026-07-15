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
- [x] `scripts/part3_e2_computematch_report.py`：C3-vs-{C0,C0_full,C0_rep(union),C0_rep(maj)} 的 Δbal-acc + 精确 McNemar + **整族 Holm（24 test，14 拒绝）** → `reports/_e2_computematch.md` + `data/part3/p1e2_summary.json`。**G7 三 vendor 一致 C3>C0_full>C0**（C3 0.92/0.88/0.83 vs C0 0.64/0.61/0.70）。**compute-match（C3 vs C0_rep-union）**：qwen Δ+0.26、gemini Δ+0.27 **两者 Holm 显著 WIN**；gpt Δ+0.05 不显著（gpt 极保守 spec≈1，union 采样把 recall 顶到 0.78 逼近 C3——但 **majority C0_rep 三家全崩 0.61/0.59/0.63**，且 C3 用 1 call 打平 gpt 的 8.5-call union）。**budget（E3）铁证**：C3 output tok=34.7/37.5/40.5 三家**最省**，C0_rep 8–10× calls（gemini C0_rep 烧 11631 reasoning tok/slide vs C3 的 402）→ 赢的条件反而最便宜，compute 解释三 vendor 均不成立。**G1 = 负控**（qwen/gpt C3≤C0 标 N/A；gemini G1 全条件近 chance）。正文 "61-test family" → 汇总 +24（`p1e2_summary.json` 的 `n_tests`）。

### 2.3 成本表（零实验成本）

- [x] `scripts/part3_cost_table.py` 已写：汇总 p1e1/p1e2 JSON 的 usage → 每 slide 调用数 / input+output tokens / total / 估算延迟，输出 `reports/cost_table.md`（+`data/part3/cost_table.json`）；另有 C0_rep-vs-C0 compute-multiplier 小表。旧 p1e1（本地权重，无 usage）如实标注为脚注省略数（64 run，GPU 不可用无法补测；p1e2 API run 全带 usage，现 24 run=3 vendor×G7+G1×4 cond）。**三 vendor G7：C3 out=34.7/37.5/40.5 tok 全场最省，C0_rep 8–10× calls；gemini C0_rep 另烧 11631 reasoning tok/slide（C3 仅 402）** → compute 预算与恢复方向相反（赢的条件反而最省 token）。

### 2.4 写入论文（`AuthorKit27/submission/main.tex` 的 elicitation 小节）

> **结果与定案（07-15，数据全出后写死；下面三分支预案作废，落 "赢" 但按下面口径措辞）**：命中 **赢** 分支，但要**功利地选对照口径**避开唯一软肋（gpt 的 union 逼近）。定案：
> - **主文双铁证（三 vendor 全成立）**：① compute 对照**只用 self-consistency = K=10 次 C0 的多数投票（majority）**——它是学界公认的"用算力换精度"标准做法（引 Wang et al. self-consistency），C3 在三 vendor 上全部 **Holm 显著**超过它（Δ+0.31/+0.29/+0.20；majority C0_rep 仅 0.61/0.59/0.63 vs C3 0.92/0.88/0.83）；② **budget**：C3 恢复时 output tok=34.7/37.5/40.5 **三家最省**、1 call vs 8–10 calls → 赢的条件最省算力，compute 解释逻辑上不成立。
> - **进 supplement、正文不 feature**：**union**（"任一 draw 报警"= 判定阈值放松，非 compute scaling；只在 gpt 上把对照顶高——被 rebuttal 追问才用一句"union 是调阈值不是加算力，且 C3 用 1/8 calls 打平其最好结果"）；**C0_full**（降级为 "definition-matched 第二对照"，qwen/gemini 上仍 < C3 且显著，gpt 上 ≈C3 不展开）；**G1**（reference-assisted 负控，与 compute 线无关，本段不写）。
> - **不许 headline 的断言**：不说 "decomposition 是关键机制"（gpt 上 C0_full≈C3 会被反杀）；正文不并列 union。改用可三家兜住的话："the whole-taxonomy pointwise format suppresses detection; breaking that format recovers it **without additional test-time compute**"。

- [ ] 加一段（6–8 行）按上面"主文双铁证"口径 + supplement 完整表（含 union / C0_full / 三 vendor 全 24 格 / budget+reasoning-token 列）。措辞："on three API-served models spanning distinct vendors, a compute-matched self-consistency control fails to recover the suppressed detection, which the atomic elicitation restores at strictly lower cost."
- [ ] 与 W3.2 联动：本段与"saw it all along"降级一致——只讲 format-suppression + 不靠算力，不声称内部表征。
- [ ] 可选加固：`reports/_e2_computematch.md` 可按此口径重排（主表 3 列 C0/self-consistency/C3 + budget 行，union/C0_full 降 supplement 段），令正文与附录一次对齐。
- [x] **验收**：p1e2 JSON 产物存在（24 个 `data/part3/p1e2_*`）；report 落 `reports/_e2_computematch.md` + `reports/cost_table.md`；**E1（C0_rep）数字 07-15 已出（提前于 07-19 gate）**。⬜ 正文段落与 supplement 表待落稿（走 W3 台账流程）。

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

### 3.6 human spot-check 在新语料上重标（回应 Weakness 9 + 新语料 QA，台账 L16）｜ Michael 亲自标注

> 背景与真正动机：旧 spot-check（`reports/_e8_spotcheck.md`）当年不只是感知基线——**那轮人工标注是发现三个数据 bug 的唯一机制**（`reports/_e8_data_audit.md` 2026-06-25：①g3g5_internal 240 个 defective 共享同一张异 deck clean twin，2-AFC 被内容混淆；②template 渲染 snap 吸收 G3 offset 致 def==clean 像素相同却占每 stratum 50%；③`--freeform-only` 过滤器静默 no-op（匹配 `__template` 后缀 vs 实际 `/template/` 目录），根因，污染全部下游——修后 G3 linter 0.70→0.90）。自动 pipeline 三处全漏，人眼看 pair 直接露馅。**因此在 Mac 重渲染的新语料上重标 v2 = 感知基线刷新 + 对新语料执行同一道 QA**（07-15 Michael 决定）。旧结果不删，降级为对照。

- [ ] **重标前的定向 bug 复查（对着旧 audit 的三条打）**：①新 manifest 逐条验证 pair 的 clean twin 是**同 deck 专属**（`distinct clean imgs == n_defectives`，一行脚本）；②确认走 faithful/freeform 渲染路径、无 `/template/` 泄漏；③验证 `--freeform-only` 过滤器对新路径编码真实生效（数过滤前后条数，勿信 flag 名）。任一不过 → 先修再标。
- [ ] **抽样**（复用 `scripts/part3_spotcheck_sample.py`）：新渲染语料 ~69 对、9 类分层；修旧协议两瑕疵——G1 换自然长文溢出（`XX/XXX` 注入标记是旧报告自己标出的 artifact）；magnitude 各档均衡（G3 参照 relg3 的 4/16/48/96px 分层）。
- [ ] **标注**（`docs/spotcheck/spotcheck.html`，协议同旧版）：Michael 主标；**能拉到第二标注者（同学）就加标一份**→ 报 inter-annotator agreement（raw + Cohen's κ），W9 升级为正经 baseline；拉不到则 Michael + Claude 交叉核验（report 脚本原生 `--claude`）。标注时保持旧版的"顺手记 note"习惯——上次的 bug 就是这么抓到的。
- [ ] **出报告**：`part3_spotcheck_report.py` → `reports/_e8_spotcheck_v2.md` + `data/part3/e8_spotcheck_v2.json`；跑 IR 忠实性审计（`part3_spotcheck_irdiff.py`）。
- [ ] **新旧对照**：v2 vs 旧版逐类比对（预期 G3≈0/n、G1/S6/G7≈1.00、twins 全干净）；一致 → supplement 一句话；**不一致 → 停，按数据 bug 处理而非标注噪声**（历史教训）。
- [ ] 落稿（配合台账 L16）：正文 3–4 句引用 v2 数字，完整表进 supplement；Limitations "No human-inspector reference point" 句改写；v2 若揪出新语料 bug，修复记录进 supplement 的 perturbation-fidelity 部分（与 45% snapping 发现同一叙事线）。
- [ ] 时间盒：bug 复查 + 抽样 + 标注 ≈ 3–4 小时，安排在 W2 跨模型跑批等待窗口；**07-24 前完成**。

**验收**：无表征级因果断言残留（grep 复查）；coverage headline 数字与表格逐格一致；三层术语无混用。

---

## W4 结构收缩 + 摘要锁死 ｜ D5–7，**07-21 AoE 摘要截止** ｜ 依赖 W3 方向

- [ ] **动笔前先清点 `reports/`（半小时，重要）**：reports/ 里是当年压 7 页时砍掉的材料（例：human spot-check 被砍导致审稿 W9 整条 weakness，见 3.6/台账 L16——删减代价已被审稿标价）。逐个 report 对照审稿 9 weakness + 8 questions 列一张"审稿点 ↔ 现成材料"配对表：能用 3–4 句正文 + supplement 表买回来的，优先于新写任何内容；特别核对 Q6（SlideAudit 逐类表）、Q5（per-cell precision 是否真在 supplement）。产出：配对清单落 `specs/`，供 W4 分配篇幅时用。

- [ ] sec:g7 的 reward audit 压至 ~半页：保留 CLIP-IQA/LAION 同 backbone dissociation + perturbation-fidelity 45% 两个点，Table 4 细节与其余讨论移 Technical Supplement。
- [ ] sec:examiner 压缩：保留 in-distribution 超 30B、abstain 行为、sim-to-real 负结果三点，训练细节移 supplement。
- [ ] 释放篇幅给 W2 ablation 段与 W3 scope 声明；检查主线接力：Intro → setup → diag → elicit（含 ablation）→ coverage → g7 → examiner(压缩) → external → limits。
- [ ] **07-21 前**：Abstract 定稿并在 OpenReview 提交。措辞范围必须与 W2 E1 结果方向一致。
- [ ] 备选标题想好一个（仅 E1 结果不利时启用），风格如 "Diagnose Before You Route: Sub-Perceptual, Format-Suppressed, and Reference-Assisted Failures in VLM Slide Inspection"。
- [ ] 页数检查：正文（不含 references）满足 AAAI-27 页限（见 Instructions.txt）。

---

## W5 机动项 ｜ D8–12 ｜ 仅 W2–W4 收工后

- [x] **5.1 frozen-route held-out**（回应 Q7）：**已并入 W7.1/7.2**——LTT 新校准集就是 held-out 语料，frozen route 作为预声明配置在同批数据上评估，不再单独采数。交付物见 7.2 第三条。
- [ ] **5.2 SlideAudit 完整逐类表**（回应 Q6）：从 `part3_p2_slideaudit.py` / `part2_slideaudit_eval.py` 已有 runs 整理 per-class bal-acc + n + Wilson CI + 完整 prompt 文本 → `supplement.tex`（07-31 截止，不占正文窗口）。
- [ ] 5.3（可选）：G6 page-offset 补一档更极端 magnitude，巩固 "genuine blind spot"。

---

## W7 LTT 风险受控路由认证（Learn-then-Test）｜ D4–10 ｜ 依赖 2.-1 渲染链路，与 W3/W4 并行

> **动机（07-15 新增，两个来源）**：① 算法岗面试官两次批"纯工程无算法"→ 论文需要一节有公式、有有限样本保证的方法内容；② 审稿 W5/Q4/Q5 打 coverage 选择偏差（0.65 阈值事后画线、配置事后挑）——LTT 把"挑选"本身变成带 FWER 保证的检验程序的输出，是对 W3.4 的**原理性修复**而非外挂。方案取舍已定案（07-15）：**选 LTT，否决 adaptive-C3 提前停止**（后者与 per-class 指标冲突、W2 已证 C3 反而最省 token 使"省 compute"动机消失、形式化只剩贪心调度）。SFT 加码也已否决（与论文"elicitation 而非模型"论点自相矛盾，且无 GPU）。
>
> **框架一句话**：把每类 k 的路由候选 Λ_k = {linter, C0, C3, linter⊕C3} 当离散假设空间；对每个 (k,λ) 在**新采校准集**上检验 H₀: R_k(λ) > α（二项精确 p 值，可换 Hoeffding–Bentkus），FWER（Holm）校正后保留通过者。产出陈述："以概率 ≥1−δ，认证表内每个配置真实风险 ≤ α；(α,δ) 下 m/9 类可认证"。
>
> **模型口径（07-15 定案，写死）**：旧本地 6 模型结果**全部冻结不动**（generality 论证 + capable-4 口径 + 61-test family 的地基；GPU 主机不可用也无法重跑；per-sample rows 已冻结在 `release/part3/rows/`）。**主认证做在 API 模型上**（qwen3-vl-plus 主力，与 W2 同阵容），定位延续 W2 科学口径：三 vendor 复制 arm 上的带保证认证，与 p1e1 不并表。ft-8B 无 API 替代品（examiner 线证据不动）。**不做"一锅端"全换 API**——可复现性（开源权重 vs 黑盒 API）、8B–31B 量级的论证力度、qwen3-vl-plus G1 上 C0>C3 的模型异质性三个理由，均已论证，不再讨论。

### 7.0 预注册（**必须在采集任何新数据之前完成并 commit，这是方法的灵魂**）

- [ ] 写 `specs/ltt_preregistration.md` 并 git commit（commit 时间戳=预注册证据），锁死：
  - **风险定义**：FNR 与 FPR **分开控制**（比合成 1−bal-acc 可解释："漏报≤α₁ 且 误报≤α₂"），认证=两个单侧检验都过；
  - **α 档位**：主档 α₁=α₂=0.25；敏感性网格 α ∈ {0.20, 0.25, 0.30, 0.35}（网格本身预注册，谁也说不出阈值事后挑）；
  - **δ=0.05**，FWER 用 Holm（与论文既有检验族同工具）；
  - **检验族大小**：9 类 × ≤4 配置 × 2 错误率 ≤ 72 检验（实际按可行候选数），族与 W2 的 24-test 分开报；
  - **候选空间 Λ_k**：全 9 类 × {linter, C0, C3, linter⊕C3}（linter 对无规则可用的类天然缺席，如实缺）；
  - **小样本预案**：认证不出（如 S6 类 n 不足）就报"该类在此 n 下不可认证"——诚实结果，不降 α 迁就。
- [ ] **功效依据（写进预注册，n 的选择理由）**：Bonferroni 到 ~72 检验后单检验水平 ≈7e-4；真实风险 0.10 的配置认证 α=0.25–0.30 需 **n≈60/侧起**，真实风险 0.15–0.20（bal-acc 0.80–0.85 带）需 **n≈120–200/侧** → 目标 **n=150/侧/类**（S6 受生成器限制做多少算多少）。

### 7.1 新校准集（**与开发数据严格分离**，兼并 W5.1）

> 现有 `release/part3/rows/` 是开发路由和 0.65 阈值时看过的数据 = "脏"校准集，只能做次要分析。新校准集从未参与开发，LTT 保证才成立。**这批数据同时就是 W5.1 的 frozen-route held-out**（frozen route 是预先声明的特定 λ，在同批数据上报告与 LTT 认证互不污染）——W5.1 并入本节，不再单独采数。

- [ ] 生成：复用注入器 + `part3_e8_regen_corpus.py`/part1/part2 pipeline，**换随机种子+换模板**，9 类分层，目标 150 对/类（def+clean twin，同 deck 专属）；渲染走 2.-1 已重建的 Mac playwright 链路。
- [ ] **fidelity 门槛照旧执行**（Protocol 3 教训：45% 注入不渲染）：`part3_g7_fidelity_check.py` 同款三查扩到全类 + 3.6 的三条定向 bug 复查（clean twin 唯一性 / 无 template 泄漏 / 过滤器真实生效）。**过不了门不许打分。**
- [ ] Linter 打分：本地确定性程序，全类全量，零成本。
- [ ] VLM 打分（API）：C0 + C3 两条件 × 9 类 × ~300 slides/类 ≈ **5400 调用/模型**；qwen3-vl-plus 主力（workers=3、`--resume`、分批续跑），Gemini 复制可选。成本 ≈¥100–200/模型，对照今日额度消耗 3.2% 无压力。linter⊕C3 由 linter 本地分 + C3 API 分合成，**不需要额外调用**。

### 7.2 认证计算 + 报告（纯本地）

- [ ] 写 `scripts/part3_ltt_certify.py`：读校准 rows → 每 (k,λ,错误率) 二项精确 p 值 → Holm → 认证表 + 敏感性表（α 网格 × m）→ `reports/_e9_ltt_cert.md` + `data/part3/e9_ltt_cert.json`。工具复用 `slide_examiner/statistics.py`。
- [ ] **次要分析**：同一程序跑冻结的 `release/part3/rows/`（本地 6 模型），结果如实标注"该数据参与过开发与阈值选择，保证意义弱化"——既给旧模型一个参考认证，又示范方法的可移植性。
- [ ] frozen-route held-out 数字（原 W5.1 交付物）：同批校准集上按冻结路由（含 S1 corrected route）一次性评估 → 正文一句 + supplement 一表。

### 7.3 落稿（`AuthorKit27/submission/main.tex`，走 W3 台账流程）

- [ ] Method 小节（~1/3 页，**论文仅有的公式集中在此**）：R_k(λ) 定义（FNR/FPR）、H₀: R_k(λ)>α、二项尾概率 p 值、FWER 保证 P(任一假认证)≤δ 四条公式 + 认证程序 3–4 行文字；引 Angelopoulos et al. Learn-then-Test（refs.bib 补条目，author 字段齐全——W1.2 教训）。
- [ ] 与 W3.4 决策 A 联动：headline = mean bal-acc 对比（不变），**"m/9 certified at (α,δ)" 作为带保证的次要 headline** 替代被喷的 ad hoc "8/9 covered"；Abstract/Fig.1/Conclusion 同步（见 W6 数字一致性）。**摘要（07-21）措辞不依赖具体 m 值**——m 出来前用方法性描述，出来后正文再填数。
- [ ] Limitations 一句：保证对合成校准分布成立（i.i.d./exchangeability），sim2real 照旧 scope。
- [ ] 检验族声明：LTT 的 ≤72 检验自成一族（预注册文档为界），与既有 61+24 族并列报，W6 数字更新点 +1。
- [ ] **预期管理（写死）**：认证口径 m 很可能 ≤6/9 甚至更少——这不是坏结果，"9 类中仅 m 类能在此样本量下被认证"本身是 honest finding，与论文 honest-negative 风格一致。**不许为了 m 好看事后调 α**。

- [ ] **验收**：预注册 commit 早于校准集生成 commit（git log 可证）；fidelity 门产物存在；认证表+敏感性表落 reports/；method 小节落稿且全部公式可被面试/审稿追问级别地辩护；**07-22 认证数字出来，07-24 落稿完成**（赶不上正文就整节降级进 supplement——预注册和数据不作废）。

---

## W6 全文终校 + 提交 ｜ D13–14（07-27~28）

- [ ] 逐条对照审稿 9 条 weakness + 8 个 question，确认每条：已修复 / Limitations 有明示 scope。
- [ ] W1 的机器检查重跑（空引用、占位引用均零命中）。
- [ ] 数字一致性：Abstract / Fig.1 caption / Table 3 / Conclusion 的 coverage 与 bal-acc 数字互相一致（W3.4 改动后极易漏）。
- [ ] Holm/BH 检验族数字更新（"61-test family" → 实际新数；W2 +24、W7 LTT 族另列，见 7.3）。
- [ ] 匿名检查（投稿版无作者信息、无 acknowledgment、self-citation 匿名化）；`grep -i "surh6\|Ruihan\|Sun Yat-sen" AuthorKit27/submission/main.tex` 零命中。
- [ ] paper/main.tex（tech-report 版）同步所有科学内容改动。
- [ ] **07-28 AoE 提交正文**；**07-31 AoE 提交 supplement**（含 W2 表、W5.2 表、per-cell precision、S1 双路由数、cost table）。

---

## 每日检查点

| 日期 | 应完成 |
|---|---|
| 07-15 | ✅ W1 全部（机器检查通过）；✅ 2.-1(a)(b)：Mac 本地环境 + G7 语料重建过 fidelity 门槛（另 part2/G1 也重建完） |
| 07-16 | ✅ 2.-1(c)：API 通道通、**三**模型 capable 冒烟全过（提前于计划，见 2.-1(c) 表）；⬜ 2.0/2.1 代码（未开始） |
| 07-17 | ✅ **提前于 07-15 完成**：E1 C0_rep 全量数字出炉（G7, qwen3-vl-plus）→ **WIN 方向**（C3=0.92 vs C0_rep-union 0.66 / C0_full 0.67；compute-match+definition-match 双对照均不恢复，C3 反而最省 token）→ 摘要走"排除 test-time compute"措辞 |
| 07-19 | W2 四条件齐 + report；W3.1–3.3 台账拍板完毕；**W7.0 预注册 commit + 校准集生成启动** |
| 07-21 | **摘要提交 OpenReview**（措辞不依赖 LTT 的 m 值）；W3.4 表格审计定稿；W7.1 校准集过 fidelity 门、API 打分跑批中 |
| 07-22 | W7.2 认证表 + 敏感性表出数 |
| 07-24 | W4 完成，正文可通读；**W7.3 method 小节落稿**（赶不上则整节降级 supplement） |
| 07-26 | W5 冻结（做多少算多少） |
| 07-28 | **正文提交** |
| 07-31 | **supplement 提交** |
