# 内部真实数据适配指南

本阶段外部开发只用 synthetic/sample fixture。真实 Word/Excel、Parser JSON、
候选审核与正式 Pilot 在内部环境完成。内部 Claude Code 主要修改 Profile、Adapter
和 Mapping，不重新设计 Dataset Builder 或生产 Context/Explore 架构。

在内部仓库 checkout 中安装依赖并激活环境后执行下文命令：

```sh
uv sync --extra dev
source .venv/bin/activate
```

正式四方案的原生服务、模型缓存与隔离 launcher 按内部部署配置接入；Builder 本身
不需要 LLM 或真实服务即可完成候选构造。

## 1. 内部真实文件放在哪里

建议使用独立于 Git 仓库与被测系统 workspace 的私有目录，例如：

```text
/srv/data-explore-internal/
  raw/                       # 原始 Word / Excel，保留原始字节
  parser-json/               # 对应正式 Parser 的交付，独立目录
  profiles/dataset.yaml      # 内部文档/Parser 适配配置
  scorer/draft-v1/            # Builder 输出，禁止提供给被测系统
  scorer/reviewed-debug/      # 人工审核的 10–15 个 Case
  scorer/reviewed-60/         # 人工审核的正式 Case/Alias
  frozen/pilot-v1/            # 冻结的 raw、scorer 文件与指纹清单
  runs/                      # 预检/Debug/正式运行输出
```

真实文件、密钥与审核答案不提交到外部 Git 仓库。Raw 目录不能混入 Parser JSON、
Gold、Alias、Review Queue 或预计算 Context。指纹清单输出到 raw 目录之外。

```sh
python -m evaluation.dataset_builder.cli inventory \
  --raw-dir /srv/data-explore-internal/raw
python -m evaluation.dataset_builder.cli inspect_raw_structure \
  --raw-dir /srv/data-explore-internal/raw
```

## 2. Parser JSON 如何接入

先检查真实 JSON 的结构及来源字段，再配置 ParserProfile：

```sh
python -m evaluation.dataset_builder.cli inspect_parser_json \
  --parser-json-dir /srv/data-explore-internal/parser-json \
  --profile /srv/data-explore-internal/profiles/dataset.yaml
```

将记录位置、实体稳定 ID、名称、类型、Alias、关系端点和 source locations 映射到
Builder 的候选 envelope。source_documents 必须能解析为 raw 相对路径；Parser 文件名
不能自动冒充原始 Word/Excel 名。没有来源定位时保留未验证状态，回到原始资料校准。

复杂嵌套、父级 ID 继承等在内部 ParserReader Adapter 完成，调用
`build(..., parser_reader=adapter)`，不扩展生产 Compiler。正式评测中的 Data Explore
仍必须 Raw → 正式 Domain Parser → Template → Compiler；Dataset Builder 使用的
JSON 仅是 scorer-side 候选发现输入，不能直接作为被测方案的外部输入或 Oracle。

## 3. 哪些 Profile 允许修改

允许修改 ParserProfile、SourceProfile、EntityMappingProfile、RelationMappingProfile、
DatasetGenerationProfile。参见
[配置样例](evaluation/dataset_builder/profiles/example.yaml) 和
[Builder README](evaluation/dataset_builder/README.md)。

真实文档的工作表、表格位置、列、正则、名称变体、技术域/主题映射都配置化。
RawReader 默认只读取部分结构，遇到旧格式、标题/文本框/复杂表头时实现内部只读
Adapter；不得把 UNSUPPORTED/UNREADABLE 解释为空知识。独立 raw 规则不能依赖
Parser 已发现的实体列表，否则无法检验 Parser blind spot。

同类型显式稳定 ID 可连接多份材料；相同名称、Alias 或物理/逻辑模型同名不能
自动证明身份相同。对 alias_collision 人工消歧，保留多个实体直到证据充分。

## 4. 哪些核心 Contract 不允许修改

保持 Compiler、Template Contract、Canonical Context、Rich Context Page、Hierarchy、
Graph-for-Machines、四个 Context Tools、Serving/Hybrid、Coverage、Binding、Snapshot
Governance 和 Explore Runtime 不变。Graph 不向 LLM 暴露逐节点遍历接口。

Builder 不变边界：DRAFT-only、Parser 不是 Oracle、来源可追溯、Query 与候选答案
构造分离、负例必须人工确认、Alias 不自动合并。评测输出与成本继续使用现有公共
协议。未知材料状态不能推断成真实环境不存在，Reference-only 不提升为当前资产。

## 5. 如何生成 DRAFT Dataset

```sh
python -m evaluation.dataset_builder.cli build \
  --raw-dir /srv/data-explore-internal/raw \
  --parser-json-dir /srv/data-explore-internal/parser-json \
  --profile /srv/data-explore-internal/profiles/dataset.yaml \
  --out /srv/data-explore-internal/scorer/draft-v1
python -m evaluation.dataset_builder.cli validate \
  --dataset-dir /srv/data-explore-internal/scorer/draft-v1
python -m evaluation.dataset_builder.cli report \
  --dataset-dir /srv/data-explore-internal/scorer/draft-v1
```

每次构造使用新目录。检查配额缺口、实体/文档/主题集中度、未验证候选、原始读取
限制和未命中 Profile 规则。调整多样性上限及规则，不通过硬编码真实 Case 修补主流程。
负例通过 generation.negative_candidates 提供待审核问题和 raw 文档范围；没有种子时
允许负例配额不足，不能利用 Parser JSON 缺项自动制造“不存在”的答案。

## 6. 如何做人工 Review

在 review_queue.xlsx 中填写 review_decision、reviewer、review_notes，完整来源和候选
载荷查 review_queue.json。人工核对：

- 原始文档是否支持实体类型、身份、模型/字段和有向关系；不能仅查看 Parser JSON。
- raw_verified 只是字面定位或已配置规则匹配，不等于语义正确；查看其 scope。
- Query 改写是否保持原意，候选答案是否遗漏原文中 Parser 未抽取的信息。
- 跨文档是否确实需要多个来源，还是同一事实重复出现；据此修正 source_span。
- Alias 是否有歧义；负例是否仅说明当前材料不能确定，而非宣称环境资产不存在。

定位命令示例：

```sh
python -m evaluation.dataset_builder.cli compare_raw_vs_parser --dataset-dir /srv/data-explore-internal/scorer/draft-v1
python -m evaluation.dataset_builder.cli inspect_case --dataset-dir /srv/data-explore-internal/scorer/draft-v1 --id '<case-id>'
python -m evaluation.dataset_builder.cli validate_case_sources \
  --dataset-dir /srv/data-explore-internal/scorer/draft-v1 --raw-dir /srv/data-explore-internal/raw
```

raw_independent_only 先排除稳定 ID 未对齐；确认以后再记为 Parser blind spot。
difficulty_suggested 仅供参考，审核人员可覆盖 difficulty 并说明理由。

## 7. 如何 APPROVE Cases

Builder 没有 approve 或自动发布功能。审核人员在独立 reviewed 目录创建正式
cases.yaml 与 aliases.yaml，原始 DRAFT 保持可追溯。不能只把 DRAFT 改为 APPROVED：
Builder 的 gold_candidate 不是正式 gold，审核后需要按实体类型整理已确认 ID 到
gold，区分 optional/forbidden，并逐条确认 relations。

正式格式见 [Pilot Dataset Contract](evaluation/cases/PILOT_DATASET.md)。人工批准后：

- Case 使用 review_status: APPROVED；保存 reviewer、审核时间、审核说明和 draft_case_id。
- Alias 也经人工确认；同名多义保留类型约束或解除无依据的 Alias，不批量合并。
- 正例的 gold 只含原文确认的实体；relations 仅用现有七种公开关系。
  has_field 是 Builder 内部结构关系，不能复制为正式关系 Gold。
- 负例必须有 expected_empty:true、空 gold/optional/relations，以及人工编写的
  empty_rationale；不得直接批准自动生成的待核实说明。
- 保留 source_documents/source_locations、candidate_origin、parser_supported、
  parser_blind_spot。删改候选后按实际选入证据更新这些标记；缺失标记会在正式
  manifest 统计为 parser_provenance_unknown_cases，不能假设为无 blind spot。

内部 Claude Code 可以整理审核后的文件，但没有人工确认时必须继续保持 DRAFT。
所有 reviewer 文件仅在 scorer 侧，不能复制到任一被测 Adapter workspace。

## 8. 如何运行 10–15 Case Debug Pilot

先选 10–15 个经人工审核的真实 Case，涵盖七类、至少一个已确认负例以及真实跨文档
依赖。使用现有配置提供 Wiki driver、正式 Parser、OpenViking、OpenCode、隔离与完整
用量遥测。先执行正式 Preflight，失败时修复接入条件：

```sh
evaluation preflight --corpus /srv/data-explore-internal/raw \
  --cases /srv/data-explore-internal/scorer/reviewed-debug/cases.yaml \
  --aliases /srv/data-explore-internal/scorer/reviewed-debug/aliases.yaml \
  --config /srv/data-explore-internal/profiles/e2e.json \
  --output /srv/data-explore-internal/runs/debug-preflight-001

evaluation run --corpus /srv/data-explore-internal/raw \
  --cases /srv/data-explore-internal/scorer/reviewed-debug/cases.yaml \
  --aliases /srv/data-explore-internal/scorer/reviewed-debug/aliases.yaml \
  --config /srv/data-explore-internal/profiles/e2e.json \
  --output /srv/data-explore-internal/runs/debug-001 --smoke --repeats 1
```

这是内部小规模诊断，smoke 标记使 headline_eligible=false；不作为正式性能结论。
保留原生 trace，区分输入适配、Parser 漏项、输出格式、归一化、检索和成本问题。
`--smoke` 不会让 DRAFT 成为有效 Gold；这里使用的是已经人工审核的文件。

## 9. 如何冻结 60 Case Formal Pilot

推荐分布为 10/12/8/8/10/8/4，跨文档至少 60%，并检查技术域、主题、对象、指标、
逻辑/物理模型和来源分布。配额只是 Warning，不能为了凑数降低审核要求。

将最终 raw、已审核 cases.yaml/aliases.yaml、Profile 和运行配置复制到独立 frozen
版本目录，记录每文件 SHA-256、Parser/Adapter 版本及 Git commit。Raw 字节和 Case
审核内容在本轮保持固定；后续变更创建新版本，不覆盖已有结果。scorer 文件与 raw
仍放在不同子目录，并由原生进程隔离 launcher 禁止被测系统访问 scorer。

## 10. 如何运行四方案正式 Benchmark

```sh
evaluation run --corpus /srv/data-explore-internal/frozen/pilot-v1/raw \
  --cases /srv/data-explore-internal/frozen/pilot-v1/scorer/cases.yaml \
  --aliases /srv/data-explore-internal/frozen/pilot-v1/scorer/aliases.yaml \
  --config /srv/data-explore-internal/frozen/pilot-v1/e2e.json \
  --output /srv/data-explore-internal/runs/formal-001 --repeats 3
```

正式 Runner 再次执行 Preflight，固定四系统 × 每 Case 至少三次。60 Case 对应
720 次评分查询，另有预检查询及构建开销。检查 Entity/Relation/Negative 指标、
Query/Build LLM Tokens、Delivered Context、工具数、延迟和单篇/跨文档报告；
manifest 的实际分布同时保留 parser_supported_cases 与 parser_blind_spot_cases。

使用现有 [EVALUATION_DESIGN.md](evaluation/EVALUATION_DESIGN.md) 的成本和公平性
口径，不将 Dataset Builder 的样例测试、Parser JSON 候选或 Debug Pilot 解释为正式
性能结果。本轮工具交付后停止扩展功能，等待内部真实数据适配。
