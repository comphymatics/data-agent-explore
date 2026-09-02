# 给真实数据环境 Code Agent 的任务书

你需要在当前受控环境中构建企业数据上下文评测集。开始前完整阅读同目录 `README.md`、`AUTO_CASE_CONSTRUCTION.md` 和 `contracts/*.schema.json`。

## 目标

基于真实的数据字典、应用场景、指标文档、模型映射、当前环境资产和已评审模型设计，生成：

```text
<output-dir>/
├── dataset-manifest.json
├── evidence.jsonl
├── cases.jsonl
└── design-oracles.jsonl
```

第一轮只构建 60 个 Pilot 案例，不要直接扩展到正式 200 题。

## 必须遵守

1. 原始资料只读，不修改、不移动、不上传。
2. Word/Excel 的表格、合并单元格、行列位置必须确定性解析。
3. 不把 Markdown 说明自动当作事实源；来源是否权威由 manifest 明确声明。
4. 不依据常识或模型推测补充资料中不存在的关系。
5. LLM 产生的内容一律先标记 `CANDIDATE`，人工批准前不得进入 Gold。
6. `required_evidence` 只能引用 `EXPLICIT/DERIVED` 且 `APPROVED` 的 Evidence。
7. 模型设计 Oracle 与评测查询输入物理隔离，防止 Gold 泄漏。
8. 输出中使用脱敏 source ID 和逻辑 URI；不得出现客户姓名、账号、密钥或不必要的业务原文。
9. 不修改 Enterprise Data Context、Explore Agent 或现有契约；发现契约不满足时输出问题报告，不自行重构。
10. 所有失败都保留明确错误，不能静默跳过文档、Sheet、表格或案例。

## 执行顺序

1. 清点资料，生成来源清单、版本、哈希和权威级别。
2. 运行 `generate_evidence_candidates.py`，从完整 Template JSON 生成 DRAFT 原子 Evidence。
3. 由业务专家复核 Evidence、完成实体归一，并填写 reviewer 和 review_status。
4. 运行 `generate_case_candidates.py`，按配额生成 Case 和 proposed Gold 审查队列。
5. 改写真实业务查询，由两名评审者确认 Required/Allowed/Forbidden。
6. 为每个模型设计案例建立一个独立 Oracle。
7. 运行校验器并修复全部错误。
8. 输出数据集统计、配额缺口、未解析资料、冲突、待评审候选和已知覆盖缺口。

## Pilot 分布

```text
requirement_research: 36
  single_layer: 12
  adjacent_mapping: 8
  multi_layer: 10
  environment_gap_conflict: 6

model_design_preparation: 24
  schema_context: 6
  processing_context: 6
  full_design_context: 6
  reuse_and_change: 3
  insufficient_context: 3
```

## 完成命令

```bash
uv run --isolated --extra dev python evaluation/scripts/validate_dataset.py \
  --dataset-dir <output-dir>
```

最终报告必须包含：

- 数据集版本和来源快照；
- 资料文件数、Evidence 数、案例数、Oracle 数；
- 按场景、子类、难度和层级的分布；
- 未处理资料和处理失败；
- Candidate、Conflict、Missing Context 数量；
- 校验命令及完整结果；
- 仍需业务专家裁决的问题。

## 数据集通过后：执行 OpenCode Explore / OpenViking 对比

数据集构建和人工审批完成后，再完整阅读 `COMPARISON.md`，按其中步骤：

1. 物化不含 Gold 的 `evidence-pages/`；
2. 使用版本化 URI 导入 OpenViking；
3. 固定 OpenCode、模型、OpenViking commit 和检索配置；
4. 先做双系统 preflight 和 Pilot；
5. 正式运行基础查询及改写，各重复 3 次；
6. 交付逐题脱敏结果、Recall、Precision、Query Tokens 和 token 完整性。

不得让任一被测系统读取 `cases.jsonl`、`design-oracles.jsonl` 或 `corpus-manifest.json`。OpenViking 未启动、Explore 子会话未被追踪、查询超时、token 不完整等情况必须原样报告，不得补造结果。
