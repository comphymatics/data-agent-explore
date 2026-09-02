from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture"
SVG_PATH = OUT / "data-agent-explore-complete.svg"
HTML_PATH = OUT / "data-agent-explore-complete.html"

svg = []


def add(line=""):
    svg.append(line)


def text(x, y, value, css="body", anchor="start"):
    add(f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{escape(value)}</text>')


def lane(y, height, number, title, subtitle, fill, stroke, badge, badge_fill, badge_text):
    add(f'<g data-graph-role="container" id="lane-{number}">')
    add(f'<rect x="40" y="{y}" width="1720" height="{height}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="1.5" stroke-dasharray="7 5"/>')
    text(64, y + 29, f"{number}  {title}", "lane-title")
    text(64, y + 51, subtitle, "lane-sub")
    badge_width = max(150, len(badge) * 14)
    add(f'<rect x="{1728-badge_width}" y="{y+16}" width="{badge_width}" height="28" rx="14" fill="{badge_fill}" stroke="{stroke}"/>')
    text(1728-badge_width/2, y + 35, badge, badge_text, "middle")
    add('</g>')


def node(node_id, x, y, width, height, title_value, details, fill="#ffffff", stroke="#d1d5db", status=None, dashed=False, title_fill="#111827"):
    detail = "；".join(details)
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    add(f'<g id="{node_id}" class="node" data-graph-role="node" data-title="{escape(title_value)}" data-detail="{escape(detail)}" tabindex="0">')
    add(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>')
    if status:
        sw = max(58, len(status) * 12)
        add(f'<rect x="{x+width-sw-10}" y="{y+10}" width="{sw}" height="22" rx="11" fill="#ffffff" fill-opacity="0.86" stroke="{stroke}"/>')
        text(x+width-sw/2-10, y+25, status, "status", "middle")
    text(x+18, y+31, title_value, "node-title")
    start = y + 56
    for index, line in enumerate(details):
        text(x+18, start + index*20, line, "node-sub")
    add('</g>')


def edge(edge_id, source, target, path, label, color="#2563eb", marker="arrow-blue", dashed=False, label_x=None, label_y=None, width=2.4):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    add(f'<g id="{edge_id}" data-graph-role="edge" data-source="{source}" data-target="{target}">')
    add(f'<path d="{path}" class="edge" stroke="{color}" stroke-width="{width}" marker-end="url(#{marker})"{dash}/>')
    if label and label_x is not None and label_y is not None:
        badge_width = max(64, len(label) * 13)
        add(f'<rect x="{label_x-badge_width/2}" y="{label_y-16}" width="{badge_width}" height="21" rx="10" fill="#ffffff" fill-opacity="0.96" stroke="{color}" stroke-opacity="0.25"/>')
        text(label_x, label_y-2, label, "edge-label", "middle")
    add('</g>')


add('<?xml version="1.0" encoding="UTF-8"?>')
add('<svg id="architecture-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 1450" width="1800" height="1450" role="img" aria-labelledby="diagram-title diagram-desc">')
add('<title id="diagram-title">Data Agent Explore 完整方案</title>')
add('<desc id="diagram-desc">展示外部解析团队通过五类 Template JSON 交付目录与 Enterprise Data Context、版本化存储和在线 Explore Agent 交互的完整架构。</desc>')
add('<style>')
add("text { font-family: 'Helvetica Neue', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', 'Microsoft JhengHei', SimHei, sans-serif; }")
add('.title { font-size: 30px; font-weight: 700; fill: #111827; }')
add('.subtitle { font-size: 14px; fill: #6b7280; }')
add('.lane-title { font-size: 16px; font-weight: 700; letter-spacing: .03em; fill: #111827; }')
add('.lane-sub { font-size: 12px; fill: #6b7280; }')
add('.node-title { font-size: 16px; font-weight: 700; fill: #111827; }')
add('.node-sub { font-size: 12px; fill: #4b5563; }')
add('.status { font-size: 11px; font-weight: 700; fill: #374151; }')
add('.badge-blue { font-size: 11px; font-weight: 700; fill: #1d4ed8; }')
add('.badge-orange { font-size: 11px; font-weight: 700; fill: #9a3412; }')
add('.badge-green { font-size: 11px; font-weight: 700; fill: #166534; }')
add('.badge-purple { font-size: 11px; font-weight: 700; fill: #7e22ce; }')
add('.edge-label { font-size: 11px; font-weight: 700; fill: #374151; }')
add('.legend { font-size: 12px; fill: #4b5563; }')
add('.note-title { font-size: 13px; font-weight: 700; fill: #111827; }')
add('.note { font-size: 12px; fill: #4b5563; }')
add('.edge { fill: none; stroke-linecap: round; stroke-linejoin: round; }')
add('.node { cursor: pointer; } .node:hover rect:first-child, .node:focus rect:first-child { stroke-width: 3; }')
add('</style>')
add('<defs>')
for marker_id, color in (("arrow-blue", "#2563eb"), ("arrow-green", "#16a34a"), ("arrow-purple", "#9333ea"), ("arrow-orange", "#ea580c"), ("arrow-gray", "#6b7280")):
    add(f'<marker id="{marker_id}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="{color}"/></marker>')
add('</defs>')
add('<rect class="canvas-bg" width="1800" height="1450" fill="#ffffff"/>')

text(48, 48, "Data Agent Explore 完整方案", "title")
text(48, 76, "五类 Template JSON 是跨团队正式边界；ContextFragment 是内部 IR；Graph 面向机器，Rich Page 与 Bundle 面向 LLM。", "subtitle")
add('<rect x="1290" y="28" width="146" height="28" rx="14" fill="#dcfce7" stroke="#86efac"/>')
text(1363, 47, "下游核心已实现", "badge-green", "middle")
add('<rect x="1448" y="28" width="138" height="28" rx="14" fill="#ffedd5" stroke="#fdba74"/>')
text(1517, 47, "解析团队外部交付", "badge-orange", "middle")
add('<rect x="1598" y="28" width="154" height="28" rx="14" fill="#faf5ff" stroke="#c084fc"/>')
text(1675, 47, "候选不升级为事实", "badge-purple", "middle")

lane(110, 250, "01", "解析与 Template JSON 交付", "真实材料只在解析侧打开；跨团队交换使用五类约定 JSON 结构的批次目录", "#fff7ed", "#fdba74", "外部模块 / 稳定契约", "#ffedd5", "badge-orange")
lane(390, 260, "02", "Enterprise Data Context 编译", "Canonical Resolution 先于多来源 Fusion；Evidence、歧义与冲突贯穿全程", "#eff6ff", "#93c5fd", "下游确定性核心", "#dbeafe", "badge-blue")
lane(680, 230, "03", "治理、索引与版本发布", "索引与 Graph 是可重建读取视图；Canonical Context 与 Rich Context Page 是版本化产物", "#f0fdf4", "#86efac", "IndexVersion / 可重放", "#dcfce7", "badge-green")
lane(940, 300, "04", "在线 Explore 运行时", "Explore 只调用四个只读工具，以少量 Rich Page 组成带缺口和证据的 Context Bundle", "#f5f3ff", "#c4b5fd", "只读 Agent / 无 SQL 生成", "#ede9fe", "badge-purple")

# Lane 01 nodes and arrows
node("raw-sources", 80, 190, 220, 108, "企业数据材料", ["Word / Excel / JSON / SQL", "SmartCare / SID / 标准 / 目录"], "#ffffff", "#fb923c", "原始输入", True)
node("parser-extractor", 360, 180, 270, 128, "解析与抽取模块", ["确定性结构解析 → Document IR", "规则优先；可选 LLM 语义辅助", "输出 Evidence + 事实状态"], "#fff7ed", "#fb923c", "同事负责", True)
node("fragment-contract", 700, 180, 270, 128, "Template JSON 交付契约", ["五类 JSON 结构 / 批次目录", "template-input.schema.json", "Schema 文件不入事实库"], "#f0fdfa", "#2dd4bf", "唯一边界")
node("contract-gate", 1040, 190, 250, 108, "Template Contract Gate", ["逐文件 Union Schema 校验", "拒绝缺字段与错误结构"], "#eff6ff", "#60a5fa", "已实现")
node("downstream-entry", 1370, 180, 300, 128, "Template Adapter + Compiler", ["compile_template_inputs(path)", "Shape → 内部 ContextFragment IR", "不重开原始 Word / Excel"], "#eff6ff", "#60a5fa", "已实现")
edge("e-source-parser", "raw-sources", "parser-extractor", "M 300 244 L 360 244", "原始文件", label_x=330, label_y=225)
edge("e-parser-fragment", "parser-extractor", "fragment-contract", "M 630 244 L 700 244", "JSON 目录", label_x=665, label_y=225)
edge("e-fragment-gate", "fragment-contract", "contract-gate", "M 970 244 L 1040 244", "Schema", color="#16a34a", marker="arrow-green", label_x=1005, label_y=225)
edge("e-gate-compiler", "contract-gate", "downstream-entry", "M 1290 244 L 1370 244", "validated", label_x=1330, label_y=225)

# Lane transition 01 -> 02
edge("e-entry-canonical", "downstream-entry", "canonical", "M 1520 308 L 1520 455", "Internal Fragment batch", label_x=1584, label_y=389)

# Lane 02 nodes and arrows (right to left)
node("canonical", 1370, 455, 300, 112, "Canonical Resolution", ["identity_hints → exact → aliases", "UNCERTAIN 保持分离，不盲目合并"], "#ffffff", "#60a5fa", "确定性")
node("fusion", 1030, 455, 270, 112, "Section-level Fusion", ["来源权威策略 + list union", "保留 kept / discarded 冲突"], "#ffffff", "#60a5fa", "确定性")
node("mapping-refs", 670, 455, 290, 112, "语义映射与引用", ["Business Mapping Rules", "Typed References → Backrefs", "环境物理适配不在此发生"], "#ffffff", "#60a5fa", "策略驱动")
node("rich-pages", 240, 445, 350, 132, "Rich Context Page", ["L0：定位摘要", "L1：局部推理页面", "L2：sections / refs / evidence", "Graph 只面向机器"], "#eff6ff", "#3b82f6", "LLM 信息单元")
node("candidate-store", 1030, 574, 270, 66, "Candidates / Conflicts", ["INFERRED 与 CANDIDATE 单独保存"], "#faf5ff", "#c084fc", None)
edge("e-canonical-fusion", "canonical", "fusion", "M 1370 511 L 1300 511", "同一 Context", label_x=1335, label_y=494)
edge("e-fusion-map", "fusion", "mapping-refs", "M 1030 511 L 960 511", "融合 sections", label_x=995, label_y=494)
edge("e-map-pages", "mapping-refs", "rich-pages", "M 670 511 L 590 511", "Canonical IR", label_x=630, label_y=494)
edge("e-fusion-candidates", "fusion", "candidate-store", "M 1165 567 L 1165 574", "", color="#9333ea", marker="arrow-purple", dashed=True, width=1.8)

# Lane transition 02 -> 03
edge("e-pages-index", "rich-pages", "index-builder", "M 415 577 L 415 710 L 220 710 L 220 750", "物化读取视图", color="#16a34a", marker="arrow-green", label_x=318, label_y=697)

# Lane 03 nodes and arrows
node("index-builder", 80, 750, 280, 104, "索引与 Machine Graph", ["PageIndex / ElementIndex", "Typed Graph / Backrefs / Impact"], "#f0fdf4", "#4ade80", "可重建")
node("quality-gate", 450, 750, 280, 104, "Quality & Golden Gate", ["Evidence / path / ref 检查", "Golden Context Recall / Coverage"], "#ffffff", "#4ade80", "治理")
node("version-snapshot", 820, 740, 340, 124, "Immutable Context Snapshot", ["fragments / contexts / pages", "quality.json + manifest.json", "content hash → IndexVersion"], "#f0fdf4", "#22c55e", "本地版本目录")
node("latest-pointer", 1280, 750, 360, 104, "Atomic latest.json", ["versions/context-<hash>", "运行时固定版本；索引可重新构建"], "#ffffff", "#22c55e", "发布指针")
edge("e-index-quality", "index-builder", "quality-gate", "M 360 802 L 450 802", "质量报告", color="#16a34a", marker="arrow-green", label_x=405, label_y=784)
edge("e-quality-snapshot", "quality-gate", "version-snapshot", "M 730 802 L 820 802", "通过后保存", color="#16a34a", marker="arrow-green", label_x=775, label_y=784)
edge("e-snapshot-latest", "version-snapshot", "latest-pointer", "M 1160 802 L 1280 802", "原子发布", color="#16a34a", marker="arrow-green", label_x=1220, label_y=784)
edge("e-candidate-quality", "candidate-store", "quality-gate", "M 1165 640 L 1165 704 L 590 704 L 590 750", "审核 / Golden 对比", color="#9333ea", marker="arrow-purple", dashed=True, label_x=877, label_y=696, width=1.8)

# Lane transition 03 -> 04
edge("e-latest-runtime", "latest-pointer", "runtime-view", "M 1460 854 L 1460 1020", "load_runtime(version)", color="#16a34a", marker="arrow-green", label_x=1535, label_y=943)

# Lane 04 nodes and arrows
node("user-query", 80, 1028, 220, 96, "业务问题 / 下游 Agent", ["找指标、模型、字段、粒度、血缘"], "#ffffff", "#a78bfa", "Query")
node("explore-agent", 370, 995, 300, 146, "Explore Agent", ["QueryRouter：范围与意图", "CoveragePlanner：检查缺口", "Focused Expansion：按需展开", "JointReasoner：结构化汇总"], "#faf5ff", "#8b5cf6", "只读")
node("data-tools", 760, 1020, 270, 110, "Data Context Tools", ["data_search / data_read", "data_expand / data_source", "平台中立；可接 MCP / HTTP"], "#eff6ff", "#60a5fa", "4 个工具")
node("runtime-view", 1280, 1020, 360, 110, "Pinned Runtime Context View", ["Rich Pages + Page/Element Index", "Machine Graph + Backrefs", "内存运行；固定 IndexVersion"], "#f0fdf4", "#4ade80", "可复现")
node("environment-adapter", 390, 1160, 250, 62, "Environment Binding", ["requirements ⇄ matched assets"], "#fff7ed", "#fb923c", None, True)
node("context-bundle", 900, 1150, 320, 76, "Context Bundle", ["coverage / missing / sources / conflicts / candidates"], "#faf5ff", "#8b5cf6", "主输出")
node("consumers", 1350, 1150, 290, 76, "下游消费者", ["建模 Agent / SQL Agent / 人工分析"], "#ffffff", "#a78bfa", "复用上下文")
edge("e-query-agent", "user-query", "explore-agent", "M 300 1076 L 370 1076", "业务问题", label_x=335, label_y=1058)
edge("e-agent-tools", "explore-agent", "data-tools", "M 670 1048 L 760 1048", "tool call", label_x=715, label_y=1030)
edge("e-tools-runtime", "data-tools", "runtime-view", "M 1030 1048 L 1280 1048", "固定版本读取", color="#16a34a", marker="arrow-green", label_x=1155, label_y=1030)
edge("e-runtime-tools", "runtime-view", "data-tools", "M 1280 1102 L 1030 1102", "Rich Page / Evidence", color="#16a34a", marker="arrow-green", label_x=1155, label_y=1124)
edge("e-tools-agent", "data-tools", "explore-agent", "M 760 1110 L 670 1110", "tool result", label_x=715, label_y=1133)
edge("e-agent-env", "explore-agent", "environment-adapter", "M 465 1141 L 465 1160", "", color="#ea580c", marker="arrow-orange", dashed=True, width=1.8)
edge("e-env-agent", "environment-adapter", "explore-agent", "M 570 1160 L 570 1141", "", color="#ea580c", marker="arrow-orange", dashed=True, width=1.8)
edge("e-agent-bundle", "explore-agent", "context-bundle", "M 670 1128 L 700 1128 L 700 1188 L 900 1188", "覆盖检查后输出", color="#9333ea", marker="arrow-purple", label_x=800, label_y=1172)
edge("e-bundle-consumers", "context-bundle", "consumers", "M 1220 1188 L 1350 1188", "可复用上下文", color="#9333ea", marker="arrow-purple", label_x=1285, label_y=1171)

# Footer and legend
add('<path data-graph-role="decoration" d="M 54 1270 H 1746 Q 1760 1270 1760 1284 V 1396 Q 1760 1410 1746 1410 H 54 Q 40 1410 40 1396 V 1284 Q 40 1270 54 1270 Z" fill="#f9fafb" stroke="#e5e7eb"/>')
text(64, 1300, "流向图例", "note-title")
add('<line x1="64" y1="1328" x2="106" y2="1328" stroke="#2563eb" stroke-width="2.4" marker-end="url(#arrow-blue)"/>')
text(118, 1332, "主数据 / Agent 调用", "legend")
add('<line x1="290" y1="1328" x2="332" y2="1328" stroke="#16a34a" stroke-width="2.4" marker-end="url(#arrow-green)"/>')
text(344, 1332, "存储写入 / 固定版本读取", "legend")
add('<line x1="575" y1="1328" x2="617" y2="1328" stroke="#9333ea" stroke-width="1.8" stroke-dasharray="6 4" marker-end="url(#arrow-purple)"/>')
text(629, 1332, "候选 / 治理 / Bundle", "legend")
add('<line x1="850" y1="1328" x2="892" y2="1328" stroke="#ea580c" stroke-width="1.8" stroke-dasharray="6 4" marker-end="url(#arrow-orange)"/>')
text(904, 1332, "可选外部适配", "legend")
text(64, 1370, "事实边界", "note-title")
text(132, 1370, "EXPLICIT / DERIVED 可进入正式 sections；INFERRED / CANDIDATE 只进入候选区，不能因置信度高而自动升级。", "note")
text(64, 1395, "存储边界", "note-title")
text(132, 1395, "当前：JSONL 交接 + 本地不可变版本目录 + 内存索引；生产可替换对象存储、搜索引擎和图存储，但契约保持不变。", "note")
add('</svg>')

OUT.mkdir(parents=True, exist_ok=True)
svg_text = "\n".join(svg)
SVG_PATH.write_text(svg_text, encoding="utf-8")

html = []
html.append('<!doctype html>')
html.append('<html lang="zh-CN"><head><meta charset="utf-8"/>')
html.append('<meta name="viewport" content="width=device-width,initial-scale=1"/>')
html.append('<title>Data Agent Explore 完整方案</title>')
html.append('''<style>
:root{color-scheme:light;--bg:#f3f4f6;--panel:#fff;--text:#111827;--muted:#6b7280;--border:#d1d5db;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
body.dark{--bg:#111827;--panel:#1f2937;--text:#f9fafb;--muted:#d1d5db;--border:#4b5563;--accent:#60a5fa;color-scheme:dark}
.topbar{height:58px;display:flex;align-items:center;gap:8px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--border);position:relative;z-index:5}
.brand{font-weight:700;margin-right:auto}.hint{font-size:12px;color:var(--muted);margin-right:12px}.btn{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:7px 11px;cursor:pointer}.btn:hover{border-color:var(--accent);color:var(--accent)}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 320px;height:calc(100vh - 58px)}
#viewport{position:relative;overflow:hidden;background:radial-gradient(circle at 1px 1px,#d1d5db 1px,transparent 0);background-size:20px 20px;cursor:grab}.dark #viewport{background-image:radial-gradient(circle at 1px 1px,#374151 1px,transparent 0)}#viewport.dragging{cursor:grabbing}
#stage{position:absolute;left:24px;top:20px;transform-origin:0 0;will-change:transform;filter:drop-shadow(0 12px 24px rgba(15,23,42,.12))}#stage svg{display:block;width:1440px;height:auto;background:white;border-radius:8px}
.panel{background:var(--panel);border-left:1px solid var(--border);padding:20px;overflow:auto}.panel h2{font-size:18px;margin:0 0 8px}.panel h3{font-size:14px;margin:24px 0 8px}.panel p,.panel li{font-size:13px;line-height:1.65;color:var(--muted)}.panel code{font-size:12px;color:var(--text)}
.status{display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:3px 8px;font-size:11px;margin-top:8px}.kbd{border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:1px 5px;font-size:11px}.selected rect:first-child{stroke:#2563eb!important;stroke-width:4!important}
@media(max-width:900px){.workspace{grid-template-columns:1fr}.panel{display:none}.hint{display:none}}
</style></head><body>''')
html.append('''<div class="topbar"><div class="brand">Data Agent Explore · 完整方案</div><div class="hint">滚轮缩放 · 拖动画布 · 点击节点查看职责</div><button class="btn" id="zoomIn">＋</button><button class="btn" id="zoomOut">－</button><button class="btn" id="reset">重置</button><button class="btn" id="theme">主题</button><button class="btn" id="saveSvg">SVG</button><button class="btn" id="savePng">PNG</button></div>''')
html.append('<div class="workspace"><main id="viewport"><div id="stage">')
html.append(svg_text)
html.append('</div></main>')
html.append('''<aside class="panel"><h2 id="detailTitle">方案阅读指南</h2><div class="status" id="detailStatus">完整端到端视图</div><p id="detailBody">从左到右、按 01→04 阅读。橙色表示外部解析责任，蓝色表示 Enterprise Data Context，绿色表示版本存储与读取，紫色表示 Explore、候选和治理。</p><h3>关键边界</h3><ul><li><code>Template JSON</code> 五类结构与目录是唯一跨团队契约。</li><li><code>ContextFragment</code> 仅是下游内部 IR。</li><li>下游不重开原始 Word / Excel。</li><li>Rich Context Page 是 LLM 信息单元。</li><li>Context Bundle 是 Explore 主输出。</li><li>Backend Graph 只面向机器。</li></ul><h3>快捷键</h3><p><span class="kbd">+</span> / <span class="kbd">-</span> 缩放，<span class="kbd">0</span> 重置。</p></aside></div>''')
html.append('''<script>
const viewport=document.getElementById('viewport'),stage=document.getElementById('stage'),svg=document.getElementById('architecture-svg');let scale=.72,tx=24,ty=20,drag=false,lastX=0,lastY=0;
function render(){stage.style.transform=`translate(${tx}px,${ty}px) scale(${scale})`}
function zoom(f,cx=viewport.clientWidth/2,cy=viewport.clientHeight/2){const old=scale;scale=Math.max(.25,Math.min(2.4,scale*f));tx=cx-(cx-tx)*(scale/old);ty=cy-(cy-ty)*(scale/old);render()}
function reset(){scale=Math.min((viewport.clientWidth-40)/1800,(viewport.clientHeight-40)/1450);tx=Math.max(20,(viewport.clientWidth-1800*scale)/2);ty=20;render()}
viewport.addEventListener('wheel',e=>{e.preventDefault();const r=viewport.getBoundingClientRect();zoom(e.deltaY<0?1.12:.89,e.clientX-r.left,e.clientY-r.top)},{passive:false});
viewport.addEventListener('pointerdown',e=>{if(e.target.closest('.node'))return;drag=true;lastX=e.clientX;lastY=e.clientY;viewport.classList.add('dragging');viewport.setPointerCapture(e.pointerId)});
viewport.addEventListener('pointermove',e=>{if(!drag)return;tx+=e.clientX-lastX;ty+=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;render()});viewport.addEventListener('pointerup',()=>{drag=false;viewport.classList.remove('dragging')});
document.getElementById('zoomIn').onclick=()=>zoom(1.18);document.getElementById('zoomOut').onclick=()=>zoom(.84);document.getElementById('reset').onclick=reset;document.getElementById('theme').onclick=()=>document.body.classList.toggle('dark');
document.querySelectorAll('.node').forEach(n=>n.addEventListener('click',()=>{document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected'));n.classList.add('selected');document.getElementById('detailTitle').textContent=n.dataset.title;document.getElementById('detailBody').textContent=n.dataset.detail;document.getElementById('detailStatus').textContent=n.querySelector('.status')?.textContent||'架构组件'}));
function download(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}
document.getElementById('saveSvg').onclick=()=>download(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}),'data-agent-explore-complete.svg');
document.getElementById('savePng').onclick=()=>{const src=new XMLSerializer().serializeToString(svg),blob=new Blob([src],{type:'image/svg+xml'}),url=URL.createObjectURL(blob),img=new Image();img.onload=()=>{const c=document.createElement('canvas');c.width=2700;c.height=2175;const ctx=c.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(url);c.toBlob(b=>download(b,'data-agent-explore-complete.png'),'image/png')};img.src=url};
window.addEventListener('keydown',e=>{if(e.key==='+')zoom(1.18);if(e.key==='-')zoom(.84);if(e.key==='0')reset()});window.addEventListener('resize',reset);reset();
</script></body></html>''')
HTML_PATH.write_text("\n".join(html), encoding="utf-8")
print(SVG_PATH)
print(HTML_PATH)
