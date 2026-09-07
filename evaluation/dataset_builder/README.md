# DRAFT Dataset Builder

独立、scorer-side 的候选数据集构造工具。输入只有原始 Word/Excel 与 Parser JSON，
通过可注入 Profile/Adapter 生成审核材料；不修改生产 Compiler、检索、Coverage、
Binding 或 Explore Runtime，不调用任何被测方案，也不读取它们的回答来构造 Gold。

**Parser JSON 仅用于发现候选，不是 Gold Oracle。Builder 没有 approve 命令，
永远只输出 review_status: DRAFT。**

## 输入与输出

```sh
python -m evaluation.dataset_builder.cli inventory --raw-dir /internal/raw

python -m evaluation.dataset_builder.cli build \
  --raw-dir /internal/raw --parser-json-dir /internal/parser-json \
  --profile /internal/profiles/dataset.yaml --out /internal/scorer/draft-v1

python -m evaluation.dataset_builder.cli validate --dataset-dir /internal/scorer/draft-v1
python -m evaluation.dataset_builder.cli report --dataset-dir /internal/scorer/draft-v1
```

raw 与 parser-json 必须是独立目录；输出必须在二者之外且为空。源文件只读，
构造前后检查路径、大小和 SHA-256。原始输入接受 .doc/.docx/.xls/.xlsx，默认
RawReader 只提取 docx 顶层段落/表格和 xlsx 单元格；旧格式明确 UNSUPPORTED，
不能静默解释成资料不存在。默认读取范围标记 PARTIAL。

| 输出 | 用途 |
|---|---|
| cases.draft.yaml | motif 生成和采样后的 DRAFT Case，含 gold_candidate，不含正式 gold |
| aliases.draft.yaml | DRAFT Alias，冲突列表保留，不自动合并 |
| candidate_entities.json | 所有实体候选、来源、验证范围与发现方式 |
| candidate_relations.json | 有向关系候选及定位；has_field 是 Builder 内部字段归属关系 |
| source_entity_map.json | 原始文档 → 实体/关系/结构单元 ID |
| review_queue.json | 完整审核内容，包括 JSON 来源定位与候选细节 |
| review_queue.xlsx | Cases/Entities/Relations/Aliases 四个 sheet；人工填写 decision/reviewer/notes |
| generation_report.json | 指纹、Profile、全体与采样后质量、漏解析候选、未命中规则与采样排除原因 |

XLSX 是审核视图，长文本提示回查完整 JSON；单元格按文本写入，名称不会作为 Excel
公式执行。Builder 不导入审核决定，也不据此发布 APPROVED Case。

## Candidate Contract

每个实体/关系及 Case 的候选答案保留：

```yaml
id: metric:source-stable-id
source_documents: ["原始资料.xlsx"]
source_locations:
  - {plane: raw, document: "原始资料.xlsx", kind: excel_row, sheet: Sheet1, row: 2}
  - {plane: parser, parser_file: candidate.json, pointer: /entities/0}
generation_method: [profile_parser_entity]
candidate_origin: parser # parser | raw_independent | both
parser_supported: true
raw_verified: false
review_status: DRAFT
```

实体 raw_verified 只表示原文名称或 Alias 在声明结构位置的**字面定位**，不证明实体
类型、身份或业务含义正确。关系只有独立 raw 规则明确匹配时才可标记 raw_verified，
仍然需要人工审核规则含义及方向。Parser 的原始 approval 字段不会继承为审核状态。

只有同类型、Profile 提供的显式稳定 ID 才能连接跨来源记录。缺 ID 的记录获得独立
occurrence ID；相同名称不合并。Alias 通过 NFKC/casefold 检查碰撞，保留全部候选。
raw_independent_only 是**潜在** Parser blind spot，仍需检查是否为身份映射未对齐。
没有配置独立 raw 规则时会明确报告，不能将 blind spot 数量为零解释为 Parser 完整。

## Profiles 与适配接口

[profiles/example.yaml](profiles/example.yaml) 仅展示候选 envelope，不猜测正式 Parser
字段布局。下列配置可以在内部环境修改：

| Profile | 可适配内容 |
|---|---|
| ParserProfile | JSON 文件 glob、记录指针、字段 mapping |
| SourceProfile | Parser 文档名称到 raw 相对路径的映射、独立 raw 规则 |
| EntityMappingProfile | 类型映射、显式 ID namespace |
| RelationMappingProfile | 原始关系类型到候选关系类型的映射 |
| DatasetGenerationProfile | Query 模板、负例审核种子、数量/多样性上限 |

records 使用 JSON Pointer 加 `*` 通配符；空字符串指向当前根。mapping 值为相对当前
record 的 JSON Pointer，`{literal: value}` 表示配置常量，嵌套对象递归映射。
关系端点使用 `{type, id}`，或者已经明确的 candidate canonical ID；不按名称查找端点。

SourceProfile raw_entities/raw_relations 规则可配置 kind、file_glob、sheet_glob、
location_match、start_row、pattern 与 mapping。kind 是 word_paragraph、word_table_row
或 excel_row；表格 record 的 `/1`、`/2` 等为 1-based 列。pattern 的命名捕获组加入
record，例如 `(?P<name>...)` 可由 `/name` 映射。不写真实列名或模型名到 Builder 主流程。

```yaml
source:
  raw_entities:
    - kind: excel_row
      file_glob: '*.xlsx'
      sheet_glob: '内部配置的工作表'
      start_row: 2
      mapping:
        type: {literal: metrics}
        id: /1
        name: /2
```

复杂父子 JSON、旧 Office 格式、文档特殊结构通过 `build(..., parser_reader=...,
raw_reader=...)` 注入 Adapter。RawReader 返回带 document/kind/location/text/record/
unit_id 的结构单元与诊断；ParserReader 返回 entities/relations 映射记录和诊断。
不能把解析失败变成空知识。适配器只读原始输入，输出仍遵守相同 DRAFT 契约。

## Case、Query 与多样性

七类 Case 基于固定、有界 motif：metric_to_model、purpose_to_data、model_to_analysis、
model_to_business、field_discovery、lineage_impact、negative。候选答案由实体/关系
集合确定；QueryGenerator 只接收 category、anchor name 和方向，不接收候选 Gold。
可注入 `paraphraser(query: str) -> str` 改写问题，默认完全不用 LLM；改写前后候选内容
与 construction hash 不变，问题是否保持原意仍要审核。

负例只从 generation.negative_candidates 的人工审核种子生成，必须声明待审核的
source_documents。始终 negative_candidate + requires_human_confirmation:true，
没有 JSON 缺项 → 不存在的生成路径；缺负例种子只会产生配额 Warning。

source_span 根据候选来源并集建议 single_document/cross_document；跨文档自动说明
各文档提供哪些候选，人工必须排除重复材料导致的伪跨文档。来源无法解析时保留
unknown 并显式报错待适配。difficulty_suggested 按来源、hop、实体类型、Alias 歧义
与冲突给 easy/medium/hard，人工可覆盖 difficulty。

Sampler 采用确定性的覆盖增益选择，覆盖 category、technology、topic、business_object、
metric、logical_model、physical_model、source_document、source_span、difficulty。
max_cases_per_entity/document/topic/motif 均可配置；相同归一化 Query 去重，相同
category/hop/实体类型 motif 有上限。目标配额缺口只警告，不自动放宽上限或批准。

## 内部诊断命令

```sh
python -m evaluation.dataset_builder.cli inspect_raw_structure --raw-dir /internal/raw
python -m evaluation.dataset_builder.cli inspect_parser_json \
  --parser-json-dir /internal/parser-json --profile /internal/profiles/dataset.yaml
python -m evaluation.dataset_builder.cli compare_raw_vs_parser --dataset-dir /internal/scorer/draft-v1
python -m evaluation.dataset_builder.cli inspect_entity --dataset-dir /internal/scorer/draft-v1 --id '<candidate-id>'
python -m evaluation.dataset_builder.cli inspect_relation --dataset-dir /internal/scorer/draft-v1 --id '<relation-id>'
python -m evaluation.dataset_builder.cli inspect_case --dataset-dir /internal/scorer/draft-v1 --id '<case-id>'
python -m evaluation.dataset_builder.cli validate_case_sources \
  --dataset-dir /internal/scorer/draft-v1 --raw-dir /internal/raw
```

所有命令输出结构化 JSON。Parser 诊断包含有界结构采样和实际 mapping 结果；
来源校验检查原始文件指纹与结构定位，不作为语义正确性的证明。

## Synthetic/sample 验收

```sh
uv run --isolated --extra dev python -c \
  'from evaluation.dataset_builder.fixtures import create_sample; create_sample("/tmp/builder-sample")'
uv run --isolated --extra dev python -m evaluation.dataset_builder.cli build \
  --raw-dir /tmp/builder-sample/raw --parser-json-dir /tmp/builder-sample/parser-json \
  --profile /tmp/builder-sample/sample-profile.yaml --out /tmp/builder-draft
uv run --isolated --extra dev pytest -q tests/test_dataset_builder.py
```

样例故意在 JSON 中遗漏原始表格中的一个指标与关系，并包含一个 Alias 碰撞和
人工提供的负例审核种子。这些样例只验证工程边界，不是企业 Oracle 或正式 Pilot。
2026-09-07 验证：全量 Python 测试 **170 passed**；实际 CLI 样例生成 **10 个实体候选、
8 个关系候选、8 个 DRAFT Case**，覆盖七类，保留 **1 个 blind spot Case、1 组 Alias
冲突**，DRAFT 与来源校验通过。未使用真实企业文件，也未生成 APPROVED Gold。
人工审核、Debug Pilot 和冻结正式数据集见仓库根目录
[INTERNAL_ADAPTATION_GUIDE.md](../../INTERNAL_ADAPTATION_GUIDE.md)。
