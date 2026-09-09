# V1.2 Retrieval Hardening Implementation

实现基线：fd8538fbe911560ac8250b59d4a47d969f8d6d23；验证日期 2026-09-09。

本轮为 scale/precision hardening。五项功能已实现，未增加 View、Page 类型、Agent、Context Tool、Graph Tool 或 Dense taxonomy classifier。正式四方案 E2E scorer/指标未修改。

开发前计划：[V1_2_RETRIEVAL_HARDENING_PLAN.md](V1_2_RETRIEVAL_HARDENING_PLAN.md)。

## 1. Exact Mention 不再扫描整个 Index

[indexes/mention.py](enterprise_data_context/indexes/mention.py) 提供统一 ExactMentionResolver；Query 抽取 identifier/限定名及组成部分/引号短语，NFKC+casefold 后查询原 Page/Element exact 字典。中文/多词 alias 的 Trie 只保存词汇，目标记录仍由原索引所有。字段显式 aliases 进入同一 Element exact posting。

Page name/alias/canonical path/stable ID/strong key 在构建与加载时登记；查询不再扫所有 Context identity_hints。返回 target ID、parent_page、entity_type、element_type、match method 与截断说明。默认最多展开 100 个命中目标。

Page/Element exact postings 使用稳定排序容器：离线承担插入/删除成本，Query 只迭代有界前缀，不排序整个大 posting。测试以禁止 `.items()`、`.values()`、`__iter__()` 的 exact 字典哨兵证明没有扫描 key 总表，并验证不同输入顺序的截断结果一致。

## 2. Large Branch 不再枚举全部成员

扩展原 HierarchyIndex 的 aggregate 更新路径，在构建时维护成员集合和最多 1000 个预览 ID；Query 仅做 membership contains，并从预览读取预算内的 ID。没有平行 Branch Search Engine。

扩展原 PageIndex 的 token postings 与文档长度统计；同一个 hybrid_search 接收内部 candidate_limit/allowed_paths/fallback_paths，继续使用 Exact/BM25/Dense/Facet/RRF。默认每分支 posting 读取最多 100、实体检查/评分最多 100、候选最多 50、选中分支最多 3、最终 Rich Page 最多 8。Global seeds 也有候选预算，Aggregate hybrid 每 View 候选最多 256。现有 BundleAssembler 在 reference/backref 读取前应用预算，避免先构造全量关系列表。

Scope 是语义范围，不能保证范围内所有实体同样相关。当前有界倒排召回加成员预览属于近似候选选择；不声称全库精确 top-k。Dense 复用现有 encoder，但只在候选池内排序。只有 Dense 相关、没有命中词面且位于预览以外的尾部实体可能漏召回。该取舍通过 candidate/branch budget、truncated 和 warnings 显式报告。

## 3. Co-classification 歧义

原 `_build_context` 在 1×N 或 N×1 时保留 DERIVED organization；多父×多子只接受已有 CONFIRMED typed reference 或 Explicit Taxonomy 的明确配对支持，否则省略 pairwise edge。仍保留来源直接证明的实体 placement。

provenance 记录两侧基数、支持标记、输入事实与 guard version。Quality Gate 检测 ambiguous_derived_edge；Graph 不接收组织关系。测试覆盖 1×3、3×1、2×2 无关系、2×2 明确关系四种情况。

## 4. Taxonomy Transition

集中 `taxonomy_transitions` 配置在原 hierarchy config 中；默认方向来自 hierarchy_contracts。允许显式 sparse skip（如 Topic→Logical Model），不填造 UNKNOWN 层。未知节点、跨 View、环、无来源证明或非法 kind 方向 fail fast。配置/错误码及 JSON schema 一并更新。

## 5. Cross-view Arbitration

保持原 Router 与已有关键词。无 exact anchor、无显式 View 且低于默认 0.80 置信度时，对三个 View 分别调用现有 AggregatePageIndex；score 取 best/mean RRF（0.7/0.3），有召回证据的原 View 使用 1.1 prior。选最好分 80% 范围内的前 1～2 个 View，复用召回行，不额外调用 LLM。

高置信/显式 View 保留；Direct 绕过。三个 View 都无相关证据时明确记录 fallback。Trace 包含 initial/arbitration/final、view_scores、最终 views 与 primary_view。

## 6. Snapshot / Incremental / Quality

hardening/mention/guard version、Taxonomy transitions、branch budget、arbitration config 均进入现有组织配置和快照指纹。新服务拒绝缺少这些策略的旧组织快照，需从 Canonical/source 重建；不会静默混用旧 Snapshot 和新策略。

Page/Element 更新依据 Page 所有权删除旧 keys/record IDs，仅重建变动 Page 的贡献。无变更编译直接复用索引；变更时克隆可丢弃索引以保留旧快照，复用 encoder 模型对象。组织增量保留已有 Aggregate/membership，只更新受影响分支及旧新祖先；routing/budget/arbitration 变化不触发 placement 重算。

新增 gate：exact_mention_index_stale、branch_member_index_stale、unbounded_branch_retrieval、ambiguous_derived_edge、invalid_taxonomy_transition、invalid_view_arbitration_config。保存前验证实际索引所有权和词汇 Trie，加载后按保存的产物重建。

**离线限制**：变化构建的内存快照复制、全量 Canonical/Fusion、配置和来源指纹计算仍存在全量成本；没有宣称整个构建器成为亚线性增量编译器。StablePosting 将稳定排序成本放在写入端。

## 7. Scale Test 实测

原始结果：[scale.json](evaluation/hierarchy/results/v1.2/scale.json)。这是实际生成记录的 synthetic index/serving 测试，不是将小 fixture 的计时外推。

- A：5000 个含字段模型，每模型 100 个字段，共 500000 条 Element 记录。`CELL_ID在哪些模型？` 长度 13，候选 2，exact get **4** 次，exact keys **1,005,001**；展开 100 个目标并标记 truncated。
- A Anchor p50 / p95：0.025 / 14.829 ms；Element Search：0.167 / 0.261 ms。
- B：单分支 **10000 members**，实际检查 **100** 个实体，返回 **8** 个 Rich Page；查询 p50 / p95：2.225 / 6.880 ms。用会抛错的 member_refs iterator 验证 Query 未枚举成员数组。
- C：100 Aggregate Branches、10000 Entity Pages、500000 Elements；每类 12 次测量（含首次调用，p95 使用该样本的近邻上界）。

| Query 类别 | p50 ms | p95 ms | exact gets | 分支实体检查总量 | Bundle Pages |
|---|---:|---:|---:|---:|---:|
| Exact | 0.817 | 2.943 | 4 | 0 | 8 |
| Broad Analysis | 4.350 | 12.359 | 2 | 300 | 8 |
| Broad Domain | 19.821 | 20.945 | 2 | 300 | 8 |
| Broad Asset | 3.532 | 9.129 | 6 | 300 | 8 |
| Hybrid | 4.315 | 12.554 | 4 | 300 | 8 |

**Dense 状态**：本次隔离测试未安装 dense extra；配置 encoder 为 `fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，但实际 dense_active=false，返回 vector_retrieval_unavailable / ModuleNotFoundError。上述计时包含回退路径，不证明真实 embedding 编码/排序、模型冷启动、LLM 或 MetaOne 性能。硬件调度可影响 p95；本轮验收依靠操作计数和禁止扫描哨兵，不绑定毫秒 SLA。

## 8. 独立 Ablation

原始结果：[hardening-ablation.json](evaluation/hierarchy/results/v1.2/hardening-ablation.json)。期待集合只由评测消费者在结果产生后读取，不注入生产 Context/配置。

| 指标 | OFF / 旧路由 | ON / 仲裁 |
|---|---:|---:|
| 无配对证据 2×2 的 DERIVED pair | 4 | 0 |
| Broad Query / Bundle Precision | 0.40 | 0.50 |
| Selected Branch Union Precision | 0.40 | 0.50 |
| Bundle Recall | 1.00 | 1.00 |
| 三条宽泛查询 Mean View Accuracy | 0.333 | 1.000 |
| Mean Branch Recall | 0.333 | 1.000 |
| Mean Entity F1 | 0.778 | 0.778 |

守卫减少分支污染，当前小样本 Recall 未下降；但 Precision 仍非 1.0，因为 Branch Recall 仍可选入其他相近分支。仲裁改善 View/Branch 选择，**没有观察到最终 Entity F1 改善**。这些只是针对性 synthetic 消融，不外推为企业查询总体收益。

## 9. 回归与复现

- 原有 227 项功能测试全部保留并通过。
- 新增 26 项功能/治理/增量/消融检查；总计 **253 passed，1 skipped**（默认跳过显式 opt-in 规模测试）。
- 单独运行大规模测试：**1 passed**。
- Git whitespace 检查通过。Context Bundle/四工具契约兼容测试仍通过，正式 E2E scorer 与 headline metric 未修改。

```bash
uv run --isolated --extra dev pytest -q
RUN_RETRIEVAL_SCALE=1 uv run --isolated --extra dev pytest -q -s tests/performance
uv run --isolated --extra dev python -m evaluation.hierarchy.hardening
```

## 10. 仍需真实数据验证

大分支内的尾部召回、纯 Dense 相关候选、跨 View RRF 的可比性/阈值、多义名词和相近分支 Precision、真实 embedding 首次加载及批量更新成本、完整企业材料构建时间/内存、MetaOne 真实契约与服务限制，都需要内部环境验证。此次索引/serving 规模 fixture 将 Field 作为 ElementIndex 的独立真实记录，不作为额外 Hierarchy branches；不声称验证了完整带字段层级的企业快照构建。

本轮停止在 V1.2 范围，不设计 V1.3。
