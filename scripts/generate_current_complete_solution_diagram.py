from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture"
SVG_PATH = OUT / "data-agent-explore-current-complete.svg"
HTML_PATH = OUT / "data-agent-explore-current-complete.html"

containers: list[str] = []
edges: list[str] = []
nodes: list[str] = []
labels: list[str] = []

STATUS_STYLE = {
    "已实现": ("#dcfce7", "#16a34a", "#166534"),
    "外部模块": ("#ffedd5", "#f97316", "#9a3412"),
    "MCP 样例": ("#fef3c7", "#f59e0b", "#92400e"),
    "待实现": ("#f3e8ff", "#a855f7", "#7e22ce"),
    "部分实现": ("#ede9fe", "#8b5cf6", "#6d28d9"),
}


def text(layer, x, y, value, css="body", anchor="start"):
    layer.append(
        f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def lane(y, height, number, title, subtitle, fill, stroke):
    containers.append(
        f'<g id="lane-{number}" data-graph-role="container">'
        f'<rect x="40" y="{y}" width="1720" height="{height}" rx="18" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.5" stroke-dasharray="7 5"/>'
        f'<text x="64" y="{y + 31}" class="lane-title">{number}  {escape(title)}</text>'
        f'<text x="64" y="{y + 54}" class="lane-sub">{escape(subtitle)}</text>'
        '</g>'
    )


def node(node_id, x, y, width, height, title, detail, fill, stroke, status=None, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    detail_value = "；".join(detail)
    nodes.append(
        f'<g id="{node_id}" class="node" data-graph-role="node" data-title="{escape(title)}" '
        f'data-detail="{escape(detail_value)}" data-status="{escape(status or "架构组件")}" tabindex="0">'
    )
    nodes.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.6"{dash}/>'
    )
    estimated_title_width = sum(14 if "\u3400" <= char <= "\u9fff" else 7 for char in title)
    if status:
        badge_width = max(68, len(status) * 13)
        if estimated_title_width + badge_width + 48 < width:
            badge_fill, badge_stroke, badge_text = STATUS_STYLE[status]
            nodes.append(
                f'<rect x="{x + width - badge_width - 10}" y="{y + 10}" width="{badge_width}" '
                f'height="22" rx="11" fill="{badge_fill}" stroke="{badge_stroke}"/>'
            )
            nodes.append(
                f'<text x="{x + width - badge_width / 2 - 10}" y="{y + 25}" class="status" '
                f'fill="{badge_text}" text-anchor="middle">{escape(status)}</text>'
            )
    text(nodes, x + 18, y + 32, title, "node-title")
    for index, line in enumerate(detail):
        text(nodes, x + 18, y + 59 + index * 20, line, "node-sub")
    nodes.append('</g>')


def edge(edge_id, source, target, path, label, color, marker, label_x=None, label_y=None, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    edges.append(
        f'<g id="{edge_id}" data-graph-role="edge" data-source="{source}" data-target="{target}">'
        f'<path d="{path}" class="edge" stroke="{color}" stroke-width="2.35" '
        f'marker-end="url(#{marker})"{dash}/></g>'
    )
    if label and label_x is not None and label_y is not None:
        text(labels, label_x, label_y, label, "edge-label", "middle")


lane(
    105, 250, "01", "外部解析与 Template JSON 交付",
    "真实 Word / Excel 只在 Parser 侧打开；五类 Template JSON 目录是唯一跨团队交付边界",
    "#fff7ed", "#fdba74",
)
lane(
    385, 290, "02", "参考基础知识库构建",
    "Template Adapter → 内部 ContextFragment IR → Canonical / Fusion → Rich Page / Index → 不可变版本",
    "#eff6ff", "#93c5fd",
)
lane(
    705, 255, "03", "双读取服务：Reference Runtime + MetaOne Environment",
    "参考库提供可复现语义基线；MetaOne 提供当前租户 / 环境真实资产，两者保持独立版本轴",
    "#f9fafb", "#cbd5e1",
)
lane(
    990, 355, "04", "Environment-first Explore 与语义绑定",
    "现网资产优先；参考语义补全；只有 NOT_FOUND_CONFIRMED 才允许 Reference-only 候选",
    "#faf5ff", "#c4b5fd",
)
lane(
    1375, 205, "05", "Context Bundle、下游消费与治理",
    "输出环境事实、参考语义、Binding、Evidence、候选、冲突、缺失和多版本信息",
    "#f0fdf4", "#86efac",
)

# Lane 01: external parser flow.
edge("e-source-parser", "source-materials", "parser", "M 300 250 L 365 250", "raw files", "#ea580c", "arrow-orange", 332, 232)
edge("e-parser-template", "parser", "template-delivery", "M 645 250 L 720 250", "JSON batch", "#ea580c", "arrow-orange", 682, 232)
edge("e-template-gate", "template-delivery", "contract-gate", "M 1000 250 L 1070 250", "schema", "#16a34a", "arrow-green", 1035, 232)
edge("e-gate-entry", "contract-gate", "consumer-entry", "M 1310 250 L 1400 250", "validated", "#2563eb", "arrow-blue", 1355, 232)

# Lane 01 -> lane 02, then right-to-left reference build.
edge("e-entry-adapter", "consumer-entry", "template-adapter", "M 1550 310 L 1550 450", "consumer-side normalize", "#2563eb", "arrow-blue", 1630, 380)
edge("e-adapter-canonical", "template-adapter", "canonical-fusion", "M 1400 510 L 1330 510", "internal IR", "#2563eb", "arrow-blue", 1365, 492)
edge("e-canonical-mapping", "canonical-fusion", "mapping-pages", "M 1050 510 L 980 510", "governed sections", "#2563eb", "arrow-blue", 1015, 492)
edge("e-mapping-index", "mapping-pages", "page-index", "M 700 510 L 630 510", "Rich Context", "#2563eb", "arrow-blue", 665, 492)
edge("e-index-snapshot", "page-index", "reference-snapshot", "M 350 510 L 280 510", "publish", "#16a34a", "arrow-green", 315, 492)

# Lane 02 -> lane 03 reference service.
edge("e-snapshot-runtime", "reference-snapshot", "reference-runtime", "M 180 570 L 180 790", "load_runtime(version)", "#16a34a", "arrow-green", 248, 680)
edge("e-runtime-tools", "reference-runtime", "data-context-tools", "M 350 850 L 420 850", "Rich Page", "#16a34a", "arrow-green", 385, 832)

# Lane 03 environment service.
edge("e-metaone-adapter", "metaone-mcp", "capability-adapter", "M 920 850 L 990 850", "MCP tools", "#ea580c", "arrow-orange", 955, 832)
edge("e-adapter-environment", "capability-adapter", "environment-view", "M 1270 850 L 1340 850", "normalized", "#ea580c", "arrow-orange", 1305, 832)

# Lane 04 primary query flow.
edge("e-query-explore", "business-query", "explore", "M 280 1115 L 340 1115", "question", "#9333ea", "arrow-purple", 310, 1097)
edge("e-explore-planner", "explore", "env-planner", "M 610 1115 L 670 1115", "intent + coverage", "#9333ea", "arrow-purple", 640, 1097)
edge("e-planner-gate", "env-planner", "availability-gate", "M 930 1115 L 990 1115", "facts + state", "#ea580c", "arrow-orange", 960, 1097)
edge("e-gate-overlay", "availability-gate", "binding-overlay", "M 1270 1095 L 1420 1095", "FOUND / PARTIAL", "#16a34a", "arrow-green", 1345, 1078)

# Independent environment and reference read corridors.
edge("e-env-view-planner", "environment-view", "env-planner", "M 1500 910 L 1500 975 L 800 975 L 800 1050", "environment facts", "#ea580c", "arrow-orange", 1150, 963)
edge("e-tools-enrichment", "data-context-tools", "reference-enrichment", "M 560 910 L 560 970 L 640 970 L 640 1280 L 730 1280", "reference semantic read", "#2563eb", "arrow-blue", 622, 1215)

# Gate branches and overlay completion.
edge("e-gate-fallback", "availability-gate", "fallback-state", "M 1130 1180 L 1130 1230", "confirmed missing / unknown", "#6b7280", "arrow-gray", 1230, 1212, True)
edge("e-enrich-overlay", "reference-enrichment", "binding-overlay", "M 990 1280 L 1020 1280 L 1020 1215 L 1380 1215 L 1380 1150 L 1420 1150", "semantic enrichment", "#2563eb", "arrow-blue", 1195, 1202)
edge("e-fallback-overlay", "fallback-state", "binding-overlay", "M 1320 1280 L 1360 1280 L 1360 1185 L 1420 1185", "REFERENCE_ONLY / missing", "#9333ea", "arrow-purple", 1390, 1262, True)

# Lane 04 -> lane 05 and consumers.
edge("e-overlay-bundle", "binding-overlay", "context-bundle", "M 1700 1210 L 1700 1360 L 400 1360 L 400 1440", "Binding Overlay", "#16a34a", "arrow-green", 1050, 1347)
edge("e-bundle-consumer", "context-bundle", "consumers", "M 620 1500 L 720 1500", "read-only bundle", "#16a34a", "arrow-green", 670, 1482)
edge("e-bundle-governance", "context-bundle", "governance", "M 400 1550 L 400 1565 L 1370 1565 L 1370 1540", "review / Golden", "#9333ea", "arrow-purple", 885, 1557, True)

# Nodes: lane 01.
node("source-materials", 80, 195, 220, 110, "企业原始材料", ["Word / Excel / 受控来源", "Parser 团队可访问真实数据"], "#ffffff", "#fb923c", "外部模块", True)
node("parser", 365, 185, 280, 130, "Parser + Extraction", ["确定性结构解析 → Document IR", "规则优先；可选 LLM 辅助", "保留来源与不确定性"], "#fff7ed", "#f97316", "外部模块", True)
node("template-delivery", 720, 185, 280, 130, "五类 Template JSON", ["APP / KPI-KQI / Tables", "Modeling / SID", "批次目录是唯一交付件"], "#f0fdfa", "#14b8a6", "外部模块")
node("contract-gate", 1070, 195, 240, 110, "Template Contract Gate", ["Union Schema 逐文件校验", "Schema 文档不进入事实库"], "#eff6ff", "#3b82f6", "已实现")
node("consumer-entry", 1400, 185, 300, 125, "Consumer Entry", ["compile_template_inputs(path)", "不重开原始 Word / Excel", "ContextFragment 仅内部 IR"], "#eff6ff", "#3b82f6", "已实现")

# Nodes: lane 02, right-to-left.
node("template-adapter", 1400, 450, 300, 120, "Template Adapter + Internal IR", ["Shape Adapter + JSON Pointer", "Evidence-bearing ContextFragment"], "#eff6ff", "#3b82f6", "已实现")
node("canonical-fusion", 1050, 445, 280, 130, "Canonical + Fusion", ["Canonical Resolution 先于 Fusion", "section authority / conflicts", "候选不进入正式 sections"], "#ffffff", "#60a5fa", "已实现")
node("mapping-pages", 700, 445, 280, 130, "Mapping + References", ["业务映射 / Typed Reference", "Backrefs 派生", "Rich Context Page L0/L1/L2"], "#ffffff", "#60a5fa", "已实现")
node("page-index", 350, 445, 280, 130, "Index + Machine Graph", ["Page / Element Index", "Graph 仅面向机器", "Quality + Golden Gate"], "#f0fdf4", "#22c55e", "已实现")
node("reference-snapshot", 80, 450, 200, 120, "Reference Snapshot", ["Immutable IndexVersion", "场景 / 需求 / 业务对象", "SID / 分层分域"], "#dcfce7", "#16a34a", "已实现")

# Nodes: lane 03.
node("reference-runtime", 80, 790, 270, 120, "Reference Runtime", ["固定 referenceIndexVersion", "Rich Pages / Index / Graph"], "#f0fdf4", "#22c55e", "已实现")
node("data-context-tools", 420, 790, 280, 120, "Data Context Tools", ["data_search / data_read", "data_expand / data_source", "平台中立、只读"], "#eff6ff", "#3b82f6", "已实现")
node("metaone-mcp", 720, 790, 200, 120, "MetaOne MCP", ["当前环境真实元数据", "接口未来允许增删改"], "#fff7ed", "#f97316", "MCP 样例", True)
node("capability-adapter", 990, 780, 280, 140, "Capability Adapter", ["tools/list + 能力协商", "工具名 / 参数 / 类型映射", "Fixture 已验证；待真实联调"], "#faf5ff", "#a855f7", "部分实现", True)
node("environment-view", 1340, 790, 320, 120, "Environment Metadata View", ["Search / Read / Expand 归一化", "维度 / 指标 / 模型 / 字段", "环境 Evidence + snapshot"], "#ffedd5", "#ea580c", "部分实现", True)

# Nodes: lane 04.
node("business-query", 80, 1065, 200, 100, "需求调研 / 模型设计", ["业务问题、范围与约束"], "#ffffff", "#a78bfa", "Query")
node("explore", 340, 1045, 270, 140, "Explore Agent", ["Intent / Scope Router", "Coverage Planner", "Focused Expansion", "不设计最终模型 / 不生成 SQL"], "#faf5ff", "#8b5cf6", "部分实现")
node("env-planner", 670, 1050, 260, 130, "Environment-first Planner", ["意图驱动先查 MetaOne", "read / expand 待接入主循环", "预算、租户、环境范围"], "#fff7ed", "#f97316", "部分实现", True)
node("availability-gate", 990, 1040, 280, 140, "Availability + Coverage Gate", ["FOUND / PARTIAL", "NOT_FOUND_CONFIRMED", "UNSUPPORTED / UNAVAILABLE", "TRUNCATED ≠ 不存在"], "#ffffff", "#7c3aed", "已实现")
node("binding-overlay", 1420, 1050, 300, 160, "Query-scoped Binding Overlay", ["环境事实 + 参考语义", "exact derived / candidate 隔离", "字段级 authority / 冲突待补", "不回写两层知识库"], "#f0fdf4", "#22c55e", "部分实现")
node("reference-enrichment", 730, 1230, 260, 100, "Reference Semantic Enrichment", ["场景 / 需求 / 业务对象", "SID / 规则推导待深化"], "#eff6ff", "#3b82f6", "部分实现")
node("fallback-state", 1050, 1230, 270, 100, "Fallback + Missing State", ["确认不存在 → REFERENCE_ONLY", "超时 / 无权限 / 不支持 → Unknown"], "#f9fafb", "#94a3b8", "已实现", True)

# Nodes: lane 05.
node("context-bundle", 180, 1440, 440, 110, "Dual-layer Context Bundle", ["environment facts / reference semantics", "Evidence / candidates / conflicts / missing", "reference + environment + policy versions"], "#f0fdf4", "#16a34a", "部分实现")
node("consumers", 720, 1440, 300, 110, "下游消费者", ["Main Agent / 建模 Agent", "SQL Agent / 人工评审"], "#ffffff", "#22c55e", "已实现")
node("governance", 1160, 1440, 420, 100, "Review + Golden Governance", ["候选映射人工确认", "MCP 兼容 fixtures / coverage cases", "候选禁止自动升级为事实"], "#faf5ff", "#a855f7", "部分实现")

# Footer: status and flow legend.
labels.append('<rect x="40" y="1605" width="1720" height="64" rx="14" fill="#f9fafb" stroke="#e5e7eb"/>')
text(labels, 64, 1632, "状态", "note-title")
for x, label, fill, stroke in (
    (118, "已实现", "#dcfce7", "#16a34a"),
    (240, "外部模块", "#ffedd5", "#f97316"),
    (382, "MCP 样例", "#fef3c7", "#f59e0b"),
    (520, "部分实现", "#ede9fe", "#8b5cf6"),
    (662, "待实现", "#f3e8ff", "#a855f7"),
):
    labels.append(f'<rect x="{x}" y="1615" width="104" height="26" rx="13" fill="{fill}" stroke="{stroke}"/>')
    text(labels, x + 52, 1633, label, "legend", "middle")
text(labels, 820, 1632, "事实边界", "note-title")
text(labels, 888, 1632, "MetaOne 决定现网有什么；Reference 解释意味着什么；失败 / 截断不能当作不存在。", "note")
text(labels, 820, 1656, "版本轴", "note-title")
text(labels, 888, 1656, "referenceIndexVersion + environment snapshot + capabilityRevision + bindingPolicyVersion", "note")

svg: list[str] = []
svg.append('<svg xmlns="http://www.w3.org/2000/svg" id="architecture-svg" viewBox="0 0 1800 1700" width="1800" height="1700" role="img" aria-labelledby="diagram-title diagram-desc">')
svg.append('<title id="diagram-title">Data Agent Explore 当前完整方案</title>')
svg.append('<desc id="diagram-desc">展示外部 Parser 到参考知识库构建、MetaOne 环境知识、Environment-first Explore、Binding Overlay、Context Bundle、版本和治理的完整架构，并区分已实现、样例与待实现组件。</desc>')
svg.append('''<style>
text{font-family:"Helvetica Neue",Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif}.title{font-size:28px;font-weight:700;fill:#111827}.subtitle{font-size:13px;fill:#64748b}.lane-title{font-size:17px;font-weight:700;fill:#111827}.lane-sub{font-size:12px;fill:#64748b}.node-title{font-size:15px;font-weight:700;fill:#111827}.node-sub{font-size:12px;fill:#475569}.status{font-size:10px;font-weight:700}.edge-label{font-size:11px;font-weight:700;fill:#475569}.note-title{font-size:12px;font-weight:700;fill:#111827}.note,.legend{font-size:12px;fill:#475569}.edge{fill:none;stroke-linecap:round;stroke-linejoin:round}.node{cursor:pointer}.node:hover rect:first-child,.node:focus rect:first-child{stroke-width:3}.canvas-bg{fill:#ffffff}
</style>''')
svg.append('<defs>')
for marker_id, color in (("arrow-blue", "#2563eb"), ("arrow-orange", "#ea580c"), ("arrow-green", "#16a34a"), ("arrow-purple", "#9333ea"), ("arrow-gray", "#6b7280")):
    svg.append(f'<marker id="{marker_id}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="{color}"/></marker>')
svg.append('</defs>')
svg.append('<rect class="canvas-bg" width="1800" height="1700"/>')
text(svg, 48, 48, "Data Agent Explore · 当前完整方案", "title")
text(svg, 48, 76, "Parser Template 交付 → Reference Context → MetaOne Environment → Environment-first Explore → Dual-layer Bundle", "subtitle")
svg.extend(containers)
svg.extend(edges)
svg.extend(nodes)
svg.extend(labels)
svg.append('</svg>')

OUT.mkdir(parents=True, exist_ok=True)
svg_text = "\n".join(svg)
SVG_PATH.write_text(svg_text, encoding="utf-8")

html = [
    '<!doctype html>',
    '<html lang="zh-CN"><head><meta charset="utf-8"/>',
    '<meta name="viewport" content="width=device-width,initial-scale=1"/>',
    '<title>Data Agent Explore 当前完整方案</title>',
    '''<style>
:root{--bg:#f3f4f6;--panel:#fff;--text:#111827;--muted:#64748b;--border:#d1d5db}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}.topbar{height:58px;display:flex;align-items:center;gap:8px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--border);position:relative;z-index:5}.brand{font-weight:700;margin-right:auto}.hint{font-size:12px;color:var(--muted)}button{border:1px solid var(--border);background:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 340px;height:calc(100vh - 58px)}#viewport{position:relative;overflow:hidden;background:radial-gradient(circle at 1px 1px,#d1d5db 1px,transparent 0);background-size:20px 20px;cursor:grab}#stage{position:absolute;transform-origin:0 0;filter:drop-shadow(0 12px 24px rgba(15,23,42,.12))}#stage svg{display:block;width:1360px;height:auto;background:#fff;border-radius:8px}.panel{background:#fff;border-left:1px solid var(--border);padding:20px;overflow:auto}.panel h2{font-size:18px;margin:0 0 8px}.panel h3{font-size:14px;margin:22px 0 8px}.panel p,.panel li{font-size:13px;line-height:1.65;color:var(--muted)}.pill{display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:3px 8px;font-size:11px}.selected rect:first-child{stroke:#2563eb!important;stroke-width:4!important}@media(max-width:900px){.workspace{grid-template-columns:1fr}.panel{display:none}.hint{display:none}}
</style></head><body>''',
    '<div class="topbar"><div class="brand">Data Agent Explore · 当前完整方案</div><div class="hint">滚轮缩放 · 拖动画布 · 点击节点</div><button id="plus">＋</button><button id="minus">－</button><button id="reset">重置</button></div>',
    '<div class="workspace"><main id="viewport"><div id="stage">',
    svg_text,
    '</div></main>',
    '''<aside class="panel"><h2 id="detailTitle">方案阅读指南</h2><div class="pill" id="detailStatus">完整视图</div><p id="detailBody">按 01→05 阅读。蓝绿组件是当前 Reference Context 主链路；橙色是外部 Parser 或 MetaOne 环境；紫色是候选、Binding 与待实现能力。</p><h3>关键边界</h3><ul><li>Parser 只交付五类 Template JSON 目录。</li><li>ContextFragment 仅是消费侧内部 IR。</li><li>Reference 与 MetaOne 不做全局融合。</li><li>MetaOne 决定现网资产是否存在。</li><li>Reference 提供场景、业务对象、SID 与建模语义。</li><li>只有确认不存在才允许 Reference-only 候选。</li><li>Graph 面向机器，Rich Page 与 Bundle 面向 LLM。</li></ul></aside></div>''',
    '''<script>
const viewport=document.getElementById('viewport'),stage=document.getElementById('stage');let scale=.62,tx=20,ty=20,drag=false,lx=0,ly=0;function draw(){stage.style.transform=`translate(${tx}px,${ty}px) scale(${scale})`}function zoom(f,cx=viewport.clientWidth/2,cy=viewport.clientHeight/2){const old=scale;scale=Math.max(.22,Math.min(2.2,scale*f));tx=cx-(cx-tx)*(scale/old);ty=cy-(cy-ty)*(scale/old);draw()}function reset(){scale=Math.min((viewport.clientWidth-40)/1800,(viewport.clientHeight-40)/1700);tx=Math.max(20,(viewport.clientWidth-1800*scale)/2);ty=20;draw()}viewport.onwheel=e=>{e.preventDefault();const r=viewport.getBoundingClientRect();zoom(e.deltaY<0?1.12:.89,e.clientX-r.left,e.clientY-r.top)};viewport.onpointerdown=e=>{if(e.target.closest('.node'))return;drag=true;lx=e.clientX;ly=e.clientY;viewport.setPointerCapture(e.pointerId)};viewport.onpointermove=e=>{if(!drag)return;tx+=e.clientX-lx;ty+=e.clientY-ly;lx=e.clientX;ly=e.clientY;draw()};viewport.onpointerup=()=>drag=false;document.getElementById('plus').onclick=()=>zoom(1.18);document.getElementById('minus').onclick=()=>zoom(.84);document.getElementById('reset').onclick=reset;document.querySelectorAll('.node').forEach(n=>n.onclick=()=>{document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected'));n.classList.add('selected');document.getElementById('detailTitle').textContent=n.dataset.title;document.getElementById('detailBody').textContent=n.dataset.detail;document.getElementById('detailStatus').textContent=n.dataset.status});window.onresize=reset;reset();
</script></body></html>''',
]
HTML_PATH.write_text("\n".join(html), encoding="utf-8")
print(SVG_PATH)
print(HTML_PATH)
