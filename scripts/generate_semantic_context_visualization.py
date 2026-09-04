#!/usr/bin/env python3
"""Generate a dependency-free semantic context browser from a saved snapshot."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from html import escape
import json
from pathlib import Path

from enterprise_data_context.persistence import load_compiled


def build_payload(compiled: dict) -> dict:
    contexts = {context.path: context for context in compiled["contexts"]}
    pages = []
    for page in compiled["pages"]:
        row = asdict(page)
        context = contexts.get(page.path)
        evidence = []
        if context:
            for section, records in context.evidence.items():
                for record in records:
                    evidence.append({
                        "section": section,
                        "source_id": record.source.source_id,
                        "path": record.source.path,
                        "sheet": record.source.sheet,
                        "source_section": record.source.section,
                        "table": record.source.table,
                        "row": record.source.row,
                        "column": record.source.column,
                        "cell": record.source.cell,
                        "note": record.note,
                    })
        row["evidence"] = evidence
        pages.append(row)

    hierarchy = compiled["hierarchy"]
    hierarchy_edges = [
        edge
        for parent_edges in hierarchy.children.values()
        for edge in parent_edges
    ]
    return {
        "manifest": compiled.get("manifest", {}),
        "association_report": compiled.get("association_report", {}),
        "coverage_declaration": compiled.get("coverage_declaration", {}),
        "inference_runs": compiled.get("inference_runs", []),
        "quality_issues": compiled.get("quality_issues", []),
        "pages": pages,
        "hierarchy": {
            "nodes": list(hierarchy.nodes.values()),
            "edges": hierarchy_edges,
        },
    }


def render_html(payload: dict, title: str) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__TITLE__", escape(title)).replace("__SNAPSHOT_JSON__", serialized)


def generate(snapshot: Path, output: Path, title: str) -> dict:
    compiled = load_compiled(snapshot)
    payload = build_payload(compiled)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(payload, title), encoding="utf-8")
    return {
        "output": str(output),
        "index_version": compiled.get("index_version"),
        "pages": len(payload["pages"]),
        "hierarchy_nodes": len(payload["hierarchy"]["nodes"]),
        "hierarchy_edges": len(payload["hierarchy"]["edges"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an offline hierarchy + association visualization"
    )
    parser.add_argument("--snapshot", default="generated", help="Snapshot root or version directory")
    parser.add_argument(
        "--output",
        default="docs/architecture/template-semantic-browser.html",
        help="Single-file HTML output",
    )
    parser.add_argument("--title", default="Template 语义上下文浏览器")
    args = parser.parse_args()
    result = generate(Path(args.snapshot), Path(args.output), args.title)
    print(json.dumps(result, ensure_ascii=False, indent=2))


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>__TITLE__</title>
<style>
:root{--bg:#f3f4f6;--panel:#fff;--text:#111827;--muted:#6b7280;--line:#d1d5db;--blue:#2563eb;--green:#16a34a;--orange:#ea580c;--purple:#9333ea;--red:#dc2626;--teal:#0f766e;--shadow:0 10px 30px rgba(15,23,42,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
button,input{font:inherit}.topbar{height:64px;display:flex;align-items:center;gap:10px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--line);position:relative;z-index:4}.brand{min-width:265px}.brand strong{display:block;font-size:16px}.brand span{display:block;color:var(--muted);font-size:11px;margin-top:3px}.search{flex:1;max-width:680px;position:relative}.search input{width:100%;height:38px;border:1px solid var(--line);border-radius:9px;padding:0 38px 0 12px;color:var(--text);background:#fff;outline:none}.search input:focus{border-color:var(--blue);box-shadow:0 0 0 3px #dbeafe}.search .key{position:absolute;right:10px;top:9px;color:var(--muted);font-size:11px}.button{border:1px solid var(--line);background:#fff;color:var(--text);border-radius:8px;padding:8px 10px;cursor:pointer}.button:hover{border-color:var(--blue);color:var(--blue)}
.workspace{height:calc(100vh - 64px);display:grid;grid-template-columns:300px minmax(480px,1fr) 390px}.panel{background:var(--panel);overflow:auto}.left{border-right:1px solid var(--line)}.right{border-left:1px solid var(--line)}.panel-head{padding:16px;border-bottom:1px solid #e5e7eb;position:sticky;top:0;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);z-index:2}.panel-head h2{font-size:14px;margin:0}.panel-head p{font-size:11px;line-height:1.5;margin:5px 0 0;color:var(--muted)}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;padding:12px}.stat{border:1px solid #e5e7eb;border-radius:8px;padding:9px}.stat b{display:block;font-size:17px}.stat span{font-size:10px;color:var(--muted)}.tree{padding:2px 8px 24px}.tree-group{margin-top:8px}.tree-title,.tree-item{width:100%;display:flex;align-items:center;gap:7px;border:0;background:transparent;text-align:left;border-radius:7px;cursor:pointer;color:var(--text)}.tree-title{font-weight:700;padding:8px}.tree-item{padding:6px 8px 6px var(--indent,16px);font-size:12px}.tree-item:hover,.tree-item.active{background:#eff6ff;color:#1d4ed8}.tree-item .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.count{margin-left:auto;background:#f3f4f6;color:var(--muted);padding:2px 6px;border-radius:10px;font-size:10px}.dot{width:8px;height:8px;border-radius:50%;flex:none}
.center{position:relative;overflow:hidden;background-color:#fafafa;background-image:radial-gradient(#d1d5db 1px,transparent 1px);background-size:20px 20px}.canvas-head{position:absolute;top:14px;left:14px;right:14px;display:flex;gap:8px;align-items:flex-start;z-index:3;pointer-events:none}.canvas-title{background:rgba(255,255,255,.95);border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;box-shadow:var(--shadow);pointer-events:auto}.canvas-title b{font-size:13px;display:block}.canvas-title span{font-size:10px;color:var(--muted)}.filters{margin-left:auto;background:rgba(255,255,255,.95);border:1px solid #e5e7eb;border-radius:10px;padding:8px;display:flex;gap:5px;box-shadow:var(--shadow);pointer-events:auto}.filter{border:1px solid #e5e7eb;background:#fff;color:var(--muted);border-radius:14px;padding:5px 8px;font-size:10px;cursor:pointer}.filter.on{color:#fff}.filter[data-status=CONFIRMED].on{background:var(--green)}.filter[data-status=UNRESOLVED].on{background:var(--orange)}.filter[data-status=CANDIDATE].on{background:var(--purple)}.filter[data-status=HIERARCHY].on{background:var(--blue)}
#graphViewport{position:absolute;inset:0;overflow:hidden;cursor:grab}#graphViewport.dragging{cursor:grabbing}#graphStage{position:absolute;inset:0;transform-origin:0 0}#graph{width:100%;height:100%;display:block}.edge{fill:none;stroke-linejoin:round;stroke-linecap:round}.edge-label{font-size:10px;font-weight:600;paint-order:stroke;stroke:#fff;stroke-width:5px;stroke-linejoin:round}.node{cursor:pointer}.node rect{stroke-width:1.5}.node:hover rect,.node.selected rect{stroke-width:3}.node-title{font-size:12px;font-weight:700;pointer-events:none}.node-sub{font-size:9.5px;fill:#6b7280;pointer-events:none}.ghost rect{stroke-dasharray:5 3}.legend{position:absolute;left:14px;bottom:14px;display:flex;gap:12px;background:rgba(255,255,255,.95);padding:8px 10px;border:1px solid #e5e7eb;border-radius:9px;font-size:10px;color:var(--muted);z-index:3}.legend i{display:inline-block;width:22px;height:3px;margin-right:5px;vertical-align:middle}.zoom{position:absolute;right:14px;bottom:14px;display:flex;gap:5px;z-index:3}.zoom button{width:34px;height:34px;padding:0;background:#fff;border:1px solid var(--line);border-radius:8px;cursor:pointer}
.detail{padding:16px}.crumb{font-size:11px;color:var(--blue);line-height:1.6;margin-bottom:10px}.type{display:inline-flex;padding:3px 8px;border-radius:12px;background:#eff6ff;color:#1d4ed8;font-size:10px;font-weight:700}.detail h1{font-size:20px;line-height:1.3;margin:8px 0 5px}.path{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);word-break:break-all}.tabs{display:flex;gap:4px;margin:14px 0 12px;border-bottom:1px solid #e5e7eb}.tab{border:0;background:transparent;padding:8px 9px;color:var(--muted);cursor:pointer;font-size:11px}.tab.active{color:var(--blue);border-bottom:2px solid var(--blue);font-weight:700}.section{margin:16px 0}.section h3{font-size:12px;margin:0 0 7px;color:#374151}.summary{font-size:12px;line-height:1.7;color:#374151;white-space:pre-wrap}.kv{display:grid;grid-template-columns:105px 1fr;gap:5px 9px;font-size:11px;line-height:1.55}.kv dt{color:var(--muted)}.kv dd{margin:0;word-break:break-word}.chip{display:inline-block;border:1px solid #e5e7eb;border-radius:12px;padding:3px 7px;margin:2px;font-size:10px;background:#fff}.relation,.evidence,.issue{border:1px solid #e5e7eb;border-radius:8px;padding:9px;margin:7px 0;font-size:11px;line-height:1.5}.relation{cursor:pointer}.relation:hover{border-color:var(--blue)}.relation .status{font-weight:700}.CONFIRMED{color:var(--green)}.UNRESOLVED{color:var(--orange)}.CANDIDATE{color:var(--purple)}.evidence b{display:block;margin-bottom:4px}.source{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);word-break:break-all}.empty{padding:30px 12px;text-align:center;color:var(--muted);font-size:12px}.search-results{position:absolute;left:0;right:0;top:43px;background:#fff;border:1px solid var(--line);border-radius:9px;box-shadow:var(--shadow);max-height:420px;overflow:auto;display:none;z-index:10}.search-results.open{display:block}.result{display:block;width:100%;border:0;border-bottom:1px solid #f3f4f6;background:#fff;text-align:left;padding:10px 12px;cursor:pointer}.result:hover{background:#eff6ff}.result b{font-size:12px}.result span{display:block;font-size:10px;color:var(--muted);margin-top:3px}.notice{margin:10px 12px;padding:9px;border-radius:8px;background:#fff7ed;color:#9a3412;font-size:10px;line-height:1.5}
@media(max-width:1100px){.workspace{grid-template-columns:260px 1fr}.right{position:absolute;right:0;top:64px;bottom:0;width:380px;box-shadow:-12px 0 30px rgba(15,23,42,.14)}.brand{min-width:210px}}@media(max-width:760px){.workspace{grid-template-columns:1fr}.left{display:none}.right{width:min(92vw,390px)}.brand span{display:none}.brand{min-width:auto}.topbar .export{display:none}}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand"><strong>__TITLE__</strong><span id="versionLabel">加载快照…</span></div>
  <div class="search"><input id="searchInput" placeholder="搜索场景、Feature、指标、对象、逻辑/物理模型…" autocomplete="off"/><span class="key">⌘ K</span><div id="searchResults" class="search-results"></div></div>
  <button class="button export" id="exportSvg">导出 SVG</button><button class="button export" id="exportPng">导出 PNG</button>
</header>
<div class="workspace">
  <aside class="panel left"><div class="panel-head"><h2>语义层次</h2><p>浏览投影，不是本体；模型按分层 / 分域 / 主题组织。</p></div><div id="stats" class="stats"></div><div id="coverageNotice"></div><nav id="tree" class="tree"></nav></aside>
  <main class="center">
    <div class="canvas-head"><div class="canvas-title"><b id="focusTitle">一跳关联视图</b><span>选中节点 + 直接关系，避免无边界图遍历</span></div><div class="filters"><button class="filter on" data-status="CONFIRMED">已确认</button><button class="filter" data-status="UNRESOLVED">未解析</button><button class="filter" data-status="CANDIDATE">候选</button><button class="filter on" data-status="HIERARCHY">层次</button></div></div>
    <div id="graphViewport"><div id="graphStage"><svg id="graph" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="选中上下文的一跳关系图"></svg></div></div>
    <div class="legend"><span><i style="background:var(--green)"></i>已确认</span><span><i style="background:var(--orange)"></i>未解析</span><span><i style="background:var(--purple)"></i>候选</span><span><i style="background:var(--blue)"></i>层次</span></div>
    <div class="zoom"><button id="zoomOut">−</button><button id="resetZoom">⌂</button><button id="zoomIn">＋</button></div>
  </main>
  <aside class="panel right"><div class="panel-head"><h2>Rich Context Page</h2><p>面向审阅与 LLM 的主要信息单元，保留 Evidence、候选与冲突。</p></div><div id="detail" class="detail"></div></aside>
</div>
<script id="snapshot-data" type="application/json">__SNAPSHOT_JSON__</script>
<script>
(() => {
const DATA=JSON.parse(document.getElementById('snapshot-data').textContent);
const pages=DATA.pages, pageByPath=new Map(pages.map(p=>[p.path,p]));
const hNodeByPath=new Map(DATA.hierarchy.nodes.map(n=>[n.path,n]));
const hierarchyEdges=DATA.hierarchy.edges;
const incoming=new Map();
pages.forEach(p=>(p.references||[]).forEach(r=>{if(r.target_path){if(!incoming.has(r.target_path))incoming.set(r.target_path,[]);incoming.get(r.target_path).push({...r,source_path:p.path});}}));
const typeLabels={'scenario':'场景','topic':'主题 / 场景组','analysis-purpose':'分析名称','metric':'指标','business-object':'业务对象','dimension':'维度','logical-model':'逻辑模型','physical-model':'物理模型','unknown':'其他'};
const typeColors={'scenario':['#fff7ed','#fb923c'],'topic':['#f0fdfa','#2dd4bf'],'analysis-purpose':['#eff6ff','#60a5fa'],'metric':['#f0fdf4','#4ade80'],'business-object':['#faf5ff','#c084fc'],'dimension':['#f9fafb','#9ca3af'],'logical-model':['#eef2ff','#818cf8'],'physical-model':['#fef2f2','#f87171'],'unknown':['#fff','#9ca3af']};
const statusColors={CONFIRMED:'#16a34a',UNRESOLVED:'#ea580c',CANDIDATE:'#9333ea',HIERARCHY:'#2563eb'};
let selected=chooseInitial(), activeTab='context', enabled=new Set(['CONFIRMED','HIERARCHY']), scale=1, tx=0, ty=0;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=(v,n=28)=>{v=String(v??'').replace(/\s+/g,' ').trim();return v.length>n?v.slice(0,n-1)+'…':v};
const array=v=>Array.isArray(v)?v:(v==null||v===''?[]:[v]);
function chooseInitial(){return pages.find(p=>p.facets?.scenario_kind==='APP_FEATURE')?.path||pages.find(p=>p.context_type==='analysis-purpose')?.path||pages[0]?.path;}
function stats(){const c=DATA.manifest.counts||{},a=DATA.association_report||{},coverage=DATA.coverage_declaration||DATA.manifest.coverage_declaration||{status:'UNKNOWN'},runs=DATA.inference_runs||[];document.getElementById('versionLabel').textContent=`${DATA.manifest.index_version||'未版本化'} · ${coverage.status||'UNKNOWN'} · ${pages.length} Pages`;document.getElementById('stats').innerHTML=[[c.pages||pages.length,'Rich Pages'],[c.hierarchy_nodes||DATA.hierarchy.nodes.length,'层次节点'],[a.references_by_status?.CONFIRMED||0,'确认关系'],[a.references_by_status?.UNRESOLVED||0,'未解析关系'],[a.references_by_status?.CANDIDATE||0,'候选关系'],[runs.length,'LLM 推断批次']].map(([n,l])=>`<div class="stat"><b>${n}</b><span>${l}</span></div>`).join('');const cross=a.cross_source_confirmed_count||0;document.getElementById('coverageNotice').innerHTML=`<div class="notice"><b>覆盖状态：${esc(coverage.status||'UNKNOWN')}</b> · ${esc(coverage.reason||'未声明完整性')}<br>当前快照跨来源确认关系：<b>${cross}</b>。缺失关系不代表不存在，候选不会自动升级为事实。</div>`;}
function group(label,items,hierarchical=false){return {label,items:[...items],hierarchical};}
function orderHierarchy(items){const allowed=new Set(items.map(p=>p.path)),children=new Map(),hasParent=new Set();hierarchyEdges.forEach(e=>{if(allowed.has(e.source)&&allowed.has(e.target)){if(!children.has(e.source))children.set(e.source,[]);children.get(e.source).push(e.target);hasParent.add(e.target)}});const roots=items.filter(p=>!hasParent.has(p.path)).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')),out=[],seen=new Set();function walk(p,depth){if(seen.has(p.path))return;seen.add(p.path);out.push({page:p,depth});(children.get(p.path)||[]).map(x=>pageByPath.get(x)).filter(Boolean).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).forEach(c=>walk(c,depth+1))}roots.forEach(p=>walk(p,0));items.filter(p=>!seen.has(p.path)).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).forEach(p=>walk(p,0));return out;}
function navGroups(){const roles=p=>p.facets?.semantic_role||'';const app=pages.filter(p=>['application','app-feature'].includes(roles(p)));const modeling=pages.filter(p=>['analysis-group','modeling-analysis'].includes(roles(p)));const models=pages.filter(p=>['logical-model','physical-model'].includes(p.context_type));const rest=pages.filter(p=>!app.includes(p)&&!modeling.includes(p)&&!models.includes(p));const modelBuckets=new Map();models.forEach(p=>{const key=[p.l2?.['classification.layer']||'未分层',p.l2?.topic_domain||'未分域',p.l2?.topic||'未归主题'].join(' / ');if(!modelBuckets.has(key))modelBuckets.set(key,[]);modelBuckets.get(key).push(p);});const typeBuckets=rest.reduce((m,p)=>((m[typeLabels[p.context_type]||p.context_type]??=[]).push(p),m),{});return [group('应用与 Feature',app,true),group('建模分析',modeling,true),...Array.from(modelBuckets,([label,items])=>group('模型 · '+label,items,true)),...Object.entries(typeBuckets).map(([label,items])=>group(label,items))].filter(g=>g.items.length);}
function renderTree(){document.getElementById('tree').innerHTML=navGroups().map(g=>{const rows=g.hierarchical?orderHierarchy(g.items):g.items.sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(page=>({page,depth:0}));return `<section class="tree-group"><button class="tree-title"><span>${esc(g.label)}</span><span class="count">${g.items.length}</span></button>${rows.map(({page:p,depth})=>`<button class="tree-item ${p.path===selected?'active':''}" data-path="${esc(p.path)}" style="--indent:${16+depth*16}px"><i class="dot" style="background:${typeColors[p.context_type]?.[1]||'#9ca3af'}"></i><span class="name">${depth?'↳ ':''}${esc(p.name)}</span></button>`).join('')}</section>`}).join('');document.querySelectorAll('.tree-item').forEach(el=>el.onclick=()=>select(el.dataset.path));}
function relationRows(p){const out=(p.references||[]).map(r=>({...r,direction:'out',source_path:p.path}));const inc=(incoming.get(p.path)||[]).map(r=>({...r,direction:'in'}));return [...out,...inc];}
function hierarchyFor(path){return hierarchyEdges.filter(e=>e.source===path||e.target===path).map(e=>({...e,status:'HIERARCHY',direction:e.source===path?'out':'in'}));}
function focused(){const p=pageByPath.get(selected);if(!p)return {nodes:[],edges:[],hidden:0};const rels=relationRows(p).filter(r=>enabled.has(r.status)),hs=enabled.has('HIERARCHY')?hierarchyFor(selected):[];const concrete=[],summaries=[];const confirmed=rels.filter(r=>r.status==='CONFIRMED');concrete.push(...confirmed.slice(0,10));if(confirmed.length>10)summaries.push({status:'CONFIRMED',relation:'更多确认关系',direction:'out',count:confirmed.length-10});for(const status of ['UNRESOLVED','CANDIDATE']){const groups=new Map();rels.filter(r=>r.status===status).forEach(r=>{const key=`${r.direction}:${r.relation}`;if(!groups.has(key))groups.set(key,{status,relation:r.relation,direction:r.direction,count:0});groups.get(key).count++});summaries.push(...groups.values())}const prioritized=[...hs,...concrete,...summaries].slice(0,18),nodes=new Map([[p.path,{path:p.path,page:p,label:p.name,kind:p.context_type}]]),edges=[];prioritized.forEach((r,i)=>{let source=r.source_path||r.source||p.path,target=r.target_path||r.target;if(r.count){const pseudo=`summary://${r.status}/${i}/${encodeURIComponent(r.relation)}`;source=r.direction==='in'?pseudo:p.path;target=r.direction==='in'?p.path:pseudo;r.raw_target=`${r.status==='UNRESOLVED'?'未解析':r.status==='CANDIDATE'?'候选':'其他'} ${r.relation} × ${r.count}`;}if(!target)target=`unresolved://${i}/${encodeURIComponent(r.raw_target||'unknown')}`;const other=source===p.path?target:source;if(!nodes.has(other)){const op=pageByPath.get(other),hn=hNodeByPath.get(other);nodes.set(other,{path:other,page:op,label:op?.name||hn?.name||r.raw_target||other,kind:op?.context_type||hn?.kind||'unknown',ghost:!op&&!hn});}edges.push({source,target,status:r.status,relation:r.count?`${r.relation} × ${r.count}`:(r.relation||r.source_relation||'contains')});});return {nodes:[...nodes.values()],edges,hidden:Math.max(0,rels.length-concrete.length-summaries.reduce((n,r)=>n+r.count,0))};}
function layoutGraph(model,w,h){const center=model.nodes.find(n=>n.path===selected),others=model.nodes.filter(n=>n.path!==selected);const cx=w/2,cy=h/2;const pos=new Map([[center.path,{x:cx,y:cy}]]);if(!others.length)return pos;const rings=others.length>14?2:1;others.forEach((n,i)=>{const ring=rings===2&&i>=14?2:1;const subset=ring===1?Math.min(14,others.length):others.length-14;const local=ring===1?i:i-14;const angle=-Math.PI/2+(2*Math.PI*local/subset);const rx=Math.min(w*(ring===1?.31:.43),ring===1?320:470),ry=Math.min(h*(ring===1?.33:.43),ring===1?230:330);pos.set(n.path,{x:cx+Math.cos(angle)*rx,y:cy+Math.sin(angle)*ry});});return pos;}
function svgEl(name,attrs={},text=''){const e=document.createElementNS('http://www.w3.org/2000/svg',name);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text)e.textContent=text;return e;}
function renderGraph(){const svg=document.getElementById('graph'),box=document.querySelector('.center').getBoundingClientRect(),w=Math.max(600,box.width),h=Math.max(500,box.height);svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.innerHTML='';const defs=svgEl('defs');Object.entries(statusColors).forEach(([s,c])=>{const m=svgEl('marker',{id:'arrow-'+s,markerWidth:10,markerHeight:7,refX:9,refY:3.5,orient:'auto'});m.append(svgEl('polygon',{points:'0 0, 10 3.5, 0 7',fill:c}));defs.append(m);});svg.append(defs);const model=focused(),pos=layoutGraph(model,w,h),pairCounts=new Map(),pairSeen=new Map();model.edges.forEach(e=>{const k=[e.source,e.target].sort().join('|');pairCounts.set(k,(pairCounts.get(k)||0)+1)});model.edges.forEach((e,i)=>{const a=pos.get(e.source),b=pos.get(e.target);if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,len=Math.max(1,Math.hypot(dx,dy)),ux=dx/len,uy=dy/len,key=[e.source,e.target].sort().join('|'),laneIndex=pairSeen.get(key)||0,laneCount=pairCounts.get(key)||1,canonical=e.source<e.target?1:-1,lane=(laneIndex-(laneCount-1)/2)*12,labelLane=(laneIndex-(laneCount-1)/2)*44,px=-uy*canonical,py=ux*canonical;pairSeen.set(key,laneIndex+1);const start={x:a.x+ux*80+px*lane,y:a.y+uy*34+py*lane},end={x:b.x-ux*80+px*lane,y:b.y-uy*34+py*lane},mx=(start.x+end.x)/2+ux*canonical*labelLane,my=(start.y+end.y)/2+uy*canonical*labelLane;const g=svgEl('g',{'data-status':e.status});g.append(svgEl('path',{d:`M ${start.x} ${start.y} L ${end.x} ${end.y}`,class:'edge',stroke:statusColors[e.status]||'#6b7280','stroke-width':e.status==='HIERARCHY'?2.2:1.8,'stroke-dasharray':e.status==='UNRESOLVED'?'6 4':e.status==='CANDIDATE'?'3 3':'','marker-end':`url(#arrow-${e.status})`}));g.append(svgEl('text',{x:mx,y:my-7,'text-anchor':'middle',fill:statusColors[e.status]||'#6b7280',class:'edge-label'},short(e.relation,18)));svg.append(g);});model.nodes.forEach(n=>{const p=pos.get(n.path),colors=typeColors[n.kind]||typeColors.unknown,g=svgEl('g',{class:`node ${n.ghost?'ghost':''} ${n.path===selected?'selected':''}`,transform:`translate(${p.x-80} ${p.y-32})`,'data-path':n.path,tabindex:'0'});g.append(svgEl('rect',{width:160,height:64,rx:9,fill:n.ghost?'#fff7ed':colors[0],stroke:n.ghost?statusColors.UNRESOLVED:colors[1]}));g.append(svgEl('text',{x:80,y:27,'text-anchor':'middle',fill:'#111827',class:'node-title'},short(n.label,19)));g.append(svgEl('text',{x:80,y:46,'text-anchor':'middle',class:'node-sub'},n.ghost?'聚合目标':(typeLabels[n.kind]||n.kind)));if(n.page){g.onclick=()=>select(n.path);g.onkeydown=e=>{if(e.key==='Enter')select(n.path)}}svg.append(g);});document.getElementById('focusTitle').textContent=`${pageByPath.get(selected)?.name||'未选择'} · ${model.nodes.length} 节点 / ${model.edges.length} 可视关系`;}
function fmtValue(v){if(Array.isArray(v))return v.map(x=>typeof x==='object'?JSON.stringify(x, null, 2):String(x)).join('、');if(v&&typeof v==='object')return JSON.stringify(v,null,2);return String(v??'');}
function detailContext(p){const summary=p.l2?.summary||p.l0||'暂无摘要';const entries=Object.entries(p.l2||{}).filter(([k,v])=>!['summary','metric_catalog'].includes(k)&&v!==null&&v!==''&&array(v).length).slice(0,18);return `<section class="section"><h3>业务含义 / 摘要</h3><div class="summary">${esc(summary)}</div></section><section class="section"><h3>结构化上下文</h3><dl class="kv">${entries.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${Array.isArray(v)&&v.every(x=>typeof x!=='object')?v.map(x=>`<span class="chip">${esc(short(x,48))}</span>`).join(''):`<span class="summary">${esc(fmtValue(v))}</span>`}</dd>`).join('')}</dl></section><section class="section"><h3>覆盖</h3>${Object.entries(p.coverage||{}).map(([k,v])=>`<span class="chip">${v?'✓':'–'} ${esc(k)}</span>`).join('')}</section>`;}
function detailRelations(p){const rows=relationRows(p);return rows.length?rows.map(r=>{const target=r.direction==='in'?r.source_path:(r.target_path||'');return `<div class="relation" ${target&&pageByPath.has(target)?`data-target="${esc(target)}"`:''}><span class="status ${esc(r.status)}">${esc(r.status)}</span> · ${r.direction==='in'?'←':'→'} ${esc(r.relation)}<br><b>${esc(short(r.raw_target||pageByPath.get(target)?.name||target,80))}</b>${target?`<div class="source">${esc(target)}</div>`:''}</div>`}).join(''):'<div class="empty">没有引用关系</div>';}
function detailEvidence(p){return p.evidence?.length?p.evidence.map(e=>`<div class="evidence"><b>${esc(e.section)}</b><div>${esc([e.sheet,e.source_section,e.table,e.cell,e.row!=null?'row '+e.row:null].filter(Boolean).join(' · ')||'文件级证据')}</div><div class="source">${esc(e.source_id)} · ${esc(e.path)}</div>${e.note?`<div>${esc(e.note)}</div>`:''}</div>`).join(''):'<div class="empty">此 Page 暂无 Evidence</div>';}
function detailGovernance(p){const candidates=Object.entries(p.candidates||{}),issues=(DATA.quality_issues||[]).filter(i=>!i.context||i.context===p.path);return `<section class="section"><h3>事实状态</h3><span class="chip">Identity ${esc(p.identity_status)}</span>${Object.entries(p.section_status||{}).map(([k,v])=>`<span class="chip">${esc(k)} · ${esc(v)}</span>`).join('')}</section><section class="section"><h3>候选内容</h3>${candidates.length?candidates.map(([k,v])=>`<div class="issue"><b>${esc(k)}</b><div class="summary">${esc(fmtValue(v))}</div></div>`).join(''):'<div class="empty">没有候选内容</div>'}</section><section class="section"><h3>冲突</h3>${p.conflicts?.length?p.conflicts.map(x=>`<div class="issue summary">${esc(fmtValue(x))}</div>`).join(''):'<div class="empty">没有记录冲突</div>'}</section><section class="section"><h3>质量提示</h3>${issues.length?issues.map(x=>`<div class="issue"><b>${esc(x.code||x.severity)}</b><div>${esc(x.message||fmtValue(x))}</div></div>`).join(''):'<div class="empty">没有相关质量提示</div>'}</section>`;}
function renderDetail(){const p=pageByPath.get(selected),root=document.getElementById('detail');if(!p){root.innerHTML='<div class="empty">请选择一个 Rich Context Page</div>';return}const crumb=(p.hierarchy?.breadcrumb||[]).map(x=>x.name).join(' › ');root.innerHTML=`<div class="crumb">${esc(crumb||typeLabels[p.context_type]||p.context_type)}</div><span class="type">${esc(typeLabels[p.context_type]||p.context_type)}</span><h1>${esc(p.name)}</h1><div class="path">${esc(p.path)}</div><div class="tabs">${[['context','上下文'],['relations','关系'],['evidence','Evidence'],['governance','治理']].map(([id,l])=>`<button class="tab ${activeTab===id?'active':''}" data-tab="${id}">${l}</button>`).join('')}</div><div id="tabContent"></div>`;document.getElementById('tabContent').innerHTML=activeTab==='relations'?detailRelations(p):activeTab==='evidence'?detailEvidence(p):activeTab==='governance'?detailGovernance(p):detailContext(p);root.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{activeTab=t.dataset.tab;renderDetail()});root.querySelectorAll('[data-target]').forEach(x=>x.onclick=()=>select(x.dataset.target));}
function select(path){if(!pageByPath.has(path))return;selected=path;activeTab='context';renderTree();renderGraph();renderDetail();document.getElementById('searchResults').classList.remove('open');}
function search(q){q=q.trim().toLowerCase();if(!q)return[];return pages.map(p=>{const hay=[p.name,p.path,p.context_type,p.l0,JSON.stringify(p.facets),JSON.stringify(p.l2)].join(' ').toLowerCase();let score=hay.includes(q)?1:0;if(p.name.toLowerCase().includes(q))score+=3;if(p.path.toLowerCase().includes(q))score+=1;return {p,score};}).filter(x=>x.score).sort((a,b)=>b.score-a.score||a.p.name.localeCompare(b.p.name,'zh-CN')).slice(0,12);}
function bindSearch(){const input=document.getElementById('searchInput'),results=document.getElementById('searchResults');input.oninput=()=>{const rows=search(input.value);results.innerHTML=rows.map(({p})=>`<button class="result" data-path="${esc(p.path)}"><b>${esc(p.name)}</b><span>${esc(typeLabels[p.context_type]||p.context_type)} · ${esc(short(p.l0,70))}</span></button>`).join('')||(input.value?'<div class="empty">没有匹配结果</div>':'');results.classList.toggle('open',!!input.value);results.querySelectorAll('[data-path]').forEach(x=>x.onclick=()=>select(x.dataset.path));};document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();input.focus()}if(e.key==='Escape')results.classList.remove('open')});document.addEventListener('click',e=>{if(!e.target.closest('.search'))results.classList.remove('open')});}
function transform(){document.getElementById('graphStage').style.transform=`translate(${tx}px,${ty}px) scale(${scale})`;}
function bindPanZoom(){const vp=document.getElementById('graphViewport');let dragging=false,sx=0,sy=0,ox=0,oy=0;vp.onpointerdown=e=>{if(e.target.closest('.node'))return;dragging=true;sx=e.clientX;sy=e.clientY;ox=tx;oy=ty;vp.classList.add('dragging');vp.setPointerCapture(e.pointerId)};vp.onpointermove=e=>{if(!dragging)return;tx=ox+e.clientX-sx;ty=oy+e.clientY-sy;transform()};vp.onpointerup=()=>{dragging=false;vp.classList.remove('dragging')};vp.onwheel=e=>{e.preventDefault();scale=Math.max(.55,Math.min(1.8,scale*(e.deltaY<0?1.08:.92)));transform()};document.getElementById('zoomIn').onclick=()=>{scale=Math.min(1.8,scale*1.15);transform()};document.getElementById('zoomOut').onclick=()=>{scale=Math.max(.55,scale/1.15);transform()};document.getElementById('resetZoom').onclick=()=>{scale=1;tx=0;ty=0;transform()};}
function bindFilters(){document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{const s=b.dataset.status;if(enabled.has(s))enabled.delete(s);else enabled.add(s);b.classList.toggle('on',enabled.has(s));renderGraph()});}
function download(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}
function bindExport(){document.getElementById('exportSvg').onclick=()=>{const svg=document.getElementById('graph').cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent='.node-title{font:700 12px Helvetica,Arial,sans-serif}.node-sub{font:9.5px Helvetica,Arial,sans-serif;fill:#6b7280}.edge-label{font:600 10px Helvetica,Arial,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:5px}.edge{fill:none;stroke-linecap:round}';svg.prepend(style);download(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}),'semantic-context-view.svg')};document.getElementById('exportPng').onclick=()=>{const svg=document.getElementById('graph'),xml=new XMLSerializer().serializeToString(svg),img=new Image(),url=URL.createObjectURL(new Blob([xml],{type:'image/svg+xml'}));img.onload=()=>{const c=document.createElement('canvas');c.width=1600;c.height=1000;const ctx=c.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);URL.revokeObjectURL(url);c.toBlob(b=>download(b,'semantic-context-view.png'),'image/png')};img.src=url};}
window.addEventListener('resize',renderGraph);stats();renderTree();renderGraph();renderDetail();bindSearch();bindPanZoom();bindFilters();bindExport();
})();
</script>
</body></html>'''


if __name__ == "__main__":
    main()
