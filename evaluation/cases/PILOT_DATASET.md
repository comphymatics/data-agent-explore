# Pilot Dataset Contract

真实 Case 在独立 scorer 目录维护，不硬编码进 Runner。`cases.yaml` 顶层为 `cases` 数组；
`aliases.yaml` 为 scorer-only `entities` 数组。仓库中的同名文件是合成 FIXTURE，不能直接
作为正式 Pilot Gold。审核以本轮 frozen 原始材料为依据，不从被测系统输出反推 Gold。

```yaml
cases:
  - case_id: pilot-001
    category: metric_to_model
    source_span: cross_document
    query: "由审核人员填写真实问题"
    gold:
      metrics: ["metric:reviewed-id"]
      physical_models: ["physical-model:reviewed-id"]
    optional: []
    forbidden: []
    relations:
      - source: metric:reviewed-id
        relation: supported_by
        target: physical-model:reviewed-id
    expected_empty: false
    difficulty: medium
    tags: [pilot]
    review_status: DRAFT
    source_documents: ["指标说明.docx", "数据字典.xlsx"]
    cross_document_rationale: "说明每份文件提供的必要信息，以及为何单篇不能确定答案"
```

模板中的 ID 是占位符，必须由审核人员在 Alias Registry 中定义后再使用。正式运行
要求 `APPROVED`；不能自动审批。八类实体键与公共输出协议一致。Alias 碰撞保留为歧义。

| Category | 推荐 Case 数 |
|---|---:|
| metric_to_model | 10 |
| purpose_to_data | 12 |
| model_to_analysis | 8 |
| model_to_business | 8 |
| field_discovery | 10 |
| lineage_impact | 8 |
| negative | 4 |

合计 60；cross_document 推荐至少 60%。30–60 Case 都可运行，不足配额仅产生
validation warning；manifest 保存实际 category/source_span/difficulty 分布。
`difficulty` 取 easy/medium/hard；single_document 必须恰好一个 source document，
cross_document 至少两个并有必要性说明。

负例设置 `expected_empty: true`、`gold: {}`、`optional: []`、`relations: []`，并提供
`empty_rationale`，说明审核过的材料为什么不能确定答案。其含义限于当前材料，
不能将未找到推断为真实环境不存在。非空 Gold 与 expected_empty 不能同时成立。

关系类型固定为 supported_by、requires_metric、requires_dimension、belongs_to_object、
implemented_by、upstream、downstream。`source/target` 必须属于本题 required 或 optional
实体集合。方向严格比较；不自动推断逆关系或传递关系。`relations: null` 表示未标注，
不参与关系评分；`relations: []` 表示已审核且没有应返回的关系，返回关系会计入关系 FP。
