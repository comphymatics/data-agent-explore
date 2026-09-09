"""V1.2 correctness, governance, incremental ownership and bounded serving."""
from copy import deepcopy
from dataclasses import asdict
import pytest

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.hierarchy_config import validate_hierarchy_config
from enterprise_data_context.indexes.element import ElementIndex
from enterprise_data_context.indexes.page import PageIndex
from enterprise_data_context.indexes.mention import ExactMentionResolver
from enterprise_data_context.indexes.hierarchy import HierarchyIndex, view_path
from enterprise_data_context.models import CanonicalContext, ContextPage, Evidence, SourceLocation, TypedReference
from enterprise_data_context.persistence import save_compiled, QualityGateError
from enterprise_data_context.runtime import from_compiled
from evaluation.hierarchy.sample import sample_fragments, sample_config


class NoScan(dict):
    def __iter__(self):
        raise AssertionError("query iterated entire exact index")
    def items(self):
        raise AssertionError("query iterated exact items")
    def values(self):
        raise AssertionError("query iterated exact values")


def page(name="LTE_PERIODIC_MR", fields=None, aliases=None):
    return ContextPage(name, "data://physical-models/"+name, "physical-model", name,
        aliases or [], {}, name, "reference model", {"important_fields": fields or [{"name": "CELL_ID"}]}, [], {}, {})


@pytest.mark.parametrize("query,expected", [
    ("查询 LTE_PERIODIC_MR.CELL_ID 对应哪些下游模型", {"lte_periodic_mr", "cell_id"}),
    ('查询 "Wireless Coverage" 支持什么', {"wireless coverage"}),
    ("无线覆盖需要哪些数据", {"无线覆盖"}),
    ("cellId在哪些模型", {"cellid"}),
])
def test_query_driven_mentions_no_index_iteration(query, expected):
    pidx, eidx = PageIndex(), ElementIndex()
    p = page(fields=[{"name": "CELL_ID"}, {"name": "cellId"}], aliases=["Wireless Coverage", "无线覆盖"])
    pidx.add(p); eidx.add(p)
    pidx.exact, eidx.exact = NoScan(pidx.exact), NoScan(eidx.exact)
    result = ExactMentionResolver(pidx, eidx).resolve(query)
    assert expected <= {m["normalized"] for m in result["mentions"]}
    assert all(t["parent_page"] == p.path for m in result["mentions"] for t in m["targets"])
    assert result["diagnostics"]["exact_lookups_count"] == result["diagnostics"]["mention_candidates_count"]*2


def test_symbol_boundaries_and_incremental_alias_field_deletion():
    pidx, eidx = PageIndex(), ElementIndex()
    p = page(aliases=["旧中文名称"]); pidx.add(p); eidx.add(p)
    resolver = ExactMentionResolver(pidx, eidx)
    assert not resolver.resolve("XCELL_ID_suffix")['mentions']
    p.aliases = ["新中文名称"]; p.l2['important_fields'] = [{"name": "NEW_FIELD"}]
    pidx.add(p); eidx.add(p)
    assert not resolver.resolve("旧中文名称 CELL_ID")['mentions']
    assert len(resolver.resolve("新中文名称 NEW_FIELD")['mentions']) == 2
    assert not pidx.validate() and not eidx.validate()
    pidx.remove(p.path); eidx.remove(p.path)
    assert not resolver.resolve("新中文名称 NEW_FIELD")['mentions']
    assert not pidx.mentions.root and not eidx.records


def co_context(parents=2, children=2, relations=False):
    evidence = Evidence(SourceLocation("co-source", "synthetic://co"))
    model = CanonicalContext("model:m", "physical-model", "M", "data://physical-models/m",
        sections={"analysis_purposes": [f"P{i}" for i in range(parents)], "metrics": [f"M{i}" for i in range(children)]})
    model.evidence = {s: [evidence] for s in model.sections}
    contexts = [model]
    if relations:
        for i in range(parents):
            metric = CanonicalContext(f"metric:m{i}", "metric", f"M{i}", f"data://metrics/m{i}")
            purpose = CanonicalContext(f"purpose:p{i}", "analysis-purpose", f"P{i}", f"data://purposes/p{i}")
            purpose.references = [TypedReference("requires_metric", metric.name, "metric", "CONFIRMED", metric.path, 1, [evidence])]
            contexts += [metric, purpose]
    return contexts


@pytest.mark.parametrize("parents,children,relations,count", [(1,3,False,3),(3,1,False,3),(2,2,False,0),(2,2,True,2)])
def test_co_classification_cardinality_and_relation_guard(parents, children, relations, count):
    index = HierarchyIndex({"version":"test", "inference_enabled":False}).project(co_context(parents, children, relations))
    pairs = [e for e in index.edges if e['source_relation'] == 'co_classification']
    assert len(pairs) == count
    assert not [i for i in index.validate() if i['severity'] == 'error']
    assert all(e['relation'] == 'organized_under' for e in pairs)


def taxonomy():
    return {"version":"test", "taxonomy_nodes":[
        {"id":"topic", "view":"domain", "kind":"topic", "label":"T"},
        {"id":"model", "view":"domain", "kind":"logical-model", "label":"M"}],
        "taxonomy_edges":[{"parent":"topic", "child":"model", "status":"CONFIRMED",
            "provenance":{"method":"explicit_taxonomy", "source":"standard"},
            "evidence":[{"source":{"source_id":"standard", "path":"synthetic://standard"}}]}]}


@pytest.mark.parametrize("change,error", [
    (lambda c: c['taxonomy_edges'][0].update(parent='model',child='topic'), 'invalid_taxonomy_transition'),
    (lambda c: c['taxonomy_nodes'][1].update(view='asset'), 'cross_view_taxonomy_edge'),
    (lambda c: c['taxonomy_edges'][0].update(child='absent'), 'unknown_taxonomy_node'),
    (lambda c: c.update(view_arbitration={'max_views':3}), 'invalid_view_arbitration_config'),
    (lambda c: c.update(hierarchy_retrieval={'entity_candidate_k':1001}), 'unbounded_branch_retrieval'),
    (lambda c: c.update(taxonomy_transitions={'analysis':{},'domain':{'invalid':[]},'asset':{}}), 'invalid_parent_kind'),
    (lambda c: c.update(taxonomy_transitions={'analysis':{},'domain':{'topic':['invalid']},'asset':{}}), 'invalid_child_kind'),
])
def test_invalid_policy_fails_fast(change, error):
    config = taxonomy(); change(config)
    with pytest.raises(ValueError, match=error):
        validate_hierarchy_config(config)


def test_sparse_configurable_transition_and_snapshot_policy_rejection():
    config = taxonomy()
    index = HierarchyIndex(config).project([])
    assert not index.validate()
    data = index.to_dict(); data['config'].pop('hardening_version')
    from enterprise_data_context.indexes.hierarchy import fingerprint
    data['config_hash'] = fingerprint(data['config'])
    with pytest.raises(ValueError, match='retrieval_policy_version_mismatch'):
        HierarchyIndex.from_dict(data, [])


def test_noop_incremental_indexes_and_policy_only_rebuild():
    compiler = ContextCompiler(hierarchy_config=sample_config())
    fragments = sample_fragments()
    before = compiler.compile_fragments(fragments)
    after = compiler.compile_fragments(fragments, previous_compiled=before)
    assert after['page_index'] is before['page_index']
    assert after['element_index'] is before['element_index']
    compiler.organization.config = {**sample_config(), 'view_arbitration': {'confidence_threshold': .9}}
    changed = compiler.compile_fragments(fragments, previous_compiled=after)
    assert changed['hierarchy'].last_update['rebuilt_entities'] == []
    assert changed['hierarchy'].last_update['rebuilt_aggregates'] == []
    assert changed['element_index'] is after['element_index']


def test_incremental_page_update_leaves_prior_snapshot_intact():
    compiler = ContextCompiler(hierarchy_config=sample_config())
    fragments = sample_fragments(); before = compiler.compile_fragments(fragments)
    changed = deepcopy(fragments)
    for fragment in changed:
        if fragment.candidate_name == 'LTE_PERIODIC_MR':
            fragment.aliases = ['新增别名']
    after = compiler.compile_fragments(changed, previous_compiled=before)
    assert ExactMentionResolver(after['page_index'], after['element_index']).resolve('新增别名')['mentions']
    assert not ExactMentionResolver(before['page_index'], before['element_index']).resolve('新增别名')['mentions']


def test_stale_quality_gates(tmp_path):
    compiled = ContextCompiler(hierarchy_config=sample_config()).compile_fragments(sample_fragments())
    compiled['page_index'].exact['forged'].add(compiled['pages'][0].path)
    with pytest.raises(QualityGateError, match='exact_mention_index_stale'):
        save_compiled(compiled, tmp_path)
    index = compiled['hierarchy']; path = next(iter(index.branch_membership))
    index.branch_membership[path] = frozenset()
    assert 'branch_member_index_stale' in {i['code'] for i in index.validate()}


def test_direct_bypasses_arbitration_and_branch_member_arrays():
    compiled = ContextCompiler(hierarchy_config=sample_config()).compile_fragments(sample_fragments())
    service = from_compiled(compiled).retrieval
    service.pidx.exact = NoScan(service.pidx.exact); service.eidx.exact = NoScan(service.eidx.exact)
    service.hierarchy.aggregate_index.search = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('direct recalled branches'))
    result = service.data_search('RSRP有哪些模型？')
    assert result['retrieval_trace']['mode'] == 'direct'
    assert not result['retrieval_trace']['routing']['arbitration']['triggered']


def test_independent_ablation_reports_precision_and_routing_without_scorer_changes():
    from evaluation.hierarchy.hardening import guard_ablation, routing_ablation
    guard = guard_ablation()
    assert guard['OFF']['derived_pair_count'] == 4 and guard['ON']['derived_pair_count'] == 0
    assert guard['ON']['broad_query_bundle']['precision'] > guard['OFF']['broad_query_bundle']['precision']
    assert guard['ON']['broad_query_bundle']['recall'] == guard['OFF']['broad_query_bundle']['recall']
    routing = routing_ablation()
    assert routing['arbitration']['mean_view_accuracy'] > routing['keyword_default']['mean_view_accuracy']
    assert routing['arbitration']['mean_branch_recall'] > routing['keyword_default']['mean_branch_recall']


def test_low_confidence_structured_route_arbitrates_and_explicit_override_does_not():
    from evaluation.hierarchy.hardening import service_for, context
    service = service_for([context('physical-model','Model X','x',{'topic':'网络设施全貌'})])
    preferred = {'mode':'hierarchical', 'hierarchy_views':['analysis'], 'primary_view':'analysis',
                 'confidence':.4, 'reasons':['bounded_router']}
    result = service.data_search('网络设施全貌的数据', intent='scenario_exploration', retrieval_strategy=preferred)
    trace = result['retrieval_trace']
    assert trace['routing']['initial']['confidence'] == .4
    assert trace['routing']['arbitration']['triggered'] and trace['hierarchy_view'] == 'domain'
    explicit = service.data_search('网络设施全貌的数据',hierarchy='analysis',retrieval_strategy=preferred)
    assert not explicit['retrieval_trace']['routing']['arbitration']['triggered']


def test_bounded_postings_are_reproducible_and_find_rare_tail_candidate():
    first,second = PageIndex(),PageIndex()
    pages = [page(f'MODEL_{i:03d}',aliases=[f'Unique_{i:03d}']) for i in range(300)]
    for p in pages: first.add(p)
    for p in reversed(pages): second.add(p)
    members = frozenset(p.path for p in pages)
    for index in (first,second):
        hits = index.search('Unique_299',candidate_limit=100,allowed_paths=members,
                            fallback_paths=tuple(sorted(members))[:100],top_k=8)
        assert hits[0].path == pages[299].path
        assert index.last_examined_count <= 100
    a = ExactMentionResolver(first,ElementIndex()).resolve('reference model')
    b = ExactMentionResolver(second,ElementIndex()).resolve('reference model')
    assert a['mentions'] == b['mentions']
    # Common exact aliases, with more targets than the budget, must be deterministic.
    for p in pages: first.add_exact_keys(p.path,['共同别名'])
    for p in reversed(pages): second.add_exact_keys(p.path,['共同别名'])
    assert ExactMentionResolver(first,ElementIndex()).resolve('共同别名')['mentions'] == ExactMentionResolver(second,ElementIndex()).resolve('共同别名')['mentions']


def test_trie_corruption_and_ambiguous_edge_quality_gate():
    pidx = PageIndex(); pidx.add(page(aliases=['中文别名']))
    pidx.mentions.root.clear()
    assert pidx.validate()[0]['code'] == 'exact_mention_index_stale'
    index = HierarchyIndex({'version':'test','inference_enabled':False,'co_classification_guard':False}).project(co_context())
    index.config['co_classification_guard'] = True
    assert 'ambiguous_derived_edge' in {i['code'] for i in index.validate()}


def test_element_alias_is_governed_and_incrementally_removed():
    pidx,eidx = PageIndex(),ElementIndex()
    p = page(fields=[{'name':'CELL_ID','aliases':['服务小区标识','Serving Cell Identifier']}])
    pidx.add(p); eidx.add(p)
    resolver = ExactMentionResolver(pidx,eidx)
    for query in ['服务小区标识在哪些模型','show Serving Cell Identifier']:
        mentions = resolver.resolve(query)['mentions']
        assert mentions and mentions[0]['targets'][0]['element_type'] == 'Field'
    eidx.remove(p.path)
    assert not resolver.resolve('服务小区标识')['mentions']
