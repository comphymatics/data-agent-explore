# Pilot Readiness

## 1. 四个 Adapter 当前是否 Ready

2026-09-07 工作区核对：四方案的统一成本/输出协议及测试已具备；**尚无四系统真实
Preflight PASS，因此当前不能启动可解释为正式性能对比的 Pilot**。

| Adapter | 工程状态 | 真实 Pilot Ready |
|---|---|---|
| LLM Wiki | native driver 协议与统一 output 已实现；工作区有 llm_wiki 0.6.11 源码 | 否：原生 driver/完整遥测尚未接入验证 |
| OpenCode Native Explore | 本机 opencode 可执行；Explore trace、递归用量、统一 prompt 已实现 | 否：进程级遥测、实际模型回执与隔离尚未验证 |
| OpenCode + OpenViking | 原生 raw ingestion、MCP 探索和遥测校验已实现 | 否：服务、实际 MCP、构建/查询模型和遥测未联调 |
| Data Explore | 合成 Word/Excel → 测试 Parser → 原有 Compiler/Explore 已跑通 | 否：正式 Domain Parser 未配置 |

## 2. 还缺哪些外部依赖

需要人工 APPROVED 的真实 Raw/Case/Alias；正式 Parser driver；Wiki 原生 driver；
OpenCode/provider 配置与进程级 usage collector；OpenViking 服务及完整遥测；
固定 backbone/version/temperature/输出预算和硬件说明；能够限制原生子进程只访问
本系统资料的 isolation launcher。配置模板里的绝对路径仍是占位符。

## 3. Token telemetry 是否完整

合成 Data Explore 的确定性 Parser/Explore 已知没有 LLM 调用，因此 Build/Query
LLM Tokens 为 0；delivered_context_tokens 是独立的 Bundle 估算。
竞争方案的完整真实用量尚未验证。OpenCode session export 不能证明后台全部调用，
需 usage_command；OpenViking ingestion/query 服务用量需另计；Wiki 格式化如调用
LLM 也必须计入。未知总用量保持 null，正式 Preflight 会失败。

## 4. 正式 Parser 是否接入

未接入。当前只执行过 evaluation.fixtures.smoke_parser，其能力限于合成表格布局。
正式 Preflight 禁止 smoke_parser/synthetic parser，不能以现有 Template JSON
替代正式原始文件解析流程。

## 5. 正式 LLM Wiki driver 是否接入

未接入。third_party/llm_wiki 的 package.json 声明版本 0.6.11，但源码存在不等于
native ingestion/query driver 可执行，更不等于 Token ledger 和公共 Output Contract
已通过。此次未修改或提交 third_party，也未用替代实现伪装 Wiki 成绩。

## 6. OpenViking service 是否接入

未配置并验证真实服务。本机未发现 openviking/ov CLI，这不证明远端没有部署服务。
需提供可用 endpoint、固定服务版本、模型回执与 ingestion/query 用量，再由真实
OpenCode Explore MCP trace 验证当前 corpus namespace 的检索。

## 7. 推荐下一步真实 Pilot 执行命令

先完成外部接入与真实数据审核，准备 30–60 Case；不足推荐 60 配额或跨文档60%
会警告并记录实际分布。以下命令包含真实模型调用和构建开销：

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

每次正式 run 重新 Preflight。只有四方案的实际构建、Explore/MCP、输出、模型和
遥测全通过才执行评分查询。预检查询成本单列，不混入正式查询均值；所有结果
目录必须为空。完成本轮后停止扩展框架，等待真实 Pilot 数据与接入配置。

## 8. 不能解释为正式性能结果的 synthetic smoke results

2026-09-07：生产及评测全量测试 **155 passed**。合成 7 Case × 3 次 smoke
**21/21 执行成功**，Entity Recall **0.583333**、Precision **0.666667**、F1
**0.622222**；Negative Accuracy **1.0**、FPR **0.0**；已标注关系诊断 F1 **1.0**。
负例只有 1 个、非空关系 Gold 只有 1 条，不能据此推断实际泛化能力。

Build/Query LLM Tokens 均为 **0**，平均 Delivered Context 估算 **4180 tokens**，
平均工具调用 **2.428571**。这些数字仅说明合成链路、格式化与计量可执行；没有
使用正式 Domain Parser，没有运行真实四系统对比，manifest 的 headline_eligible
为 false。模拟 Adapter 的单元测试结果也不作为 Pilot 性能结果。
