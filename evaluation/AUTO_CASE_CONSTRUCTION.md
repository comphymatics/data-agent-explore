# 基于完整 Template JSON 的评测用例自动构造方法

## 1. 目标和自动化边界

输入是 `source-materials/templates` 中五类完整 Template JSON：应用场景、KPI/KQI、表字段、建模文档和 SID 业务对象。输出是可进入 OpenCode Explore / OpenViking 对比测评的 Evidence、Case 和模型设计 Oracle。

自动化分成四个阶段：

```text
Template JSON
  -> DRAFT 原子 Evidence 候选
  -> Evidence 人工审批
  -> DRAFT Case/Gold 候选
  -> 查询改写 + Gold/Oracle 人工审批
  -> 冻结评测集
```

程序可以自动完成结构校验、原子拆分、实体关系图、路径采样、案例骨架、拟议 Gold、配额统计和泄漏检查。以下事项不能自动批准：

- 来源权威性；
- 同名实体是否为同一业务实体；
- `DERIVED` 证据链是否充分；
- “资料缺失”是否代表真实缺失；
- 冲突采用哪个版本；
- 模型设计 Oracle 是否正确。

因此生成物始终为 `DRAFT/CANDIDATE`，不能直接作为正式 Gold。

## 2. 输入要求

完整目录必须继续符合 `contracts/template-input.schema.json`：

```text
source-materials/templates/
├── APP售前说明书*.json
├── KPI-KQI*.json
├── tables*.json
├── 建模文档*.json
├── sid_knowledge_base.json
└── *Schema.json
```

文件名包含 `Schema` 的文件只描述结构，不作为事实输入。真实数据到位后先冻结目录、文件哈希和来源版本，不要在构造过程中原地修改。

仅靠这五类模板可以构造“全局企业上下文”案例，但不能可靠构造所有 `current_environment`、缺失和负样本。若要覆盖这些题型，还需要额外提供：

- 当前环境实际部署的数据源、模型、表和版本清单；
- 全量覆盖声明，例如“该清单包含环境内全部可查询模型”；
- 环境资产到全局物理模型的已审批映射；
- 已评审的新模型设计，用于隐藏 Oracle。

没有全量覆盖声明时，“模板中没出现”只能记为 `expected_missing` 的待确认候选，不能作为不存在的 Gold。

模板的关键覆盖关系是：

| 模板 | 主要实体/关系 | 主要生成场景 |
|---|---|---|
| APP | 应用、场景、指标 | 需求调研入口 |
| KPI/KQI | 指标、Counter、维度、公式、字段 | 指标定义和计算链路 |
| tables | 物理模型、逻辑模型、表字段、粒度、来源、加工逻辑 | 表字段调研、Schema、加工逻辑 |
| 建模文档 | 分析目的、指标、测量点、接口、探针、维度 | 多层需求和设计复用 |
| SID | 业务对象、属性、物理模型映射 | 对象到模型映射 |

## 3. 阶段一：自动生成 Evidence 候选

运行：

```bash
uv run --isolated --extra dev python evaluation/scripts/generate_evidence_candidates.py \
  --templates /secure/source-materials/templates \
  --output-dir /secure/eval-work/evidence-candidates
```

可使用 `--authority authority.json` 覆盖临时权威等级。该文件是 `source_type -> rank` 的 JSON 对象。默认等级只是工作值，必须由项目治理人员确认。

输出：

```text
evidence-candidates/
├── evidence-candidates.jsonl
└── evidence-construction-report.json
```

确定性拆分规则：

- Template Reference 每条转换为一个主体—关系—客体 Evidence；
- 表或模型的每个字段产生 `has_field` Evidence；
- 字段类型、描述、来源列、加工逻辑分别产生字段属性 Evidence；
- 粒度、公式、上游模型、业务对象映射分别独立成 Evidence；
- Evidence ID 由来源、JSON Pointer、Fragment ID 和语义内容哈希生成；
- 来源版本使用 Template 文件 SHA-256；
- 所有记录均为 `review_status=DRAFT`；
- 无完整 `derived_from` 的自动派生内容降为 `CANDIDATE`。

CodeAgent 随后逐条执行：

1. 对照 JSON Pointer 核验 statement 和 excerpt；
2. 合并语义重复 Evidence，拆分非原子 Evidence；
3. 处理同义词和同名异义实体；
4. 核验来源类型、版本、权威等级；
5. 为 `DERIVED` 补齐 `derived_from`；
6. 人工评审后才改为 `APPROVED` 并填写真实 reviewer。

审批后的文件保存为安全评测目录的 `evidence.jsonl`。

实体归一必须在生成 Case 前完成：同义名称使用同一 canonical `entity_id`，同名异义实体使用不同 ID。否则路径生成器只能按当前 entity ID 连边，跨文档链路会被错误断开。

## 4. 阶段二：自动生成 Case 候选

只有 `APPROVED + EXPLICIT` 或证据链完整的 `APPROVED + DERIVED` Evidence 才参与拟议 Gold：

```bash
uv run --isolated --extra dev python evaluation/scripts/generate_case_candidates.py \
  --evidence /secure/eval-work/evidence.jsonl \
  --quotas evaluation/construction/pilot-quotas.json \
  --output-dir /secure/eval-work/case-candidates
```

输出：

```text
case-candidates/
├── candidate-cases.jsonl
├── case-blueprints.jsonl
└── construction-report.json
```

`candidate-cases.jsonl` 已符合 Case JSON Schema，但全部为 `DRAFT`。`case-blueprints.jsonl` 额外包含 Evidence 摘要、自动生成版本、Oracle 要求和人工检查项，只供构造和审核，不进入被测语料。

## 5. 用例生成算法

### 5.1 单层问题

从标量事实生成，例如指标定义、公式、粒度、字段类型。每题默认一个 Required Evidence。

### 5.2 相邻映射

从一条已审批实体边生成，例如：

```text
scenario -> metric
metric -> physical_model
physical_model -> table
table -> field
business_object -> physical_model
```

### 5.3 多层需求调研

在 Evidence 图上执行无环、有限深度路径采样：

- 路径长度3～6条 Evidence；
- 不做 LLM 逐节点遍历；
- 正反向关系都可用于发现路径，但 Gold 保留原始方向；
- 同一 Evidence 集只生成一个基础案例；
- 路径之外、与路径节点相邻的已审批 Evidence 可进入 Allowed；
- 只有明确的 `CANDIDATE/INFERRED/REJECTED` 才能自动进入 Forbidden。

### 5.4 模型设计准备

以物理模型、表或已存在的目标模型为锚点，在两跳 Evidence 邻域内分类：

- Schema 类：字段、粒度、键、维度、类型、分区、存储；
- Processing 类：公式、来源、上游、映射、Join、过滤、聚合、去重；
- 同时覆盖两类且证据达到最低数量时，生成 Full Design 候选。

模型设计 Case 的 Required Evidence 表示“完成设计前必须找回的上下文”，不表示自动生成的 Schema 就是正确答案。

### 5.5 缺失、冲突和负样本

仅当来源明确声明 `missing/unavailable/conflict/inconsistent` 时自动生成候选。不能因为当前模板中没有某个字段，就推断企业中不存在该字段。

`insufficient_context`、负样本和大部分冲突题需要数据覆盖声明或人工设计。生成器会把未满足数量写入 `quota_deficits`，CodeAgent 必须报告缺口，不能自动编造题目填满配额。

## 6. CodeAgent 查询改写约束

自动查询只是种子。CodeAgent 可以将其改写成自然业务表达，但必须满足：

- 只能改 `query/query_variants`，不得自行增加 Required Evidence；
- 查询中不得出现 `evidence_id`、Gold 数量、JSON Pointer 或文件名提示；
- 同一基础案例至少保留一个非精确编码表达；
- 改写前后意图和 Required Evidence 必须一致；
- 不得把答案、表名或字段名直接写进本应考察发现能力的问题；
- 一个改写版本不作为新的独立基础案例。

推荐让 CodeAgent 对每个 Blueprint 输出：

```json
{
  "blueprint_id": "...",
  "rewritten_query": "...",
  "query_variants": ["..."],
  "gold_change_requested": false,
  "review_notes": ["..."]
}
```

如果认为 Gold 不足，CodeAgent 只能提出 `gold_change_requested=true` 和理由，由人工复核 Evidence 后调整。

## 7. 模型设计 Oracle 构造

每个模型设计 Case 必须创建一个独立 `design-oracles.jsonl` 记录。构造顺序是：

1. 专家先独立完成目标模型设计；
2. 标记粒度、键、字段角色、来源、Join、加工步骤；
3. 每一项关联支持它的 Evidence ID；
4. 无证据支持的决策进入 `missing_decisions`；
5. Oracle 审批后才能把对应 Case 改为 `APPROVED`。

CodeAgent 可以从已审批设计文档预填 Oracle，但不得填写虚构的 Join、字段类型、过滤条件或聚合规则。

## 8. 配额和抽样

默认 Pilot 配额位于 `evaluation/construction/pilot-quotas.json`，目标为36个需求调研案例和24个模型设计案例。

选择过程按以下优先级确定性排序：

1. 层级覆盖更多；
2. Required Evidence 更完整；
3. 稳定 Case ID。

真实数据建议额外做来源和实体去重：同一指标、模型或来源文档不超过对应子类的20%，避免大量近重复问题主导总分。

## 9. 审批与冻结

最终转正前必须完成：

- 两名业务评审者确认查询和 Required/Allowed/Forbidden；
- 模型设计 Case 有且仅有一个已评审 Oracle；
- `quota_deficits` 已补齐或书面接受；
- 查询和检索语料不包含 Gold 字段；
- 运行数据集校验器；
- 冻结 manifest、文件哈希和数据集版本。

```bash
uv run --isolated --extra dev python evaluation/scripts/validate_dataset.py \
  --dataset-dir /secure/eval-dataset
```

只有校验通过的冻结数据集才能进入 OpenCode Explore / OpenViking 正式比较。
