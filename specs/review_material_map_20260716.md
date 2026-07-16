# W4 审稿点 ↔ 现成材料配对清单（2026-07-16）

目的：执行 `TODO_aaai27_revision.md` 的 W4 第 1 条——先清点 `reports/`，把**审稿点 / 问题**与**现成可回收材料**对上，优先用“3–4 句正文 + supplement 一张表/一段”买回分数，而不是再开新实验。

本清单只记录**当前真实状态**，刻意区分：

- **已落主文**：`AuthorKit27/submission/main.tex` 已有对应文字。
- **已落 supplement**：`AuthorKit27/submission/supplement.tex` 已有对应表/节/图。
- **报告已就绪，尚未落 supplement**：`reports/`/`data/` 里已有数字，但 PDF supplement 里还没有显式表格。
- **仍需新工作**：当前没有可直接回收的成品，不能假装已经有。

---

## 一、按 Weakness 配对

| 审稿点 | 现成材料 | 当前状态 | W4 可直接怎么用 |
|---|---|---|---|
| **W1** attribution / oracle 定义不清，容易被读成 internal-representation claim | `revision_ledger_aaai27.md` 的 L3/L4；`AuthorKit27/submission/main.tex` 的 attribution 定义段 | **已落主文** | 不再补实验。W4 只需确保这类 scope 说明仍只出现两处，不在别处反复加 hedge。 |
| **W2** “saw it all along”/表征级因果措辞过强 | ledger L1/L10；`reports/_e1_decomp.md`（naming vs pairing）；`main.tex` 已改成行为级描述 | **已落主文**；`_e1_decomp.md` 为补充证据 | 正文保持现在的行为级口径即可；若要补一条 supplement 指针，可引用 `reports/_e1_decomp.md` 的 naming/pairing 分解，但不是当前最缺口。 |
| **W3** C0/C3 没有 compute-matched 对照（对应 **Q1/Q2**） | `reports/_e2_computematch.md`、`reports/cost_table.md`、`data/part3/p1e2_summary.json` | **主文已落 1 段**；**完整表仍未落 supplement** | 这是 W4 最值得补回的现成材料之一：正文已有结论，补充材料里应显式放一张三 vendor 的 compute-matched 表，外加 budget 行；union / C0_full / G1 negative control 可放 appendix 风格表。 |
| **W4** pairwise 不是纯 elicitation，而是多了 clean reference | `reports/_e1_decomp.md`；`main.tex` 现已把 G1/S6 改成 **reference-assisted**，把 G7 保留为 format-suppressed | **已落主文** | 不需要再新算。W4 只要保证 Abstract / Conclusion / Fig.1 caption 不把 G1/S6 再混回 “not the eyes” 总叙事。 |
| **W5** coverage 有选择偏差 / 定义漏洞（对应 **Q4/Q5**） | `main.tex` 当前 Table 3 严格口径（mean bal-acc + strict 6/9）；`reports/_e8_table2_cells.md`（G3/G5 corrected cells）；`reports/_p2_tables.md`（含 per-cell precision，但标明 G3/G5/G6/S6 已 stale）；`reports/part3_multiplicity.md`（61-test family）；`revision_ledger_aaai27.md` L7/L8/L9 | **已落主文主结论**；**per-cell precision 尚未落 PDF supplement** | 这是另一个高价值补口：coverage headline 已在主文纠正，但 reviewer 想看的“逐格证据”还应在 supplement 更显式。至少要把 per-cell precision 从“Code and Data Supplement”前移为 PDF supplement 一表或一段。 |
| **W6** 结构过满 / 主线被杂项挤压 | `revision_ledger_aaai27.md` L13/L14；`specs/PAPER_SPINE.md`；`reports/part3_hybrid.md`、`reports/part2.md`（都能支撑裁剪时的保底口径） | **尚未执行压缩** | W4 真正该做的是“把已有材料往 supplement 搬”，不是再扩写：G7 reward audit 留 CLIP-IQA vs LAION + 45% perturbation-fidelity；examiner 节只保留 30B、abstain、sim2real negative 三点。 |
| **W7** 小样本 / 小 n 过度阐释 | `reports/part2.md`（`†` 小样本标记、CI）、`reports/_p1_tables.md`（Wilson CI + n）、`main.tex` 当前 small-cell wording | **已基本落主文** | 不必新做，只需在 W4 压缩时不要把 small-n caveat 删掉。 |
| **W8** reward audit 的外推过强：scorer 数量有限、DocReward 容量/域标签混淆 | `supplement.tex` 已有 `Full multi-reward / VLM-judge audit grid`；`reports/part3_multiplicity.md`；ledger L12 | **已落主文 + 已落 supplement** | 这块材料已经够用。W4 只需在主文继续坚持现在的 scoped wording，不要重新写回“perceptual capability rather than training domain”那种大话。 |
| **W9** 没有人类 spot-check / human baseline | `reports/_e8_spotcheck_v2.md`、`reports/_e8_spotcheck_v2_delta.md`、`data/part3/e8_spotcheck_v2.json`、`data/part3/e8_ir_faithfulness_v2.json`；`supplement.tex` 的 `Human spot-check v2`；`main.tex` 新 limitations/diag 文字 | **已落主文 + 已落 supplement** | 已经是这轮最完整收口的一项。W4 不需要再加料，只需避免后续压缩时把它挤掉。 |

---

## 二、按 Questions 配对

| 问题 | 现成材料 | 当前状态 | 备注 |
|---|---|---|---|
| **Q1** C3 会不会只是比 C0 花了更多 test-time compute？ | `reports/_e2_computematch.md` 主表（self-consistency vs C3）、`reports/cost_table.md` | **证据齐，但 supplement 未显式成表** | 和 Q2 一起补一张表最划算。 |
| **Q2** 还有 definition-matched / union / budget 这些对照吗？ | 同上，外加 `_e2_computematch.md` 的 C0_full / union / budget 段 | **报告有，PDF supplement 暂无** | 这正是 W4 应优先搬进 supplement 的现成材料。 |
| **Q3** 哪些 route 是事先冻结的，哪些是 data-driven correction？ | `main.tex` 现有 `A data-driven routing correction` 段；ledger L8；S1 frozen-route 数字已在正文（0.25 / 0.09） | **已落主文** | 如果 W4 还有脚注空间，可在 supplement 单独列 frozen vs corrected route 一小表，但不是最紧缺项。 |
| **Q4** “covered” 的阈值/定义是不是事后改的？ | `main.tex` Table 3 现已用 strict rule；ledger L7；`reports/part3_multiplicity.md` | **已落主文** | 主要问题已修；W4 要做的是让 supporting evidence 更显眼，而不是重辩定义。 |
| **Q5** per-cell precision 真的在 supplement 吗？ | `reports/_p2_tables.md`、`reports/part2.md`、`reports/_e8_table2_cells.md` 都有 precision；`supplement.tex` 目前只有一句 “Per-cell precision ... in the Code and Data Supplement” | **当前答案：不在 PDF supplement，只有代码补充材料** | 这是当前最明确的缺口之一。若 reviewer 期待 PDF supplement，这一项现在还不能算“完全买回”。 |
| **Q6** SlideAudit 完整逐类表在哪？ | `reports/_p2_tables.md` 的 Result 2b；`reports/part2.md` Table 5；`supplement.tex` 当前只有 SlideAudit crosswalk + open-world figure，没有完整 per-class table | **报告有；PDF supplement 尚无完整逐类表** | 与 Q5 类似，都是“材料已经有，但还没进 PDF supplement”。W5.2 就是这个缺口。 |
| **Q7** frozen-route held-out 呢？ | 目前只有 TODO/W7 计划；尚无 `e9_ltt` 产物 | **仍需新工作** | 不能假装已有。当前唯一诚实说法是：已并入 W7 LTT，尚未出数。 |
| **Q8** capable subset / selected-on-same-test-items 的选择偏差 | ledger L9；`main.tex` 现已加 “descriptive rather than confirmatory” 口径 | **已落主文** | 这是写作层修复，不需要新表。 |

---

## 三、对 W4 的直接执行建议（按回报率排序）

### 第一优先级：立刻能补回、且 reviewer 最容易在 supplement 里找的两项

1. **把 W2/Q1/Q2 的 compute-matched 表显式放进 `supplement.tex`**
   - 现成来源：`reports/_e2_computematch.md` + `reports/cost_table.md`
   - 最小可用版本：
     - 一张主表：3 vendor × {C0, self-consistency, C3, Δ}
     - 一行 budget：calls/slide + output tok/slide
     - 文中一句：union / C0_full / G1 negative control 也完整报告于 code-and-data supplement 或 appendix 段

2. **把 Q5/Q6 关心的 per-cell precision / SlideAudit per-class table 放进 `supplement.tex`**
   - 现成来源：`reports/_p2_tables.md` Result 2b + `reports/part2.md` Table 5
   - 注意：`_p2_tables.md` 已明确标了 **G3/G5/G6/S6 的 synth coverage cells 是 stale**；
     所以如果补表，应该优先补：
     - **SlideAudit real-data per-class table**（不受 E8 stale 影响）
     - 或者只补 **Table 3 的 precision companion table**，并用 corrected E8 cells 覆盖 G3/G5

### 第二优先级：正文减负而不丢论证

3. **G7 reward audit 在正文只留两个钉子**
   - CLIP-IQA vs LAION（同 backbone dissociation）
   - perturbation-fidelity 45%
   - 其余 scorer 细格全部由 supplement 现有 reward table 承接。

4. **examiner 节只留三点**
   - in-distribution 超 30B
   - abstain behavior
   - sim-to-real negative
   - deck-scope / training detail 一律交给现有 supplement `Full page-semantic examiner table`。

### 第三优先级：当前不要假装已经有的内容

5. **Q7 held-out / LTT 仍是新工作，不属于“回收旧材料”**
   - 当前只能在正文/回复里如实说“已并入 W7，尚未出数”。

---

## 四、结论：哪些点已经买回，哪些点还差最后一脚

### 已基本买回

- W1 / W2 / W4 / W7 / W8 / W9
- Q3 / Q4 / Q8

### 材料已存在，但还差“落到 PDF supplement”这最后一脚

- **W3 / Q1 / Q2**：compute-matched full table
- **W5 / Q5**：per-cell precision 明示表
- **Q6**：SlideAudit 完整逐类表

### 仍是未来工作，不应伪装为已解决

- **Q7**：frozen-route held-out / LTT 认证结果

这意味着 W4 的最高回报动作非常明确：

> **不要再开新实验；把已经在 `reports/` 里的 compute-matched 表、per-cell precision、SlideAudit per-class table 补进 `supplement.tex`，同时把正文的 G7 reward / examiner 叙述压短。**
