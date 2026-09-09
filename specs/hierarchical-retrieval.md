# Hierarchical Retrieval

Serving 和 Explore 继续只使用 `data_search/data_read/data_expand/data_source` 及独立 Environment Binding adapter。没有新增 graph/tree traversal 工具。

## 入口和路由

`data_search(..., mode="auto", hierarchy=None)` 与 `ExploreAgent.explore(..., mode="auto", hierarchy=None)` 支持 `auto/direct/hierarchical/hybrid`；View 可选 `analysis/domain/asset`。参数已同步到 Python tools 和 MCP input schema。Context Bundle 只新增可选 `retrieval_trace`，旧字段保持。

- Direct：精确 Model/Metric/Dimension Name、Canonical/Stable ID、Field/Counter 等 Element ID 命中，直接进入原 Hybrid Anchor + Relation Completion。中文语法紧邻 ASCII 标识符仍能识别。明确命名的 Page 优先于其他模型中的共享字段。
- Hierarchical：没有强实体锚点时，消费 intent/scope/anchor type/requested aspects 的集中策略选择 View。
- Hybrid：明确 Anchor 加“还需要/跨域/结合”等扩展意图，结合直接锚点和 Analysis 等分支。

“小区”等业务对象名可能也是建模 taxonomy alias。宽泛“有哪些数据”问题没有明确建模层/主题约束时，Router 不把隐含分类层级当成硬 filter。显式传给 `data_search(scope=...)` 的 scope 仍受治理；DERIVED active 组织可满足相应导航筛选，候选不能满足。

## 一次 Serving 操作

```text
Direct: exact/element anchor + existing hybrid retrieval
Hierarchical: view filter → AggregatePageIndex hybrid channels → RRF → branch rerank → L1 aggregate
              → real member anchors + existing entity hybrid relevance
Hybrid: merge the two anchor sets
    → existing BundleAssembler relation/backref completion
    → diversity/ranking/budget
    → Context Bundle assembly
    → existing Coverage Check
    → existing Focused Expansion
```

`AggregatePageIndex` 按 view 包装现有 PageIndex，复用 Exact/Alias、BM25、既有 Dense encoder、Facet 与 RRF；默认一次最多两个视图、合计三个分支。没有复制 embedding 或实体排序算法。V1.1 复用实体 Hybrid 排序；V1.2 在同一路径上增加候选计算预算，详见下文。

仅索引 branch ID/name/aliases/view、L0、有界 L1 summary/objects/metrics/dimensions/purposes/models 和 taxonomy labels。L2 的全量成员、边、Evidence、候选审计不进入 embedding。按文档指纹更新 postings，并缓存未变更文档向量；服务查询不重建组织。

Rerank 使用融合分数和有效 placement 比例，候选会产生惩罚，不给大分支天然加分。全局 availability 未验证，因此只返回明确 UNRESOLVED 摘要，不伪造 availability 加分。Candidate-only 分支不进入索引；本轮 candidate_branch_weight 仅允许默认 0，不实现低权重候选召回。Facet-only 无语义相关性结果被过滤。Dense 不可用时输出显式 branch_warnings 并保留 lexical/exact 回退。

`retrieval_strategy.py` 是唯一 mode/view policy，QueryRouter 产出固定 `retrieval_strategy`（mode、hierarchy_views、primary_view、confidence、reasons）；Python/MCP data_search 接受该可选 contract。服务用实际 Page/Element exact matches 校准临时标识符，不让自由文本伪造强 Anchor。Bounded semantic router 继续固定 intent/entities/aspects schema，只能从受限 intent/aspect enum 选择；View 由策略映射生成，不能由模型自由命名。显式 mode/hierarchy 参数仍兼容。明确层级 scope 优先；隐含 taxonomy alias 不成为用户未要求的 hard layer filter。策略最多选择两个视图。

Branch trace 返回 path/hierarchy_view/score/score_breakdown（exact、bm25、dense、facet、rrf）、l0、member_summary、placement_quality、实际 encoder 版本/通道。分支内部成员再经过原类型/scope 策略和现有 BundleAssembler；无支持成员时回退 Entity Retrieval 并记录 no_supported_branch。

## Trace 和边界

`retrieval_trace` 包含 mode、hierarchy_view、exact/page/element anchors、branch candidates、selected_branches、披露的 hierarchy_contexts、fallback、预算截断信息。

状态区别始终可查：原 Page 的 `hierarchy.parents` 和 Focused Expansion 返回 Edge status/provenance/active/conflicts；DERIVED/CANDIDATE 不会变成 Canonical `topic`。Coverage 仍仅根据原支持事实及环境覆盖判定，不因一个组织分支就自动满足字段、粒度、Join 或可用性。

现有 Explore 流程正常仍为一次 `data_search` 加最多一次有界 `data_expand`；Hierarchy 不增加调用轮次。External Environment Adapter 和用户已有查询期 semantic provider 的调用仍按原 telemetry 单独记录。

## 独立 ablation

```bash
uv run --isolated --extra dev python -m evaluation.hierarchy.run \
  --out evaluation/hierarchy/results
```

比较 Full、Hierarchy disabled、Lexical branch retrieval、Hybrid branch retrieval、Semantic inference disabled 五组。Hierarchy disabled 关闭查询期分支检索与 Page 组织披露；Semantic inference disabled 保留显式/受治理 Backbone，关闭新增 semantic overlay。输入资料和 Gold 分离，case expectations 只交给评价消费者，绝不进入 compiler、组织配置或 Explore query options。

报告 Recall/Precision/F1、Query LLM Tokens、完整 Delivered Context 估计 Tokens、Tool Calls，并按 exact、broad/cross-document、purpose→data、model→analysis、unknown、cross-domain 和 inferred organization 分组。内部诊断含 entry/routing accuracy、Branch Recall@1/@3、Branch Precision@3、独立标注 Anchor Recall、Aggregate Precision、Candidate Placement Rate、Candidate Precision、Inference Coverage、Unclassified Rate；另按 exact/broad 分组。空分母保持 null；UNKNOWN 不强行当正确实体。该报告独立于正式四方案 E2E leaderboard。

本次小样本查询期不启用 LLM，因此 Query LLM Tokens 为真实零调用，不能据此推断接入真实 LLM 后的成本。Fixture provider 测试验证 bounded output gate，不代表真实模型准确率。真实 MetaOne、真实 taxonomy、邻居有效性、多义查询路由和 token/latency 收益仍需内部实测。

V1.1 实测报告：`evaluation/hierarchy/results/v1.1/trained/sample-ablation.json`。非词面分支实验可独立执行：

```bash
uv run --isolated --extra dev --extra dense python -m evaluation.hierarchy.semantic_branches \
  --out /tmp/trained-semantic-branches.json
```

该命令使用本机缓存的真实多语言 MiniLM，local_files_only=True；数据仍为 synthetic。另有受控 FixtureSemanticEncoder 机械测试，仅位于 evaluation，不进入生产编码器。没有 Dense Entity Classification。缺失真实数据评审时，不把两条样例命中解读为企业语义检索整体准确率。

## V1.2：规模与精度加固

### Query-driven Exact Mention

统一 `ExactMentionResolver` 消费 **现有** PageIndex.exact 和 ElementIndex.exact。ASCII identifier（含 snake_case/camelCase/UPPER_CASE）、限定名及其组成部分、引号短语由 Query 提取；中文/多词 alias 使用随所属索引增量维护的词汇 Trie。Trie 不复制目标记录，不引入 embedding。字段的显式 alias 同样进入原 Element exact postings。

Query 只对候选执行 `exact.get(normalized)`；不会迭代 exact keys，也不会再遍历所有 Context 的 stable IDs。Canonical path/stable ID/strong key 在构建/加载时进入同一 Page exact 索引。Mention 结果保留实际目标 ID、parent_page、entity_type、element_type；过多同名目标按预算截断并明确报告，不能视为穷尽全部匹配。

复杂度是 O(Q×L + C log C + T log T)，其中 Q 为 Query 长度、L 为最长匹配词长度、C 为查询候选数、T 为有界目标展开量；不含遍历所有 exact keys 的项。Trie 为逐起点匹配，最坏 O(Q²)，并非声称 Aho-Corasick 的严格 O(Q)。排序 posting 在离线维护，查询不对整个命中 posting 排序。

### Bounded Branch-scoped Entity Retrieval

配置位于现有 hierarchy config：

```yaml
hierarchy_retrieval:
  branch_k: 3
  entity_candidate_k: 50
  max_entities_examined_per_branch: 100
  bundle_k: 8
view_arbitration:
  enabled: true
  confidence_threshold: 0.80
  max_views: 2
  branch_k: 3
```

`HierarchyIndex._index_aggregate` 在受影响 Aggregate 更新时维护成员 membership 与最多 1000 个确定性预览 ID；这是原组织索引的内部投影。查询不读取或枚举全量 `member_refs`。

现有 PageIndex 增量维护 BM25 token postings、文档长度及总长度。现有 Hybrid Retrieval 增加内部 `candidate_limit/allowed_paths/fallback_paths` 参数：优先从 exact、低文档频率 token postings 取得有界候选，对 branch membership 做 contains 过滤；不足时使用已物化的有界成员预览。随后仍执行原 Exact/BM25/Dense/Facet/RRF。没有第二套搜索引擎。每个分支最多读取 100 个 posting ID、检查/评分 100 个实体，再保留 50 个候选；所有选中分支合计默认最多检查 300 个实体，最终最多 8 个 Rich Page。

全局 seed 同样使用预算。Aggregate hybrid recall 每个 View 的候选池上限为 256，最多仲裁三个 View；该常量归属 hardening policy 版本。传统 lexical branch ablation 仍是离线基线。原 BundleAssembler 也在读取 reference/backref 时应用已有候选预算，避免先构造全量关系列表再截断。

**召回取舍必须显式说明**：这是有界候选检索，不保证全库或大分支 exact top-k。Dense 在召回候选池内排序；不新增 ANN 或 Dense taxonomy classifier。只有 Dense 相关、没有词面召回且不在有界预览中的尾部实体可能被遗漏。命中分支提供 scope 分数，不伪造实体的词面命中。`truncated` 和各阶段预算均进入 diagnostics；真实语料需校准候选预算、Precision 与 Recall。

L1 保留摘要、top members 和计数；全量 member_refs 仅属于 L2/内部索引。成员数量不再线性影响这些 Query-time 阶段的计算量。对外 Context Tool、Context Bundle 和四方案 E2E 合约保持不变。

### Low-confidence Cross-view Arbitration

保留集中策略与已有关键词，不新增领域关键词补丁。无 exact anchor、非显式 View、confidence < 0.80 时，对 Analysis/Domain/Asset **分别复用 AggregatePageIndex Hybrid Recall**。当前 view score = 0.7×best RRF + 0.3×top-k mean RRF；有实际召回证据的初始 View 给予 1.1 倍 prior，用于相近排名的裁决。选择得分不低于最好分 80% 的前 1～2 个 View，并复用已召回行，不重复执行分支搜索。

零相关证据时保留初始路由并报告 fallback，不伪造正确 View；Exact Direct 和明确 View override 均绕过仲裁。置信度高的结构化路由保持原 View；低置信 preferred strategy 不会因 intent 映射被抬高为 0.95。无新增 LLM 调用。

Trace 增加 `mention_resolution`、`entity_retrieval`、`branch_budget`、`view_arbitration`、`routing.initial/arbitration/final` 与 `relation_completion`，旧消费者可忽略。

### 验证与边界

```bash
uv run --isolated --extra dev pytest -q
RUN_RETRIEVAL_SCALE=1 uv run --isolated --extra dev pytest -q -s tests/performance
uv run --isolated --extra dev python -m evaluation.hierarchy.hardening
```

规模诊断真实构建 5000 个含字段模型/500000 条 Element 记录；另运行 10000 成员单分支和 100 Aggregate/10000 Page/500000 Element 组合场景。通过禁止 exact 迭代、禁止分支 member_refs 迭代的运行时哨兵及计数检查验证复杂度，不仅比较毫秒数。结果在 `evaluation/hierarchy/results/v1.2/`。

该规模实验验证索引与 serving，不是完整 Parser/Canonical 构建、真实 Dense/LLM 或 MetaOne 联调的规模认证。Guard/Arbitration ablation 是独立消费者，不修改正式 E2E scorer，也不向生产配置或索引传递期待答案。
