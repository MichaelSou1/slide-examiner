# Slide-Examiner I/O 接口契约(返修依据 v1.1)

> 用途:这份文档是 examiner 输入/输出的**唯一事实来源**。训练数据生成、运行时 client 调用、GEPA ASI 解析三处都必须引用本契约。
> 技术栈假设:examiner = 微调后的 Qwen3-VL-8B,vLLM serve(OpenAI 兼容多模态端点)。下面用 Pydantic v2 作 schema 单一来源:同一组 model 同时用于(a)生成训练标签、(b)解析运行时输出,保证"训练标签格式 == 运行时输出格式"。
>
> v1.1 相对 v1.0 的关键修订:拆分 page/deck 两级 I/O;severity 从连续分数改为有序档位;Element 显式禁止 oracle 泄漏;补 render spec;规范 evidence 生成,避免把 ASI 训成模板套话。

-----

## 0. 五条硬不变量(返修首先核对)

**INV-1｜运行时一律模态 C**:运行时调用必须同时提供「渲染图 + 结构化表示」。结构是生成 slide 时已知的 actual render state(bbox/text/style),不需要从图反推。

**INV-2｜训练数据必须混入模态 A**:训练集中需按比例(建议 page 级和 deck 级各自 A >= 30%)加入「只给图、不给结构」的样本,强制 examiner 练视觉通道。否则模型会学成只读结构字段,运行时遇到结构缺失、图文不一致或渲染误差即失效。

**INV-3｜训练标签格式 == 运行时输出格式**:训练样本 assistant 轮就是运行时要 parse 的 JSON。用同一个 `PageExamResult` / `DeckExamResult` / `PairwiseResult` model 序列化训练标签、反序列化运行时输出。

**INV-4｜检查粒度必须匹配缺陷粒度**:page 级 request 只承接 page-local 缺陷;deck 级 request 承接跨页语义缺陷。不要让单页 I/O 硬查 deck 级问题。

**INV-5｜输入只含实际态,严禁答案泄漏**:`Element` / page / deck 的结构化输入只能包含实际渲染态和运行时本来可得的任务上下文,禁止携带 `expected_*`、注入标志、正确答案、缺陷标签、修复提示等字段。合成数据必须经 `oracle_view()` 或等价过滤后才能进入模态 B/C。

-----

## 1. 缺陷粒度与职责边界

|粒度|缺陷类型|推荐运行时处理|
|---|---|---|
|page|G1_TEXT_OVERFLOW, G2_ELEMENT_OVERLAP, G3_ALIGNMENT_OFFSET, G4_FONT_SIZE_INCONSISTENCY, G5_BRAND_COLOR_VIOLATION, G6_MARGIN_VIOLATION|G 组主力交给符号 linter;examiner 用于训练/归因、兜底与交叉验证|
|page|S1_TITLE_BODY_MISMATCH, S4_DENSITY_RULE_VIOLATION, S6_IMAGE_TEXT_CONTRADICTION|examiner page 模式|
|deck|S2_NARRATIVE_ORDER_BREAK, S3_TERMINOLOGY_INCONSISTENCY, S5_MISSING_LOGIC_SECTION|examiner deck 模式|

`deck_outline` 只给标题列表不足以训练 S2/S3/S5。deck 模式必须看到全 deck 的可见文本摘要、页序、关键术语/实体、必要时的缩略图或结构化元素摘要。

-----

## 2. 枚举(共享同一份定义,不要为改名制造 churn)

DefectType 的字符串值沿用当前代码库 `taxonomy.py` 的稳定 ID,训练、serving、client 三处只 import 一份定义,不要各自硬编码。

```python
from enum import Enum

class DefectType(str, Enum):
    # G 组 - 几何/感知类
    G1_TEXT_OVERFLOW = "G1_TEXT_OVERFLOW"
    G2_ELEMENT_OVERLAP = "G2_ELEMENT_OVERLAP"
    G3_ALIGNMENT_OFFSET = "G3_ALIGNMENT_OFFSET"
    G4_FONT_SIZE_INCONSISTENCY = "G4_FONT_SIZE_INCONSISTENCY"
    G5_BRAND_COLOR_VIOLATION = "G5_BRAND_COLOR_VIOLATION"
    G6_MARGIN_VIOLATION = "G6_MARGIN_VIOLATION"

    # S 组 - 语义/推理类
    S1_TITLE_BODY_MISMATCH = "S1_TITLE_BODY_MISMATCH"
    S2_NARRATIVE_ORDER_BREAK = "S2_NARRATIVE_ORDER_BREAK"
    S3_TERMINOLOGY_INCONSISTENCY = "S3_TERMINOLOGY_INCONSISTENCY"
    S4_DENSITY_RULE_VIOLATION = "S4_DENSITY_RULE_VIOLATION"
    S5_MISSING_LOGIC_SECTION = "S5_MISSING_LOGIC_SECTION"
    S6_IMAGE_TEXT_CONTRADICTION = "S6_IMAGE_TEXT_CONTRADICTION"

class ElementType(str, Enum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    BODY = "body"
    IMAGE = "image"
    TABLE = "table"
    CHART = "chart"
    SHAPE = "shape"
    ICON = "icon"
    FOOTER = "footer"
    OTHER = "other"

class Scene(str, Enum):
    LAUNCH = "launch"
    CLIENT_INTRO = "client_intro"
    FULL_PROPOSAL = "full_proposal"

class Modality(str, Enum):
    A_IMAGE_ONLY = "A"       # 只给渲染图/缩略图
    B_STRUCT_ONLY = "B"      # 只给 oracle_view 后的结构
    C_BOTH = "C"             # 图 + 结构;运行时恒 C
    B_CAPTION_ONLY = "B_prime"  # 归因对照臂:自然语言 caption oracle,不作为主训练格式

class ExamMode(str, Enum):
    POINTWISE = "pointwise"
    PAIRWISE = "pairwise"

class ExamLevel(str, Enum):
    PAGE = "page"
    DECK = "deck"

class SeverityLevel(str, Enum):
    NONE = "none"        # 仅用于汇总/无缺陷维度;Finding 内不得使用
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"

class Dimension(str, Enum):
    TEXT_FIT = "text_fit"
    OVERLAP = "overlap"
    ALIGNMENT = "alignment"
    TYPOGRAPHY = "typography"
    BRAND_COLOR = "brand_color"
    MARGINS = "margins"
    TITLE_BODY = "title_body"
    NARRATIVE_ORDER = "narrative_order"
    TERMINOLOGY = "terminology"
    DENSITY = "density"
    MISSING_SECTION = "missing_section"
    FIGURE_TEXT = "figure_text"
```

-----

## 3. 坐标与渲染约定

- bbox 一律是**渲染图像素坐标**,不是 EMU、不是归一化坐标。
- 为贴合当前 IR,序列化采用 `{x, y, width, height}`。`x/y` 可以为负或超过画布,用于表达出界/贴边问题;`width/height >= 0`。
- `RenderSpec` 必须随 request 一起传。即使模态 B 没有图片,bbox 仍以该 render spec 的像素空间解释。
- 训练样本的图片、bbox、render scale 必须来自同一次渲染配置。若图是 1920x1080,bbox 就必须按 1920x1080 像素解释。

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal

class BBoxPx(BaseModel):
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)

class RenderSpec(BaseModel):
    image_width_px: int = Field(gt=0)
    image_height_px: int = Field(gt=0)
    scale_x: float = Field(gt=0)  # source slide unit -> render pixel 的水平缩放
    scale_y: float = Field(gt=0)  # source slide unit -> render pixel 的垂直缩放
    dpi: Optional[float] = None
    renderer: Optional[str] = None
```

-----

## 4. 输入契约

### 4.1 Element:只放实际渲染态

`Element` 是 examiner 可见的"完美感知"结构,不是标签容器。禁止自由 `metadata` 直接透传给模型。

```python
class Element(BaseModel):
    element_id: str
    type: ElementType
    bbox: BBoxPx
    text: Optional[str] = None
    font_size_pt: Optional[float] = None
    font_color_hex: Optional[str] = None
    fill_color_hex: Optional[str] = None
    font_family: Optional[str] = None
    z_index: Optional[int] = None
    placeholder_role: Optional[str] = None
    content_summary: Optional[str] = None  # 图/表/图表的实际可见内容摘要,不得含答案
```

**禁止进入 examiner 输入的字段/模式**:

- `expected_*`, `correct_*`, `target_*`
- `defect`, `defect_type`, `labels`, `label`, `severity`, `repair_hint`
- `narrative_order_broken`, `swapped_indices`, `missing_section`
- `canonical_term`, `variant_term` 等由注入器写入的答案键
- `placeholder_bbox` 这类"应然位置/参考位置"

任务本来就有的需求可以进入 `DeckContext.task_brief` 或 `DeckContext.required_sections`,但必须来自生成前的用户需求/项目 brief,不能来自注入器 ground truth。

### 4.2 Page 级请求

```python
PAGE_SCOPED_DEFECTS = {
    DefectType.G1_TEXT_OVERFLOW,
    DefectType.G2_ELEMENT_OVERLAP,
    DefectType.G3_ALIGNMENT_OFFSET,
    DefectType.G4_FONT_SIZE_INCONSISTENCY,
    DefectType.G5_BRAND_COLOR_VIOLATION,
    DefectType.G6_MARGIN_VIOLATION,
    DefectType.S1_TITLE_BODY_MISMATCH,
    DefectType.S4_DENSITY_RULE_VIOLATION,
    DefectType.S6_IMAGE_TEXT_CONTRADICTION,
}

class PageContext(BaseModel):
    scene: Scene
    template_id: Optional[str] = None
    deck_id: Optional[str] = None
    page_index: Optional[int] = None
    task_brief: Optional[str] = None

class PageExamRequest(BaseModel):
    page_id: str
    render: RenderSpec
    image_png_base64: Optional[str] = None       # 模态 A/C 必填;模态 B 为 None
    elements: Optional[list[Element]] = None     # 模态 B/C 必填;模态 A 为 None
    context: PageContext
    check_scope: list[DefectType] = Field(default_factory=lambda: sorted(PAGE_SCOPED_DEFECTS, key=lambda d: d.value))
    mode: Literal[ExamMode.POINTWISE] = ExamMode.POINTWISE
    level: Literal[ExamLevel.PAGE] = ExamLevel.PAGE
    modality: Modality = Modality.C_BOTH
```

### 4.3 Deck 级请求

deck 模式用于 S2/S3/S5。它看的是全 deck 内容流,不是某一页截图的附带上下文。

```python
DECK_SCOPED_DEFECTS = {
    DefectType.S2_NARRATIVE_ORDER_BREAK,
    DefectType.S3_TERMINOLOGY_INCONSISTENCY,
    DefectType.S5_MISSING_LOGIC_SECTION,
}

class DeckPageInput(BaseModel):
    page_id: str
    page_index: int
    render: Optional[RenderSpec] = None
    image_png_base64: Optional[str] = None       # 模态 A/C 可用缩略图或低分辨率页图
    elements: Optional[list[Element]] = None     # 模态 B/C 的结构化 actual state
    title_text: Optional[str] = None
    visible_text: Optional[str] = None
    key_terms: list[str] = Field(default_factory=list)
    figure_summaries: list[str] = Field(default_factory=list)

class DeckContext(BaseModel):
    scene: Scene
    template_id: Optional[str] = None
    task_brief: Optional[str] = None
    required_sections: list[str] = Field(default_factory=list)  # 仅限生成前 brief
    project_glossary: dict[str, list[str]] = Field(default_factory=dict)  # 仅限生成前 glossary

class DeckExamRequest(BaseModel):
    deck_id: str
    pages: list[DeckPageInput]
    context: DeckContext
    check_scope: list[DefectType] = Field(default_factory=lambda: sorted(DECK_SCOPED_DEFECTS, key=lambda d: d.value))
    mode: Literal[ExamMode.POINTWISE] = ExamMode.POINTWISE
    level: Literal[ExamLevel.DECK] = ExamLevel.DECK
    modality: Modality = Modality.C_BOTH
```

Deck 请求不要求每页都传完整 1920x1080 图。可用缩略图 + 结构化文本摘要降低 token,但训练与运行必须共用同一个构造函数,避免分布漂移。

-----

## 5. 输出契约(= 训练标签格式)

### 5.1 Finding 与定位

```python
class Locator(BaseModel):
    level: ExamLevel
    page_id: Optional[str] = None
    element_id: Optional[str] = None
    bbox: Optional[BBoxPx] = None
    related_page_ids: list[str] = Field(default_factory=list)

class Finding(BaseModel):
    type: DefectType
    severity: SeverityLevel       # Finding 内只允许 minor/moderate/severe
    locator: Locator
    evidence: str                 # 非空、具体、接地图像/文本事实
    fix_suggestion: str           # 非空、可执行

class PageExamResult(BaseModel):
    page_id: str
    has_defect: bool
    findings: list[Finding] = Field(default_factory=list)
    clean_dimensions: list[Dimension] = Field(default_factory=list)
    # 不变式:
    # 1. has_defect == (len(findings) > 0)
    # 2. findings[*].type in PAGE_SCOPED_DEFECTS
    # 3. findings[*].locator.level == "page"

class DeckExamResult(BaseModel):
    deck_id: str
    has_defect: bool
    findings: list[Finding] = Field(default_factory=list)
    clean_dimensions: list[Dimension] = Field(default_factory=list)
    # 不变式:
    # 1. has_defect == (len(findings) > 0)
    # 2. findings[*].type in DECK_SCOPED_DEFECTS
    # 3. findings[*].locator.level == "deck"
```

`clean_dimensions` 必须用固定 `Dimension` 枚举,不要输出自由字符串。正向信号只表示本次 `check_scope` 中明确检查过且未发现问题的维度。

### 5.2 Pairwise 输出

Pairwise 用于 GEPA 离线选优、多变体选择和"相对判断优于绝对打分"的实验臂。不要用 pairwise 替代 pointwise 缺陷定位。

```python
class PairwiseChoice(str, Enum):
    A = "A"
    B = "B"
    TIE = "tie"

class PairwiseResult(BaseModel):
    level: ExamLevel
    subject_id: str       # page_id 或 deck_id
    better: PairwiseChoice
    reason: str
    per_dimension: dict[Dimension, PairwiseChoice] = Field(default_factory=dict)
```

-----

## 6. severity 语义与训练标签生成

examiner 输出有序档位,不输出连续 0-1 分数。连续 `theta` / `severity_score` 仍保留在 manifest 或 eval metadata 中,用于心理物理曲线、linter 阈值和离线分析,但不进入 `target_json`。

### 6.1 G 组:由注入参数确定档位

|缺陷|注入参数 theta|minor|moderate|severe|
|---|---|---|---|---|
|G1_TEXT_OVERFLOW|溢出 Δpx in {4,8,16,32,64}|4,8|16,32|64|
|G2_ELEMENT_OVERLAP|IoU in {0.05,0.1,0.2,0.4}|0.05|0.1,0.2|0.4|
|G3_ALIGNMENT_OFFSET|偏移 Δpx in {2,4,8,16,32}|2,4|8,16|32|
|G4_FONT_SIZE_INCONSISTENCY|字号差 Δpt in {1,2,4,8}|1|2,4|8|
|G5_BRAND_COLOR_VIOLATION|色差 ΔE in {3,6,12,24}|3|6,12|24|
|G6_MARGIN_VIOLATION|边距/出界 Δpx in {4,8,16,32}|4,8|16|32|

### 6.2 S 组:由注入器或任务规则确定档位

- S1/S2/S3/S5/S6:注入器在制造缺陷时直接标注 `minor/moderate/severe`,判定规则写在注入器配置中。
- S4:按场景密度阈值的超出比例定档,建议 `<=20% minor`, `20-50% moderate`, `>50% severe`。
- 真实 deck 人工标注时也使用同一三档 rubric,不要让标注员给连续分。

运行时若下游需要排序,使用 `(severity_rank, finding_count, pairwise_result, linter_numeric)` 组合,不要把 examiner 的 ordinal 输出重新伪装成精确连续分数。

-----

## 7. evidence / fix_suggestion 生成约束

`evidence` 是 GEPA reflection 的 ASI,不能训练成模板套话。

训练标签生成流程:

1. 注入器产生结构化槽位:缺陷类型、页面/元素、可见文本、theta、相关页等。这些槽位只用于造标签,不得进入模型输入。
2. `fix_suggestion` 可用模板填槽生成,因为修法通常机械且需要稳定。
3. `evidence` 必须由强模型或规则+改写生成自然语言依据,并满足:
   - 非空,且不是只复述缺陷名;
   - 至少引用一个可见事实:页号/元素/文本片段/术语变体/相关页面顺序/图文冲突点;
   - 措辞多样,同类缺陷不能全是同一模板;
   - 不包含 `expected_*`、注入参数名、hidden metadata key。
4. 生成后跑 validator:检查 evidence 长度、是否命中可见事实、是否泄漏 forbidden keys。失败样本重写或丢弃。

建议离线记录 `evidence_quality` 指标,例如 grounded-token 命中率、模板重复率、平均信息量;该指标不进入模型输出 schema。

-----

## 8. 序列化:Request -> vLLM 多模态消息

训练与运行时必须共用同一个 serializer。不要 page 训练一套 prompt、runtime 又手写另一套 prompt。

```python
SYSTEM_PROMPT_PAGE = (
    "You are a slide quality examiner. Inspect the given single slide page for "
    "the requested page-scoped defect types. Output ONLY one valid JSON object "
    "matching PageExamResult. No prose, no code fences."
)

SYSTEM_PROMPT_DECK = (
    "You are a slide deck quality examiner. Inspect the whole deck for the "
    "requested deck-scoped defect types. Output ONLY one valid JSON object "
    "matching DeckExamResult. No prose, no code fences."
)

def serialize_bbox(b: BBoxPx) -> str:
    return f"x={b.x} y={b.y} w={b.width} h={b.height}"

def serialize_render(r: RenderSpec) -> str:
    return (
        f"render={r.image_width_px}x{r.image_height_px} "
        f"scale=({r.scale_x},{r.scale_y}) dpi={r.dpi} renderer={r.renderer}"
    )

def serialize_elements(elements: list[Element]) -> str:
    lines = []
    for e in sorted(elements, key=lambda item: item.element_id):
        lines.append(
            f"[{e.element_id}] type={e.type.value} bbox=({serialize_bbox(e.bbox)}) "
            f"font={e.font_size_pt}pt color={e.font_color_hex} fill={e.fill_color_hex} "
            f"role={e.placeholder_role} z={e.z_index} text={e.text!r} "
            f"summary={e.content_summary!r}"
        )
    return "\n".join(lines)

def build_page_messages(req: PageExamRequest) -> list[dict]:
    content = []
    if req.modality in (Modality.A_IMAGE_ONLY, Modality.C_BOTH):
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{req.image_png_base64}"}})

    struct_txt = ""
    if req.modality in (Modality.B_STRUCT_ONLY, Modality.C_BOTH):
        struct_txt = "ELEMENTS:\n" + serialize_elements(req.elements or []) + "\n"

    instruction = (
        f"PAGE_ID: {req.page_id}\n"
        f"{serialize_render(req.render)}\n"
        f"{struct_txt}"
        f"SCENE: {req.context.scene.value}\n"
        f"TEMPLATE_ID: {req.context.template_id}\n"
        f"PAGE_INDEX: {req.context.page_index}\n"
        f"TASK_BRIEF: {req.context.task_brief}\n"
        f"CHECK_SCOPE: {[d.value for d in req.check_scope]}\n"
    )
    content.append({"type": "text", "text": instruction})
    return [{"role": "system", "content": SYSTEM_PROMPT_PAGE},
            {"role": "user", "content": content}]

def build_deck_messages(req: DeckExamRequest) -> list[dict]:
    content = []
    page_blocks = []
    for page in sorted(req.pages, key=lambda item: item.page_index):
        if req.modality in (Modality.A_IMAGE_ONLY, Modality.C_BOTH) and page.image_png_base64:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{page.image_png_base64}"}})

        elements_txt = ""
        if req.modality in (Modality.B_STRUCT_ONLY, Modality.C_BOTH) and page.elements:
            elements_txt = "\nELEMENTS:\n" + serialize_elements(page.elements)

        page_blocks.append(
            f"PAGE {page.page_index} id={page.page_id}\n"
            f"TITLE: {page.title_text}\n"
            f"VISIBLE_TEXT: {page.visible_text}\n"
            f"KEY_TERMS: {page.key_terms}\n"
            f"FIGURES: {page.figure_summaries}"
            f"{elements_txt}"
        )

    instruction = (
        f"DECK_ID: {req.deck_id}\n"
        f"SCENE: {req.context.scene.value}\n"
        f"TEMPLATE_ID: {req.context.template_id}\n"
        f"TASK_BRIEF: {req.context.task_brief}\n"
        f"REQUIRED_SECTIONS: {req.context.required_sections}\n"
        f"PROJECT_GLOSSARY: {req.context.project_glossary}\n"
        f"CHECK_SCOPE: {[d.value for d in req.check_scope]}\n\n"
        + "\n\n".join(page_blocks)
    )
    content.append({"type": "text", "text": instruction})
    return [{"role": "system", "content": SYSTEM_PROMPT_DECK},
            {"role": "user", "content": content}]
```

Pairwise 模式同理:同一 `level` 下放 A/B 两份候选图与结构,输出 `PairwiseResult`。A/B 的 serializer 也必须与 pointwise 共用底层函数。

-----

## 9. 反序列化与校验

```python
import json
import re

def _load_json_object(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.MULTILINE).strip()
    return json.loads(s)

def parse_page_result(raw: str) -> PageExamResult:
    res = PageExamResult(**_load_json_object(raw))
    assert res.has_defect == (len(res.findings) > 0)
    for finding in res.findings:
        assert finding.type in PAGE_SCOPED_DEFECTS
        assert finding.severity != SeverityLevel.NONE
        assert finding.locator.level == ExamLevel.PAGE
        assert finding.evidence.strip()
        assert finding.fix_suggestion.strip()
    return res

def parse_deck_result(raw: str) -> DeckExamResult:
    res = DeckExamResult(**_load_json_object(raw))
    assert res.has_defect == (len(res.findings) > 0)
    for finding in res.findings:
        assert finding.type in DECK_SCOPED_DEFECTS
        assert finding.severity != SeverityLevel.NONE
        assert finding.locator.level == ExamLevel.DECK
        assert finding.evidence.strip()
        assert finding.fix_suggestion.strip()
    return res
```

解析或校验失败时,带"OUTPUT VALID JSON ONLY AND MATCH THE GIVEN SCHEMA"重试 1-2 次;仍失败则记为 examiner 故障样本,不要静默吞掉或返回空结果。

-----

## 10. 训练样本落盘格式

一条训练样本 = `(messages, target_json, metadata)`:

- page 样本:`messages = build_page_messages(req)`, `target_json = PageExamResult(...).model_dump_json()`。
- deck 样本:`messages = build_deck_messages(req)`, `target_json = DeckExamResult(...).model_dump_json()`。
- `metadata` 保存实验用信息,如 `defect_type`, `theta`, `severity_score`, `split`, `source_deck`, `modality`, `exam_level`。这些字段**不得**出现在 assistant target JSON 中,也不得出现在 B/C 的结构化输入中。

LLaMA-Factory 多模态 SFT 落地时,assistant 轮内容就是 `target_json` 字符串。核对点:生成脚本吐出的 target 能否被 §9 parser 无错解析;不能则按本契约改生成脚本。

采样建议:

- page 数据集中 A >= 30%,B/C 按归因和运行需求采样。
- deck 数据集中 A >= 30%,A 可用全 deck 缩略图序列;B 使用 deck 文本/结构摘要;C 使用缩略图 + 结构摘要。
- S2/S3/S5 不再用"第一页图 + deck_outline"凑 page 样本,必须生成 deck 样本。

-----

## 11. 运行时调用建议

1. 对每页先跑符号 linter 查 G1-G6,保留连续几何量用于排序和修复。
2. 对每页调用 `PageExamRequest(check_scope=[DefectType.S1_TITLE_BODY_MISMATCH, DefectType.S4_DENSITY_RULE_VIOLATION, DefectType.S6_IMAGE_TEXT_CONTRADICTION])`;需要 examiner 兜底几何时再把相关 G 类型加入 scope。
3. 对整 deck 调用 `DeckExamRequest(check_scope=[DefectType.S2_NARRATIVE_ORDER_BREAK, DefectType.S3_TERMINOLOGY_INCONSISTENCY, DefectType.S5_MISSING_LOGIC_SECTION])`。
4. 聚合时保留来源: `source = linter | page_examiner | deck_examiner | pairwise_examiner`。不要把 deck finding 强行贴到某一页,除非 locator 给出 `related_page_ids`。
5. GEPA ASI 优先消费 `evidence + fix_suggestion`;排序优先用 pairwise 或 ordinal severity,不要依赖 examiner 连续分。

-----

## 12. 返修检查清单

1. **[INV-3]** 训练标签结构与运行时输出解析是否共用同一组 Pydantic model?若两套,合并。
1. **[INV-4]** S2/S3/S5 是否已迁移到 deck 级 request/result?若还用单页输入,先改。
1. **[INV-5]** B/C 结构化输入是否经过 `oracle_view()` 或等价过滤?是否禁止 `expected_*`、缺陷标志、修复提示进入模型输入?
1. **[§3]** bbox 是否为渲染像素坐标?`RenderSpec` 是否随样本记录并与图片对齐?
1. **[INV-2]** page/deck 两类训练数据是否都混入模态 A,且 A >= 30%?
1. **[§5/§6]** 输出 severity 是否为 `minor/moderate/severe` 档位,连续 theta 是否只留在 metadata/eval 中?
1. **[§7]** evidence 是否非空、接地、非纯模板?是否有 validator 防泄漏和防套话?
1. **[§8]** 训练与运行时是否共用同一个 `build_page_messages` / `build_deck_messages`?
1. **[§5]** `has_defect == (len(findings)>0)` 是否在序列化前和解析后都断言?
1. **[§9]** 解析失败是否有重试 + 故障记录,而非静默返回空/默认值?
1. **[枚举]** `DefectType` / `Dimension` / `SeverityLevel` 是否训练、serving、client 三处共享同一份定义?
1. **[运行时]** G 组是否由 linter 主查,examiner 只做语义、兜底和交叉验证?GEPA 是否消费 evidence/fix_suggestion 而非连续分?
