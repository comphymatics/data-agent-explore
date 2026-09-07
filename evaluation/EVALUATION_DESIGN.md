# 四方案 Raw E2E 统一评测设计

本轮实现位于 `evaluation/`，生产 Compiler、Template Contract、Canonical Context、
检索算法、Router/Reasoner 均未修改。旧 Evidence benchmark 和 retrieval Golden
保留为历史/底层回归，不再作为四方案 E2E 主排行榜。

## 要求与实现

| 要求 | 实现 | 验证边界 |
|---|---|---|
| 相同原始输入 | `benchmark/raw_corpus.py`：逐文件 SHA-256、私有只读副本、每阶段变更检查 | Word/Excel 原始字节相同；JSON/中间产物和符号链接不能作为 raw input |
| 四个完整系统 | `adapters/llm_wiki.py`、`opencode_native.py`、`opencode_openviking.py`、`data_explore.py` | 四个独立 Adapter；外部服务/原生入口必须由运行配置指定，缺失会显式不可用 |
| Wiki 原生 ingestion | 版本化原生进程 driver 协议，校验完整 raw 文件接收回执与 Wiki ingestion/index 阶段 | 未擅自假定 “LLM Wiki” 指某个具体仓库；真实项目命令仍需配置 |
| OpenCode Native Explore | 实际 `opencode run --agent plan --format json`，要求 export trace 中存在内置 explore 子任务 | 不把 primary-only 回答视为 Explore；关闭额外工具，记录实际模型调用 |
| OpenCode + OpenViking | 逐个原始文件 native upload/add-resource 并等待 ingestion；OpenCode explore 通过 OpenViking MCP 查询独立 namespace | HTTP search 本身不构成结果；没有实际 MCP retrieval 或作用域不符则 INVALID |
| Data Explore 从 raw 开始 | 外部 Domain Parser → 私有 Template 目录 → 原有 `compile_template_inputs` → snapshot → 原有 Explore | 没有预计算 Context/Gold 输入接口；只读消费生产能力 |
| 可重用离线产物 | cache key 含 corpus/parser/compiler 指纹；回执、snapshot 版本及内容指纹检查 | 明确 cold/reused，保存原始 build tokens；本轮未改 Snapshot Governance |
| 相同 Gold 与 Alias 隔离 | 公共 `BenchmarkCase` 仅含 case_id/query；Registry 只在评分器；单一 normalizer/scorer 无 system 参数 | 不传 Gold、Alias、Gold 类型/来源说明或评分器路径；未知和歧义实体计入 Precision 分母 |
| 八类稳定语义实体 | `cases/aliases.yaml`、`cases/schema.py` 与 `normalization/` | 场景、目的、指标、维度、业务对象、逻辑模型、物理模型、字段；不以 Evidence ID 计分 |
| Q1–Q6 / 跨文档 | 六个合成 fixture case；跨文档必须声明多个 raw 文件和必要性说明 | FIXTURE 不允许成为正式 APPROVED Gold；合成解析器没有覆盖全部语义，分数如实保留 |
| 主指标 | micro Recall / Precision / F1，分类型 Recall、per-case/per-repeat mean/std/min/max、invalid rate | Optional 只影响正确返回集合，不扩张必需 Recall；Forbidden 保留明细并作为错误返回 |
| 完整 LLM 成本 | 去重 call ledger；OpenCode 递归 export 子孙 session，包含 reasoning 与 cache；进程级 ledger 补充后台调用；OpenViking ingestion/query 服务调用独立计量 | 只有 session export 时总成本仍为 null；确定性 Data Explore 的实际 LLM calls=0，Context token 估算单列 |
| Tool Calls | 完整 trace 与 total/search/read/retrieval/expand 计数 | 子任务 tool 计入总数；不存在可靠 trace 时不伪造 0 |
| 构建/查询/摊销 | build 与 query usage 分列，N=1/10/100/1000，冷构建等价摊销另列 | 本次使用缓存的构建开销可为 0，但不抹掉原始离线成本 |
| 统一运行条件 | manifest 的 model/version/temperature/max_output/hardware；native effective/observed models 独立记录 | Data Explore 当前是确定性 Explore，显式记录 native model constraint，未人为接入新 LLM |
| 三次重复 | 正式入口强制四系统且 repeats≥3，逐 case/system/repeat 原始结果和 trace 持久化 | smoke 可选择单系统，永远不是正式四方案结果 |
| 报告 | leaderboard/category/source-span/amortized CSV，完整 run_detail JSONL、statistics JSON、run_manifest JSON | 不可用/失败也保留；遥测不完整时 Token headline 不具备可比性 |

## 已执行与未执行

已执行：真实合成 Word 与 Excel 文件经过一个明确受限的确定性表格 parser，生成
Template JSON 后调用原有 Compiler/Explore。六类问题各三次，共 18 次完整查询；
自动计算实体分数、Token、工具数和各报表。该 parser 仅用于测试交接路径，不是
替代另一团队的 Domain Parser；未解析的叙述语义会产生真实的漏召回。

2026-09-07 验收：`uv run --isolated --extra dev pytest -q` 共 **143 passed**。
`run_e2e_smoke` 共 **18/18 执行成功**；micro Recall **0.583333**、Precision
**0.666667**、F1 **0.622222**，invalid rate **0**。已知无 LLM 的合成 Parser/
确定性 Explore 实际 Build/Query LLM Tokens 均为 **0**；工具数平均 **2.666667**。
这些数值仅验证链路与计量，不能外推正式 Parser 或四方案的性能优劣。

四个 Adapter 的协议、隔离、计量和失败路径由自动化测试覆盖。没有把测试驱动、
mock HTTP 或伪造的竞争系统输出放入正式四方案排行榜。

尚未完成真实四方案实验：需要用户明确 LLM Wiki 项目及 driver、正式 Domain Parser
入口、可用 OpenViking 服务（含 ingestion/query LLM 用量遥测）、统一 OpenCode/provider
配置，以及人工 APPROVED 的企业 Raw Corpus/Gold。未配置时 manifest 记录 UNAVAILABLE，
正式 CLI 非零退出。这些条件不能用已有 Template JSON 或已生成 Context 绕过。

## Native driver 协议

运行配置采用 argv 数组；不经 shell 拼接。一个请求通过 stdin JSON 输入，stdout
只返回一个 `protocol: raw-e2e-driver/v1` JSON 回执。进程 stderr 不参与结果评分。

Wiki prepare 请求含 `phase=prepare`、raw `corpus_path/files/corpus_fingerprint`、
私有 workspace 与统一 model 参数。回执必须包含 `status`、与原始 inventory 完全
一致的 `consumed_files`、`stages: [llm_wiki_native_ingestion, wiki_index]`。
同时返回 `cold_build/reused_snapshot/native_version/effective_model`，不能隐藏版本差异。

Wiki query 请求只含 `case: {case_id, query}`、budget、workspace、model、repeat。
回执含 `raw_output`、`trace`、`tools_complete`、`retrieval_rounds`，以及
`llm_calls: [{call_id, input_tokens, output_tokens}]` 和 `usage_complete`。
用量覆盖 native pipeline 的全部模型调用；call_id 用于防止重复计费。
全覆盖且无任何 LLM 调用时才可返回 `usage_complete: true, llm_calls: []`。

OpenCode 可配置 `usage_command` 接收 `phase=query_usage`、本次 session_ids/run_id/
case_id/repeat/workspace，从独立 provider 计量收集本进程全部调用。回执必须声明
`scope: process_all_llm_calls`、`covered_session_ids`、`usage_complete` 和包含所有
已导出 message call_id 的 `llm_calls`，并覆盖后台标题/摘要等辅助调用。观察记录
与完整 ledger 的用量冲突会使总成本未知。没有该入口时保留 session 用量和 trace，
但不把它们声明为完整成本，不允许进入正式成本榜单。

Domain Parser 接收 `phase=parse`、原始文件清单和新建的 `output_dir`，只能把符合
现有 Template Contract 的文件写入这个内部目录；stdout 返回 `parser_version`、
`consumed_files`、Token ledger 和 trace。它不接收 Query/Gold/Alias。

## 结果格式和评分限制

系统可返回实体类型分组的原生 JSON、带 type/name 的实体列表、Context Bundle，
或逐行列出的实体名。所有系统执行完全相同的类型/名称规范化规则。为避免只识别
已知 Alias 而忽略幻觉实体，评分器不在任意自然语言段落中搜索 Gold 词；无法确认
的名称、歧义或不受支持输出会显式进入 unknown。建议 native query 返回实体列表。
Raw output 与完整 native trace 永远保留，便于人工审计规范化错误。

数据隔离是输入/目录/权限与调用 trace 的工程约束，不宣称它是对恶意任意 shell
代码的操作系统沙箱。正式环境应以独立账户/容器限制被测进程只访问原始语料与
本系统产物，并禁用环境级附加插件、共享记忆和非本轮数据源。

官方接口依据：
[OpenCode 配置](https://opencode.ai/docs/config/)、
[OpenCode Agents](https://opencode.ai/docs/agents/)、
[OpenCode Token 字段实现](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/session.ts)、
[OpenViking raw resources](https://docs.openviking.ai/en/api/02-resources)、
[OpenViking MCP/OpenCode 接入](https://docs.openviking.ai/en/guides/06-mcp-integration)。
