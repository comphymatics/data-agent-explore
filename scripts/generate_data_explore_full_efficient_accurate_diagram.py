from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture"
BASE = "data-explore-full-efficient-accurate"
SVG_PATH = OUT / f"{BASE}.svg"
HTML_PATH = OUT / f"{BASE}.html"

svg = []


def add(line=""):
    svg.append(line)


def text(x, y, value, css="body", anchor="start"):
    add(f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{escape(value)}</text>')


def lane(number, y, height, title_value, subtitle, fill, stroke, badge):
    add(f'<g data-graph-role="container" id="lane-{number}">')
    add(f'<rect x="40" y="{y}" width="1720" height="{height}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="1.5" stroke-dasharray="7 5"/>')
    text(64, y + 30, f"{number}  {title_value}", "lane-title")
    text(64, y + 52, subtitle, "lane-sub")
    badge_width = max(170, len(badge) * 13)
    add(f'<rect x="{1728-badge_width}" y="{y+16}" width="{badge_width}" height="28" rx="14" fill="#ffffff" fill-opacity=".85" stroke="{stroke}"/>')
    text(1728 - badge_width / 2, y + 35, badge, "lane-badge", "middle")
    add('</g>')


def principle(pid, x, title_value, role, description, fill, stroke, badge):
    add(f'<g id="principle-{pid}" class="principle-card" data-principle="{pid}" tabindex="0">')
    add(f'<rect x="{x}" y="105" width="540" height="112" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    add(f'<circle cx="{x+42}" cy="142" r="22" fill="{stroke}"/>')
    text(x + 42, 150, badge, "principle-mark", "middle")
    text(x + 78, 137, title_value, "principle-title")
    text(x + 78, 158, role, "principle-role")
    text(x + 24, 194, description, "principle-body")
    add('</g>')


def node(node_id, x, y, width, height, title_value, details, fill="#ffffff", stroke="#d1d5db", status=None, principles="", dashed=False):
    detail = "；".join(details)
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    add(f'<g id="{node_id}" class="node" data-graph-role="node" data-title="{escape(title_value)}" data-detail="{escape(detail)}" data-principles="{principles}" tabindex="0">')
    add(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>')
    if status:
        status_width = max(54, len(status) * 12)
        add(f'<rect x="{x+width-status_width-10}" y="{y+10}" width="{status_width}" height="22" rx="11" fill="#ffffff" fill-opacity=".9" stroke="{stroke}"/>')
        text(x + width - status_width / 2 - 10, y + 25, status, "status", "middle")
    text(x + 18, y + 32, title_value, "node-title")
    start = y + 58
    for index, line in enumerate(details):
        text(x + 18, start + index * 20, line, "node-sub")
    add('</g>')


def edge(edge_id, source, target, path, label, color="#2563eb", marker="arrow-blue", dashed=False, label_x=None, label_y=None, width=2.3):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    add(f'<g id="{edge_id}" data-graph-role="edge" data-source="{source}" data-target="{target}">')
    add(f'<path d="{path}" class="edge" stroke="{color}" stroke-width="{width}" marker-end="url(#{marker})"{dash}/>')
    if label and label_x is not None and label_y is not None:
        badge_width = max(58, len(label) * 12)
        add(f'<rect x="{label_x-badge_width/2}" y="{label_y-16}" width="{badge_width}" height="21" rx="10" fill="#ffffff" fill-opacity=".96" stroke="{color}" stroke-opacity=".25"/>')
        text(label_x, label_y - 2, label, "edge-label", "middle")
    add('</g>')


add('<?xml version="1.0" encoding="UTF-8"?>')
add('<svg id="architecture-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 1660" width="1800" height="1660" role="img" aria-labelledby="diagram-title diagram-desc">')
add('<title id="diagram-title">Data Explore 技术方案：全、省、准</title>')
add('<desc id="diagram-desc">以全、省、准为一级原则，展示外部解析交接、企业数据上下文编译、版本化 Context Serving，以及面向 Main Agent 的 Explore SubAgent。</desc>')
add('<style>')
add("text { font-family: 'Helvetica Neue', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', 'Microsoft JhengHei', SimHei, sans-serif; }")
add('.title { font-size:30px;font-weight:700;fill:#111827 }.subtitle{font-size:14px;fill:#6b7280}')
add('.principle-title{font-size:19px;font-weight:700;fill:#111827}.principle-role{font-size:12px;font-weight:700;fill:#4b5563}.principle-body{font-size:12px;fill:#4b5563}.principle-mark{font-size:22px;font-weight:800;fill:#fff}')
add('.lane-title{font-size:16px;font-weight:700;fill:#111827}.lane-sub{font-size:12px;fill:#6b7280}.lane-badge{font-size:11px;font-weight:700;fill:#374151}')
add('.node-title{font-size:16px;font-weight:700;fill:#111827}.node-sub{font-size:12px;fill:#4b5563}.status{font-size:11px;font-weight:700;fill:#374151}.edge-label{font-size:11px;font-weight:700;fill:#374151}')
add('.legend{font-size:12px;fill:#4b5563}.note-title{font-size:13px;font-weight:700;fill:#111827}.note{font-size:12px;fill:#4b5563}')
add('.edge{fill:none;stroke-linecap:round;stroke-linejoin:round}.node{cursor:pointer;transition:opacity .18s}.node:hover rect:first-child,.node:focus rect:first-child{stroke-width:3}.node.dim{opacity:.16}.principle-card{cursor:pointer}')
add('</style>')
add('<defs>')
for marker_id, color in (("arrow-blue", "#2563eb"), ("arrow-green", "#16a34a"), ("arrow-purple", "#9333ea"), ("arrow-orange", "#ea580c"), ("arrow-gray", "#6b7280")):
    add(f'<marker id="{marker_id}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="{color}"/></marker>')
add('</defs>')
add('<rect class="canvas-bg" width="1800" height="1660" fill="#ffffff"/>')

text(48, 48, "Data Explore 技术方案 · 全 / 省 / 准", "title")
text(48, 76, "Explore 是面向 Main Agent 的只读 SubAgent；MCP 是访问 Enterprise Data Context 的稳定协议。", "subtitle")

principle("full", 40, "全 · Query-relative Coverage", "任务目标", "所需上下文覆盖完整；证据不足或材料缺失必须显式返回", "#eff6ff", "#3b82f6", "全")
principle("efficient", 630, "省 · Bounded Context Cost", "优化目标", "少 Tool Call、少重复 Page、少 Token；优先少量 Rich Reads", "#f0fdf4", "#22c55e", "省")
principle("accurate", 1220, "准 · Evidence-governed", "硬约束", "事实可定位、可解释、可重放；候选与冲突不能冒充事实", "#faf5ff", "#8b5cf6", "准")

lane("01", 250, 240, "INPUT & PARSER DELIVERY", "真实材料只在外部解析侧打开；五类 Template JSON 结构与目录是唯一跨团队正式边界", "#fff7ed", "#fdba74", "外部 Parser / 稳定契约")
lane("02", 520, 290, "ENTERPRISE DATA CONTEXT COMPILE", "Canonical Resolution 先于多来源 Fusion；Graph 面向机器，Rich Context Page 面向 LLM", "#eff6ff", "#93c5fd", "确定性编译 / 事实治理")
lane("03", 840, 280, "GOVERNED CONTEXT SERVING", "不可变版本发布后重建 Page/Element Index、Backrefs 与 Machine Graph；MCP/HTTP 仅是传输适配", "#f0fdf4", "#86efac", "IndexVersion / 可重放")
lane("04", 1150, 380, "ONLINE EXPLORE SUBAGENT", "Main Agent 只接收 Context Bundle；Explore 负责 Policy、Coverage、Focused Expansion 与显式 Exploration State", "#f5f3ff", "#c4b5fd", "只读 SubAgent / 无 SQL 生成")

# Cross-layer containers in the runtime lane.
add('<g data-graph-role="container" id="explore-subagent-boundary">')
add('<rect x="330" y="1215" width="1140" height="280" rx="14" fill="#ffffff" fill-opacity=".35" stroke="#8b5cf6" stroke-width="1.5" stroke-dasharray="8 5"/>')
add('<rect x="352" y="1199" width="196" height="26" rx="13" fill="#ede9fe" stroke="#c4b5fd"/>')
text(450, 1217, "Explore SubAgent · Logical Boundary", "lane-badge", "middle")
add('</g>')

# Arrows are drawn before nodes so connectors never cover component text.
# Lane 01.
edge("e-source-parser", "source-materials", "external-parser", "M 320 392 L 390 392", "raw", label_x=355, label_y=374)
edge("e-parser-fragment", "external-parser", "fragment-contract", "M 660 392 L 740 392", "JSON 目录", label_x=700, label_y=374)
edge("e-fragment-gate", "fragment-contract", "contract-gate", "M 1030 392 L 1110 392", "schema", color="#16a34a", marker="arrow-green", label_x=1070, label_y=374)
edge("e-gate-compiler", "contract-gate", "downstream-compiler", "M 1360 392 L 1440 392", "batch", label_x=1400, label_y=374)
edge("e-compiler-canonical", "downstream-compiler", "canonical", "M 1580 455 L 1580 610", "Internal IR", label_x=1633, label_y=532)

# Lane 02: right to left, with explicit numbered stages.
edge("e-canonical-fusion", "canonical", "fusion", "M 1430 667 L 1360 667", "identity", label_x=1395, label_y=649)
edge("e-fusion-mapping", "fusion", "mapping-refs", "M 1080 667 L 1000 667", "sections", label_x=1040, label_y=649)
edge("e-mapping-pages", "mapping-refs", "rich-pages", "M 680 667 L 590 667", "Page IR", label_x=635, label_y=649)
edge("e-fusion-candidates", "fusion", "candidate-governance", "M 1220 725 L 1220 745", "", color="#9333ea", marker="arrow-purple", dashed=True, width=1.8)
edge("e-pages-quality", "rich-pages", "quality-gate", "M 410 725 L 410 925", "materialize", color="#16a34a", marker="arrow-green", label_x=466, label_y=825)

# Lane 03.
edge("e-quality-snapshot", "quality-gate", "immutable-snapshot", "M 590 985 L 660 985", "publish", color="#16a34a", marker="arrow-green", label_x=625, label_y=967)
edge("e-snapshot-runtime", "immutable-snapshot", "pinned-runtime", "M 980 985 L 1050 985", "pinned", color="#16a34a", marker="arrow-green", label_x=1015, label_y=967)
edge("e-runtime-serving", "pinned-runtime", "context-serving", "M 1370 985 L 1440 985", "serve", color="#16a34a", marker="arrow-green", label_x=1405, label_y=967)
edge("e-candidate-quality", "candidate-governance", "quality-gate", "M 1220 795 L 1220 885 L 610 885 L 610 985 L 590 985", "review", color="#9333ea", marker="arrow-purple", dashed=True, label_x=915, label_y=875, width=1.8)

# MCP request and result corridors between runtime and serving.
edge("e-explore-serving", "anchor-search", "context-serving", "M 750 1280 L 750 1128 L 1510 1128 L 1510 1045", "MCP calls", label_x=1180, label_y=1118)
edge("e-serving-explore", "context-serving", "bundle-assembly", "M 1580 1045 L 1580 1145 L 1040 1145 L 1040 1265", "Rich Page / Evidence", color="#16a34a", marker="arrow-green", label_x=1310, label_y=1165)

# Lane 04 agent flow.
edge("e-main-router", "main-agent", "intent-policy", "M 280 1332 L 370 1332", "invoke", label_x=325, label_y=1314)
edge("e-router-anchor", "intent-policy", "anchor-search", "M 590 1332 L 640 1332", "policy", label_x=615, label_y=1314)
edge("e-anchor-assembly", "anchor-search", "bundle-assembly", "M 860 1332 L 910 1332", "anchors", label_x=885, label_y=1314)
edge("e-assembly-coverage", "bundle-assembly", "coverage-check", "M 1170 1332 L 1220 1332", "bundle", color="#9333ea", marker="arrow-purple", label_x=1195, label_y=1314)
edge("e-coverage-output", "coverage-check", "context-bundle", "M 1430 1332 L 1510 1332", "enough", color="#9333ea", marker="arrow-purple", label_x=1470, label_y=1314)
edge("e-coverage-focus", "coverage-check", "focused-expand", "M 1260 1385 L 1260 1398 L 1195 1398 L 1195 1441 L 1170 1441", "missing", color="#9333ea", marker="arrow-purple", dashed=True, label_x=1218, label_y=1388, width=1.8)
edge("e-focus-assembly", "focused-expand", "bundle-assembly", "M 1040 1408 L 1040 1390", "retry", color="#9333ea", marker="arrow-purple", dashed=True, label_x=1080, label_y=1408, width=1.8)
edge("e-env-assembly", "environment-binding", "bundle-assembly", "M 860 1441 L 885 1441 L 885 1380 L 910 1380", "", color="#ea580c", marker="arrow-orange", dashed=True, width=1.8)
edge("e-coverage-state", "coverage-check", "exploration-state", "M 1325 1385 L 1325 1408", "", color="#9333ea", marker="arrow-purple", dashed=True, width=1.8)
edge("e-state-main", "exploration-state", "main-agent", "M 1220 1441 L 1180 1441 L 1180 1510 L 170 1510 L 170 1385", "resume next round", color="#9333ea", marker="arrow-purple", dashed=True, label_x=675, label_y=1499, width=1.8)

# Nodes lane 01.
node("source-materials", 70, 340, 250, 105, "企业材料与语义参考", ["Word / Excel / JSON / SQL", "SID / 标准 / 全局模型声明"], "#ffffff", "#fb923c", "原始输入", "full accurate", True)
node("external-parser", 390, 330, 270, 125, "外部解析与抽取", ["确定性结构解析 → Document IR", "规则优先；可选 LLM 语义辅助", "真实材料仅解析团队可访问"], "#fff7ed", "#fb923c", "同事负责", "accurate", True)
node("fragment-contract", 740, 330, 290, 125, "Template JSON 交付契约", ["五类 JSON 结构 / 批次目录", "template-input.schema.json", "Schema 文件不入事实库"], "#f0fdfa", "#2dd4bf", "唯一边界", "full accurate")
node("contract-gate", 1110, 340, 250, 105, "Template Contract Gate", ["逐文件 Union Schema 校验", "拒绝缺字段与错误结构"], "#eff6ff", "#60a5fa", "已实现", "accurate")
node("downstream-compiler", 1440, 330, 290, 125, "Template Adapter + Compiler", ["compile_template_inputs(path)", "Shape → 内部 ContextFragment IR", "不重开原始 Word / Excel"], "#eff6ff", "#60a5fa", "已实现", "accurate")

# Nodes lane 02.
node("rich-pages", 230, 610, 360, 115, "④ Rich Context Page", ["L0 定位摘要 / L1 局部推理", "L2 sections / refs / Evidence", "Primary LLM-facing information unit"], "#eff6ff", "#3b82f6", "LLM 单元", "full efficient accurate")
node("mapping-refs", 680, 610, 320, 115, "③ Mapping & References", ["Physical/Field → Object/Attribute", "Typed References → Backrefs", "环境适配不在全局编译发生"], "#ffffff", "#60a5fa", "策略驱动", "full accurate")
node("fusion", 1080, 610, 280, 115, "② Section-level Fusion", ["来源权威策略 + list union", "保留 kept / discarded 冲突", "缺失不等于不存在"], "#ffffff", "#60a5fa", "确定性", "full accurate")
node("canonical", 1430, 610, 300, 115, "① Canonical Resolution", ["identity_hints → exact → aliases", "UNCERTAIN 保持分离", "先 Resolution，后多来源 Fusion"], "#ffffff", "#60a5fa", "确定性", "accurate")
node("candidate-governance", 1080, 745, 280, 50, "Candidates / Conflicts · 独立保存", [], "#faf5ff", "#c084fc", None, "accurate")

# Nodes lane 03.
node("quality-gate", 230, 925, 360, 120, "Quality & Golden Gate", ["Evidence / path / ref 检查", "Golden Context Recall / Coverage", "候选不得进入正式索引"], "#ffffff", "#4ade80", "准入治理", "full accurate")
node("immutable-snapshot", 660, 925, 320, 120, "Immutable Context Snapshot", ["fragments / contexts / pages", "quality.json + manifest.json", "content hash → IndexVersion"], "#f0fdf4", "#22c55e", "不可变", "accurate")
node("pinned-runtime", 1050, 925, 320, 120, "Pinned Runtime View", ["Rich Pages + Page/Element Index", "Machine Graph + Backrefs", "固定 IndexVersion，可重放"], "#f0fdf4", "#4ade80", "可复现", "efficient accurate")
node("context-serving", 1440, 925, 290, 120, "Context Serving · MCP", ["data_search / data_read", "data_expand / data_source", "平台中立；MCP / HTTP adapter"], "#eff6ff", "#60a5fa", "4 个只读工具", "efficient accurate")

# Nodes lane 04.
node("main-agent", 60, 1280, 220, 105, "Main Agent / User", ["提交探索问题", "接收并复用 Context Bundle"], "#ffffff", "#a78bfa", "调用方", "full efficient accurate")
node("intent-policy", 370, 1280, 220, 105, "Intent + Context Policy", ["范围 / 意图 / required coverage", "准是门槛；全是任务目标"], "#faf5ff", "#8b5cf6", "全", "full accurate")
node("anchor-search", 640, 1280, 220, 105, "Anchor Search", ["Fast: inline L0 / L1", "Managed: Top-N anchor pages"], "#ffffff", "#8b5cf6", "省", "efficient")
node("bundle-assembly", 910, 1265, 260, 125, "Managed Bundle Assembly", ["Typed expansion + rerank", "Dedup / Diversity / Novelty", "Token-budget hydration"], "#faf5ff", "#8b5cf6", "省", "full efficient accurate")
node("coverage-check", 1220, 1280, 210, 105, "Coverage Check", ["required coverage satisfied?", "不足则 Focused Expansion"], "#ffffff", "#8b5cf6", "全", "full accurate")
node("environment-binding", 640, 1408, 220, 67, "Environment Binding", ["requirements ⇄ matched assets"], "#fff7ed", "#fb923c", None, "full accurate", True)
node("focused-expand", 910, 1408, 260, 67, "Focused Expansion", ["只补缺失且未看过的 Context"], "#faf5ff", "#8b5cf6", None, "full efficient")
node("exploration-state", 1220, 1408, 210, 67, "Exploration State", ["seen IDs / anchors / budget / version"], "#faf5ff", "#8b5cf6", None, "efficient accurate", True)
node("context-bundle", 1510, 1270, 230, 125, "Context Bundle", ["coverage / missing / budget", "sources / conflicts / candidates", "warnings / truncated / IndexVersion"], "#faf5ff", "#8b5cf6", "主输出", "full efficient accurate")

# Footer.
add('<path data-graph-role="decoration" d="M54 1550 H1746 Q1760 1550 1760 1564 V1626 Q1760 1640 1746 1640 H54 Q40 1640 40 1626 V1564 Q40 1550 54 1550Z" fill="#f9fafb" stroke="#e5e7eb"/>')
text(64, 1578, "原则约束", "note-title")
text(140, 1578, "准是硬约束；全是 Query-dependent 任务目标；省是在前两者满足后最小化读取、跳转与 Token。", "note")
text(64, 1608, "职责边界", "note-title")
text(140, 1608, "Explore 是逻辑 SubAgent；MCP 是协议；Context Engine 不回答问题，Main Agent 不直接遍历 Backend Graph。", "note")
text(64, 1632, "状态边界", "note-title")
text(140, 1632, "每轮显式返回 Context Bundle + Exploration State；不依赖 SubAgent session memory。", "note")
add('</svg>')

OUT.mkdir(parents=True, exist_ok=True)
svg_text = "\n".join(svg)
SVG_PATH.write_text(svg_text, encoding="utf-8")

html = []
html.append('<!doctype html>')
html.append('<html lang="zh-CN"><head><meta charset="utf-8"/>')
html.append('<meta name="viewport" content="width=device-width,initial-scale=1"/>')
html.append('<title>Data Explore 技术方案 · 全 / 省 / 准</title>')
html.append('''<style>
:root{color-scheme:light;--bg:#f3f4f6;--panel:#fff;--text:#111827;--muted:#6b7280;--border:#d1d5db;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
body.dark{--bg:#111827;--panel:#1f2937;--text:#f9fafb;--muted:#d1d5db;--border:#4b5563;--accent:#60a5fa;color-scheme:dark}
.topbar{height:58px;display:flex;align-items:center;gap:8px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--border);position:relative;z-index:5}
.brand{font-weight:700;margin-right:auto}.hint{font-size:12px;color:var(--muted);margin-right:8px}.btn{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:7px 11px;cursor:pointer}.btn:hover,.btn.active{border-color:var(--accent);color:var(--accent)}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 330px;height:calc(100vh - 58px)}
#viewport{position:relative;overflow:hidden;background:radial-gradient(circle at 1px 1px,#d1d5db 1px,transparent 0);background-size:20px 20px;cursor:grab}.dark #viewport{background-image:radial-gradient(circle at 1px 1px,#374151 1px,transparent 0)}#viewport.dragging{cursor:grabbing}
#stage{position:absolute;left:24px;top:20px;transform-origin:0 0;will-change:transform;filter:drop-shadow(0 12px 24px rgba(15,23,42,.12))}#stage svg{display:block;width:1440px;height:auto;background:white;border-radius:8px}
.panel{background:var(--panel);border-left:1px solid var(--border);padding:20px;overflow:auto}.panel h2{font-size:18px;margin:0 0 8px}.panel h3{font-size:14px;margin:24px 0 8px}.panel p,.panel li{font-size:13px;line-height:1.65;color:var(--muted)}.panel code{font-size:12px;color:var(--text)}
.status-pill{display:inline-flex;border:1px solid var(--border);border-radius:999px;padding:3px 8px;font-size:11px;margin-top:8px}.kbd{border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:1px 5px;font-size:11px}.selected rect:first-child{stroke:#2563eb!important;stroke-width:4!important}
@media(max-width:900px){.workspace{grid-template-columns:1fr}.panel{display:none}.hint{display:none}}
</style></head><body>''')
html.append('''<div class="topbar"><div class="brand">Data Explore · 全 / 省 / 准</div><div class="hint">点击原则高亮 · 点击节点查看职责</div><button class="btn principle-filter" data-principle="full">全</button><button class="btn principle-filter" data-principle="efficient">省</button><button class="btn principle-filter" data-principle="accurate">准</button><button class="btn" id="clearFilter">全部</button><button class="btn" id="zoomIn">＋</button><button class="btn" id="zoomOut">－</button><button class="btn" id="reset">重置</button><button class="btn" id="theme">主题</button><button class="btn" id="saveSvg">SVG</button><button class="btn" id="savePng">PNG</button></div>''')
html.append('<div class="workspace"><main id="viewport"><div id="stage">')
html.append(svg_text)
html.append('</div></main>')
html.append('''<aside class="panel"><h2 id="detailTitle">方案阅读指南</h2><div class="status-pill" id="detailStatus">融合优化版</div><p id="detailBody">顶部是全、省、准一级原则；按 01→04 阅读外部交付、Context 编译、版本化 Serving 和 Explore SubAgent。点击原则可高亮它所约束的组件。</p><h3>三个原则</h3><ul><li><b>全</b>：问题所需上下文完整，缺失显式。</li><li><b>省</b>：少跳转、少重复、预算内 hydration。</li><li><b>准</b>：Evidence 治理、冲突保留、版本可重放。</li></ul><h3>关键边界</h3><ul><li><code>Template JSON</code> 五类结构与目录是唯一解析交付契约。</li><li><code>ContextFragment</code> 仅是下游内部 IR。</li><li>Explore 是逻辑 SubAgent，MCP 是协议。</li><li>Graph 面向机器，Rich Page 面向 LLM。</li><li>Context Bundle 是主输出。</li></ul><h3>快捷键</h3><p><span class="kbd">+</span> / <span class="kbd">-</span> 缩放，<span class="kbd">0</span> 重置。</p></aside></div>''')
html.append('''<script>
const viewport=document.getElementById('viewport'),stage=document.getElementById('stage'),svg=document.getElementById('architecture-svg');let scale=.72,tx=24,ty=20,drag=false,lastX=0,lastY=0;
function render(){stage.style.transform=`translate(${tx}px,${ty}px) scale(${scale})`}
function zoom(f,cx=viewport.clientWidth/2,cy=viewport.clientHeight/2){const old=scale;scale=Math.max(.22,Math.min(2.4,scale*f));tx=cx-(cx-tx)*(scale/old);ty=cy-(cy-ty)*(scale/old);render()}
function reset(){scale=Math.min((viewport.clientWidth-40)/1800,(viewport.clientHeight-40)/1660);tx=Math.max(20,(viewport.clientWidth-1800*scale)/2);ty=20;render()}
viewport.addEventListener('wheel',e=>{e.preventDefault();const r=viewport.getBoundingClientRect();zoom(e.deltaY<0?1.12:.89,e.clientX-r.left,e.clientY-r.top)},{passive:false});
viewport.addEventListener('pointerdown',e=>{if(e.target.closest('.node,.principle-card'))return;drag=true;lastX=e.clientX;lastY=e.clientY;viewport.classList.add('dragging');viewport.setPointerCapture(e.pointerId)});
viewport.addEventListener('pointermove',e=>{if(!drag)return;tx+=e.clientX-lastX;ty+=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;render()});viewport.addEventListener('pointerup',()=>{drag=false;viewport.classList.remove('dragging')});
document.getElementById('zoomIn').onclick=()=>zoom(1.18);document.getElementById('zoomOut').onclick=()=>zoom(.84);document.getElementById('reset').onclick=reset;document.getElementById('theme').onclick=()=>document.body.classList.toggle('dark');
function filterPrinciple(p){document.querySelectorAll('.node').forEach(n=>n.classList.toggle('dim',!n.dataset.principles.split(' ').includes(p)));document.querySelectorAll('.principle-filter').forEach(b=>b.classList.toggle('active',b.dataset.principle===p))}
document.querySelectorAll('.principle-filter').forEach(b=>b.onclick=()=>filterPrinciple(b.dataset.principle));document.querySelectorAll('.principle-card').forEach(c=>c.addEventListener('click',()=>filterPrinciple(c.dataset.principle)));document.getElementById('clearFilter').onclick=()=>{document.querySelectorAll('.node').forEach(n=>n.classList.remove('dim'));document.querySelectorAll('.principle-filter').forEach(b=>b.classList.remove('active'))};
document.querySelectorAll('.node').forEach(n=>n.addEventListener('click',()=>{document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected'));n.classList.add('selected');document.getElementById('detailTitle').textContent=n.dataset.title;document.getElementById('detailBody').textContent=n.dataset.detail;document.getElementById('detailStatus').textContent=n.querySelector('.status')?.textContent||'架构组件'}));
function download(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}
document.getElementById('saveSvg').onclick=()=>download(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}),'data-explore-full-efficient-accurate.svg');
document.getElementById('savePng').onclick=()=>{const src=new XMLSerializer().serializeToString(svg),blob=new Blob([src],{type:'image/svg+xml'}),url=URL.createObjectURL(blob),img=new Image();img.onload=()=>{const c=document.createElement('canvas');c.width=3600;c.height=3320;const ctx=c.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(url);c.toBlob(b=>download(b,'data-explore-full-efficient-accurate.png'),'image/png')};img.src=url};
window.addEventListener('keydown',e=>{if(e.key==='+')zoom(1.18);if(e.key==='-')zoom(.84);if(e.key==='0')reset()});window.addEventListener('resize',reset);reset();
</script></body></html>''')
HTML_PATH.write_text("\n".join(html), encoding="utf-8")

print(SVG_PATH)
print(HTML_PATH)
