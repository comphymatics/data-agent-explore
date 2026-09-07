# Official Evaluation = Four-System Raw E2E Benchmark

唯一正式入口为 `evaluation run` / `evaluation preflight`（也可使用
`python -m evaluation`）。固定比较 LLM Wiki、OpenCode Native Explore、
OpenCode + OpenViking、Data Explore。生产 Compiler、检索、Coverage、Binding、
Router/Reasoner 均不因评测改变。

## 外部输入与隔离

四系统从同一份 frozen Raw Word/Excel 原始字节启动，逐文件 SHA-256、大小和路径
记录在 manifest；每个系统得到私有副本，构建和查询前后核对指纹。
Data Explore 的 Domain Parser → Template JSON → 原有 Compiler → Context Bundle
是方案内部流程，其他方案不会收到 Template、Context 或 Gold。

Gold/Alias 在 scorer 侧维护，传给 Adapter 的 Case 只有 case_id/query。正式运行要求
配置原生进程隔离 launcher，禁止被测进程读取 scorer/其他系统工作目录；Preflight
用不含 Gold 的外部 canary 测试隔离，并扫描 workspace 中完整或嵌入的 scorer 记录。
检查不宣称证明所有恶意程序的信息流；实际部署仍需正确配置账户/容器权限。
launcher 接口见 [设计文档](EVALUATION_DESIGN.md)。

## 统一公共 Output Contract

所有系统被要求使用原始材料中的实体名称返回以下结构，协议没有正确答案或 Alias：

```json
{
  "schema": "data-explore-eval-result/v1",
  "scenarios": [], "purposes": [], "metrics": [], "dimensions": [],
  "business_objects": [], "logical_models": [], "physical_models": [], "fields": [],
  "relations": []
}
```

八类值必须是字符串数组；字段使用 `model.field` 限定名称。可选 relations 中
source/target 使用 `{"type":"metrics","name":"原文实体名"}`，必须指向返回的实体。
OpenCode 两方案通过相同 prompt 要求该格式；Wiki query 接收 output_contract；
Data Explore 从实际已交付 Bundle 转换。原生 raw_output 和统一 output 同时留存。
格式错误标为 INVALID，不能通过宽松自然语言 Alias 扫描选择性忽略幻觉。

## 成本与原生预算

| 正式概念 | Result 字段 | Leaderboard |
|---|---|---|
| Build LLM Tokens | build_llm_input_tokens / build_llm_output_tokens / build_llm_total_tokens | BuildLLMTokens |
| Query LLM Tokens | query_llm_input_tokens / query_llm_output_tokens / query_llm_total_tokens | AvgQueryLLMTokens |
| Delivered Context Tokens | delivered_context_tokens | AvgDeliveredContextTokens |

LLM Token 累加主 Agent、Explore 子任务、Router、Reranker、摘要、格式化等全部
模型调用，包含 reasoning 与 cache input，按 call ID 去重。未知总用量为 null。
OpenCode session export 只证明已观测用量，正式运行还需进程级 usage_command。
OpenViking 的构建/查询服务调用另计；不能只计 OpenCode 主模型。

Data Explore delivered_context_tokens 是实际返回 Context Bundle 的估算，metadata
明确标记估算方法；它不是 LLM 计算成本，也不是所有工具响应 Token 的总和。
其他系统只有可靠测量及方法说明时才报告该值；否则为 null，并写明原因。
确定性 Parser/Explore 没有 LLM 调用时可以明确记录 0；CPU 时间不转换为 Token。

> 不同系统采用各自原生 Context Management 策略，Benchmark 不强制其采用相同内部
> Context Window；实际资源消耗作为评测结果的一部分。

`QueryBudget.native_context_budget` 仅是 Adapter 内部预算（目前主要约束
Data Explore），不是四系统共同 hard limit。统一配置 backbone/version/temperature、
max_output_tokens 和 timeout；实际 Query LLM Tokens、Tool Calls、Latency 用于比较。
原生模型限制或差异必须写明原因。Delivered Context 未知不阻止正式结果，但完整
LLM 遥测缺失会使 Preflight 失败。

## Pilot Case 与评分

真实 Case 由外部 YAML 加载。完整格式见 [PILOT_DATASET.md](cases/PILOT_DATASET.md)。
支持 metric_to_model、purpose_to_data、model_to_analysis、model_to_business、
field_discovery、lineage_impact、negative，single_document/cross_document，
easy/medium/hard，以及 tags。

Required/optional/forbidden 相互独立；统一 Registry 按类型归一化并去重，
歧义和未知实体保留在 Precision 分母。Headline Entity Recall/Precision/F1 用总计数
进行 micro 聚合；Optional 不扩大 required Recall。

`expected_empty: true` 要求审核后的空 Gold 与材料范围内的 empty_rationale。
空集合且执行有效为正确；乱返回为 False Positive。Negative Case Accuracy =
正确空答案数 / 负例运行数；False Positive Rate = 返回非空实体/关系的负例运行数 /
负例运行数。失败不算正确空答案；失败率另列。负例不通过 Recall=1 人为抬高实体 F1。

Relation Recall/Precision/F1 只作诊断，严格匹配有向三元组，独立于实体 F1。
关系类型固定七种；`relations: null` 表示未标注，`[]` 表示审核过且应为空。
不进行 LLM Judge，不恢复 Evidence Recall 为 headline。

推荐 60 Case 配额：10/12/8/8/10/8/4，cross_document ≥60%。不足只警告，
manifest 输出实际分布。正式运行每 Case × 每 System 至少 3 次，保存
mean/std/min/max、invalid rate、分类型 Recall 及 per-case/per-repeat 统计。

## Preflight 与正式执行

先按 [配置模板](benchmark/e2e.config.example.json) 提供正式 Parser、Wiki driver、
OpenCode、OpenViking、模型、完整用量收集器及隔离 launcher。Gold 必须人工 APPROVED。
Preflight 会进行真实构建和一次无 Gold 探测查询，会发生实际资源消耗。

```sh
uv run --isolated --extra dev --extra dense evaluation preflight \
  --corpus /secure/pilot/raw --cases /secure/scorer/cases.yaml \
  --aliases /secure/scorer/aliases.yaml --config /secure/pilot/config.json \
  --output /secure/pilot/preflight-001

uv run --isolated --extra dev --extra dense evaluation run \
  --corpus /secure/pilot/raw --cases /secure/scorer/cases.yaml \
  --aliases /secure/scorer/aliases.yaml --config /secure/pilot/config.json \
  --output /secure/pilot/run-001 --repeats 3
```

每次正式 run 都重新 Preflight，不复用可过期的 PASS 文件。四系统的构建、输出、
真实 Explore/MCP、模型与完整遥测检查全部通过后才派发评分 Case；P0 失败非零退出，
写入失败 manifest。预检查询 Token 和 trace 单独记录，不混入被评分查询均值；
构建成本只记录一次。独立 preflight 与之后的 run 是两次操作，费用各自留账。

## 报告

| 文件 | 内容 |
|---|---|
| leaderboard.csv | Entity F1、三类成本、工具数、延迟、负例与关系诊断、single/cross 分项 |
| category_breakdown.csv | 按问题类型的 Recall/Precision/F1、AvgQueryLLMTokens、AvgToolCalls |
| source_span_breakdown.csv | 单篇/跨文档效果和实际消耗 |
| amortized_cost.csv | BuildLLMTokens/N + AvgQueryLLMTokens，N=1/10/100/1000；冷构建等价成本另列 |
| effect_cost_scatter.csv | F1/Recall vs Query LLM Tokens 的独立坐标；没有综合分 |
| run_detail.jsonl | 每次原生回答、统一 output、trace、成本、模型、repeat_index 和评分 |
| run_manifest.json | 版本、commit、源码/语料/Case 哈希、模型、构建快照、环境、实际分布和 Preflight |
| statistics.json | per-case/per-repeat mean/std/min/max、遥测覆盖数及诊断指标 |

CSV 中空白代表未知，不是 0。Token 样本不全时均值/摊销不伪装成完整成本；JSON
保留已测样本统计及 measured/expected 分母。无法直接用独立的显著性结论替代
这些数据；单篇/跨文档差异必须由真实 Pilot 结果支持。

## Synthetic smoke 与 Legacy

```sh
uv run --isolated --extra dev python -m evaluation.scripts.run_e2e_smoke \
  --output /tmp/data-explore-pilot-smoke
```

这是合成 Word/Excel → 受限测试 Parser → 原有 Compiler → Explore 的 7 Case × 3 次
链路验证，含负例及关系诊断。它跳过正式外部接入 Preflight，永远没有 headline 资格，
不能说明正式 Parser、四方案接入或相对性能已通过。当前接入状态见
[PILOT_READINESS.md](PILOT_READINESS.md)。

旧 Evidence 对比与构造入口为了已有测试兼容保留原路径，相关文件顶部标记
`LEGACY / NON-HEADLINE EVALUATION`。它们不参与正式 CLI 默认调度；
历史文档为 [LEGACY_EVIDENCE_EVALUATION.md](LEGACY_EVIDENCE_EVALUATION.md)、
[COMPARISON.md](COMPARISON.md)。底层 retrieval Golden 仍是生产回归，不能替代 Raw E2E。
