# 历史 Evidence 评测集构建指南

本文件保留旧 Evidence/Oracle 构造流程，仅用于历史分析和回归。当前四方案
Raw E2E 主评测入口见 [README.md](README.md)，本文件中的 CodeGraph 和 Evidence
主指标不属于当前正式 leaderboard。

本目录是交给可访问真实业务资料的 Code Agent 的实施包。目标是构建一套可复现、可审计、不会把候选知识升级为事实的企业数据上下文评测集，用于比较：

- OpenCode Explore；
- OpenViking；
- CodeGraph（企业适配模式，必须标记为 `ADAPTED`）；
- 本仓库的 Enterprise Data Context + Explore Agent；
- 本方案的 Page-only、Flat baseline 等消融变体。

OpenCode Explore 与 OpenViking 的可运行双系统适配、语料导入、断点续跑和报告流程见
[`COMPARISON.md`](COMPARISON.md)。

真实 `source-materials/templates` 到 Evidence 候选、Case 候选和人工审批的自动构造方法见
[`AUTO_CASE_CONSTRUCTION.md`](AUTO_CASE_CONSTRUCTION.md)。

主指标只有三个：

1. Evidence Recall@Budget；
2. Evidence Precision@Budget；
3. Query Tokens。

## 1. 架构与数据边界

本仓库的正式运行边界是外部解析器按 `source-materials/templates/` 五类结构发布的 Template JSON 目录。`ContextFragment` 是消费侧内部 IR，不是外部交付件。评测集构建环境可以读取真实 Word、Excel、数据字典、指标文档和模型设计资料，但不得把原始资料复制到本仓库。

真实环境负责产出：

```text
真实业务资料
  -> 确定性结构解析
  -> 原子 Evidence 记录
  -> Gold 评测案例
  -> 模型设计 Oracle（仅模型设计案例）
  -> 可选：符合 template-input.schema.json 的五类 Template JSON 目录
```

本仓库负责：

```text
JSON Schema 校验
  -> 引用完整性校验
  -> Gold 泄漏隔离
  -> 数据集冻结
  -> 各方案 Adapter 和评测运行
```

禁止事项：

- 不得把 Markdown 说明文档自动当作业务事实，除非数据集负责人明确将其登记为权威源。
- 不得根据“常识”补齐资料中不存在的指标、字段、Join 或加工规则。
- `INFERRED`、`CANDIDATE` 不得进入 `required_evidence`。
- 不得让被测系统读取 `cases.jsonl` 中的 Gold 字段或 `design-oracles.jsonl`。
- 不得为 CodeGraph、OpenViking 或本方案编造其余方案得不到的额外业务关系。
- 不得在提交、日志、示例或错误信息中输出敏感原文、账号、密钥或客户标识。

## 2. 需要的真实输入

最低输入包括：

1. 数据字典：模型、表、字段、类型、主键、粒度、来源、刷新周期；
2. 指标文档：定义、公式、维度、过滤条件、统计粒度、权威版本；
3. 应用场景：业务目标、典型问题、分析对象、所需指标；
4. 映射资料：场景 -> 指标 -> 对象 -> 逻辑模型 -> 物理模型 -> 表 -> 字段；
5. 当前环境资产：实际部署的数据源、模型、表和版本；
6. 已评审模型设计：目标 Schema、Source-to-Target、Join、SQL 或加工逻辑。

先登记权威顺序。例如：已发布指标标准 > 已评审模型设计 > 当前资产目录 > 项目说明 > LLM/人工候选。权威策略必须写入 `dataset-manifest.json`，不能在标注过程中临时改变。

## 3. 评测集组成

一个完整数据集目录如下：

```text
secure-eval-dataset/
├── dataset-manifest.json
├── evidence.jsonl
├── cases.jsonl
└── design-oracles.jsonl
```

- `evidence.jsonl`：原子事实与精确来源位置；
- `cases.jsonl`：查询、预算和 Gold Evidence 集；
- `design-oracles.jsonl`：隐藏的专家模型设计，只供标注和审计；
- `dataset-manifest.json`：版本、来源快照、权威策略和文件声明。

对应契约位于 `evaluation/contracts/`。`evaluation/examples/` 只包含合成数据，不得替换为真实资料后提交到非安全仓库。

## 4. Evidence 构建规则

### 4.1 原子化

一个 Evidence 只表达一个可判定事实。例如：

- `metric:rsrp --provided_by--> physical-model:mr-cell-hour`；
- `field:avg_rsrp --belongs_to--> table:mr_cell_hour`；
- `target-model:nr-cell-hour --grain--> stat_hour + cell_id`。

同一段原文包含多个事实时，应拆成多个 Evidence 记录，但可以共享相同来源位置和内容哈希。

### 4.2 稳定标识

`evidence_id` 在同一数据集版本内必须唯一且稳定。推荐：

```text
ev-<source-id>-<section-or-sheet>-<semantic-slug>-<short-hash>
```

不要使用数组序号作为稳定 ID。

### 4.3 来源位置

至少提供：

- `source_id`；
- `source_version`；
- 脱敏后的相对路径或逻辑 URI；
- Word 的 section/paragraph，Excel 的 sheet/table/row/column/cell，SQL/文本的行号；
- `content_hash`；
- 最短但足以支持事实的 `excerpt`。

### 4.4 状态

- `EXPLICIT`：来源直接陈述；
- `DERIVED`：可由多个明确事实确定性推导，必须列出 `derived_from`；
- `INFERRED`：推测；
- `CANDIDATE`：待评审候选。

只有 `EXPLICIT` 和证据链完整的 `DERIVED` 可以进入案例的 `required_evidence`。候选可以保留在 Evidence 集中，用于验证系统是否错误提升候选，但不能作为 Gold 必需事实。

## 5. 两类评测案例

### 5.1 需求调研 `requirement_research`

正式集建议 120 个基础案例：

| 子类 | 数量 | 内容 |
|---|---:|---|
| `single_layer` | 35 | 场景、指标、对象、逻辑模型、物理模型、表、字段各 5 题 |
| `adjacent_mapping` | 30 | 六种相邻或反向映射各 5 题 |
| `multi_layer` | 35 | 覆盖 3 到 7 层的真实需求调研 |
| `environment_gap_conflict` | 20 | 当前环境、部分缺失、完全无答案、多源冲突 |

层级标签统一使用：

```text
scenario, metric, business_object, logical_model, physical_model,
table, field, dimension, grain, lineage, processing_logic,
environment_asset
```

### 5.2 模型设计准备 `model_design_preparation`

正式集建议 80 个基础案例：

| 子类 | 数量 | 内容 |
|---|---:|---|
| `schema_context` | 20 | 粒度、键、维度、度量、类型、分区、命名规范 |
| `processing_context` | 20 | 来源、字段映射、Join、公式、过滤、聚合、时间、去重 |
| `full_design_context` | 20 | 完整目标模型所需 Context Bundle |
| `reuse_and_change` | 10 | 复用、扩展、合并、影响分析 |
| `insufficient_context` | 10 | 来源粒度不足、关键映射缺失、规则冲突 |

Explore 的 Gold 是“完成设计必须召回的证据”，不是最终 Schema 文本。每个模型设计案例必须有一个隐藏 Oracle，记录专家认可的目标粒度、字段类别、来源、Join 和加工步骤。Oracle 只用于反向确定 `required_evidence`，不得作为输入交给被测系统。

## 6. Gold Evidence 集合

每个案例包含：

- `required_evidence`：完成任务不可缺少，Recall 的分母；
- `allowed_relevant_evidence`：有帮助但非最低必需，不应被 Precision 当作噪声；
- `forbidden_evidence`：已知错误、过期、冲突中被否决或候选事实；
- `expected_missing`：资料确实缺少的上下文类别；
- `expected_conflicts`：必须披露的冲突组。

主指标：

```text
Evidence Recall@Budget
= 命中的 required_evidence / required_evidence 总数

Evidence Precision@Budget
= 命中的 required_evidence 或 allowed_relevant_evidence / 返回 Evidence 总数
```

负样本没有 `required_evidence`：正确返回空 Evidence 时 Precision 记为 1；返回伪相关 Evidence 时 Precision 记为 0；负样本不参与 Recall 平均。

## 7. 预算与难度

| 难度 | 典型范围 | `context_token_budget` |
|---|---|---:|
| `S` | 单层、精确实体 | 2048 |
| `M` | 相邻关系、Schema/加工局部问题 | 4096 |
| `L` | 多层调研、完整模型设计 | 8192 |

同一案例的所有被测方案必须使用相同预算。Query Tokens 统计查询阶段所有 LLM input/output tokens，加上最终交付给上层 Agent 的上下文 Token。索引构建 Token 单独记录，不进入主排名。

## 8. 构建流程

### 阶段 0：冻结输入

1. 为所有原始资料分配 `source_id` 和 `source_version`；
2. 计算文件哈希；
3. 只读挂载原始资料；
4. 建立脱敏路径映射；
5. 在 manifest 中写明权威策略和来源快照。

### 阶段 1：构建 Evidence

1. Word/Excel 结构解析必须确定性执行；
2. 提取原子事实和精确位置；
3. 建立实体、关系、公式、字段和加工规则 Evidence；
4. LLM 只可提出候选，不可自动审批；
5. 两名业务评审者确认 Gold，冲突交第三人裁决；
6. 只有 `review_status=APPROVED` 的事实可进入 `required_evidence`。

### 阶段 2：构建案例

1. 先选择真实用户任务，再编写查询；
2. 为每题确定层级、难度、预算和环境范围；
3. 标注 required/allowed/forbidden Evidence；
4. 模型设计题建立独立 Oracle；
5. 查询至少有一个业务表达版本，避免全是精确编码搜索；
6. 同一业务事实的改写问题作为 `query_variants`，不要重复计为多个独立基础案例。

### 阶段 3：防止 Gold 泄漏

运行时只向被测系统提供：

```text
query + environment_scope + context_token_budget
```

禁止提供：

```text
required_evidence
allowed_relevant_evidence
forbidden_evidence
expected_missing
expected_conflicts
design_oracle
review_notes
```

### 阶段 4：验证和冻结

在本仓库或安全环境运行：

```bash
uv run --isolated --extra dev python evaluation/scripts/validate_dataset.py \
  --dataset-dir /secure/path/to/secure-eval-dataset
```

校验通过后冻结数据集版本，不允许原地修改。任何 Gold 修改都发布新版本并记录变更原因。

## 9. Pilot 与验收

第一轮 Pilot 使用 60 个基础案例：

- 需求调研 36：单层 12、相邻 8、多层 10、环境/缺失/冲突 6；
- 模型设计 24：Schema 6、加工逻辑 6、完整设计 6、复用变更 3、上下文不足 3。

数据集发布前必须满足：

- Schema 校验 100% 通过；
- Evidence ID、Case ID 唯一；
- 所有 Evidence 引用可解析；
- required/allowed/forbidden 不重叠；
- 正例至少有一个 required Evidence；
- 模型设计题恰好有一个 Oracle；
- 所有 required/allowed Evidence 均为 `APPROVED`；
- `CANDIDATE/INFERRED` 不进入 required Evidence；
- 原始敏感资料未写入非安全仓库；
- 至少一名数据领域专家完成最终签署。

## 10. 交付物

真实环境最终只需交付以下脱敏或受控文件：

1. 数据集 manifest；
2. Evidence JSONL；
3. Cases JSONL；
4. Design Oracle JSONL；
5. 可选 Template JSON 交付目录；
6. 校验日志；
7. 来源、版本、权威策略和评审记录摘要。

如果真实资料不能离开受控环境，评测运行器也应部署在受控环境，只带回聚合指标和脱敏错误摘要。
