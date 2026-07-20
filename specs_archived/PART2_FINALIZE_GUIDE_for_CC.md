# Part 2 收尾返修指引(交给 Claude Code 执行)

> 背景:Part 1(SlideProbe 诊断)与 Part 2(examiner QLoRA 训练)已产出真实结果(`reports/slideprobe.md`, `reports/part2.md`)。本指引**不改训练好的模型**,只补三类必须在进入 Part 3 之前完成的收尾工作:(1) 救 H2 真实迁移,(2) 补统计严谨性,(3) 补 deck 级语义控制。每个任务给出锚点文件、改法、验收标准。**按 P0 → P1 → P2 顺序做,P0 不过不要开 Part 3。**

---

## P0-1｜救 H2:带结构的真实迁移评测(最高优先级)

**问题**:`reports/part2.md` Table 5(SlideAudit 真实迁移)全部在 0.5 附近。但 SlideAudit 是 image-only(无元素结构),而 examiner 的设计运行态是模态 B/C(图+结构)+ linter。当前 Table 5 等于用"裸真实像素"测一个"本就该配结构跑"的模型,既不公平也踩中 H2 的证伪线(`specs/SPEC_*.md` H2:合成→真实迁移 F1<0.5 则 sim2real gap 成为主发现)。**不补这一格,H2 悬而未决,审稿人会直接攻这里。**

**要做的**:
1. 在 `slide_examiner/data_prep.py` 已有的 clean-corpus 流程基础上,新增一条**带结构的真实迁移评测集**构造路径:
   - 数据源优先级:① 脱敏实习 deck(`data_sources.py` 里 `internal_desensitized`,有原生 pptx → 可经 `ingest.py` 的 PPTX 几何抽取得到真实结构);② Zenodo10K 清洗子集(同样走 PPTX→IR 抽结构)。
   - 关键:这批样本必须**保留真实元素结构**(bbox/text/style),从而支持模态 B/C 评测——这正是 SlideAudit 缺的。
   - 缺陷标签:真实 deck 没有注入标签。两条路二选一或并用:(a) 用 Part 1 已验证的几何 linter 在真实 deck 上自动标 G 组(linter 在 Part 1 是 detector of record,0 FP,可信);(b) 语义 S 组需少量人工标(见 P0-2 的标注协议),先标 page 级 S1/S4,deck 级 S2/S5 留到 P2。
2. 在评测 harness(`probe.py` / `orchestrator.py` 路径)上增加对这批集的 **模态 C** 跑法,产出 `reports/part2_real_transfer_structured.md`,表格列与 Table 5 对齐但增加 modality 列(A vs C 对照)。

**验收标准**:
- 产出 ft-8b / zs-8b / zs-30b 在真实 deck **模态 C** 下的 bal-acc(带 n 与 95% CI)。
- 报告必须明确写出二选一结论:**(i)** 模态 C 真实迁移显著高于模态 A(Table 5)→ 故事闭合:"sim2real gap 来自缺结构,非缺能力",H2 以"结构化设定下迁移成立"通过;**(ii)** 模态 C 也崩 → 诚实记为 sim2real 主发现,H2 触发证伪分支,在报告显式声明。
- 不允许只在 limitation 里一句话带过。

---

## P0-2｜真实语义标注协议 + panel 落地

**问题**:`slide_examiner/panel.py` 存在但 `eval/panel_ratings.jsonl` 不存在(404)——panel 聚合代码有、真实标注数据没有。P0-1 的语义真实迁移依赖它。

**要做的**:
1. 写一份**极简标注协议**(`docs/annotation_protocol.md`):每个 (page, defect_type) 给 present/absent/uncertain 三选一;每样本 ≥2 人标,取 strong-agreement(全一致)作正负例,uncertain 或分歧样本入灰区不计入主指标。这与 Table 5 已用的 "strong-agreement present/absent" 口径一致,保持可比。
2. 规模:page 级 S1/S4 各 ≥30 正 + ≥30 负(够 P0-1 出 CI 即可,不求大)。deck 级 S2/S5 留 P2。
3. 标注产物落 `eval/panel_ratings.jsonl`,字段对齐 `panel.py` 的 `panel eval` 期望 schema;跑 `slide-examiner panel eval/panel_ratings.jsonl -o reports/panel_summary.json` 验证可聚合。

**验收标准**:`panel summary` 能跑通且报告 inter-annotator agreement(κ 或一致率);P0-1 的语义格能引用这批 ground truth。

---

## P1-1｜统计严谨性:所有进 paper 的数字补 n 与 CI

**问题**:`reports/part2.md` / `reports/slideprobe.md` 大量 1.000、0.5 等点估计无样本量、无区间。Table 3 的 2-AFC、Table 1 的若干 1.000 尤其需要——**裸的"完美分数"在审稿时是减分项**。仓库已有 `power.py`(两比例样本量)和 `statistics.py`(方差门控),基建齐了,缺的是把它接到报告生成。

**要做的**:
1. 在 `analysis.py` / `reports.py` 的指标产出处,为每个 balanced-accuracy / 2-AFC 单元格附带:`n`(该格样本数)、Wilson 95% CI(二项比例,适合小样本和近 1.0/0.0 的格)。
2. 报告渲染(`reports.py`)的表格统一改为 `value [lo, hi] (n=k)` 形式。对 n<10 的格加显式标注(如 `†` 脚注"n<10, 解释性而非确证")。
3. 对每一对"ft-8b vs zs-30b"的 headline 对比(如语义 0.99 vs 0.785),跑一次两比例显著性(McNemar 若配对,否则 two-proportion z),报 p 值。这件事你主线 internalization 实验做过,直接复用范式。

**验收标准**:`reports/part2.md` 与 `reports/slideprobe.md` 重新生成后,**无任何裸点估计**;headline 对比带 p 值;n<10 的格已标注。

---

## P1-2｜冻结评测配置,防止"各自最优 prompt"被质疑

**问题**:`reports/part2.md` Notes 写明 "finetuned 在 trained prompt format,zero-shot 在 scoped format 评测"。这是合理的(各用各的 intended setup),但**审稿人会问:是不是给 ft-8b 挑了有利 prompt?** 需要一次对称性检查兜底。

**要做的**:加一个对照——zero-shot 基线**也**在 ft-8b 的 trained format 上跑一遍(即使它没被训练成这个格式),作为 robustness 附录。若 zs 在两种 format 下都输 → 优势来自能力非 prompt,主 claim 稳。把结果放 `reports/part2_prompt_robustness.md`。

**验收标准**:附录表证明 ft-8b 优势在 zs 的 best-of-formats 下依然成立,或诚实记录差距缩小幅度。

---

## P2-1｜补 deck 级语义(S2/S5)的 paired-clean 控制

**问题**:`reports/part2.md` 与 `slideprobe.md` 中 deck-scope 语义(S2 叙事顺序 / S5 逻辑缺段)多处显示 "—"。`part2.md` Limitations 已自承:"deck-scope 多页样本的 paired-clean 控制未由 eval harness 构造"。但 S2/S5 恰是"推理瓶颈"故事里最该有的两类,缺了语义结论只站在 page 级 S1/S4 上,单薄。

**要做的**:
1. 在 eval harness(构造 paired-clean 的那段,定位 `dataset.py` / `synthetic.py` 里负样本/clean 配对逻辑)扩展到 **deck 粒度**:一个 deck 级 defective 样本(打乱页序 / 删章节)需配一个同源 clean deck 作配对控制,balanced accuracy 才能算。
2. 跑 ft-8b / zs 基线在 S2/S5 上的 deck 级 bal-acc,回填 `reports/part2.md` Table 4 的 `ood_defect`/deck 行与 `slideprobe.md` Table 1 deck 级行。

**验收标准**:S2/S5 不再是 "—";deck 级语义有真实数字(带 n/CI)。若 S2/S5 也证伪某假设,如实记录。

---

## P2-2｜S3 路由的最终归位确认(已基本完成,仅核对)

`reports/slideprobe.md` 已把 S3 术语一致性踢出 VLM、改 `slide_examiner/term_consistency.py` 符号 linter(bal-acc 1.0 vs VLM 0.69)。**这是项目最漂亮的负例处理之一,无需改,仅核对两点**:
1. `--glossary` 企业术语表变体和 text-LLM 模糊漂移(K8s/Kubernetes)兜底是否有最小测试覆盖(`tests/` 下)。
2. 确认 S3 已从 examiner 的 `check_scope` 默认集中移除(避免 examiner 仍被喂 S3),路由到 term-linter。

---

## 收尾产物清单(P0–P2 完成后应存在)

- `reports/part2_real_transfer_structured.md`(P0-1,带结构真实迁移,模态 A vs C)
- `eval/panel_ratings.jsonl` + `reports/panel_summary.json`(P0-2)
- `docs/annotation_protocol.md`(P0-2)
- 重新生成的 `reports/part2.md` / `reports/slideprobe.md`(P1-1,全部带 n/CI/p)
- `reports/part2_prompt_robustness.md`(P1-2)
- 回填 deck 级 S2/S5 的 `reports/part2.md` Table 4(P2-1)

---

## 给 CC 的执行纪律

1. **不重训模型**:本轮全部是评测/统计/数据补齐,Part 2 的 ft-8b v2 权重冻结。任何需要重训的发现先记 issue,不在本轮动。
2. **诚实负例优先**:若 P0-1 模态 C 真实迁移仍崩、或 P2-1 的 S2/S5 翻车,**如实写进报告并触发对应假设的证伪分支**,不得粉饰。这套项目的可信度建立在 S3/position-bias 这类负例上,继续保持。
3. **每个数字可溯源**:报告里每个表格单元格能回指到产生它的 run JSONL 与样本数。
4. **改报告生成而非手改报告**:数字进 `analysis.py`/`reports.py` 的生成逻辑,报告由命令重新渲染,不手工编辑 md 里的数字。
5. 改完跑 `slide-examiner audit` + `pytest` 确认入口面与契约测试不破。

---

## 完成后才进入 Part 3(预告,本轮不做)

Part 1/2 的数据已经改写了 Part 3 的 hybrid 条件设计:examiner 的优势经证实**全在语义 pointwise + 结构化设定**,几何它学到的是"弃权(0 FPR 不幻觉)"。因此 Part 3 的 hybrid 反馈源应落成**数据推导出的精确分工**——G 组→linter、S1/S2/S4/S5/S6→ft-8b examiner、S3→符号 term-linter——而非原 spec 的笼统五档。这个分工每条边界都有 Part 1/2 背书,GEPA 要验证的是"它作为 ASI 源收敛是否快于任一单源"。待 P0–P2 收尾后另起 Part 3 指引。
