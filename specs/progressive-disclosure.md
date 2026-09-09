# Progressive Disclosure

Semantic View 是“从什么语义视角组织”，Disclosure Level 是“读多少”。Analysis/Domain/Asset 的任一分组都支持 L0/L1/L2；Canonical Rich Context Page 的基本契约保留。

| Level | Entity Page | Aggregate Context Page |
|---|---|---|
| L0 | 紧凑摘要，用于召回与候选判断 | 分支名、成员数量、对象/指标/维度/目的的紧凑摘要 |
| L1 | 现有富语义内容，附带各 View 组织路径和状态 | Summary、Primary Objects、Core Metrics/Dimensions、Main Purposes、Logical/Physical Models、Child Groups、Availability、三种 Edge 状态计数 |
| L2 | 按需读取字段、公式、Join、粒度、映射、lineage、约束、Evidence/Conflict | 去重的完整成员、组织边、provenance、Evidence、冲突、未/部分分类成员、候选 placements |

聚合页由 `materialization/aggregate_pages.py` 确定性生成。输入是该 View 下 active 子树的真实 Canonical members；跨路径同一成员只计一次，不跨 View 串接路径。沿子树汇总字段值频次及模型计数，列表必须来自已有成员，CANDIDATE 不算 confirmed member。没有调用 LLM 生成成员或自由总结。

L0 长度有界；L1 的频次、模型列表、child groups 各最多 12 项，同时给完整数量和 `truncated`；完整列表在 L2。重要字段仅预览配置上限数量（默认 8），节点标记为 Element 并指向父模型，全部字段仍在 ElementIndex，不生成 Field Rich Context Page。

全局聚合页的 Environment 状态为 `UNRESOLVED/REFERENCE`。实体上遗留的 environment binding 不足以让全局页面声称 available。Explore 可用本次 Binding V3 已验证的 identity bindings，对已披露模型列表生成局部可用性摘要，明确 `complete=false`；不会把未检查成员说成不存在，也不修改快照。

## 四个工具中的读取

```python
service.data_read("data://views/domain/topic/无线覆盖", level="L0")
service.data_read("data://views/domain/topic/无线覆盖", level="L1")
service.data_read("data://views/domain/topic/无线覆盖", level="L2", sections=["members", "evidence"])
```

实际 path 应使用索引返回的 percent-encoded URI。Canonical 与 aggregate 永远不同址：`data://topics/<slug>` 的 L0/L1/L2 始终是 Canonical Page；`data://views/domain/topic/<slug>` 始终是 Aggregate Page。内部节点可复用 Canonical identity，但不会复用页面寻址。每个 aggregate 仅包含一个 view，继续保留 view-keyed content 兼容结构。

Aggregate 返回 canonical_ref、member_refs、child_branches。L1 引用预览有界，L2 可获取全部成员；L2 sections 指定后只返回请求内容，不额外附全量 member refs。显式 taxonomy 的叶分组也可读取空成员 aggregate。Important Element 预览用 machine-facing `hierarchy://elements/...`，继续属于 ElementIndex，不创建 Field Rich Page。

默认 `data_expand(..., ["hierarchy"])` 返回有界 L1 组织摘要；完整组织边、推断审计和 Evidence 用 `hierarchy_provenance` 显式展开。预算优先保留 Focused Expansion 的 support 与内容，再分配可选导航元数据，避免层级信息挤掉字段证据。

`data_source` 支持聚合 Evidence。L2 不是首轮默认内容，使用选定分支/模型 Focused Expansion 获取详细关系与字段，不重新从根浏览。

## 预算

分支召回和 L1 判读在 Serving 内完成。返回的 aggregate 与 Entity Page 共用现有 hydration token budget；aggregate 最多使用四分之一。L1 放不下时尝试 L0，再放不下则保留路径 trace 并标记 `aggregate_disclosure_budget`。这不新增 LLM tool call。

该预算作用于搜索内容 hydration，并非完整 ContextBundle 序列化大小的上限。Focused Expansion 仍有自身既有预算，Coverage、Evidence、trace、Binding 元数据都会增加实际交付长度；ablation 记录完整 Bundle 的估计 token 数，避免把搜索预算误报成总成本。
