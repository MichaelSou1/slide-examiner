# AAAI-27 修订台账（claim ledger）

> **工作流**：本文件是 W3/W4 所有措辞与结构改动的**唯一决策记录**。规则：
> 1. 改动先入账，不直接改 tex。每条记：位置 / 原句 / 新句 / 类型 / 理由。
> 2. 状态列由 Michael 拍板：`拟定` → `已批准` / `否决` / `改用备选`。
> 3. 全部批准后，做**一次**整合写作 pass 落入 `AuthorKit27/submission/main.tex`（用论文原有声音重写受影响段落，不做逐句替换拼贴）。
> 4. 落稿后跑 Michael 的去 AI 味提示词做最后一道纯风格 pass（该 pass 不得再动 claim 强度——强度已在本台账定案）。
> 5. **类型=替换 的条目：新句应不长于原句。类型=追加 的条目要有充分理由**——追加 hedge 是论文变松散的主因。scope 声明全文只允许集中两处：attribution 定义段、Limitations。
>
> W1 的机械修复（空引用 / bib 补 author / S3 矛盾句重写）不过台账，直接落 tex。
> W2 实验段是新增内容，结果出来后按三种预案（TODO 2.4）入账再写。

| # | 位置 | 原句（摘录） | 拟改为 | 类型 | 理由（对应审稿点） | 状态 |
|---|---|---|---|---|---|---|
| L1 | sec:elicit "It is the format, not the eyes" 段末 | "the suppressor is the one-call format, not perception: **the model saw the overflow all along**" | "the suppressor is the one-call format: under an atomic query the same model, on the same image, recovers the detection the rubric call buries"（删除表征级断言，改为可观察行为描述） | 替换 | W2 审稿点：prompt 会改变计算过程，现证据不支持"表征早已形成" | 已落稿（待 Michael 批准） |
| L2 | Abstract | "others vanish the moment we change how we ask, with the model and image frozen" | 保留（这句本身是行为级的，不越界）；但检查 Abstract 是否有 G1/S6 pairwise 被并入 "not the eyes" 总述，若有，单独摘出一句 "a further reference-assisted class recovers only when a clean twin is available" | 替换 | W4 审稿点：pairwise 提供了额外信息，不属于纯 elicitation 恢复 | 已落稿（待 Michael 批准） |
| L3 | sec:setup "Attribution modalities and metric" 段 | "if the model fails on the image alone (A) but succeeds given the oracle (B), the bottleneck is perception" | 同位置加一句操作性定义："We use 'perception-bottlenecked' operationally: the task becomes solvable when the same information is made explicit as lossless structure. This is a diagnosis of which engine can solve the class, not a claim about the model's internal representations."（全文唯一 scope 声明点之一） | 追加（获准的两处之一） | W1 审稿点：oracle 同时改变表示与任务接口；routing 只需引擎级答案 | 已落稿（待 Michael 批准） |
| L4 | 同段脚注 2 附近 | "if it fails under both, the bottleneck is reasoning" | "if it fails under both, the class is unsolved even at the structured interface, and we route it symbolically"（避免断言 reasoning 为唯一原因） | 替换 | W1 审稿点反向：B 失败亦可能是序列/格式问题 | 已落稿（待 Michael 批准） |
| L5 | 全文首次出现处（sec:diag） | "genuinely sub-perceptual" | 首次出现处定义："sub-perceptual (i.e., below the tested models' effective threshold under this protocol)"；其后全文直接用 sub-perceptual 不再重复限定 | 替换+一次性定义 | W9 审稿点：无 human baseline，不能主张普遍知觉阈值；一次定义避免散布 hedge | 已落稿（待 Michael 批准） |
| L6 | sec:elicit G1/S6 段、Abstract、Contributions | "milder availability-of-reference effect"（正文已有）但 Abstract/Contributions 仍并入总叙事 | 三层术语在 Table 1 或 sec:diag 统一定义：sub-perceptual / format-suppressed / reference-assisted；Abstract 与 Contributions 用同一组词，G1/S6 归 reference-assisted | 替换 | W4 审稿点；同时是净收紧（替掉散落的临时限定） | 已落稿（待 Michael 批准） |
| L7 | sec:coverage headline + Abstract + Fig.1 caption + Conclusion | "covers 8 of 9 classes, matching the pre-registered routed hybrid" | 待 Table 3 逐格审计后二选一（TODO 3.4 决策 A/B）：A=改以 mean bal-acc 为 headline（0.85–0.86 vs C0 0.59），coverage 按严格定义如实报；B=改定义为 ≥0.75 并逐格执行。**"matching a pre-registered routed hybrid" 中被 S1 re-route 违反的部分删除或限定为 "pre-registered up to one data-driven correction (S1), which we report both ways"** | 替换 | W5 审稿点 + Q4/Q5：G6=0.75 不满足 exceeds；linter+C3 列 S1 下界 0.63<0.65 | 已落稿（待 Michael 批准） |
| L8 | sec:coverage "A data-driven routing correction" 段 | （正文已如实写 re-route） | 保留现有坦诚写法；补 frozen route 的数字（S1→LLM: 0.25/0.09）进正文或脚注，使两个版本的 coverage 都可算 | 追加（数字补报，非 hedge） | Q3：哪些规则在观察结果前冻结 | 已落稿（待 Michael 批准） |
| L9 | sec:elicit "capable subset" 定义处 | "a model counts as 'capable' only if, under C3, it both detects…" | 加半句："selected on the same test items, so the subset is descriptive rather than confirmatory"（或引用 W5.1 的 held-out 结果，若做了） | 追加（一句内） | Q8/W5：selection bias 声明 | 已落稿（待 Michael 批准） |
| L10 | Conclusion | "turns 'VLMs are bad at layout' into a routing rule" 前后的 "saw all along" 同类表述 | 与 L1 同步：行为级措辞（"recovers under targeted elicitation"） | 替换 | 与 L1 一致性 | 已落稿（待 Michael 批准） |
| L11 | Fig.1 caption | "merely format-suppressed defects are recovered by a vision–language model under a changed elicitation" | 保留（本身是行为级）；只需把 caption 里 "(Sec. )" 空引用修掉（W1 已管） | 不动 | — | 拟定 |
| L12 | sec:g7 reward audit 结论句 | "its detection tracks perceptual capability rather than training domain" | "its detection tracks a rendered-quality read-out rather than the training-domain label, on the scorers tested"（限定在被测 scorer 集合内） | 替换 | W8 审稿点：scorer 数量少、DocReward 容量混淆（正文 Limitations 已认，主文措辞对齐） | 已落稿（待 Michael 批准） |
| L13 | W4 结构：sec:g7 reward audit | 全节约 1 页 | 压至半页：保留同 backbone dissociation（CLIP-IQA vs LAION）+ perturbation fidelity 45%；Table 4 与其余移 Technical Supplement | 结构 | W7：主线过密 | 已落稿（待 Michael 批准） |
| L14 | W4 结构：sec:examiner | 全节约 1 页 | 压缩：保留 in-dist 超 30B、abstain 行为、sim-to-real 负结果三点；训练细节移 supplement | 结构 | W7 | 已落稿（待 Michael 批准） |
| L15 | W2 新增段（sec:elicit） | — | **三 vendor 24 run 全出（`reports/_e2_computematch.md` + `cost_table.md`），赢分支 + 功利口径（07-15/07-16 Michael 两轮定案，详见 TODO 2.4）**：主文双铁证＝① compute 对照只用 **self-consistency（K=10 多数投票，引 Wang et al.）**：C3 三 vendor 全 Holm 显著胜（0.92/0.88/0.83 vs maj 0.61/0.59/0.63，Δ+0.31/+0.29/+0.20）；② **budget**：C3 output tok 34.7/37.5/40.5 三家最省、1 call vs 8–10 calls → 赢的条件最省算力。**主表只三列 C0 / self-consistency / C3**（六格对比三 vendor 全过 Holm，零 n.s.）+ budget 行。**Supplement 完整报**：union 聚合（含 gpt Δ+0.05 n.s. 全部数字）+ 一段解释（union=任一 draw 报警的 OR 聚合，等效放松判定阈值而非增加有效算力——对高保守模型白捡 recall；majority 才是标准 self-consistency 口径，故正文以其为对照；且 C3 以 1 call 打平 union 8.5-call 最好成绩）；C0_full（definition-matched 第二对照）、G1（负控）同进 supplement；Holm 族按全部 24 test 报，不缩族。正文一句指针指向 supplement。禁写：不 headline "decomposition 是机制"；正文不并列 union。段落要点：①对照定义一句 ②三 vendor G7 数字 ③budget 反向一句 ④supplement 指针一句 ⑤模型来源声明（API-served，与 p1e1 不并表） | 新增一段+supplement 表 | W3 审稿点 Q1/Q2：test-time-compute 备择解释被排除且反向 | 已批准（07-16 定稿，待整合 pass 落稿） |
| L16 | Limitations 首句 + sec:diag 相关处 | "No human-inspector reference point is provided" | **在新渲染语料上重标 spot-check（v2）后引用 v2 数字**（Michael 决定 07-15：亲自重标；07-15 晚已完成 v1 标注并确认当前普通 spot-check 的 G3/G5 样本口径失效——G3 7/7、G5 7/7 均 not visible，且 notes 直接指出“bullets 其实对齐”“只有粗细区别没有颜色区别”。因此不重刷 69 对，而改走 replacement：`docs/spotcheck/manifest_g3g5_replacement.json` 已生成；G3 的 8 对已有有效人标 `docs/spotcheck/labels_g3_only_replacement.json`，随后 corrected G5 的 10 对以 `docs/spotcheck/manifest_g5_only_replacement.json` + `annotate_current_g5_only_replacement_zh.html` 重标完成，并导出 `docs/spotcheck/labels_g5_only_replacement_v2.json`。合并后得到 `docs/spotcheck/{manifest_v2,labels_v2}.json`，v2 报告 `reports/_e8_spotcheck_v2.md` / `data/part3/e8_spotcheck_v2.json`，结果为 **73/73 defect-visible、73/73 twin-clean、flagged pairs = 0**；`data/part3/e8_ir_faithfulness_v2.json` 给出 **55/55 source-structure present**。另有 `reports/_e8_spotcheck_v2_delta.md` 证明非替换的旧 55 对一条未变，变化仅限 G3 `0/7 -> 8/8` 与 G5 `0/7 -> 10/10`，即修复的是抽样口径而非整体人标漂移。正文 3–4 句目标不变：G3/G5 用纠正口径的人标结果，G1/S6/G7 保留人工背书，完整表进 supplement；Limitations 句改写。工具链复用 docs/spotcheck/ + part3_spotcheck_*。详见 TODO 3.6 | 替换+新增 3-4 句 | W9 审稿点：从“无人标”推进到“已有 v2 人标 + replacement-v2 收口完成”，且显式记录了为什么必须 replacement 而不是继续沿用错误口径 | 已落稿（待 Michael 批准） |

## 整合 pass 检查单（落稿时用）

- [ ] 每条"替换"型：新句 ≤ 原句长度；没有原句不动+追加从句的情况
- [ ] scope 声明只出现在 L3 位置和 Limitations，其他地方 grep `under this protocol|it is worth noting|we note that` 应零新增
- [x] 三层术语全文一致（投稿版已统一；author 版仍有残留，见 handoff）
- [x] 数字联动：投稿版 Abstract / Table 3 / Conclusion 的 coverage 数字已对齐为 mean bal-acc + strict 6/9 口径；supplement 图注已同步
- [ ] 落稿后跑去 AI 味提示词（纯风格 pass，声明"claim 强度已定案不得改动"）
- [ ] 最后请一个没参与改稿的眼睛（或新开会话的模拟审稿）通读，专查"松散/补丁感"
