# Semantic Hierarchy contract

状态：已实现；测试与 ablation 使用 synthetic/sample 数据。真实语义目录与真实 LLM 精度仍需内部验证。

## 语义组织、事实图与披露等级

Canonical Entity 仍只有一份。`HierarchyIndex` 是现有 `SemanticOrganizationBuilder` 的多视图组织投影，不是 Ontology，也不构成第二个 Canonical Registry。

| 机制 | 回答的问题 | 边界 |
|---|---|---|
| TypedReference | 哪些明确的业务/模型关系成立 | 继续使用现有引用解析、Evidence 和状态契约 |
| Backend Graph | 上下游、影响、反向引用、关系补全 | machine-facing；不加入 `organized_under` |
| HierarchyEdge | 从哪个语义分支可以找到实体 | 组织路径，不是 `requires_metric` 等业务事实 |
| L0/L1/L2 | 同一实体/聚合视图披露多少内容 | 与 Analysis/Domain/Asset 正交 |

## 三个正式 View

- Analysis：Scenario → Purpose → Metric/Dimension → Business Object → Logical/Physical Model。
- Domain：Business Category/Data Domain → Topic Domain → Topic → Object/Sub-object → Logical/Physical Model。
- Asset：Layer → Logical Model → Physical Model → 有界 Important Element 预览。

以上是导航层级，允许跳级和多个 parent。不存在的 Topic 不补 UNKNOWN 节点。一个模型可以同时在三个 View 中；同名虚拟分组按 `view + kind + label` 稳定寻址。若标签精确匹配唯一 Canonical Entity，内部组织节点复用其 path；aggregate 始终使用独立 View URI，并以 canonical_ref 指向它。别名歧义保留诊断并停止该匹配。

`data://views/domain/topic/<percent-encoded-label>` 是聚合分组路径。旧 `hierarchy://models/<layer>/<domain>/<topic>` 作为 URI 兼容入口分别映射到 Asset Layer、Domain Topic Domain、Domain Topic。它不再表示一棵 Layer→Domain→Topic 树。每个 Page 保留全部 `parents` 和各 View 的 `breadcrumbs`；单个 `breadcrumb` 只作兼容预览。

APP/Analysis Group 使用旧 `topic` Canonical 类型的兼容语义保持不变；Scenario 的显式 `part_of` 进入 Analysis 导航，不把 APP 当成建模 Topic。

## Edge 与状态

正式契约见 `contracts/semantic-hierarchy-edge.schema.json` 和 `hierarchy_contracts.HierarchyEdge`：

```yaml
hierarchy_id: domain
parent_id: data://views/domain/topic/...
child_id: data://physical-models/...
relation: organized_under
status: CONFIRMED | DERIVED | CANDIDATE
confidence: 0.95
provenance:
  method: explicit | explicit_taxonomy | domain_rule | metadata_inference | neighbor_inference | llm_inference
  source_ids: [source-id]
  source_relation: topic
  rule_id: enterprise-rule/v1
  input_facts: [{context: context-path, section: metrics, value: [metric-name]}]
evidence: [existing-source-location]
inference_version: policy-version
created_at: UTC-timestamp
```

`edge_id` 不含时间戳；`source/target/assertion_status` 是旧可视化消费者的兼容字段。重复来源合并成一个 Edge，保留 source IDs、Evidence 和 owners。

- CONFIRMED：只投影显式且有 Evidence 的分类、结构化标签、明确引用。
- DERIVED：已有受治理分类、配置规则，以及显式共分类的导航组织投影。必须保存 rule ID、输入事实、confidence、policy version；不回写 Canonical 的 `topic` 等字段。
- CANDIDATE：元数据特征匹配、邻居归纳或受控 LLM 选择。保存在独立贡献/audit 中，`active=false`；不会成为硬筛选或 Backend Graph 的事实。

同一 View、child、parent kind 出现竞争时，显式 taxonomy 优先，其次 CONFIRMED > DERIVED > CANDIDATE；较弱结果保留，附 `placement_conflict`。同等级多父组织允许存在，多个 confirmed placement 会报告诊断；企业配置可通过 `exclusive_slots` 指定互斥的 view/kind，使冲突阻止发布。跨 View 的重复出现不是冲突。

## Backbone 和配置

Compiler 在 Canonical Fusion、Business Mapping、Reference Resolution 后调用现有组织模块。Builder 读取显式 sections、已解析 typed references、结构化 tags、受治理分类，不调用 Parser，也不将 lineage 转换成 hierarchy。

明确的结构化标签示例：

```json
{"hierarchy_id":"domain","kind":"topic","label":"企业主题","status":"EXPLICIT"}
```

标签仍需 `evidence.tags`。字符串标签只有在配置 `tag_mappings` 中存在带 `rule_id` 的明确映射时，才产生 DERIVED 组织边。普通名称相似只能产生候选。

配置由 `hierarchy_config.py` 校验；示例为 `config/semantic-hierarchy.sample.json`。支持 taxonomy、rules、tag_mappings、feature_weights、confidence_threshold、ambiguity_margin、candidate_limit、max_neighbors、branch_k、important_element_limit、max_llm_calls、max_input_characters、prompt_version、exclusive_slots 及三个开关。默认没有企业 taxonomy，不擅自补全分类。

来源优先级在 `hierarchy_contracts.SOURCE_PRIORITY` 中统一定义：Explicit Metadata → Document Mapping → Standard/SID Exact → Model Tags → Explicit Relations → Grain/Dimension/Metric → Important Fields → Neighbor → Dense Similarity → LLM。显式组织占据的分类槽不会交给 classifier 重判；领域规则先于特征/邻居评分，只有不确定时才允许 LLM。本版本没有新增全库 Dense 分类任务；现有 Hybrid Retrieval 保持独立。

## Bounded inference 与撤销

`hierarchy_inference.OverlayClassifier` 复用现有 `StructuredInferenceProvider.infer` 协议。它只输出组织 placement，不运行已有文档语义抽取任务，不生成 Fragment/Canonical Fact。

流程：有界特征 → 共享 metrics/dimensions/grain/objects/重要字段/明确引用的已分类邻居 → 候选标签 → 显式输入规则 → 特征/邻居评分 → 歧义时可选 LLM。邻居只使用 confirmed 分类分布，避免候选自我强化。

LLM 输入包含候选 ID、模型局部内容、邻居分布、允许支持的 context IDs 和领域规则。输出只接受 `selected/confidence/reasons/supporting_context_ids` 的有效选择；越界标签、无效 confidence、未知支持 Context/缺 Evidence 被拒绝。低 confidence 或 abstention 保持 UNKNOWN，不 fallback 到最高候选。候选审计保存 candidate set、selected、confidence、supporting features/contexts、model、prompt version、scores/reasons。

默认禁用 LLM。调用次数、候选数量、邻居数量、输入字符数有界；实际 HTTP timeout/retry/output limit 复用既有 provider 配置。关闭 inference、改变规则、删除源事实或更新上下文会撤销当前 placement；旧贡献及审计保存在 `history`。没有自动 promotion 机制。

## 增量和快照

`HierarchyIndex.update(contexts)` 对输入 Context 和组织策略做 fingerprint，利用 Entity→引用/共享特征依赖找到受影响实体。只重建相关贡献、必要邻居推断和旧/新 Aggregate Ancestors；无变更时不会重新 inference 或 materialize。增加、删除、重新分类都失效旧祖先，未受影响 aggregate 对象继续复用。仅推断相关配置变化允许实体分类全量失效；taxonomy 边修改只更新变动端点和旧/新祖先，routing 版本变化不重跑分类，materializer/index 版本变化只失效 aggregate。

`ContextCompiler.compile_fragments(..., previous_compiled=previous)` 接入此路径。Canonical 编译本身仍使用原有流程；本轮增量保证针对组织贡献、aggregate 和 branch postings，并不宣称 Parser 或全部 Canonical Fusion 已增量化。

`semantic-organization.json` 与不可变快照一同保存，包含贡献、候选审计、聚合页、依赖、fingerprints、历史。没有组织文件的旧快照可重建 deterministic backbone，不调用 LLM；已有 V1 组织文件必须显式从原始 Template/Fragment 交付重建，V1.1 loader 拒绝将它与新 contract 混用。组织内容进入快照 hash，`created_at` 作为审计时间不进入语义 hash。重载不重新推断。

## Quality gate

发布和加载检查：broken parent/child、cycle（包括候选）、duplicate edge、confirmed placement 冲突、alias collision、无效 view/status/relation、candidate promotion、confidence、provenance、rule inputs、inference version、Evidence 是否存在、aggregate membership mismatch。结构化 snapshot 契约见 `contracts/semantic-organization.schema.json`。缺失知识/不完整来源是显式状态，不是发布错误；造假的引用、环、错误成员等是阻断错误。

## V1.1 Applicable View 与显式 Taxonomy

`hierarchy_config.validate_hierarchy_config` 是适用矩阵的单一入口；默认取正式 View 的实体类型交集，允许配置为更窄的非空集合。Metric/Dimension 仅 analysis；Scenario/Purpose 仅 analysis；Business Object 为 analysis/domain；两个 Model 类型适用全部三个视图。旧 topic 类型兼容 APP，适用 analysis/domain。

classification 保留小写 status（classified/partially_classified/unclassified）和 views，增加 applicable_views、confirmed_views、derived_views、candidate_views、missing_views。只有 active CONFIRMED/DERIVED 的入边计入正式 placement；不适用视图不进分母，CANDIDATE 永远不能使分类完成。根节点没有 parent 时仍可以显示 unclassified，这不表示缺少源事实。

`taxonomy_nodes` 是受治理标签定义，`taxonomy_edges` 是独立规范关系；原 `taxonomy` 继续是 classifier 候选集合，不自动生成事实。示例及结构见 `config/semantic-hierarchy.sample.json`、`contracts/semantic-hierarchy-config.schema.json`。每条 edge 必须有 parent/child、CONFIRMED、provenance.method=explicit_taxonomy、provenance.source 和有效 SourceLocation Evidence。纯 source 名称不能代替 Evidence。无需任何模型携带共同标签即可构建 sparse taxonomy；不制造 UNKNOWN 层。配置节点 alias 可用于精确 placement，实例冲突边保留审计并失活。

V1.1 新 gate 包含 page_path_collision、invalid_taxonomy_edge、taxonomy_cycle、unknown_taxonomy_node、entity_placed_in_non_applicable_view、candidate_as_classified、aggregate_index_stale、view_uri_mismatch、organization_config_stale。配置错误在构建前拒绝；其余错误阻止发布/加载。组织快照版本为 semantic-hierarchy/v1.1，保存适用矩阵、routing/materializer/index/inference 配置及指纹和 aggregate index manifest。
