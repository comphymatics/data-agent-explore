"""Opt-in real-size index/serving diagnostics (not an end-to-end Parser benchmark).

RUN_RETRIEVAL_SCALE=1 uv run --isolated --extra dev pytest -q -s tests/performance
Builds real PageIndex/ElementIndex and HierarchyIndex fixtures; no fake field counts.
"""
import gc
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter
import pytest

from enterprise_data_context.indexes.page import PageIndex
from enterprise_data_context.indexes.element import ElementIndex
from enterprise_data_context.indexes.mention import ExactMentionResolver
from enterprise_data_context.indexes.hierarchy import HierarchyIndex
from enterprise_data_context.models import CanonicalContext, ContextPage, Evidence, SourceLocation
from enterprise_data_context.retrieval import ContextRetrievalService
from enterprise_data_context.graph.backend import BackendGraph

pytestmark = pytest.mark.skipif(os.environ.get('RUN_RETRIEVAL_SCALE') != '1', reason='opt-in 500k field scale diagnostics')


class NoScan(dict):
    def __iter__(self): raise AssertionError('exact dictionary scan')
    def items(self): raise AssertionError('exact items scan')
    def values(self): raise AssertionError('exact values scan')


class NoMembers(list):
    def __iter__(self): raise AssertionError('query enumerated all branch members')


def timed(fn, repeats=12):
    samples = []
    result = None
    for _ in range(repeats):
        start = perf_counter(); result = fn(); samples.append((perf_counter()-start)*1000)
    ordered = sorted(samples)
    return result, {'p50_ms':median(samples), 'p95_ms':ordered[min(len(ordered)-1, int(len(ordered)*.95))], 'samples':len(samples)}


def test_enterprise_size_indices_and_serving():
    started = perf_counter()
    pidx, eidx = PageIndex(), ElementIndex()
    pages = []
    for i in range(5000):
        name = f'MODEL_{i:05d}'
        # 5,000 x 100 physically allocated, searchable governed field records.
        fields = [{'name':'CELL_ID' if j == 0 else f'FIELD_{i:05d}_{j:03d}'} for j in range(100)] if i < 5000 else []
        p = ContextPage(name, f'data://physical-models/{name}', 'physical-model', name, [], {},
            f'无线覆盖质量 Network resource inventory {i}', f'无线覆盖质量分析 network resource inventory {i}',
            {'important_fields':fields}, [], {}, {})
        pidx.add(p); eidx.add(p); pages.append(p)
    assert len(eidx.records) == 500000
    original_page_exact, original_element_exact = pidx.exact, eidx.exact
    pidx.exact, eidx.exact = NoScan(pidx.exact), NoScan(eidx.exact)
    resolver = ExactMentionResolver(pidx,eidx)
    mentions, mention_time = timed(lambda: resolver.resolve('CELL_ID在哪些模型？'))
    rows, element_time = timed(lambda: eidx.search('CELL_ID'))
    assert rows and all(r['match'] == 'EXACT_IDENTIFIER' for r in rows)
    d = mentions['diagnostics']
    assert d['exact_lookups_count'] < 50 and d['total_exact_keys'] > 500000
    assert d['targets_examined'] <= 100
    report = {'fixture_kind':'synthetic index and serving diagnostics; not Parser/E2E benchmark',
        'page_count':len(pages), 'field_parent_count':5000, 'element_count':len(eidx.records),
        'index_build_seconds':perf_counter()-started,
        'A':{'mention':d, 'anchor_latency':mention_time, 'element_search_latency':element_time,
             'element_diagnostics':eidx.last_diagnostics}}
    pidx.exact, eidx.exact = original_page_exact, original_element_exact
    report['encoder'] = {'version':pidx.encoder.version, 'channel':pidx.encoder.channel}
    for i in range(5000,10000):
        name = f'MODEL_{i:05d}'
        p = ContextPage(name, f'data://physical-models/{name}', 'physical-model', name, [], {},
            f'无线覆盖质量 Network resource inventory {i}', f'无线覆盖质量分析 network resource inventory {i}',
            {}, [], {}, {})
        pidx.add(p); eidx.add(p); pages.append(p)
    pidx.exact, eidx.exact = NoScan(pidx.exact), NoScan(eidx.exact)
    evidence = Evidence(SourceLocation('scale-source','synthetic://scale'))
    contexts = [CanonicalContext(p.canonical_id,p.context_type,p.name,p.path,
        sections={'topic':'无线覆盖质量', 'summary':p.l1}, evidence={'topic':[evidence], 'summary':[evidence]}) for p in pages]
    hierarchy = HierarchyIndex({'version':'scale/v1.2','inference_enabled':False}).project(contexts)
    assert len(hierarchy.aggregate_pages) == 1
    for aggregate in hierarchy.aggregate_pages.values():
        aggregate['member_refs'] = NoMembers(aggregate['member_refs'])
    compiled = {'pages':pages,'contexts':contexts,'page_index':pidx,'element_index':eidx,'hierarchy':hierarchy,
                'graph':BackendGraph(),'backrefs':{},'index_version':'synthetic-scale-v1.2'}
    service = ContextRetrievalService(compiled)
    result, latency = timed(lambda: service.data_search('哪些数据可以支持无线覆盖质量分析？',hierarchy='domain',read_content='L1'))
    trace = result['retrieval_trace']
    assert len(trace['selected_branches']) <= 3 and len(result['contexts']) <= 8
    assert trace['branch_budget']['examined_members'] <= 100
    assert trace['branch_budget']['branches'][0]['branch_size'] == 10000
    report['B'] = {'latency':latency,'branch_recall_latency_ms':trace['branch_recall_latency_ms'],
                   'branch_budget':trace['branch_budget'],'bundle_size':len(result['contexts']),
                   'dense_active':bool(pidx.vectors),'retrieval_warnings':result['warnings']}
    # Independent organization fixture: exactly 100 aggregate branches across views.
    # Elements remain in the same production ElementIndex, never in branch L1.
    del hierarchy, service, compiled
    for i,c in enumerate(contexts):
        branch = i % 100
        section = 'analysis_purposes' if branch < 34 else 'topic' if branch < 67 else 'classification.layer'
        label = f'无线覆盖分析 {branch}' if branch < 34 else f'网络资源配置 {branch}' if branch < 67 else f'Asset Inventory {branch}'
        c.sections = {section:[label] if section == 'analysis_purposes' else label, 'summary':pages[i].l1}
        c.evidence = {key:[evidence] for key in c.sections}
    hierarchy = HierarchyIndex({'version':'scale/v1.2','inference_enabled':False}).project(contexts)
    assert len(hierarchy.aggregate_pages) == 100
    for aggregate in hierarchy.aggregate_pages.values():
        aggregate['member_refs'] = NoMembers(aggregate['member_refs'])
    service = ContextRetrievalService({'pages':pages,'contexts':contexts,'page_index':pidx,'element_index':eidx,
        'hierarchy':hierarchy,'graph':BackendGraph(),'backrefs':{},'index_version':'synthetic-scale-c-v1.2'})
    cases = [('Exact','CELL_ID在哪些模型？',{}),
        ('Broad Analysis','哪些数据支持无线覆盖分析？',{'hierarchy':'analysis'}),
        ('Broad Domain','有哪些数据可以描述网络资源配置？',{}),
        ('Broad Asset','Asset Inventory',{'hierarchy':'asset'}),
        ('Hybrid','MODEL_00001用于覆盖分析还需要哪些数据？',{})]
    report['C'] = {'aggregate_branch_count':100, 'page_count':len(pages), 'element_count':len(eidx.records), 'queries':[]}
    for label,query,kwargs in cases:
        result, latency = timed(lambda: service.data_search(query,read_content='L1',**kwargs))
        trace = result['retrieval_trace']; budget = trace.get('branch_budget',{})
        assert trace['mention_resolution']['exact_lookups_count'] < 100
        assert budget.get('examined_members',0) <= 300
        assert len(result['contexts']) <= (16 if trace['mode']=='direct' else 8)
        report['C']['queries'].append({'case':label,'query':query,'latency':latency,
            'routing':trace['routing'],'mention':{k:v for k,v in trace['mention_resolution'].items() if k!='mentions'},
            'entity_candidates':trace['entity_retrieval'], 'branch_budget':budget,'bundle_size':len(result['contexts']),
            'dense_active':bool(pidx.vectors),'retrieval_warnings':result['warnings']})
    report['total_seconds'] = perf_counter()-started
    output = Path(os.environ.get('RETRIEVAL_SCALE_OUTPUT','evaluation/hierarchy/results/v1.2/scale.json'))
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'scale_report':str(output),'fields':500000,'large_branch_members':10000,'total_seconds':report['total_seconds']}))
