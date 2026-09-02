from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture"
SVG_PATH = OUT / "dual-layer-knowledge-architecture.svg"
HTML_PATH = OUT / "dual-layer-knowledge-architecture.html"

containers: list[str] = []
edges: list[str] = []
nodes: list[str] = []
labels: list[str] = []


def text(layer, x, y, value, css="body", anchor="start"):
    layer.append(
        f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def lane(y, height, number, title, subtitle, fill, stroke):
    containers.append(
        f'<g id="lane-{number}" data-graph-role="container">'
        f'<rect x="40" y="{y}" width="1720" height="{height}" rx="18" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5" stroke-dasharray="7 5"/>'
        f'<text x="64" y="{y + 31}" class="lane-title">{number}  {escape(title)}</text>'
        f'<text x="64" y="{y + 54}" class="lane-sub">{escape(subtitle)}</text>'
        '</g>'
    )


def group(group_id, x, y, width, height, title, fill, stroke):
    containers.append(
        f'<g id="{group_id}" data-graph-role="decoration">'
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="14" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.2" data-graph-role="decoration"/>'
        f'<text x="{x + 18}" y="{y + 27}" class="group-title">{escape(title)}</text>'
        '</g>'
    )


def node(node_id, x, y, width, height, title, detail, fill, stroke, status=None, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    detail_value = "；".join(detail)
    nodes.append(
        f'<g id="{node_id}" class="node" data-graph-role="node" '
        f'data-title="{escape(title)}" data-detail="{escape(detail_value)}" tabindex="0">'
    )
    nodes.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>'
    )
    estimated_title_width = sum(14 if "\u3400" <= char <= "\u9fff" else 7 for char in title)
    if status and estimated_title_width + max(64, len(status) * 12) + 48 < width:
        badge_width = max(64, len(status) * 12)
        nodes.append(
            f'<rect x="{x + width - badge_width - 10}" y="{y + 10}" width="{badge_width}" '
            f'height="22" rx="11" fill="#ffffff" fill-opacity="0.9" stroke="{stroke}"/>'
        )
        text(nodes, x + width - badge_width / 2 - 10, y + 25, status, "status", "middle")
    text(nodes, x + 18, y + 32, title, "node-title")
    for index, line in enumerate(detail):
        text(nodes, x + 18, y + 59 + index * 20, line, "node-sub")
    nodes.append('</g>')


def edge(edge_id, source, target, path, label, color, marker, label_x=None, label_y=None, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    edges.append(
        f'<g id="{edge_id}" data-graph-role="edge" data-source="{source}" data-target="{target}">'
        f'<path d="{path}" class="edge" stroke="{color}" stroke-width="2.3" '
        f'marker-end="url(#{marker})"{dash}/></g>'
    )
    if label and label_x is not None and label_y is not None:
        text(labels, label_x, label_y, label, "edge-label", "middle")


lane(
    105, 305, "01", "两层知识来源",
    "参考库是全局版本化语义基线；MetaOne 是当前租户 / 环境事实，两者不做全局盲融合",
    "#f9fafb", "#cbd5e1",
)
group("reference-plane", 64, 176, 790, 200, "REFERENCE KNOWLEDGE · 已实现", "#eff6ff", "#93c5fd")
group("environment-plane", 946, 176, 790, 200, "ENVIRONMENT KNOWLEDGE · 目标适配", "#fff7ed", "#fdba74")

lane(
    440, 450, "02", "Environment-first 查询与语义绑定",
    "先确认现网资产，再用参考库补语义；只有确认不存在时才返回 Reference-only 候选",
    "#ffffff", "#c4b5fd",
)
lane(
    920, 225, "03", "Context Bundle 与治理输出",
    "双版本、双证据链；候选、冲突、缺失、接口不可用与截断均显式返回",
    "#f0fdf4", "#86efac",
)

# Cross-layer edges are drawn before nodes.
edge("e-template-compiler", "template-json", "reference-compiler", "M 294 286 L 344 286", "validated JSON", "#2563eb", "arrow-blue", 319, 268)
edge("e-compiler-reference", "reference-compiler", "reference-snapshot", "M 574 286 L 624 286", "Rich Pages", "#2563eb", "arrow-blue", 599, 268)
edge("e-metaone-adapter", "metaone-mcp", "metaone-adapter", "M 1194 286 L 1234 286", "MCP tools", "#ea580c", "arrow-orange", 1214, 268)
edge("e-adapter-env", "metaone-adapter", "environment-view", "M 1464 286 L 1504 286", "normalized", "#ea580c", "arrow-orange", 1484, 268)

edge("e-query-intent", "business-query", "requirements", "M 280 574 L 330 574", "query", "#2563eb", "arrow-blue", 305, 557)
edge("e-intent-env", "requirements", "environment-first", "M 570 574 L 620 574", "requirements", "#2563eb", "arrow-blue", 595, 557)
edge("e-env-gate", "environment-first", "availability-gate", "M 880 574 L 930 574", "facts + state", "#ea580c", "arrow-orange", 905, 557)
edge("e-gate-overlay", "availability-gate", "binding-overlay", "M 1210 556 L 1460 556", "FOUND / PARTIAL", "#16a34a", "arrow-green", 1335, 539)

edge("e-env-view-search", "environment-view", "environment-first", "M 1614 346 L 1614 468 L 750 468 L 750 506", "environment read", "#ea580c", "arrow-orange", 1180, 455)
edge("e-reference-enrich", "reference-snapshot", "reference-enrichment", "M 724 346 L 724 420 L 600 420 L 600 760 L 590 760", "reference read", "#2563eb", "arrow-blue", 650, 682)

edge("e-gate-reference-only", "availability-gate", "reference-only", "M 1070 654 L 1070 700", "NOT_FOUND_CONFIRMED", "#9333ea", "arrow-purple", 1152, 682)
edge("e-gate-missing", "availability-gate", "missing-state", "M 960 654 L 960 676 L 780 676 L 780 700", "unknown", "#6b7280", "arrow-gray", 870, 666, True)
edge("e-reference-only-overlay", "reference-only", "binding-overlay", "M 1210 760 L 1410 760 L 1410 674 L 1530 674 L 1530 654", "candidate", "#9333ea", "arrow-purple", 1310, 744, True)
edge("e-enrich-overlay", "reference-enrichment", "binding-overlay", "M 460 820 L 460 850 L 1590 850 L 1590 654", "semantic enrichment", "#2563eb", "arrow-blue", 1025, 837)
edge("e-missing-overlay", "missing-state", "binding-overlay", "M 780 820 L 780 870 L 1650 870 L 1650 654", "missing / warning", "#6b7280", "arrow-gray", 1215, 857, True)

edge("e-overlay-bundle", "binding-overlay", "context-bundle", "M 1710 654 L 1710 894 L 420 894 L 420 1002", "binding overlay", "#16a34a", "arrow-green", 1065, 881)
edge("e-bundle-consumers", "context-bundle", "consumers", "M 650 1058 L 760 1058", "read-only context", "#16a34a", "arrow-green", 705, 1041)
edge("e-bundle-review", "context-bundle", "governance", "M 420 1114 L 420 1128 L 1385 1128 L 1385 1114", "candidates / conflicts", "#9333ea", "arrow-purple", 902, 1120, True)

# Lane 01 nodes.
node("template-json", 94, 226, 200, 120, "Template JSON + SID", ["五类交付结构", "建模规范 / 参考语义"], "#ffffff", "#60a5fa", "全局输入")
node("reference-compiler", 344, 216, 230, 140, "Reference Compiler", ["Canonical + Fusion", "Evidence + Rich Page", "Machine Graph / Index"], "#eff6ff", "#3b82f6", "确定性")
node("reference-snapshot", 624, 226, 200, 120, "Reference Snapshot", ["场景 / 需求 / 业务对象", "语义定义 / 分层分域"], "#dbeafe", "#2563eb", "版本化")

node("metaone-mcp", 976, 226, 218, 120, "MetaOne MCP", ["真实环境元数据", "接口允许增删改"], "#ffffff", "#fb923c", "外部")
node("metaone-adapter", 1234, 216, 230, 140, "Capability Adapter", ["tools/list + capability", "字段 / 类型归一化", "错误 / 分页 / 截断"], "#fff7ed", "#f97316", "待实现")
node("environment-view", 1504, 226, 202, 120, "Environment View", ["维度 / 度量 / 指标", "逻辑 / 物理 / 字段"], "#ffedd5", "#ea580c", "实时")

# Lane 02 nodes.
node("business-query", 80, 526, 200, 96, "需求调研 / 模型设计", ["业务问题与约束"], "#ffffff", "#a78bfa", "Query")
node("requirements", 330, 516, 240, 116, "Intent + Requirements", ["场景 / 指标 / 粒度", "所需 coverage"], "#faf5ff", "#8b5cf6", "规划")
node("environment-first", 620, 506, 260, 136, "Environment-first Lookup", ["先 search MetaOne", "再 read / expand", "少量锚点 + 明确预算"], "#fff7ed", "#f97316", "优先")
node("availability-gate", 930, 494, 280, 160, "Availability + Coverage Gate", ["FOUND / PARTIAL", "NOT_FOUND_CONFIRMED", "UNSUPPORTED / UNAVAILABLE", "TRUNCATED ≠ 不存在"], "#ffffff", "#7c3aed", "关键决策")
node("binding-overlay", 1460, 506, 260, 148, "Query-scoped Binding Overlay", ["环境事实 + 参考语义", "confirmed / derived / candidate", "不回写两层知识库"], "#f0fdf4", "#22c55e", "临时视图")

node("reference-enrichment", 330, 700, 260, 120, "Reference Semantic Enrichment", ["场景 / 需求 / 业务对象", "SID / 分层分域规则"], "#eff6ff", "#3b82f6", "语义来源")
node("missing-state", 660, 700, 240, 120, "Missing / Unknown", ["无权限 / 超时 / 不支持", "保持 unknown，不假装缺失"], "#f9fafb", "#94a3b8", "显式")
node("reference-only", 950, 700, 260, 120, "Reference-only Candidate", ["仅确认现网不存在后启用", "不能声称环境可用"], "#faf5ff", "#a855f7", "候选", True)

# Lane 03 nodes.
node("context-bundle", 190, 1002, 460, 112, "Dual-layer Context Bundle", ["environment facts / reference semantics", "missing / conflicts / candidates / warnings", "reference + environment + policy versions"], "#f0fdf4", "#16a34a", "主输出")
node("consumers", 760, 1002, 320, 112, "下游消费者", ["Main Agent / 建模 Agent", "SQL Agent / 人工评审"], "#ffffff", "#22c55e", "只读")
node("governance", 1180, 1002, 410, 112, "Review + Golden Governance", ["候选映射人工确认", "接口兼容 fixtures / coverage cases", "禁止候选自动升级为事实"], "#faf5ff", "#a855f7", "治理")

# Notes and legend.
labels.append('<rect x="40" y="1172" width="1720" height="94" rx="14" fill="#f9fafb" stroke="#e5e7eb"/>')
text(labels, 64, 1201, "权威规则", "note-title")
text(labels, 136, 1201, "MetaOne 决定当前环境有什么；Reference Context 解释它意味着什么；Binding Overlay 只负责本次查询的对齐。", "note")
text(labels, 64, 1230, "回退规则", "note-title")
text(labels, 136, 1230, "只有 NOT_FOUND_CONFIRMED 才允许 Reference-only；超时、无权限、不支持与截断均返回 Unknown / Missing。", "note")
text(labels, 64, 1254, "版本轴", "note-title")
text(labels, 136, 1254, "referenceIndexVersion + environment snapshot/capturedAt + capabilityRevision + bindingPolicyVersion。", "note")

svg: list[str] = []
svg.append('<svg xmlns="http://www.w3.org/2000/svg" id="architecture-svg" viewBox="0 0 1800 1300" width="1800" height="1300" role="img" aria-labelledby="diagram-title diagram-desc">')
svg.append('<title id="diagram-title">Data Agent Explore 双层知识库与 MetaOne Binding 方案</title>')
svg.append('<desc id="diagram-desc">参考基础知识库与 MetaOne 环境知识库保持分离，通过 Environment-first 查询、能力适配、可用性判断和临时 Binding Overlay 组成双层 Context Bundle。</desc>')
svg.append('''<style>
text{font-family:"Helvetica Neue",Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif}.title{font-size:27px;font-weight:700;fill:#111827}.subtitle{font-size:13px;fill:#64748b}.lane-title{font-size:17px;font-weight:700;fill:#111827}.lane-sub{font-size:12px;fill:#64748b}.group-title{font-size:12px;font-weight:700;letter-spacing:.08em;fill:#475569}.node-title{font-size:15px;font-weight:700;fill:#111827}.node-sub{font-size:12px;fill:#475569}.status{font-size:10px;font-weight:700;fill:#334155}.edge-label{font-size:11px;font-weight:700;fill:#475569}.note-title{font-size:12px;font-weight:700;fill:#111827}.note{font-size:12px;fill:#475569}.edge{fill:none;stroke-linecap:round;stroke-linejoin:round}.node{cursor:pointer}.node:hover rect:first-child,.node:focus rect:first-child{stroke-width:3}.canvas-bg{fill:#ffffff}
</style>''')
svg.append('<defs>')
for marker_id, color in (("arrow-blue", "#2563eb"), ("arrow-orange", "#ea580c"), ("arrow-green", "#16a34a"), ("arrow-purple", "#9333ea"), ("arrow-gray", "#6b7280")):
    svg.append(f'<marker id="{marker_id}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="{color}"/></marker>')
svg.append('</defs>')
svg.append('<rect class="canvas-bg" width="1800" height="1300"/>')
text(svg, 48, 48, "Data Agent Explore · 双层知识库与 MetaOne Binding", "title")
text(svg, 48, 76, "环境事实优先 · 参考语义补全 · 确认缺失才回退 · MCP 变化隔离在 Adapter", "subtitle")
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
    '<title>双层知识库与 MetaOne Binding</title>',
    '''<style>
:root{--bg:#f3f4f6;--panel:#fff;--text:#111827;--muted:#64748b;--border:#d1d5db}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}.topbar{height:58px;display:flex;align-items:center;gap:8px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--border);position:relative;z-index:5}.brand{font-weight:700;margin-right:auto}.hint{font-size:12px;color:var(--muted)}button{border:1px solid var(--border);background:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 330px;height:calc(100vh - 58px)}#viewport{position:relative;overflow:hidden;background:radial-gradient(circle at 1px 1px,#d1d5db 1px,transparent 0);background-size:20px 20px;cursor:grab}#stage{position:absolute;transform-origin:0 0;filter:drop-shadow(0 12px 24px rgba(15,23,42,.12))}#stage svg{display:block;width:1440px;height:auto;background:#fff;border-radius:8px}.panel{background:#fff;border-left:1px solid var(--border);padding:20px;overflow:auto}.panel h2{font-size:18px;margin:0 0 8px}.panel h3{font-size:14px;margin:22px 0 8px}.panel p,.panel li{font-size:13px;line-height:1.65;color:var(--muted)}.selected rect:first-child{stroke:#2563eb!important;stroke-width:4!important}@media(max-width:900px){.workspace{grid-template-columns:1fr}.panel{display:none}.hint{display:none}}
</style></head><body>''',
    '<div class="topbar"><div class="brand">双层知识库 · MetaOne Binding</div><div class="hint">滚轮缩放 · 拖动画布 · 点击节点</div><button id="plus">＋</button><button id="minus">－</button><button id="reset">重置</button></div>',
    '<div class="workspace"><main id="viewport"><div id="stage">',
    svg_text,
    '</div></main>',
    '''<aside class="panel"><h2 id="detailTitle">方案阅读指南</h2><p id="detailBody">从上到下阅读：两层知识来源保持独立；查询时先查 MetaOne，再做字段级语义补全和受控回退；最终输出双版本 Context Bundle。</p><h3>三个关键判断</h3><ul><li>MetaOne 找到资产：以环境事实为主，参考库只补语义。</li><li>MetaOne 明确不存在：允许返回 Reference-only 候选。</li><li>超时、无权限、不支持、截断：只能标为 Unknown，不能当作不存在。</li></ul><h3>接口演进</h3><p>Explore 不依赖 MetaOne MCP 工具名。Capability Adapter 负责工具发现、参数映射、响应归一化和兼容 fixtures。</p></aside></div>''',
    '''<script>
const viewport=document.getElementById('viewport'),stage=document.getElementById('stage');let scale=.7,tx=20,ty=20,drag=false,lx=0,ly=0;function draw(){stage.style.transform=`translate(${tx}px,${ty}px) scale(${scale})`}function zoom(f,cx=viewport.clientWidth/2,cy=viewport.clientHeight/2){const old=scale;scale=Math.max(.25,Math.min(2.2,scale*f));tx=cx-(cx-tx)*(scale/old);ty=cy-(cy-ty)*(scale/old);draw()}function reset(){scale=Math.min((viewport.clientWidth-40)/1800,(viewport.clientHeight-40)/1300);tx=Math.max(20,(viewport.clientWidth-1800*scale)/2);ty=20;draw()}viewport.onwheel=e=>{e.preventDefault();const r=viewport.getBoundingClientRect();zoom(e.deltaY<0?1.12:.89,e.clientX-r.left,e.clientY-r.top)};viewport.onpointerdown=e=>{if(e.target.closest('.node'))return;drag=true;lx=e.clientX;ly=e.clientY;viewport.setPointerCapture(e.pointerId)};viewport.onpointermove=e=>{if(!drag)return;tx+=e.clientX-lx;ty+=e.clientY-ly;lx=e.clientX;ly=e.clientY;draw()};viewport.onpointerup=()=>drag=false;document.getElementById('plus').onclick=()=>zoom(1.18);document.getElementById('minus').onclick=()=>zoom(.84);document.getElementById('reset').onclick=reset;document.querySelectorAll('.node').forEach(n=>n.onclick=()=>{document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected'));n.classList.add('selected');document.getElementById('detailTitle').textContent=n.dataset.title;document.getElementById('detailBody').textContent=n.dataset.detail});window.onresize=reset;reset();
</script></body></html>''',
]
HTML_PATH.write_text("\n".join(html), encoding="utf-8")
print(SVG_PATH)
print(HTML_PATH)
