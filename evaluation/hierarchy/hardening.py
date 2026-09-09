"""Independent V1.2 internal ablation; no formal E2E scorer changes.

Synthetic sources are built independently of the expected sets. Expectations are
used only after serving results have been produced.
"""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

from enterprise_data_context.models import CanonicalContext, Evidence, SourceLocation
from enterprise_data_context.indexes.hierarchy import HierarchyIndex
from enterprise_data_context.indexes.page import PageIndex
from enterprise_data_context.indexes.element import ElementIndex
from enterprise_data_context.materialization.pages import PageMaterializer
from enterprise_data_context.graph.backend import BackendGraph
from enterprise_data_context.references.resolver import build_backrefs
from enterprise_data_context.retrieval import ContextRetrievalService


def context(kind, name, slug, sections):
    c = CanonicalContext(kind+':'+slug,kind,name,'data://'+kind+'s/'+slug,sections=sections)
    proof = Evidence(SourceLocation('hardening-source','synthetic://hardening',section=slug))
    c.evidence = {key:[proof] for key in ['identity', *sections]}
    return c


def service_for(contexts, **policy):
    hierarchy = HierarchyIndex({'version':'internal-ablation/v1.2','inference_enabled':False,**policy}).project(contexts)
    pages = [PageMaterializer().materialize(c,hierarchy=hierarchy.navigation(c.path)) for c in contexts]
    pidx,eidx = PageIndex(),ElementIndex()
    for p in pages: pidx.add(p); eidx.add(p)
    return ContextRetrievalService({'contexts':contexts,'pages':pages,'page_index':pidx,'element_index':eidx,
        'graph':BackendGraph().project(contexts),'backrefs':build_backrefs(contexts),'hierarchy':hierarchy})


def metrics(actual, expected):
    actual, expected = set(actual),set(expected)
    hits = len(actual & expected)
    precision = hits/len(actual) if actual else 0
    recall = hits/len(expected) if expected else 0
    return {'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0}


def guard_ablation():
    sources = [context('analysis-purpose','Purpose Alpha','alpha',{'summary':'Purpose Alpha'}),
        context('analysis-purpose','Purpose Beta','beta',{'summary':'Purpose Beta'}),
        context('metric','Metric One','one',{'summary':'Metric One'}),
        context('metric','Metric Two','two',{'summary':'Metric Two'}),
        context('physical-model','Mixed Source Model','mixed',{'analysis_purposes':['Purpose Alpha','Purpose Beta'],
            'metrics':['Metric One','Metric Two'],'summary':'Mixed source classifications'})]
    # Source proves each purpose -> model; does not prove purpose -> metric pairs.
    expected = {sources[0].path,sources[-1].path}
    results = {}
    for enabled in (False,True):
        service = service_for(deepcopy(sources),co_classification_guard=enabled,view_arbitration={'enabled':False})
        result = service.data_search('Purpose Alpha data',hierarchy='analysis',bundle_k=8)
        selected = result['retrieval_trace']['selected_branches']
        members = set().union(*(service.hierarchy.branch_membership[p] for p in selected)) if selected else set()
        derived = [e for e in service.hierarchy.edges if e['source_relation']=='co_classification']
        results['ON' if enabled else 'OFF'] = {'derived_pair_count':len(derived),
            'branch_precision':metrics(members,expected),'broad_query_bundle':metrics(result['selected_context_ids'],expected),
            'selected_branches':selected,'selected_entities':result['selected_context_ids']}
    return results


def routing_ablation():
    sources = [context('physical-model','A','a',{'analysis_purposes':['弱覆盖诊断'],'summary':'信号测量'}),
        context('physical-model','D','d',{'topic':'网络设施全貌','summary':'资源描述'}),
        context('physical-model','S','s',{'classification.layer':'存储归档','summary':'历史数据'})]
    cases = [('有哪些数据描述网络设施全貌？','domain',sources[1].path),
             ('介绍存储归档中的数据','asset',sources[2].path),
             ('弱覆盖诊断有哪些支撑数据？','analysis',sources[0].path)]
    results = {}
    for enabled in (False,True):
        service = service_for(deepcopy(sources),view_arbitration={'enabled':enabled})
        rows = []
        for query,expected_view,expected_entity in cases:
            result = service.data_search(query,bundle_k=8)
            trace = result['retrieval_trace']
            expected_branches = {p for p,a in service.hierarchy.aggregate_pages.items()
                if a['hierarchy_view']==expected_view and expected_entity in service.hierarchy.branch_membership[p]}
            rows.append({'query':query,'routing':trace['routing'],
                'view_accuracy':int(trace['hierarchy_view']==expected_view),
                'branch_recall':metrics(trace['selected_branches'],expected_branches)['recall'],
                'entity_metrics':metrics(result['selected_context_ids'],{expected_entity})})
        results['arbitration' if enabled else 'keyword_default'] = {'cases':rows,
            'mean_view_accuracy':sum(r['view_accuracy'] for r in rows)/len(rows),
            'mean_branch_recall':sum(r['branch_recall'] for r in rows)/len(rows),
            'mean_entity_f1':sum(r['entity_metrics']['f1'] for r in rows)/len(rows)}
    return results


def run():
    report = {'scope':'synthetic internal ablation; not enterprise E2E readiness',
              'guard':guard_ablation(),'routing':routing_ablation()}
    output = Path('evaluation/hierarchy/results/v1.2/hardening-ablation.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__ == '__main__':
    run()
