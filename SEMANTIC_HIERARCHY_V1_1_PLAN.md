# Semantic Hierarchy V1.1 实施计划

基线：`648c4746209ac0e4ace5214fb6cb3af687efbebe`。已读取 hierarchy contracts/config/inference/index、aggregate materialization、hierarchical retrieval、retrieval service、Explore router/agent；继续使用现有 organization projection。

| GAP | 当前实现和问题 | 复用与修改 | Contract / 兼容性 | 验证 |
| --- | --- | --- | --- | --- |
| Applicable views | classification 固定以三个 view 为分母 | hierarchy_config 集中矩阵，HierarchyIndex.classification 和 edge gate 消费 | 保留小写 status 与 views，新增 applicable/confirmed/derived/candidate/missing_views | metric 仅 analysis 即 classified；candidate 不计数；非法 placement 报错 |
| URI | canonical node path 同时作为 aggregate key | 保留内部 canonical node identity；materializer 为每个 node/view 输出独立 URI | aggregate 新增 node_ref/canonical_ref/member_refs/child_branches；canonical read 不变；旧 organization snapshot 明确版本拒绝并要求重建 | 同名 canonical/aggregate 各自 L0/L1/L2；碰撞和 view mismatch gate |
| Explicit taxonomy | 只有 classifier label，层级依赖实例 co-classification | config 扩展 nodes/edges，复用 _node/_record/_reindex；配置贡献独立 owner | evidence-backed CONFIRMED explicit_taxonomy；最高组织优先级；不生成 Canonical/TypedReference | 无实例 sparse taxonomy、冲突保留、未知节点/非法边/循环 |
| Routing | intent 参数未消费，view 按几个关键词 | 新增集中 retrieval_strategy policy；QueryRouter 与 serving 共用；复用 bounded semantic router | 固定 mode/views(max2)/primary/confidence/reasons schema；新增可选 strategy，服务端以真实 exact anchor 校准；旧调用兼容 | 六组 golden + 第二条 hybrid 例子；unknown view 拒绝；exact 两次 tool call 上限 |
| Branch hybrid | L0 overlap + 名称 + L1 + size | 新增 AggregatePageIndex 包装现有 PageIndex/Exact/BM25/encoder/Facet/RRF；原 entity 排序不变，仅增加通道诊断 | 每 view 独立索引；只嵌入 L0/L1 有界概要；返回各通道分数、成员概要与 placement_quality | 非词面 fixture encoder 检验 hybrid 胜 lexical；candidate 不进入 strong index；view prefilter |

实施顺序：Applicable/URI → taxonomy → router → AggregatePageIndex → serving → incremental/snapshot/quality → tests/ablation → docs。

增量：将推断配置 fingerprint 与 taxonomy/materialization/routing fingerprint 分开；taxonomy 改动只更新配置贡献、受影响 placement 节点与新旧祖先；aggregate 按内部 node_ref 跟踪，索引按内容指纹更新。routing 变更更新快照版本但不重跑分类。保存适用矩阵、policy/materializer/index 版本，拒绝混用旧版组织快照。

测试与报告：运行现有 Python 测试，新增 V1.1 回归；独立 hierarchy ablation 增至五组并按 exact/broad 和六类查询分组，增加 routing/view/branch/anchor/aggregate/classification 指标。非词面语义 fixture encoder 仅属于 evaluation/test，明确不等于真实企业 embedding 集成；不向生产 encoder 注入评测 alias/gold。同步三份 specs 和 V1.1 implementation。Dense entity classification 不实现，保持现有规则/邻居/bounded LLM 扩展边界。

不改动 Parser、Canonical、ElementIndex、Graph、Coverage、Binding、Bundle 主 contract、四工具数量或正式 E2E benchmark。工作区原有 IDE/图表/忽略规则改动保持原样。
