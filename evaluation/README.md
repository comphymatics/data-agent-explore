# 四方案企业原始文档 E2E 评测

本目录主评测比较 **LLM Wiki、OpenCode Native Explore、OpenCode + OpenViking、
Data Explore** 面对同一份 frozen raw Word/Excel 企业资料的完整数据探索效果。
主指标为实体 Recall / Precision / F1、完整 Query Tokens、Build Tokens 和 Tool Calls。
Evidence Retrieval 与 CodeGraph 不进入本轮四方案正式排行榜。

## 输入和系统边界

四个 Adapter 从相同原始文件字节开始。框架冻结相对路径、大小和 SHA-256，为每个
系统建立只包含原始文件的私有副本，并在构建/查询前后核对指纹。

| System | 完整路径 |
|---|---|
| LLM Wiki | Raw → 所选 Wiki 项目的 native ingestion → Wiki/context/index → native query |
| OpenCode Native | Raw workspace → OpenCode primary → 原生 explore 子任务 → search/read/reason → result |
| OpenCode + OpenViking | Raw → OpenViking native ingestion → OpenCode explore 使用该 namespace 的 MCP retrieval → result |
| Data Explore | Raw → 外部 Domain Deterministic Parser → 私有 Template JSON → 原有 Compiler → Context/Hybrid → 原有 Explore → Bundle |

Template JSON 是 Data Explore 内部产物。Raw 入口拒绝 JSON、YAML、程序文件与符号链接；
不能把 `source-materials/templates`、已有 Context 或 Gold 当作 raw corpus。
其他企业格式允许 `.doc/.docx/.xls/.xlsx/.pdf/.md/.txt/.csv`；实际格式支持由各方案
的 native ingestion 决定，不支持的文件不能静默跳过。

## 完整 smoke

```sh
uv run --isolated --extra dev python -m evaluation.scripts.run_e2e_smoke \
  --output /tmp/data-explore-e2e-smoke
```

脚本创建合成 Word/Excel，经测试专用的受限确定性表格 parser 生成合法 Template
JSON，调用生产 Compiler/Explore，执行 Q1–Q6 各三次并生成报表。这是完整执行链路
测试，**不是生产 Domain Parser 或四个真实系统的实验**。未解析的叙述关系保留为
漏召回，不会为了 smoke 得分修改生产 Context、检索逻辑或单独调整本方案 Gold。

## 正式运行

准备独立 raw 目录、评分器私有 Gold/Alias，人工审核案例并设为 `APPROVED`。
不要自动审批仓库中的合成 FIXTURE。复制 `benchmark/e2e.config.example.json`，填写
固定 backbone/version/temperature、预算与硬件，配置 Wiki native driver、OpenCode、
OpenViking 服务及正式 Parser。被测账户/容器只应访问 raw 和本系统产物；关闭全局
额外 MCP、共享记忆、Gold/Alias 目录。OpenCode 额外工具会关闭并检查实际 trace。

```sh
uv run --isolated --extra dev --extra dense python -m evaluation.scripts.run_e2e_benchmark \
  --corpus /secure/benchmark/raw \
  --cases /secure/scorer/cases.yaml \
  --aliases /secure/scorer/aliases.yaml \
  --config /secure/benchmark/e2e.config.json \
  --output /secure/benchmark/runs/run-001 \
  --repeats 3
```

正式运行强制四系统和至少三次重复。依赖不可用、用量不完整或执行失败均显式记录，
CLI 非零退出，不会把一次 HTTP search 或 mock 当作成功。`--smoke --systems data_explore`
允许局部诊断，但不获得正式 headline 资格。输出目录必须为空，避免混合不同实验。

## Gold 和归一化

`cases/cases.yaml` 展示 Q1–Q6；`cases/aliases.yaml` 是 scorer-only 稳定 ID Registry。
八类实体为 scenarios、purposes、metrics、dimensions、business_objects、logical_models、
physical_models、fields。Required/optional/forbidden 互不重叠；跨文档案例必须指定
至少两个原始文件并说明单篇文档为什么不够。

Adapter 的 `BenchmarkCase` 只有 case_id/query，不包含 Gold、Alias、答案类型或来源。
统一 normalizer 支持类型化 JSON、实体列表、Context Bundle、逐行实体名。未知实体、
歧义 Alias 保留并影响 Precision；不在任意段落中只搜索已知 Gold 词而忽略幻觉。
建议 native query 返回清晰实体列表；原始答案和规范化明细同时保留。

总体 Recall = 正确 required ID 数 / required ID 总数；Precision = 正确 required/optional
ID 数 / 全部返回实体数（含未知/禁止实体）；F1 为调和平均。按 Canonical ID 去重。
分类型、单篇/跨文档、每题重复统计单独输出。失效运行不从样本中消失，须同时查看 invalid rate。

## 成本口径

- 累加所有 LLM 调用的 input/output/total，包括子孙 Agent、reasoning、cache 输入、
  ingestion、query-time rerank/understanding/summarization；按唯一 call ID 去重。
- 不完整 usage 为 null，不是 0；不能用最终回答长度替代总 Token。
- OpenCode session export 只证明已观测主/子任务用量；正式总成本还需配置
  `usage_command` 收集进程级全量 ledger（含后台标题/摘要），协议见设计文档。
- Data Explore adapter 调用原有确定性 Explore，没有新 LLM，实际 query LLM tokens 为 0；
  Context payload 估算 Token 独立保留，native model constraint 在 manifest 中显式记录。
- Build/Query 分开；记录 cold/reused、parser/compiler/snapshot 版本和指纹。
  摊销为 Build/N + AvgQuery，N=1/10/100/1000，另列冷构建等价成本。
- Tool Calls 包含原生子任务，分列 search/read/retrieval/expand；延迟单位毫秒。
  确定性解析和本地 embedding CPU 时间计入延迟，不伪造 LLM Token。

## 报表

| 文件 | 内容 |
|---|---|
| `leaderboard.csv` | 状态、micro Recall/Precision/F1、平均/总 Query Tokens、Build Tokens、工具数、延迟、invalid rate |
| `category_breakdown.csv` | Q1–Q6 正确率、Token 和 invalid rate |
| `source_span_breakdown.csv` | Single / cross-document Recall/F1 |
| `run_detail.jsonl` | 每次 query/repeat 的 raw output、native trace、Token ledger、normalized IDs 和评分 |
| `amortized_cost.csv` | N=1/10/100/1000 的本次与冷构建等价 Token |
| `statistics.json` | 系统/每题 mean/std/min/max、重复波动、分类型 Recall、遥测分母 |
| `run_manifest.json` | Raw 指纹、隐藏集哈希、构建回执、模型差异、版本、预算和正式结果资格 |

实现、native driver 协议和验收映射见 [EVALUATION_DESIGN.md](EVALUATION_DESIGN.md)。
历史入口：[Evidence 构造](LEGACY_EVIDENCE_EVALUATION.md)、
[旧 OpenCode/HTTP Search 对比](COMPARISON.md)、[底层 Retrieval Golden](retrieval_golden/README.md)。
