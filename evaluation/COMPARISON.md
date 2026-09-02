# OpenCode Explore 与 OpenViking 同步对比测评

本实现测的是企业数据上下文的“召回是否准确、成本是多少”，不是回答文案质量。两套系统接收同一份脱离 Gold 的 Evidence 语料、同一查询和同一 `context_token_budget`，输出统一为 Evidence ID 集合。

## 1. 为什么这样接入

OpenCode 的 Explore 是 `subagent`。官方 CLI 不允许把 subagent 直接作为 `opencode run --agent` 的主 Agent，因此适配器默认使用禁止 edit 的 Plan 作为 primary orchestrator，并要求它恰好调用一次内置 Explore。事件流中没有唯一 Explore 子会话时，该次运行无效，防止把主 Agent 自己的检索结果冒充 Explore。运行时使用中性语料的私有副本，并做前后哈希校验；任何改写都会使样本无效且触发副本重建。

OpenViking 使用官方 HTTP 接口：

- `POST /api/v1/resources/temp_upload` 上传版本化 ZIP；
- `POST /api/v1/resources` 导入固定 `viking://resources/...` URI；
- `POST /api/v1/search/search` 或 `find` 查询；
- `include_provenance=true`、`read_content=true`、`telemetry=true`。

选择 list 模式是因为它同时支持 `target_uri` 和 `read_content`，便于把检索严格限制在本次评测语料。返回内容随后按案例预算确定性截断。不要把同一 URI 原地覆盖为另一个数据集版本；每次冻结数据集使用新 URI。

相关官方依据：

- [OpenCode run CLI 源码](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/cli/cmd/run.ts)
- [OpenCode Agents 文档](https://opencode.ai/docs/agents/)
- [OpenViking retrieval API](https://docs.openviking.ai/en/api/06-retrieval)
- [OpenViking resources API](https://docs.openviking.ai/en/api/02-resources)
- [OpenViking operation telemetry](https://docs.openviking.ai/en/guides/07-operation-telemetry)
- [OpenViking resources router 源码](https://github.com/volcengine/OpenViking/blob/main/openviking/server/routers/resources.py)

## 2. 目录和数据隔离

```text
secure-eval-dataset/             # 仅评分器可读
├── dataset-manifest.json
├── evidence.jsonl
├── cases.jsonl                  # 含 Gold，绝不能进入检索目录
└── design-oracles.jsonl         # 隐藏 Oracle

neutral-corpus/                  # 两个被测系统都只读这一目录
├── corpus-manifest.json
├── README.txt
└── evidence-pages/<source>/<evidence-id>.md

comparison-output/               # 可断点续跑
├── run-manifest.json
├── results.jsonl
├── scores.jsonl
├── summary.json
└── summary.md
```

中性语料是评测专用的确定性 Evidence 序列化，不包含 required、allowed、forbidden、设计 Oracle 或评审说明。被测系统只读取或导入 `evidence-pages/`；`corpus-manifest.json` 仅供评分控制面校验，不进入检索。它隔离了解析质量，只测检索与 Explore 编排能力；原始 Word/Excel 到 Evidence 的抽取质量应作为独立上游门禁，不与本次排名混合。

## 3. 在真实业务环境运行

先校验真实评测集：

```bash
uv run --isolated --extra dev python evaluation/scripts/validate_dataset.py \
  --dataset-dir /secure/eval/telecom-context-v1
```

物化同一份中性检索语料。输出目录必须为空，脚本不会覆盖已有语料：

```bash
uv run --isolated --extra dev python evaluation/scripts/materialize_comparison_corpus.py \
  --dataset-dir /secure/eval/telecom-context-v1 \
  --output-dir /secure/eval/corpora/telecom-context-v1
```

复制并编辑配置。OpenViking `target_uri` 必须带数据集版本；凭据只通过环境变量传入：

```bash
cp evaluation/benchmark/config.example.json /secure/eval/config-v1.json
export OPENVIKING_API_KEY='...'
```

把完全相同的中性语料导入 OpenViking：

```bash
uv run --isolated --extra dev python evaluation/scripts/prepare_openviking_corpus.py \
  --corpus-dir /secure/eval/corpora/telecom-context-v1 \
  --config /secure/eval/config-v1.json
```

先做双系统预检。若只想查看缺失依赖，可加 `--skip-unavailable`；正式测评不得跳过不可用系统：

```bash
uv run --isolated --extra dev python evaluation/scripts/run_opencode_openviking_comparison.py \
  --dataset-dir /secure/eval/telecom-context-v1 \
  --corpus-dir /secure/eval/corpora/telecom-context-v1 \
  --config /secure/eval/config-v1.json \
  --output-dir /secure/eval/runs/preflight-v1 \
  --preflight-only
```

正式运行建议每个基础查询和改写各重复 3 次：

```bash
uv run --isolated --extra dev python evaluation/scripts/run_opencode_openviking_comparison.py \
  --dataset-dir /secure/eval/telecom-context-v1 \
  --corpus-dir /secure/eval/corpora/telecom-context-v1 \
  --config /secure/eval/config-v1.json \
  --output-dir /secure/eval/runs/open-explore-vs-viking-v1 \
  --repeats 3 \
  --include-variants
```

中断后使用完全相同的参数并追加 `--resume`。运行指纹覆盖数据集版本、语料 manifest、脱敏配置、案例选择、重复次数和改写开关；任一项变化都会拒绝错误续跑。

## 4. 指标口径

主指标只有：

```text
Evidence Recall@Budget
= 命中的 required Evidence / required Evidence 总数

Evidence Precision@Budget
= 命中的 required 或 allowed Evidence / 返回 Evidence 总数

Query Tokens
= 查询阶段 LLM input/output tokens + 最终交付上下文 tokens
```

实现细节：

- OpenCode：主会话事件流 token + 唯一 Explore 子会话 export token；缺任一子会话用量时标记不完整。
- OpenViking：operation telemetry 的 LLM token + 预算内返回上下文的确定性估算；无 telemetry 时仍记录上下文估算，但标记不完整。
- 无效正例：Recall 和 Precision 都记 0，不能通过运行失败逃避准确性惩罚。
- 负例：正确返回空集合时 Precision 为 1，不进入 Recall 平均。
- `summary.json` 同时给出总体、`requirement_research`、`model_design_preparation` 三组结果和 OpenCode 减 OpenViking 的差值。

Token 仅在两个系统的 `token_complete_runs == runs` 时进入正式成本比较。如果版本无法返回原生 token，应将成本结果标为探索性，不得进入最终排名。

## 5. 正式测评控制

- 固定 OpenCode 版本、模型、OpenViking commit/config、Embedding/LLM/Reranker 和硬件环境。
- 先用 Pilot 的 P95 时延确定查询超时；示例配置为 600 秒。超时样本保留部分事件和可取得的 token，但仍判为无效。
- 两边只允许访问中性语料目录，不得读取数据集目录。
- 先完成 Pilot，再冻结配置；不得看到测试集得分后修改 prompt、limit 或 URI 范围。
- 正式集至少覆盖两类场景并分层报告，不只看总体均值。
- 保留 `results.jsonl` 的逐题错误和无效原因；只有聚合报告可以离开受控环境。
- OpenViking 索引构建 token 单独留存，不计入 Query Tokens；这是离线建设成本，不是单次查询成本。

## 6. 当前环境验证边界

当前工作区可用 OpenCode，因此可做真实 Explore 子会话烟测。当前未安装或启动 OpenViking 服务，所以本仓库只能验证 HTTP 请求契约、响应解析、预算截断和评分逻辑；真实 OpenViking 数值必须在部署该服务并导入同一语料后生成。
