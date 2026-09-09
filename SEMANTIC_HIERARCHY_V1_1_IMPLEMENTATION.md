# Semantic Hierarchy V1.1 Implementation

基线：`648c4746209ac0e4ace5214fb6cb3af687efbebe`。实施前已完成 [PLAN](SEMANTIC_HIERARCHY_V1_1_PLAN.md)。沿用原 Context Engine、Explore、Canonical、Coverage、Binding 与四工具架构。

## 1. 五个 GAP 如何关闭

| GAP | 实现 |
|---|---|
| Intent-aware routing | retrieval_strategy.py 集中策略，QueryRouter/serving 共享固定 contract |
| Hybrid aggregate recall | AggregatePageIndex 包装现有 PageIndex，复用五通道与 RRF |
| Aggregate URI | 每个 view 独立 data://views URI，Canonical 只作为 canonical_ref |
| Applicable views | 单一配置矩阵，仅 active CONFIRMED/DERIVED 入边计数 |
| Explicit taxonomy | 带 Evidence 的独立配置贡献，优先于实例推导边，保留冲突 |

## 2. Routing 如何工作

统一策略消费 intent、scope、anchor types、requested aspects。精确 Metric/Dimension/Model/Field/Stable ID 走 direct；宽泛问题无强 anchor 走 hierarchical；anchor 加补充数据/跨场景需求走 hybrid。最多两个 views，总分支上限默认三个。服务端以实际 Page/ElementIndex 命中校准 QueryRouter 的临时标识符判断。

固定输出 mode、hierarchy_views、primary_view、confidence、reasons；契约同步 Python/MCP/schema。Bounded semantic router 保持 intent/entities/aspects 固定 schema，扩展受限 intent enum，不能自由生成 View。显式 mode/hierarchy 参数兼容；明确 warehouse layer scope 优先，普通业务语句匹配到 taxonomy alias 不再自动成为用户未要求的 hard layer filter。

## 3. Aggregate Hybrid Search 如何工作

每个 view 独立 PageIndex，先限定 view，再复用 Exact/Alias、BM25、既有 Dense encoder、Facet 与 RRF。仅嵌入 L0/L1 的 branch ID/name/aliases/view、summary、top objects/metrics/dimensions/purposes/models、taxonomy labels；L2 全量成员、Evidence 和候选审计不进入 embedding。

返回原始各通道分数和 rrf、成员概要、placement_quality、实际 encoder 版本及告警。Rerank 轻度惩罚 candidate 比例，不按分支大小加分。全局 availability 未验证，不伪造可用性加分。Candidate-only 分支排除；本轮 candidate_branch_weight 仅支持默认 0。Facet-only 结果不能冒充查询相关分支。Dense 不可用时显式告警并保留 lexical fallback。

原 Entity Hybrid 排序算法保持不变，仅增加通道诊断；PageIndex 增加 remove。适配器按文档指纹维护索引，复用未变更 L0/L1 文档向量。查询不重跑 hierarchy 构建或推断。

## 4. URI 如何消歧

`data://topics/<slug>` 的 L0/L1/L2 始终返回 Canonical Page。`data://views/domain/topic/<slug>` 始终返回 Aggregate Page，包含 node_ref、canonical_ref、member_refs、child_branches。每页单一 view，保留 view-keyed content 兼容结构；L1 引用预览有界，完整成员在 L2。

显式 taxonomy 叶分组也有可读取的空 aggregate。Important Element 预览改用 machine-facing `hierarchy://elements/...`，不生成字段 Rich Page。V1 organization snapshot 明确拒绝混用，需要从原 Template/Fragment 交付重建 V1.1；V1.1 snapshot 正常 roundtrip。

## 5. Applicable View 如何计算

hierarchy_config 为单一矩阵入口：Metric/Dimension/Scenario/Purpose 仅 analysis；Business Object 为 analysis/domain；两个 Model 类型为全部三视图。旧 topic 类型兼容 APP，因此适用 analysis/domain。可配置为合法更窄集合。

保留小写 classified/partially_classified/unclassified 和 views，增加 applicable_views、confirmed_views、derived_views、candidate_views、missing_views。只有 active CONFIRMED/DERIVED 入边计数；CANDIDATE 不使正式分类完成。不适用视图 placement 报错。根节点没有 parent 时可显示 unclassified，不等于缺少源事实。

## 6. Explicit Taxonomy 如何构建

taxonomy_nodes/taxonomy_edges 进入现有 HierarchyIndex 的 @taxonomy 贡献；原 taxonomy 保持 classifier 候选集用途。规范边必须有 CONFIRMED、explicit_taxonomy、source 和有效 SourceLocation Evidence，仅 source 名称不足以确认。样例配置明确标记 synthetic。

无需共同标签实例即可构建 sparse Domain→Topic。精确 node alias 可供 placement 使用。显式 taxonomy 在相同 view/child/parent-kind 槽优先，实例冲突边保留 audit 并失活。未知节点、非法 edge、cycle、不适用视图在构建前拒绝。

## 7. Incremental / Snapshot / Quality

拆分 inference、taxonomy、materialization/index、routing 指纹。Taxonomy edge 修改只更新变化端点和旧/新祖先；label/alias 修改重新投影依赖它的实例与规则 placement。实体变更沿既有依赖更新；routing 版本变化不重跑分类；materializer/index 版本变化只重建 aggregate。未变化聚合对象和索引文档复用，向量缓存只补编码变化文档。

semantic-hierarchy/v1.1 快照保存适用矩阵、版本、组织配置、依赖、历史、聚合页与 aggregate_index_manifest。新增 gate：page_path_collision、invalid_taxonomy_edge、taxonomy_cycle、unknown_taxonomy_node、entity_placed_in_non_applicable_view、candidate_as_classified、aggregate_index_stale、view_uri_mismatch、organization_config_stale。

Template 样例：792 fragments、110 contexts/pages、275 hierarchy nodes、363 edges；163 个质量诊断均非 error，339 unresolved references 保留，来源仍为 PARTIAL。输出 `/tmp/data-explore-hierarchy-v11-final`；无变更重建至 `/tmp/data-explore-hierarchy-v11-final-reloaded` 后版本均为 `context-e663170050964688`，changed/rebuilt entities、rebuilt aggregates、inference calls 全为零。

## 8. Tests 与 Ablation

`uv run --isolated --extra dev pytest -q`：**227 passed**。新增回归覆盖路由 golden cases、schema、URI 逐级读取、taxonomy 优先级、candidate 隔离、增量重投影、向量复用、快照与污染 gate、bounded router、四工具调用边界。

九条样例覆盖 exact、broad analysis/domain/asset、cross-domain、cross-document 和 unknown。正式四方案 Benchmark 未改。下面使用 FastEmbed 0.8.0 + 本地多语言 MiniLM 真实 embedding；无检索告警，Query LLM 关闭，所有 variant 平均两次 Context Tool 调用。

| Variant | Recall | Precision | F1 | Broad Recall | Broad F1 |
|---|---:|---:|---:|---:|---:|
| Full | 1.0000 | 0.5503 | 0.7336 | 1.0000 | 0.7539 |
| Hierarchy disabled | 0.9531 | 0.5562 | 0.7184 | 0.9375 | 0.7337 |
| Lexical branch | 1.0000 | 0.5503 | 0.7336 | 1.0000 | 0.7539 |
| Hybrid branch | 1.0000 | 0.5503 | 0.7336 | 1.0000 | 0.7539 |
| Inference disabled | 0.9688 | 0.5423 | 0.7184 | 0.9583 | 0.7337 |

启用 Hierarchy 各组 mode/view accuracy 均为 1.0；exact 组在所有 variant 的 Recall/Precision/F1 一致，工具调用没有增加。Hierarchy disabled 强制 direct，其宽泛路由低分来自消融定义。

该九条样例 lexical/hybrid branch 的最终成员指标相同，不能据此宣称 Hybrid 普遍优胜。独立非词面实验有 Mobility / Wireless Coverage / Billing 三个英文分支，两条中文问题均未命中 lexical；真实 MiniLM 与受控 fixture encoder 两组实验中，Hybrid Branch Recall@1/@3 均为 1.0，lexical 均为 0。真实编码器的两条目标相似度约 0.5571 / 0.3306，排名均为第一。

- [真实 embedding 五组消融](evaluation/hierarchy/results/v1.1/trained/sample-ablation.json)
- [真实 embedding 非词面实验](evaluation/hierarchy/results/v1.1/trained-semantic-branches.json)
- [轻依赖与受控编码器机械验证](evaluation/hierarchy/results/v1.1/sample-ablation.json)

完整报告保留分类率、候选率、Branch@1/@3、AnchorRecall、AggregatePrecision、逐 case 缺失和 token 估计。Anchor 期望只保存在评价 case，不传入生产。空分母为 null。

```bash
uv run --isolated --extra dev --extra dense python -m evaluation.hierarchy.run --out /tmp/v11-ablation
uv run --isolated --extra dev --extra dense python -m evaluation.hierarchy.semantic_branches --out /tmp/v11-semantic.json
```

完整 delivered token 包含 Coverage/Evidence/trace，不能等同 hydration budget。本次宽泛 Recall/F1 提升伴随额外 token，Precision 没有同步提升，不声明成本优势。

## 9. 仍需真实数据验证

真实 embedding 已验证；语料、taxonomy、查询和环境仍是 synthetic/template。企业 taxonomy/evidence 审批、真实查询分布、多义分支 Precision、大规模索引、延迟/内存/token 成本、真实 MetaOne 可用性与 LLM 路由准确性仍需验证。未修改 DatasetBuilder、正式 E2E benchmark，未向生产注入 Gold/Alias/评分器内容。

## 10. 为什么未实现 Dense Semantic Classification

Dense 仅用于查询期 aggregate recall；构建期保留 explicit/rule/tag/neighbor/bounded LLM，没有逐实体 embedding taxonomy 分类。现有 OverlayClassifier.classify 的有界 placement 输出保留扩展边界；未来接入仍须遵守候选和证据 gate，不能提升 Canonical 事实。

本轮提交仅包含 V1.1 相关代码、契约、测试、评测结果和文档；原有 IDE、图表、忽略规则等改动保持原样。
