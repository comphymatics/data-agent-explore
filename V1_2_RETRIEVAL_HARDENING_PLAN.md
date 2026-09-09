# V1.2 Retrieval Hardening Plan

基线 fd8538f；范围仅为 scale/precision hardening。已阅读任务指定的十个源文件。

| 问题 / 当前瓶颈 | 修改位置与复用能力 | 内部契约 / 复杂度 | 兼容性与测试 |
|---|---|---|---|
| Exact anchor 遍历 Page/Element exact keys 及 Context identity | 复用两个 exact 字典；统一 ExactMentionResolver 提取 identifier、限定名、短语、中文 alias；索引所有权仍在 PageIndex/ElementIndex | 增量 Trie 仅存词，不复制目标记录；查询按 query 长度与实际匹配输出执行，目标展开有预算；diagnostics 记录候选与 get 次数 | 保留 parent_page/type/kind；5000 模型、500000 字段；禁止 exact.items/values 迭代的哨兵测试 |
| Branch member_refs 全量枚举再评分 | HierarchyIndex 在 aggregate 更新时维护内部 membership；PageIndex 增量倒排/长度信息；现有 hybrid_search 接收内部候选预算与 membership scope，仍使用 Exact/BM25/Dense/Facet/RRF | 分支召回后有界候选，membership 只做 contains；候选池、单分支检查量、最终 Bundle 均有硬上界；密集通道在候选池重排，截断明确可见 | 不增加工具或第二套搜索算法；10K 分支，毒化 member_refs 防止查询迭代；精度/召回损失需要报告 |
| 多父多子 co-classification 笛卡尔积 | HierarchyIndex._build_context 增加关系依据守卫 | 单边基数为1允许；多对多仅保留明确关系/Taxonomy支持；默认省略歧义边 | 1×3、3×1、2×2 无关系、有关系测试；Guard OFF/ON 独立消融 |
| Explicit Taxonomy 未校验 kind 方向 | hierarchy_config + hierarchy_contracts 的集中 transitions 配置 | 有向合法关系表，允许配置 sparse skip；非法配置 fail fast | 独立错误码、反向/跨 View/环/未知节点测试 |
| 宽泛低置信 Query 默认 Analysis | 在现有 AggregatePageIndex 上做逐 View 轻量 recall，复用命中结果 | confidence threshold、top view≤2；initial/arbitration/final trace；无额外 LLM | 精确 Direct bypass；高置信/显式 View 保留；跨 View 独立消融 |
| Snapshot / Incremental / Quality | 扩展现有配置指纹、Hierarchy dependencies、Page/Element add/remove 和 snapshot gate | mention/branch/policy/guard version 纳入指纹；局部变更按所有权删除旧词与 posting，分支只更新受影响 aggregate | stale/tamper、无变化/alias更新、删除、持久化回读、旧策略拒绝混用 |

## 执行与验收

1. Mention → bounded branch retrieval → ambiguity guard → transition validation → arbitration。
2. 扩展当前增量、Snapshot 与 Quality Gate，不新建持久化系统。
3. 在 tests/performance 提供可重复的大规模 A/B/C 场景，记录 p50/p95、latency、候选与检查量；毫秒数不作为跨硬件 SLA。
4. 在独立内部评测中比较 Guard OFF/ON、原始路由/Arbitration；不修改正式 E2E scorer、Gold 或生产语义来优化分数。
5. 跑现有功能回归及新测试，输出实施报告、真实测量结果与尚需真实企业数据验证的局限。

Canonical Context、Context Bundle、四工具、现有 View/Page 类型和 Graph 边界保持稳定。查询诊断仅为可选 trace。不会自动设计 V1.3。
