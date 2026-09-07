# Pilot Evaluation 收口设计

本轮只修改 evaluation、对应测试和 CLI 注册。生产 Enterprise Data Context、
Compiler、Hybrid Retrieval、Coverage、MetaOne Binding、Explore Runtime 没有变更。
版本为 `four-system-raw-e2e/v2`，公共实体输出为 `data-explore-eval-result/v1`。

## 要求与实现

| 要求 | 实现 | 验证边界 |
|---|---|---|
| 三类成本 | result_contract.py 与四个 Adapter、reports/e2e.py | LLM 计算成本与 Bundle 交付估算独立；未知为 null |
| 原生预算 | QueryBudget.native_context_budget | 不承诺内部 Context Window 等价；实际资源消耗进入报告 |
| 同一输出 | output_contract.py，Wiki output_contract 请求，两个 OpenCode prompt，Bundle formatter | 只含格式/类型，无 Gold/Alias；八类名称数组及可选有向关系 |
| Negative | cases/schema.py、entity_scoring.py | 审核空 Gold 和 empty_rationale；失败不是正确空答案；不抬高正例 Recall |
| Relation | normalizer.py、entity_scoring.py | 类型+Alias 归一化三元组；方向严格；不进入 Entity F1 |
| Legacy 收口 | 唯一 evaluation run/preflight 调度 e2e_runner，旧文件顶部标识 | 旧 imports 为兼容保留，不能当正式榜单 |
| Pilot Contract/配额 | cases/schema.py、cases/PILOT_DATASET.md | 外部数据加载，60 Case 推荐分布和跨文档60%只警告 |
| 报告 | leaderboard/category/source_span/amortized/scatter/statistics | 原始指标分开，无综合分；提供重复波动和未知用量分母 |
| Manifest | run_manifest.py、e2e_runner.py | commit、实际源码哈希、数据哈希、Adapter MRO 源码版本、模型、环境、快照、repeat |
| Preflight | preflight.py、正式 Runner | 配置检查、隔离探测、四系统真实构建/查询/模型/遥测验证；P0 fail fast |
| Synthetic | fixtures 与 7 Case × 3 repeat smoke | 验证工程链路，不是生产 Parser 或四系统真实成绩 |

## 成本与格式迁移

旧 build_tokens_input/output/total、query_tokens_input/output/total 替换为
build_llm_input_tokens/output_tokens/total_tokens 与
query_llm_input_tokens/output_tokens/total_tokens；新增 delivered_context_tokens。
旧 AvgQueryTokens 被移除，CSV 使用 AvgQueryLLMTokens、AvgDeliveredContextTokens、
BuildLLMTokens。历史报告不与 v2 合并。Data Explore 缓存 key 增加成本协议版本，
防止旧回执导致冷构建成本被抹掉。

Data Explore 使用当前 Bundle 整体的原生 estimate，metadata 记录方法和 estimated；
各工具输入/输出估算仍仅用于诊断。Wiki/OpenCode 只有明确报告的可靠 context 测量
与方法才能填 delivered_context_tokens，否则 null + reason。

Native driver 仍使用 stdin/stdout 的 raw-e2e-driver/v1。query request 附带公开
output_contract；receipt 输出符合协议的 output，raw_output 保留原生结果。
旧任意自然语言输出不再直接获得有效正式评分。如果 Wiki 需要格式化，可以在
其 driver 内使用同一 backbone，仅输入原始回答和公共格式；调用必须计入完整
llm_calls 并在 trace 中单列 formatting，不得接入 scorer 或再次检索隐藏资料。
框架没有默认格式化 LLM，也不隐瞒格式化 Token。

## 原生用量与模型回执

Wiki/Parser native 回执提供 usage_complete、唯一 call_id 的 llm_calls；
OpenCode usage_command 的 query_usage 回执提供 scope=process_all_llm_calls、
covered_session_ids、完整 llm_calls，覆盖 session exports 外的辅助调用。
OpenViking ingestion/query 服务用量另加；响应提供的 effective_model 和
model_settings_verified 用于核对构建模型。没有完整计量/验证则 Preflight FAIL，
不能因为配置里写了某个模型就宣称真实调用符合约束。

模型回执的键为 model/version/temperature/max_output/native_model_constraint。
与请求不同的模型必须标注 native_model_constraint=true 和 reason。
Query 和非零 LLM Build 都验证；确定性无模型调用的路径显式说明约束。
llm_calls 的 input/output/total 必须自洽；缺项、冲突、重复冲突不能计为 0。

## 输入隔离与 Preflight 执行顺序

1. 读取 scorer-side YAML 并验证人工审批、Gold 类型、负例依据和来源。
2. 冻结 Raw Word/Excel；记录实际配额分布，非硬性缺额为 warning。
3. 检查四方案可执行入口、正式 Parser、OpenViking 配置和完整用量入口。
4. 每系统创建独立 raw/workspace，验证指纹，执行隔离 launcher 探测。
5. 原生构建及一次固定、无 Gold 的探索查询；校验真实 Explore 子任务、OV MCP、
   公共输出、Token/工具数与实际模型回执。保存每次预检原始 trace 和成本。
6. 全部通过才执行评分查询。每次前后检查 workspace 和 raw；复制 Gold/Alias 或
   原始资料变化立即中止。整个 run 结束前再校验一次，并调用原生 cleanup。

isolation_command 使用 argv 数组，调用形式为：

```text
<launcher argv...> --workspace <private directory> -- <native command argv...>
```

实际部署负责提供已配置的容器/账户/沙箱 launcher，使原生进程及子进程只能读取
本系统 raw/build 和必要运行时文件，禁用共享记忆、额外插件及其他 scorer 工作区。
框架用同一个 launcher 执行可丢弃的外部 canary 读取；读取成功即 FAIL。canary 不含
Gold/Alias，真实 scorer 路径不会传给 Adapter。被隔离环境不可见 canary 或拒绝访问
才通过。可执行程序返回成功不是原生 Adapter 可用的唯一证据，后续真实探测仍要通过。

workspace 扫描按内容哈希及 JSON/YAML 内嵌 case/Alias 记录检查，禁止符号链接。
这属于工程隔离验证，不能证明恶意程序的任意编码/网络外泄；部署权限仍须正确。
测试中的模拟 launcher/Adapter 仅证明失败检测、调用次序与协议，不代表真实隔离验收。

## 指标定义与解释

Entity micro Recall = 正确 required / 全部 required；
Precision = 正确 required/optional / 全部返回实体（含 unknown/forbidden）。
负例返回的实体也进入总体 Precision 分母。负例成功不增加 required 分子。
Negative Accuracy 计有效正确空答案，FPR 计负例的非空返回；INVALID 单独报告，
不会通过空 raw_output 被当成成功。

Relation 仅汇总已标注案例，未知端点会降低 Relation Precision；不对同名实体建立
关系，不从共同出现推导 implemented_by，也不作逆关系或传递闭包。
Bundle formatter 仅格式化已返回的实体、字段及具有明确类型方向的 section 关系；
不调用检索、不读 Graph、不访问 Registry、不提升候选为事实。

Query LLM 成本不含离线 Build；Build/N + AvgQuery 用于摊销。预检查询成本单列，
不进入被评分查询均值；全部运行开销需另外加上 manifest 中的 preflight query 成本。
现有 smoke 的 CPU/解析时间没有转换成伪 Token。

真实接入状态与下一步命令仅见 [PILOT_READINESS.md](PILOT_READINESS.md)。
本轮完成后停止扩展框架，等待真实 Pilot 数据和外部接入配置。
