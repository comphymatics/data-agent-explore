# Hierarchical Retrieval

Serving 和 Explore 继续只使用 `data_search/data_read/data_expand/data_source` 及独立 Environment Binding adapter。没有新增 graph/tree traversal 工具。

## 入口和路由

`data_search(..., mode="auto", hierarchy=None)` 与 `ExploreAgent.explore(..., mode="auto", hierarchy=None)` 支持 `auto/direct/hierarchical/hybrid`；View 可选 `analysis/domain/asset`。参数已同步到 Python tools 和 MCP input schema。Context Bundle 只新增可选 `retrieval_trace`，旧字段保持。

- Direct：精确 Model/Metric/Dimension Name、Canonical/Stable ID、Field/Counter 等 Element ID 命中，直接进入原 Hybrid Anchor + Relation Completion。中文语法紧邻 ASCII 标识符仍能识别。明确命名的 Page 优先于其他模型中的共享字段。
- Hierarchical：没有强实体锚点时，根据业务场景/目的或明确主题/资产词选择 View。
- Hybrid：明确 Anchor 加“还需要/跨域/结合”等扩展意图，结合直接锚点和 Analysis 等分支。

“小区”等业务对象名可能也是建模 taxonomy alias。宽泛“有哪些数据”问题没有明确建模层/主题约束时，Router 不把隐含分类层级当成硬 filter。显式传给 `data_search(scope=...)` 的 scope 仍受治理；DERIVED active 组织可满足相应导航筛选，候选不能满足。

## 一次 Serving 操作

```text
Direct: exact/element anchor + existing hybrid retrieval
Hierarchical: L0 inverted branch index → branch rerank → L1 aggregate
              → real member anchors + existing entity hybrid relevance
Hybrid: merge the two anchor sets
    → existing BundleAssembler relation/backref completion
    → diversity/ranking/budget
    → Context Bundle assembly
    → existing Coverage Check
    → existing Focused Expansion
```

L0 branch postings 在 aggregate 变化时局部更新。召回后按分支名称、L0、L1 重合与分支大小排序，默认最多选 3 个分支。继承 Canonical identity/type/scope 策略，成员先验证，再补全既有 typed relations。没有支持的分支时回退原 Entity Retrieval，并在 trace 标记 `no_supported_branch`。

实现使用现有 Hybrid Retrieval 的实体 relevance，加确定性分支得分，不新增逐 Entity 的 LLM 排序。分类/推断在构建期，查询期只读。

## Trace 和边界

`retrieval_trace` 包含 mode、hierarchy_view、exact/page/element anchors、branch candidates、selected_branches、披露的 hierarchy_contexts、fallback、预算截断信息。

状态区别始终可查：原 Page 的 `hierarchy.parents` 和 Focused Expansion 返回 Edge status/provenance/active/conflicts；DERIVED/CANDIDATE 不会变成 Canonical `topic`。Coverage 仍仅根据原支持事实及环境覆盖判定，不因一个组织分支就自动满足字段、粒度、Join 或可用性。

现有 Explore 流程正常仍为一次 `data_search` 加最多一次有界 `data_expand`；Hierarchy 不增加调用轮次。External Environment Adapter 和用户已有查询期 semantic provider 的调用仍按原 telemetry 单独记录。

## 独立 ablation

```bash
uv run --isolated --extra dev python -m evaluation.hierarchy.run \
  --out evaluation/hierarchy/results
```

比较 Data Explore、Hierarchy disabled、Semantic inference disabled。Hierarchy disabled 关闭查询期分支检索与 Page 组织披露；Semantic inference disabled 保留显式/受治理 Backbone，关闭新增 semantic overlay。输入资料和 Gold 分离，case expectations 只交给评价消费者，绝不进入 compiler、组织配置或 Explore query options。

报告 Recall/Precision/F1、Query LLM Tokens、完整 Delivered Context 估计 Tokens、Tool Calls，并按 exact、broad/cross-document、purpose→data、model→analysis、unknown、cross-domain 和 inferred organization 分组。内部诊断含 entry/routing accuracy、Branch Recall@K、Aggregate Precision、Candidate Precision、Inference Coverage、Unclassified Rate。空分母保持 null；UNKNOWN 不强行当正确实体。该报告独立于正式四方案 E2E leaderboard。

本次小样本查询期不启用 LLM，因此 Query LLM Tokens 为真实零调用，不能据此推断接入真实 LLM 后的成本。Fixture provider 测试验证 bounded output gate，不代表真实模型准确率。真实 MetaOne、真实 taxonomy、邻居有效性、多义查询路由和 token/latency 收益仍需内部实测。
