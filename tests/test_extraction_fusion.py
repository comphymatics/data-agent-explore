from enterprise_data_context.models import DocumentIR,DocumentElement,SourceLocation,ContextFragment
from enterprise_data_context.extraction.rule_extractor import RuleExtractor
from enterprise_data_context.canonical.resolver import CanonicalResolver
from enterprise_data_context.fusion.merge import MergeEngine

def test_metric_profile():
    ir=DocumentIR("x","x.xlsx","kpi_definition",elements=[
        DocumentElement("table","t",headers=["指标名称","指标描述","公式","维度"],
        rows=[["RSRP","信号强度","AVG(RSRP)","Cell,Grid"]],source=SourceLocation("x","x.xlsx"))
    ])
    fs=RuleExtractor().extract(ir)
    assert any(f.context_type=="metric" and f.candidate_name=="RSRP" for f in fs)
    assert any(f.section_type=="formula" for f in fs)

def test_authority_and_conflict():
    r=CanonicalResolver(); m=MergeEngine()
    a=ContextFragment("1","metric","RSRP","formula","A",source_type="unknown")
    b=ContextFragment("2","metric","RSRP","formula","B",source_type="kpi_definition")
    c=r.resolve_or_create(a); m.merge(c,a); m.merge(c,b)
    assert c.sections["formula"]=="B"
    assert c.conflicts
