"""Generate the code-grounded V1.1 architecture atlas (offline HTML + SVG).

The diagrams are explanatory artifacts, not production configuration.
Run from any directory: python scripts/render_current_architecture.py
"""
from pathlib import Path
from html import escape
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/architecture"
PREFIX = "data-explore-v1.1"
COLORS = {"blue": ("#2563eb", "#eff6ff"), "green": ("#15803d", "#f0fdf4"),
          "purple": ("#9333ea", "#faf5ff"), "orange": ("#c2410c", "#fff7ed"),
          "gray": ("#475569", "#f8fafc")}
DETAILS = {}


def node(key, x, y, w, h, title, lines, color="blue", detail="", sources=(), status="已实现", badge=""):
    DETAILS[key] = {"title": title, "body": detail or "；".join(lines), "sources": list(sources), "status": status}
    return dict(id=key, x=x, y=y, w=w, h=h, title=title, lines=lines, color=color, badge=badge)


def edge(source, target, points, color="blue", label=None, dashed=False):
    return dict(source=source, target=target, points=points, color=color, label=label, dashed=dashed)


def txt(lines, x, y, content, size=20, color="#111827", weight=400, anchor="start"):
    lines.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(content)}</text>')


def render(key, title, subtitle, height, nodes, edges, regions=(), notes=()):
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1680 {height}" width="1680" height="{height}" role="img" aria-labelledby="{key}-title {key}-desc" data-quality-profile="standard">']
    lines += [f'<title id="{key}-title">{escape(title)}</title>', f'<desc id="{key}-desc">{escape(subtitle)}</desc>',
              '<style>text{font-family:"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif}.node{cursor:pointer}.node:focus{outline:none}.node:focus .card,.node.selected .card{stroke:#111827;stroke-width:3}.node:hover .card{stroke-width:3}</style>', '<defs>']
    for name, (stroke, _) in COLORS.items():
        lines.append(f'<marker id="{key}-arrow-{name}" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L10 3.5 L0 7 Z" fill="{stroke}"/></marker>')
    lines += ['</defs>', f'<rect width="1680" height="{height}" fill="#ffffff" data-graph-role="background"/>']
    txt(lines, 40, 60, title, 34, weight=600)
    txt(lines, 40, 98, subtitle, 19, "#64748b")
    for x, y, w, h, name, sub, color in regions:
        stroke, tint = COLORS[color]
        lines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{tint}" fill-opacity="0.45" stroke="{stroke}" stroke-opacity="0.3" stroke-dasharray="8 6" data-graph-role="container"/>')
        txt(lines, x+24, y+36, name, 23, stroke, 600)
        txt(lines, x+24, y+65, sub, 17, "#64748b")
    for i, e in enumerate(edges):
        stroke = COLORS[e["color"]][0]
        d = "M " + " L ".join(f"{x} {y}" for x, y in e["points"])
        dash = ' stroke-dasharray="7 5"' if e["dashed"] else ""
        lines.append(f'<path id="{key}-edge-{i}" d="{d}" fill="none" stroke="{stroke}" stroke-width="2"{dash} marker-end="url(#{key}-arrow-{e["color"]})" data-graph-role="edge" data-source="{e["source"]}" data-target="{e["target"]}"/>')
        if e["label"]:
            x, y, label = e["label"]
            txt(lines, x, y, label, 16, stroke)
    for n in nodes:
        x, y, w, h = (n[k] for k in ("x", "y", "w", "h"))
        stroke, tint = COLORS[n["color"]]
        lines.append(f'<g class="node" data-detail="{n["id"]}" id="{n["id"]}" role="button" aria-label="{escape(n["title"])}" tabindex="0">')
        lines.append(f'<rect class="card" x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="{stroke}" stroke-opacity="0.55" stroke-width="1.5" data-graph-role="node" data-node-id="{n["id"]}"/>')
        lines.append(f'<rect x="{x+1}" y="{y+1}" width="6" height="{h-2}" rx="3" fill="{stroke}" data-graph-role="decoration"/>')
        txt(lines, x+24, y+39, n["title"], 23, weight=600)
        for i, line in enumerate(n["lines"]):
            txt(lines, x+24, y+76+i*24, line, 19, "#475569")
        if n["badge"]:
            txt(lines, x+w-20, y+h-16, n["badge"], 15, stroke, 600, "end")
        lines.append('</g>')
    for x, y, content, color in notes:
        txt(lines, x, y, content, 18, COLORS[color][0])
    lines.append('<g data-graph-role="legend">')
    for i, (label, color, dashed) in enumerate((("参考知识写入 / 读取", "green", False), ("查询与上下文流", "blue", False), ("环境事实 / 外部边界", "orange", True), ("治理与可选候选控制", "purple", True))):
        x = 42+i*340
        lines.append(f'<path d="M{x} {height-40} L{x+42} {height-40}" stroke="{COLORS[color][0]}" stroke-width="2" fill="none"'+(' stroke-dasharray="7 5"' if dashed else '')+f' marker-end="url(#{key}-arrow-{color})"/>')
        txt(lines, x+55, height-34, label, 16, "#64748b")
    lines.append('</g>')
    txt(lines, 1640, height-34, "fd8538f · 2026-09-09", 16, "#64748b", anchor="end")
    lines.append('</svg>')
    svg = "\n".join(lines)
    (OUT / f"{PREFIX}-{key}.svg").write_text(svg, encoding="utf-8")
    return svg


def diagrams():
    overview = render("overview", "Data Explore｜当前整体技术方案", "离线构建参考语义，在线读取环境事实；Explore 编排检索，输出带证据的 Context Bundle。", 1340, [
        node("o-input",80,245,580,120,"01  外部材料与 Parser 交付",["Word / Excel / SID / 建模规范","约定 Template JSON → 校验 → ContextFragment"],"orange", "正式 Parser 由外部团队负责；仓库保留兼容解析入口。主交付入口 compile_template_inputs 校验五类 Template JSON，再转为内部 Fragment。SID 是语义参考，不是主层级。", ["enterprise_data_context/delivery.py","enterprise_data_context/compiler.py","specs/14-parser-handoff.md"],"交付消费已实现；真实 Parser 联调待验证"),
        node("o-compile",80,425,580,120,"02  Context Engine：语义编译",["Canonical Resolution → Section-level Fusion","业务映射 + Typed Reference Resolution"],"green", "先做实体身份归一，再按来源权威融合 sections。保留 Evidence、候选、冲突与 unresolved references；物理模型/字段到业务对象/属性的映射是一等能力。", ["enterprise_data_context/compiler.py","enterprise_data_context/fusion/merge.py","enterprise_data_context/mapping/business.py"]),
        node("o-represent",80,605,580,140,"03  同一实体，多种读取表示",["Rich Page + 多视图 Hierarchy / Aggregate Page","Page / Aggregate Hybrid Index + ElementIndex","Typed Graph / Backrefs 仅服务机器补全"],"green", "Canonical Entity 只有一份。Hierarchy 是组织边，不能转成业务事实。Analysis / Domain / Asset 各有独立 aggregate URI；LLM 读取 Rich Page 与 Bundle，Graph 仅供服务内部使用。", ["enterprise_data_context/indexes/hierarchy.py","enterprise_data_context/indexes/aggregate.py","enterprise_data_context/graph/backend.py"]),
        node("o-snapshot",80,805,580,125,"04  质量校验与不可变参考快照",["Evidence / URI / Taxonomy / Index 一致性 Gate","固定 IndexVersion；加载时重建索引与图"],"green", "保存 Canonical、Pages、组织贡献、aggregate、配置指纹与 manifest；原子更新 latest.json。Hierarchy 的增量失效覆盖变动实体、相关分支及祖先，不等于整个 Parser/Canonical 流水线都已增量化。", ["enterprise_data_context/persistence.py","enterprise_data_context/runtime.py"]),
        node("o-router",1000,245,420,120,"05  用户问题 → Explore Router",["Intent / Scope / Requirements","Direct · Hierarchical · Hybrid"],"blue", "集中策略依据意图、范围、真实精确锚点与请求方面选择模式。明确实体直接查；宽泛问题先找语义分支；锚点+扩展需求合并两条路径。最多两个视图。", ["explore_agent/router.py","enterprise_data_context/retrieval_strategy.py"]),
        node("o-search",820,440,350,175,"06  调用 Context Engine",["四个只读 Context Tools","Anchor / Aggregate Hybrid","L0 选分支 → L1 富读","机器端关系补全与预算"],"blue", "data_search 在一次服务操作内完成 branch recall、成员锚点发现、TypedReference/Backref 补全、排序与 hydration。data_read/data_expand/data_source 负责不同披露与来源访问，不增加逐节点图遍历工具。", ["enterprise_data_context/tools.py","enterprise_data_context/retrieval.py","enterprise_data_context/hierarchical_retrieval.py"]),
        node("o-env",1250,440,350,175,"按需：MetaOne 环境读取",["Adapter → MCP / Gateway","当前资产、字段、显式关系","保留能力 / 来源 / 快照","失败或截断 ≠ 不存在"],"orange", "需要环境事实时，Explore 先调用 EnvironmentBindingAdapter.resolve。MetaOneMcpAdapter 归一化 capability/search/read/expand；Gateway 接受规范化 envelope，真实原始 payload 映射尚待内部校准。默认 Null adapter 不声称已接入现网。", ["enterprise_data_context/environment.py","mcp/data-catalog/README.md"],"适配机制已实现；真实环境待联调"),
        node("o-assemble",820,710,780,150,"07  Coverage + Focused Expansion + Binding",["按 Entity × Aspect × Layer × Selector 检查需求","缺口触发有界 L2 扩展；严格身份绑定与语义映射分开","保留 UNKNOWN / PARTIAL、候选、冲突和两层 Evidence"],"blue", "先对已读证据做 requirement coverage，再批量 focused expand，重新评估。IdentityBinding 只接受同类型、当前环境/快照证据下的显式 crosswalk 或稳定强键；名称相似不是身份。Overlay 为 query-scoped，不回写全局参考库。", ["explore_agent/agent.py","explore_agent/coverage.py","explore_agent/binding.py"]),
        node("o-bundle",1020,920,380,90,"Context Bundle → 主 Agent",["参考语义 + 环境事实 + 缺口"],"purple", "Explore 不生成最终 SQL、分析结论或最终模型。它返回结构化 Context Bundle，由主 Agent/业务应用继续消费。Bundle 保留 coverage、Evidence、binding、版本、预算、stop_reason 和 retrieval trace。", ["enterprise_data_context/models.py","explore_agent/agent.py"]),
        node("o-eval",80,1155,455,105,"独立评测：消费运行结果",["正式 Benchmark + Hierarchy Ablation"],"gray", "Evaluation 是独立消费者，不能为了得分修改生产 Context。五组 hierarchy ablation 与正式四方案 Benchmark 分开；Gold/Alias/评分器不进入检索或组织配置。", ["evaluation/hierarchy/run.py","evaluation/EVALUATION_DESIGN.md"]),
        node("o-draft",610,1155,455,105,"Dataset Builder：仅 DRAFT",["Raw + Parser 候选 → 人工审核"],"gray", "Parser JSON 用于发现候选，不是 Oracle。Builder 只输出 DRAFT Case/Alias/Review Queue；人工核对原始材料后，scorer 侧独立冻结审核结果。", ["evaluation/dataset_builder/README.md","INTERNAL_ADAPTATION_GUIDE.md"]),
        node("o-evidence",1140,1155,460,105,"验证范围：代码与样例",["真实 embedding 已验；现网待验"],"gray", "227 项 Python 回归通过；本机真实多语言 MiniLM 的非词面样例召回验证通过。企业真实语料、MetaOne payload/认证/分页与大规模成本仍待验证。", ["SEMANTIC_HIERARCHY_V1_1_IMPLEMENTATION.md","evaluation/hierarchy/results/v1.1/trained-semantic-branches.json"],"已验证与待验证分开"),
    ], [
        edge("o-input","o-compile",[(370,365),(370,425)],"green",(394,401,"有来源的 Fragments")),
        edge("o-compile","o-represent",[(370,545),(370,605)],"green",(394,582,"Canonical Contexts")),
        edge("o-represent","o-snapshot",[(370,745),(370,805)],"green",(394,782,"版本化产物")),
        edge("o-snapshot","o-search",[(660,865),(740,865),(740,530),(820,530)],"green"),
        edge("o-router","o-search",[(1050,365),(1050,395),(995,395),(995,440)],label=(819,385,"Reference 检索")),
        edge("o-router","o-env",[(1370,365),(1370,395),(1425,395),(1425,440)],"orange",(1450,393,"需要时先读"),True),
        edge("o-search","o-assemble",[(995,615),(995,710)],label=(1015,666,"富语义上下文")),
        edge("o-env","o-assemble",[(1425,615),(1425,710)],"orange",(1443,666,"环境证据"),True),
        edge("o-assemble","o-bundle",[(1210,860),(1210,920)],label=(1230,894,"有界组装")),
    ], regions=[(40,150,660,890,"参考语义｜构建与发布","外部 Parser 交付 → Enterprise Data Context", "green"),(780,150,860,890,"Explore Agent｜查询期编排","参考知识与环境事实保留各自的权威和版本", "blue")], notes=[(80,994,"Context Engine 管上下文；不回答最终业务问题。","green"),(40,1100,"独立质量验证与评测：Gold / Alias / Scorer 不进入生产链路", "gray")])

    build = render("build", "参考语义如何构建与发布", "Canonical 实体唯一；事实图、组织视图、LLM 页面承担不同职责。", 1150, [
        node("b-input",80,190,350,160,"Parser 交付边界",["五类 Template JSON","Schema + 来源 / Shape 校验","转为内部 ContextFragment"],"orange",sources=["enterprise_data_context/delivery.py","contracts/template-input.schema.json"]),
        node("b-compiler",540,190,600,160,"ContextCompiler：确定性语义主链",["① Canonical Resolution  ② Section-level Fusion","③ 业务语义映射与分类规范化","④ Typed Reference Resolution：明确与未解引用"],"green",sources=["enterprise_data_context/compiler.py","enterprise_data_context/canonical/resolver.py","enterprise_data_context/fusion/authority.py"]),
        node("b-policy",1250,190,350,160,"独立治理配置",["来源权威 / 显式 Taxonomy","Applicable Views / Rules","候选推断有界、默认无 LLM"],"purple",sources=["enterprise_data_context/hierarchy_config.py","enterprise_data_context/hierarchy_inference.py","config/semantic-hierarchy.sample.json"]),
        node("b-pages",80,510,440,215,"Rich Context Page + PageIndex",["L0 摘要 / L1 富语义 / L2 细节","实体级 Exact + BM25 + Dense","Facet + RRF 融合","Canonical URI：data://metrics/…"],"green",sources=["enterprise_data_context/materialization/pages.py","enterprise_data_context/indexes/page.py","enterprise_data_context/indexes/hybrid.py"]),
        node("b-hierarchy",620,510,440,215,"Hierarchy + Aggregate Pages",["Analysis / Domain / Asset","CONFIRMED / DERIVED / CANDIDATE","独立 URI：data://views/…","AggregatePageIndex 复用 Hybrid"],"green", "Explicit Taxonomy > 同槽实例分类/规则；候选不参与强导航。实体只按 applicable views 计算分类状态。聚合页由有效成员确定性生成，L0/L1 索引不嵌入全量 L2。", ["enterprise_data_context/indexes/hierarchy.py","enterprise_data_context/indexes/aggregate.py","enterprise_data_context/materialization/aggregate_pages.py"]),
        node("b-machine",1160,510,440,215,"机器端关系与局部元素",["Typed Graph：血缘 / 关系补全","Backrefs：从前向引用派生","ElementIndex：字段 / Counter 等","不暴露逐节点 LLM traversal"],"green",sources=["enterprise_data_context/graph/backend.py","enterprise_data_context/references/resolver.py","enterprise_data_context/indexes/element.py"]),
        node("b-publish",580,900,520,150,"Quality Gate → Immutable Snapshot",["Evidence / Path / Cycle / Index 一致性","保存配置、贡献、Aggregate 与指纹","固定版本加载；重建可丢弃索引与图"],"green",sources=["enterprise_data_context/persistence.py","contracts/semantic-organization.schema.json"]),
    ],[
        edge("b-input","b-compiler",[(430,270),(540,270)],"green"),
        edge("b-policy","b-compiler",[(1250,270),(1140,270)],"purple",dashed=True),
        edge("b-compiler","b-pages",[(620,350),(620,420),(300,420),(300,510)],"green"),
        edge("b-compiler","b-hierarchy",[(840,350),(840,510)],"green",(860,463,"组织投影")),
        edge("b-compiler","b-machine",[(1060,350),(1060,420),(1380,420),(1380,510)],"green"),
        edge("b-pages","b-publish",[(300,725),(300,820),(680,820),(680,900)],"green"),
        edge("b-hierarchy","b-publish",[(840,725),(840,900)],"green"),
        edge("b-machine","b-publish",[(1380,725),(1380,820),(1000,820),(1000,900)],"green"),
    ],notes=[(40,130,"输入材料默认 PARTIAL；缺失来源不代表企业知识不存在。","gray"),(80,1080,"增量：变动实体 / Taxonomy → 受影响分支与旧新祖先；路由变化不重跑分类。","gray")])

    runtime = render("runtime", "一次 Explore 查询如何运行", "需要环境事实时先完成 Adapter 读取；这里展开 Reference 检索、Coverage 与最终绑定。", 1370,[
        node("r-router",620,180,440,120,"Intent / Scope → Retrieval Strategy",["真实 Exact Anchor 校准模式","View 来自 intent / scope / aspects"],"blue",sources=["explore_agent/router.py","enterprise_data_context/retrieval_strategy.py"]),
        node("r-direct",80,410,440,155,"Direct：明确实体",["RSRP 有哪些模型？","Exact / Element Anchor","复用 Entity Hybrid Search"],"blue",sources=["enterprise_data_context/hierarchical_retrieval.py"]),
        node("r-hybrid",620,410,440,155,"Hybrid：实体 + 扩展需求",["RSRP 用于弱覆盖还需哪些数据？","Direct Anchor + Relevant Branch","合并两路上下文锚点"],"blue",sources=["enterprise_data_context/retrieval_strategy.py","enterprise_data_context/hierarchical_retrieval.py"]),
        node("r-hier",1160,410,440,155,"Hierarchical：宽泛语义",["地铁弱覆盖需要哪些数据？","View Filter → Aggregate Hybrid","L0 选分支 → L1 读概要 → 成员"],"blue",sources=["enterprise_data_context/indexes/aggregate.py"]),
        node("r-complete",620,700,440,120,"机器端上下文补全与组装",["Typed References + Backrefs","相关性 / 多样性 / Token Budget"],"blue",sources=["enterprise_data_context/serving.py","enterprise_data_context/retrieval.py"]),
        node("r-env",1160,700,440,120,"已按需读取的环境事实",["MetaOne Adapter：来源与快照","状态完整性 / 能力 / 实际关系"],"orange",sources=["enterprise_data_context/environment.py","mcp/data-catalog/README.md"],status="机制已实现；现网 payload 待验证"),
        node("r-coverage",80,940,440,155,"Requirement Coverage",["Entity × Aspect × Layer × Selector","SATISFIED / PARTIAL / UNKNOWN","MISSING 必须有完整缺失证据"],"blue",sources=["explore_agent/coverage.py","specs/10-explore-agent.md"]),
        node("r-focused",620,940,440,155,"Focused L2 → 再评估",["针对缺口批量展开，最多一次","字段 / 粒度 / Join / 业务映射","不够就保留缺口与 stop_reason"],"blue",sources=["explore_agent/agent.py","enterprise_data_context/retrieval.py"]),
        node("r-bind",1160,940,440,155,"Binding Overlay",["Identity / Semantic / Structural 分离","同类型 + 稳定键 / 显式 Crosswalk","不回写 Reference；保留冲突"],"purple",sources=["explore_agent/binding.py","contracts/binding-overlay.schema.json"]),
        node("r-output",620,1200,440,95,"Context Bundle",["Evidence / Coverage / Versions / Trace"],"purple", "可选 JointReasoner 从可见证据选择可核对原文片段，不能改 Coverage 或提升候选。通常一次 data_search 加至多一次 data_expand；环境和可选语义模型调用单独计量。", ["explore_agent/reasoner.py","explore_agent/agent.py"]),
    ],[
        edge("r-router","r-direct",[(700,300),(700,350),(300,350),(300,410)]),
        edge("r-router","r-hybrid",[(840,300),(840,410)]),
        edge("r-router","r-hier",[(980,300),(980,350),(1380,350),(1380,410)]),
        edge("r-direct","r-complete",[(300,565),(300,640),(680,640),(680,700)]),
        edge("r-hybrid","r-complete",[(840,565),(840,700)],label=(860,610,"同一次 data_search")),
        edge("r-hier","r-complete",[(1380,565),(1380,640),(1000,640),(1000,700)]),
        edge("r-complete","r-coverage",[(840,820),(840,880),(300,880),(300,940)]),
        edge("r-coverage","r-focused",[(520,1018),(620,1018)]),
        edge("r-focused","r-bind",[(1060,1018),(1160,1018)]),
        edge("r-env","r-bind",[(1380,820),(1380,940)],"orange",(1400,880,"环境证据"),True),
        edge("r-bind","r-output",[(1380,1095),(1380,1145),(840,1145),(840,1200)]),
    ],notes=[(80,180,"四个 Context Tools 保持不变", "gray"),(80,213,"data_search · data_read", "gray"),(80,246,"data_expand · data_source", "gray"),(1160,210,"分支默认最多 3 个 / 同时最多 2 个 View", "gray"),(1160,245,"Dense 用于召回；不做逐实体 Dense 分类", "gray")])
    return {"overview":overview,"build":build,"runtime":runtime}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    svgs = diagrams()
    template = Path(__file__).with_name("current_architecture_template.html").read_text(encoding="utf-8")
    sections = "\n".join(f'<section id="view-{key}" class="diagram-view" {"" if key == "overview" else "hidden"}>{svg}</section>' for key, svg in svgs.items())
    content = template.replace("__DIAGRAMS__", sections).replace("__DETAILS__", json.dumps(DETAILS, ensure_ascii=False).replace("<", "\\u003c"))
    (OUT / f"{PREFIX}-architecture.html").write_text(content, encoding="utf-8")
    print(f"Generated {len(svgs)} SVG diagrams and offline HTML in {OUT}")


if __name__ == "__main__":
    main()
