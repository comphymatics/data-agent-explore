# 接入验证记录

日期：2026-09-09。使用当前本机 checkout 与真实发布快照
`context-70d6ec1b561057b9`，未调用生成式 LLM。

| 验证层次 | Claude Code 2.1.172 | Codex CLI 0.153.0-alpha.5 | OpenCode 1.17.8 |
| --- | --- | --- | --- |
| 配置文件解析 | CLI 识别项目 `.mcp.json` | CLI 和 app-server `config/read` 识别 MCP | CLI 识别配置 |
| 默认探索角色 | 内置 Explore 的本机定义未排除 MCP；不加载 CLAUDE.md | 自定义 data-explore 的 TOML 必填字段校验通过；未实际委派 | `debug agent explore` 保持 native=true，四个 MCP 工具的最终权限均为 allow |
| 原生命令启动 MCP + 四工具调用 | 通过 | 通过 | 通过 |
| 客户端自己连接 | 项目授权待用户在 Claude Code 内完成 | `mcp get` 是配置识别，未当作连接证明 | `opencode mcp list` 返回 connected |
| 真实 LLM 委派与 handoff 质量 | 未验证 | 未验证 | 未验证 |

三个 MCP smoke 分别消费 `.mcp.json`、`.codex/config.toml` 和 `opencode.json` 的
实际 command/args/env，进行 initialize、initialized、tools/list 和四个 tools/call。
每次“高铁场景”搜索命中 3 个上下文，检索警告为空；Serving 标识包含真实本地
FastEmbed 0.8.0 / multilingual MiniLM。检索结果不是 live MetaOne 可用性证明。

完整报告：

- [Claude Code MCP](../../outputs/harness-integration/claude-code-mcp.json)
- [Codex MCP](../../outputs/harness-integration/codex-mcp.json)
- [OpenCode MCP](../../outputs/harness-integration/opencode-mcp.json)
- [OpenCode 内置 Explore 权限](../../outputs/harness-integration/opencode-builtin-explore.json)

内置角色复用检查：本机 Claude Code 2.1.172 内置 Explore 的 disallowedTools
解析为 Agent、ExitPlanMode、Edit、Write、NotebookEdit；未排除 MCP，omitClaudeMd=true。
其内置默认模型定义为 Haiku，不能套用之前自定义 data-explore 的模型继承说明。
此证据来自已安装客户端的内置定义，不代表已完成真实 LLM 工具调用。
OpenCode 原始 explore 配置使用默认 deny 且未放行 MCP；本次追加四个精确 allow，
保留其 native 标记、代码检索 prompt、既有模型配置和 Read/Edit 等权限。
原自定义 Claude Code/OpenCode 角色移到 examples/，仍可显式选择 custom 安装。

自动化验证：

```bash
uv run --isolated --extra dev pytest -q \
  tests/test_harness_integration.py tests/test_downstream_pipeline.py
# 22 passed

uv run scripts/configure_harness.py --client all --mode both --dry-run
# changed: []

git diff --check
# passed
```

测试覆盖配置保留与冲突前置检测、重复执行、带空格/引号/中文路径、直接模式不创建
子 Agent、原生格式与工具限制，以及已有 MCP/ContextBundle 下游回归。
未把客户端模型、账户认证、真实子 Agent 推理正确性或成本记为已通过。
