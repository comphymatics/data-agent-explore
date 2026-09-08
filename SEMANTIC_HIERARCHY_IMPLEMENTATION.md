# Semantic Hierarchy Implementation Review

实现范围：在原 `organization.py` / `indexes/hierarchy.py` 上增强多视图 Semantic Organization、Aggregate Progressive Disclosure 和 Serving 路由。不是 Ontology 改造；Canonical、Typed Graph、Parser、正式四方案 Benchmark 均保持各自职责。

## 1. 修改了哪些模块

| 模块 | 实现 |
|---|---|
| `hierarchy_contracts.py`、`hierarchy_config.py` | Edge 契约、来源优先级、状态和配置校验 |
| 原 `organization.py`、`indexes/hierarchy.py` | Analysis/Domain/Asset、显式/规则 Backbone、稀疏多父组织、依赖失效、质量检查、历史贡献 |
| `hierarchy_inference.py` | 规则推导、已分类邻居汇总、特征评分、受控 LLM 选择；复用现有 provider 协议 |
| `materialization/aggregate_pages.py` | 确定性 L0/L1/L2 聚合；原 `pages.py` 附多视图路径和状态 |
| `compiler.py`、`persistence.py` | 组织构建阶段、previous_compiled、组织快照保存/重载/发布校验 |
| `hierarchical_retrieval.py`、`retrieval.py` | 内部分支索引/排序/读取、实体补全、直接/层级/混合路由，共享 hydration 预算 |
| `tools.py`、MCP adapter、Explore | 原四工具扩参、可选 retrieval_trace、现有 Coverage/Binding/Focused Expansion 复用 |
| 构建脚本 | 原三种输入入口接受组织配置；`build_hierarchy.py` 支持独立组织更新与显式 opt-in LLM |
| `evaluation/hierarchy/` | 独立 synthetic ablation、按查询类别和内部诊断报告 |

## 2. 新增哪些 Contract

- `contracts/semantic-hierarchy-edge.schema.json`：view、parent/child、organized_under、CONFIRMED/DERIVED/CANDIDATE、confidence、Evidence、provenance、inference_version、created_at。
- `contracts/semantic-organization.schema.json`：组织贡献、聚合页、推断审计、依赖、fingerprint 和历史。
- Context Bundle 增加可选 `retrieval_trace`，同步 dataclass 与 JSON Schema；无第二套输出契约。
- `data_search` 增加 mode/hierarchy 参数，同步服务、Python tools、MCP schema 和 Explore。

## 3. 如何避免唯一树

一份 Canonical Entity 使用同一 path，在三个 View 中独立放置。每条 Edge 带 hierarchy_id；节点保存多父/多子组织，稀疏层级不造 UNKNOWN parent。全部 parents 和各 View breadcrumbs 可读；旧单 breadcrumb 只作兼容预览。TypedReference 的事实方向不因导航改变；模型 upstream/downstream/dependency 仍只进 Backend Graph。

## 4. 如何处理缺失语义

状态为 classified / partially_classified / unclassified。只有 Layer 的模型仍可能 partially_classified，但 Topic 保持 UNKNOWN。缺标签、无可靠规则、低 confidence 或无 Evidence 不强制选择；缺来源覆盖继续保留 PARTIAL/UNKNOWN。规范化中遗留的 raw/candidate sections 不会自动进入强导航。

## 5. Rule / LLM inference 如何治理

显式元数据、结构化标签和明确引用先构建 Backbone。规则需精确匹配带 Evidence 的 EXPLICIT 输入，保存 rule ID、输入、confidence 和配置版本。特征与邻居评分只产生 CANDIDATE；邻居分类只使用 confirmed 信息，避免候选传播。

LLM 只在剩余分类槽歧义时调用，只能选择 bounded candidate ID。越界、无效 confidence、未知 supporting context 或缺 Evidence 被拒绝，低 confidence/abstention 为 UNKNOWN。审计保留 candidate set、selected、features、support contexts、model、prompt/version、scores/reasons。

LLM 默认关闭；调用次数、邻居数、候选数和输入字符数有界，HTTP timeout/retry/output limit 复用现有 provider。推断不写 Canonical sections，不生成事实图边，不自动 promotion。配置关闭、事实变化或来源删除撤销当前 overlay，旧贡献/audit 保存在 history。

## 6. Aggregate Page 如何生成

沿单个 View 的 active 子树，去重汇总真实 Canonical members、对象/指标/维度/目的频次、模型数和子组。L1 列表有界，L2 提供完整 members/relations/provenance/Evidence/conflicts/candidates；没有 LLM 自由总结或创造成员。

Field 仍是 Element：默认最多 8 个 important-element 预览，10,000 字段测试保持 10 个 Canonical Context / 10 个 Rich Page。聚合不是新的 Canonical Business Entity。

全局 Environment 状态为 UNRESOLVED。当前查询可以用已验证 Binding V3 identities 装饰已披露成员的可用性摘要，complete=false，未校验成员不会被写成 available 或 confirmed absent。

## 7. Direct / Hierarchical Routing 如何工作

Exact Model/Metric/Dimension、稳定 ID、Field/Counter 等强锚点走 Direct；宽泛问题走 Analysis/Domain/Asset；锚点加跨域扩展走 Hybrid。直接 Page 名优先于其他模型中的同名字段。宽泛业务对象词不再自动施加隐含数仓层硬筛选。

Serving 一次完成 L0 branch recall、rerank、L1 aggregate、member anchors 与原 Entity Hybrid relevance 合并，再使用原 BundleAssembler 和 Coverage。无支持分支保留 fallback trace，缺字段/粒度等继续 Focused Expansion。DERIVED 组织可补足缺失的导航 facet；不能推翻已有明确 Canonical facet，CANDIDATE 不满足硬筛选。

## 8. 是否增加 LLM tool calls

不增加 Context Tool 种类或逐节点调用。本次 7 个 synthetic 查询、3 组 ablation 均为每 query 两次 Context Tool Calls；Direct 回归也验证 auto 与 explicit direct 调用数相同。

默认 hierarchy expansion 返回有界 L1 导航摘要，完整组织审计通过 `hierarchy_provenance` 显式展开。预算先保留 Focused Expansion 的 support 与内容，再考虑可选导航信息，避免新增层级使字段 Coverage 退化。搜索 aggregate 占 hydration 预算最多 1/4，必要时 L1 降为 L0，仍不足则标记截断。

## 9. 增量构建如何实现

Context fingerprints → 相关 Edge contributors / 引用及共享特征邻居 / 标签身份依赖 → 旧、新 Aggregate Ancestors → 局部 aggregate 和 branch postings 更新。处理修改、删除、改分类以及新 Canonical Entity 替换同名虚拟标签；不变分支复用原 aggregate。

`compile_fragments(..., previous_compiled=...)` 和 `build_hierarchy.py --previous-snapshot` 可使用原组织状态。组织快照保留候选审计与依赖，重载不重新 LLM inference。配置变化允许全量失效。Canonical 编译和原 Page/Graph 构建继续原流程，不宣称整个 Parser/Compiler 都已增量化。

本地 Template JSON 快照重载后：changed_entities=[]、rebuilt_entities=[]、rebuilt_aggregates=[]、inference_calls=0，并保持相同 index_version。源数据中的时间字段仍参与内容标识；只有组织 Edge 创建时间作为审计元数据排除于语义 hash。

## 10. 验证结果和真实数据待验证项

运行方式：

```bash
uv run --isolated --extra dev pytest -q
uv run --isolated --extra dev python -m evaluation.hierarchy.run --out evaluation/hierarchy/results
```

测试覆盖：多视图、Sparse hierarchy、状态优先级与审计保留、越界/低 confidence/无支持 LLM 输出、未知分类、更新/删除/身份重绑定、aggregate rebuild、Snapshot roundtrip、显式标签、字段规模、路由、四工具边界、Lineage 边界、明确 facet 优先与独立 ablation。最终全量回归：**198 passed**；`git diff --check` 与 Python 编译检查通过。

本地五类 Template JSON sample 完整构建通过发布 gate：792 Fragments、110 Contexts、110 Pages；339 个 unresolved typed references 与 163 条质量诊断保留，来源覆盖仍为 PARTIAL。这是 sample 集成验证，不是完整企业资料或 live MetaOne 验证。

| 验收 Query | Synthetic 结果 |
|---|---|
| A：RSRP有哪些现有模型可以提供？ | Direct；环境可用性仍取决于独立 adapter，Reference model 不被宣称当前 available |
| B：地铁弱覆盖需要哪些数据？ | Analysis Hierarchical；召回 Purpose、Metric/Dimension 和模型 |
| C：有哪些数据可以描述小区无线覆盖质量？ | Analysis Hierarchical；避免“小区”词隐含施加 SDL 等层级限制 |
| D：LTE_PERIODIC_MR属于哪个主题域和主题？ | Direct；组织路径保留 CONFIRMED/DERIVED/CANDIDATE 的可区分状态，样例明确分类为 CONFIRMED |
| E：一个没有Topic标签的新模型应该归到哪里？ | 没有足够支持时保留 UNKNOWN；样例 UNKNOWN_MODEL 没有 Topic placement |

独立报告见 [sample-ablation.md](evaluation/hierarchy/results/sample-ablation.md) 与完整 [JSON](evaluation/hierarchy/results/sample-ablation.json)。最新 sample macro Recall：完整 0.875、Hierarchy disabled 0.830、Inference disabled 0.875；完整 Precision 0.624，关闭 Hierarchy 0.660；F1 约 0.791 / 0.789 / 0.791。完整配置交付上下文更大，不能宣称总体效率或精度提升。各组 query LLM 实际关闭，tokens=0；Context tokens 是完整 Bundle 的估计值。候选精度无样本分母时报告 null。

仍需内部验证：真实 taxonomy/同义与多义标签、企业 rule 有效性、未知模型分布、邻居候选 precision、真实 bounded LLM 的输出和成本、跨文档宽泛查询的 Recall/Precision、当前 MetaOne 的快照证据与身份映射、真实资产规模下的构建/查询延迟与上下文预算。共享特征依赖当前在内存计算，超大模型集合仍需容量测试；本轮没有新增全库 Dense 语义分类。正式四方案 E2E Benchmark、Gold/Alias、Dataset Builder 不受本轮修改。

## 文档入口

- [Semantic Hierarchy](specs/semantic-hierarchy.md)
- [Progressive Disclosure](specs/progressive-disclosure.md)
- [Hierarchical Retrieval](specs/hierarchical-retrieval.md)
- [主架构](specs/01-target-architecture.md)
