# Claude Code / Codex / OpenCode 接入

本目录提供同一检索服务的直接 MCP 和 Explore Subagent 接入。
当前项目已生成两种方式共存的配置；用户级模型、凭据和权限设置保持原样。
服务名统一为 `enterprise_data_context`。Claude Code 默认复用内置 `Explore`，
OpenCode 默认复用内置 `explore`，Codex 保留已配置的 `data-explore`。
自定义 Claude Code/OpenCode `data-explore` 定义移到 `examples/`，作为可选方案。

## 两种方式的边界

| 方式 | 调用链 | LLM 与输出 |
| --- | --- | --- |
| 直接 MCP | 主 Agent → 四个 Context Tools | 主 Agent 使用宿主模型组织答案 |
| 内置 Explore + MCP | 主 Agent → Claude Code Explore / OpenCode explore → 四个 Context Tools | 子 Agent 使用宿主的内置模型策略，返回带证据的上下文 handoff；主 Agent 完成最终任务 |
| 自定义子 Agent（可选） | 主 Agent → data-explore → 四个 Context Tools | 适合需要固定提示词、独立模型或更窄工具权限的场合 |
| 已有 Python API | 调用方 → `ExploreAgent(runtime.retrieval).explore(...)` | 默认无生成式 LLM；执行确定性 Coverage、Environment Gate、状态和正式 ContextBundle 组装 |

以上 Harness 配置不会自动调用 Python API，也没有新增第五个 MCP 工具。子 Agent 的
handoff 是模型组织的上下文，不冒充 `contracts/context-bundle.schema.json` 校验过的
Python ContextBundle，不伪造 Coverage 认证或恢复状态。如果应用需要正式合同，
直接使用既有 Python API；不要靠复制一份提示词替代代码约束。

四个 MCP 工具是 `data_search`、`data_read`、`data_expand`、`data_source`。
服务内部执行精确/BM25/向量/分类混合检索、聚合视图定位及有界关系补全。
Agent 读取 Rich Pages，Graph 只在服务内部使用。

## 当前项目直接使用

从服务项目目录启动客户端：

```bash
cd /Users/fengyajie/Projects/data-agent-explore
claude      # 或 codex / opencode，选择一个启动
```

| 客户端 | MCP 配置 | 子 Agent 配置 | 主 Agent 路由说明 |
| --- | --- | --- | --- |
| Claude Code | `.mcp.json` | 内置 `Explore`，不创建 Agent 文件 | `CLAUDE.md`，要求主 Agent 将检索约束写进委派消息 |
| Codex | `.codex/config.toml` | `.codex/agents/data-explore.toml` | `AGENTS.md` 中的托管区块 |
| OpenCode | `opencode.json` | 内置 `explore`，在 `agent.explore.permission` 放行四个 MCP 工具 | `AGENTS.md` 中的托管区块 |

Claude Code 首次加载项目 `.mcp.json` 时会显示项目 MCP 启用确认；在客户端中启用
`enterprise_data_context`，再用 `/mcp` 查看状态。这是 Claude Code 的项目配置授权，
生成器不代替用户写入授权决定。Codex 需信任项目配置；如果上层配置关闭了子 Agent，
需在宿主恢复该功能。新增配置后重启客户端会话。

检查客户端识别情况：

```bash
claude mcp get enterprise_data_context
codex mcp get enterprise_data_context
opencode mcp list
opencode debug agent explore
```

**直接调用示例：**

> 请直接调用 enterprise_data_context 的 data_search 查询“高铁场景”，mode=auto、
> top_k=3、bundle_k=3、token_budget=2000、read_content=auto。
> 根据结果列出相关专题、证据来源和缺失信息，本次不委派子 Agent。

**内置 Explore 示例（Claude Code）：**

> 请委派给内置 Explore 子 Agent，检索“高铁场景弱覆盖分析需要哪些指标、模型、
> 字段和粒度”。请在委派任务中明确：本任务只使用 enterprise_data_context 的四个
> MCP 工具，先 data_search，再按缺口 data_expand，不搜索项目文件或原始材料。
> 返回上下文与证据、候选、冲突、缺失项和 index_version，然后你根据结果回答。

Claude Code 内置 Explore 会省略 `CLAUDE.md`，因此不能只在该文件写规则就期待
子 Agent 自动继承。主 Agent 必须把工具选择、预算、Evidence 和输出要求随任务传入。
本机 Claude Code 2.1.172 的内置 Explore 定义只排除 Agent/ExitPlanMode/Edit/Write/
NotebookEdit，没有排除 MCP 工具；但项目 MCP 必须先获准连接。

**子 Agent 示例（OpenCode）：**

> @explore 使用 enterprise_data_context MCP 检索“高铁场景弱覆盖分析需要哪些指标、
> 模型、字段和粒度”。只使用四个 Context Tools，不搜索文件；返回上下文、来源、
> 候选、冲突、缺失项和版本。

OpenCode 1.17.8 内置 explore 原始权限有 `*: deny`，仅注册 MCP 并不自动放行。
生成器只在 `agent.explore.permission` 添加四个完整工具名的 allow，不替换内置
prompt/model，也不改变它正常代码探索时的 Read/Grep 等权限。数据探索任务通过
委派消息限定只读 Context Tools。Codex 的示例仍为“请委派给 data-explore”。

OpenCode 的 `mode: subagent` 通过 `@explore` 或主 Agent 的 Task 委派使用；
不要把它当作主 Agent 使用 `opencode run --agent explore`。
验证委派时应在任务记录中看到对应的 Explore/explore/data-explore，及其实际 MCP 调用；
仅出现同名文字或一个看似合理的答案，不证明发生了委派。

## 给其他项目生成配置

生成器通过 `uv` 使用 Python 3.11+，只依赖标准库。macOS 自带 Python 3.9 不适用。
服务 checkout 和 `generated/latest.json` 必须已存在；配置生成不会编译或修改知识快照。

```bash
# 当前项目全部客户端，两种方式共存（重复执行不重复添加）
uv run scripts/configure_harness.py --client all --mode both

# 只为某个业务项目接入 Claude Code 子 Agent，同时注册四工具 MCP
uv run scripts/configure_harness.py \
  --client claude-code --mode subagent --target /absolute/path/to/business-project

# 为另一个项目生成只含直接检索入口的 OpenCode 配置
uv run scripts/configure_harness.py \
  --client opencode --mode direct --target /absolute/path/to/another-project

# 可选：确需固定角色提示词和更窄权限时，安装自定义 data-explore
uv run scripts/configure_harness.py \
  --client claude-code --mode subagent --subagent-kind custom \
  --target /absolute/path/to/project

# 不写入，查看待修改的文件路径
uv run scripts/configure_harness.py --client codex --target /absolute/path/to/project --dry-run
```

`--client` 为 `claude-code / codex / opencode / all`。
`--mode direct` 不配置子 Agent；`subagent` 和 `both` 配置 MCP 与委派方式。
默认 `--subagent-kind auto` 为 Claude Code/OpenCode 复用内置 Explore，为 Codex
生成自定义 data-explore；`custom` 显式选择自定义角色；`builtin` 用于前两种客户端。
并给主 Agent 添加优先委派复杂检索任务的说明。后两者有意保留直接工具入口，
不声称主 Agent 与子 Agent 之间存在强制工具隔离。模式参数是添加配置的选择，
不是卸载命令；运行 direct/auto 不会删除已安装的可选自定义角色或已有权限配置。

服务位置可通过 `--repo`、`--snapshot`、`--uv` 指定。生成文件使用绝对路径，
因此客户端可以在业务项目启动，检索服务仍读取指定 checkout 和快照。
换机器后应在新目录重新生成；不要把本机绝对路径直接发给同事当通用配置。

生成器保留无关 JSON 设置、Codex TOML 原文及原有 AGENTS/CLAUDE 指令。
同名服务参数或同名子 Agent 有差异时，会在写入任何配置前报冲突；不自动覆盖。
遇到冲突或已有 `opencode.jsonc`，把配置生成到一个新的 staging 目录，审阅后合并。
`AGENTS.md` / `CLAUDE.md` 只更新带 `data-explore integration` 标记的区块。
不会更新用户级配置、模型凭据、宿主权限或环境变量全局值。

## 模型与权限

- Claude Code 内置 Explore：沿用宿主的内置策略。本机 2.1.172 定义为 Haiku，
  不应套用自定义角色的 `model: inherit` 结论。官方文档说明 2.1.198 起策略改变。
  可选自定义 data-explore 才是 `model: inherit` 和四工具 allowlist。
- Codex 子 Agent：不指定 model，继承宿主设置；read-only sandbox、禁用 Web Search，
  提示词只允许四个 Context Tools。Codex 仍可能继承其他工具，且父会话覆盖项可能
  改变 sandbox；这里不声称 TOML 建立了“只有四工具”的强制安全沙箱。
- OpenCode 内置 explore：不新增 model，精确追加四个 MCP 工具权限；保留内置能力。
  可选自定义 data-explore 才采用默认 deny、仅放行四工具的配置。
- 原生子 Agent 的轮次和返回文本由 Harness 管理；调用预算是提示词约束，不能
  替代 Python `ExploreAgent` 的确定性控制。可选自定义角色的 maxTurns/steps 为 8，
  内置 Explore 沿用客户端原有轮次策略。
- 本 MCP 不加载 `config/llm-inference.json`，也不需要 `SILICONFLOW_API_KEY` 等
  本仓库生成式 LLM 凭据。宿主的 LLM 登录/Provider 仍按客户端原配置。

Embedding 独立于生成式 LLM：默认 `--dense cached` 使用本机缓存的 FastEmbed 模型；
在新机器可以使用 `--dense download` 允许首次下载权重（页面编码在本地进行），
或 `--dense disabled` 只使用词法/精确/分类检索。缺依赖或权重时，服务明确告警并回退，
不能把回退称为向量检索成功。

当前配置接入 Reference Context，未注册 MetaOne Environment Binding。
现网存在性、部署状态和物理可用性应报告 UNKNOWN，不能从参考页面推断。
重建 `generated/latest.json` 后重启 MCP 进程加载新快照；每个运行中的进程保持其
已经加载的版本，不在一轮探索中混合新旧版本。

## 无 LLM 的服务验证

使用与客户端配置完全一致的 command/args/env 启动 MCP，完成协议握手、工具发现、
搜索，并针对真实命中的页面读取、展开和核查来源：

```bash
uv run scripts/check_harness_mcp.py --config .mcp.json
uv run scripts/check_harness_mcp.py --config .codex/config.toml
uv run scripts/check_harness_mcp.py --config opencode.json

uv run --isolated --extra dev pytest -q tests/test_harness_integration.py
```

`--query` 可以替换为当前语料中已知的对象；零命中时报告 `partial_no_hits`，
不会把没有执行的 read/expand/source 标为通过。`--output` 可保存报告。
此检查直接启动配置中的命令，不绕过也不替代 Harness 自己的项目授权。

当前[分层验证记录](VALIDATION.md)及实测报告见 `outputs/harness-integration/`。MCP 验证、客户端配置识别和真实 LLM
子 Agent 委派是三个独立层次。没有真实委派轨迹时，不宣称三客户端端到端验收完成。
这套接入不接触评测数据，也不改变生产语义、检索策略或 Benchmark。

## 配置格式来源

核对日期：2026-09-09。使用既有原生文件格式，不依赖插件安装。

- [Claude Code MCP](https://code.claude.com/docs/en/mcp)：项目 `.mcp.json` 和首次启用。
- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)：Markdown frontmatter、工具清单、model inheritance。
- [OpenAI 官方 Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)：项目 TOML 和 STDIO 命令。
- [OpenAI 官方 Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)：`.codex/agents/*.toml` 原生 Agent。
- [OpenCode MCP](https://opencode.ai/docs/mcp-servers/)：local command 数组与 environment。
- [OpenCode Agents](https://opencode.ai/docs/agents/)：Markdown 子 Agent、权限与模型继承。
