"""Synthetic source material. No evaluation expectations enter the compiler."""
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation, TypedReference


def sample_fragments():
    rows = []
    def entity(kind, name, source, **sections):
        sections = {"identity": {"name": name}, **sections}
        for section, value in sections.items():
            proofs = [Evidence(SourceLocation(source, f"synthetic://{source}", section=f"{name}/{section}"))]
            refs = []
            if section == "references":
                refs = [TypedReference(relation, target, target_type, evidence=proofs)
                        for relation, target, target_type in value]
                value = []
            rows.append(ContextFragment(f"{name}/{section}", kind, name, section, value,
                evidence=proofs, source_type="synthetic", references=refs))
    entity("scenario", "地铁覆盖分析", "scenario-doc", summary="地铁弱覆盖需要哪些数据；地铁沿线分析", references=[("has_purpose", "弱覆盖诊断", "analysis-purpose")])
    entity("analysis-purpose", "弱覆盖诊断", "purpose-doc", summary="描述小区无线覆盖质量", references=[
        ("uses_metric", "RSRP", "metric"), ("uses_dimension", "位置", "dimension"),
        ("uses_model", "LTE MR Logical Model", "logical-model")])
    entity("metric", "RSRP", "metric-doc", summary="参考信号接收功率", references=[("uses_model", "LTE_PERIODIC_MR", "physical-model")])
    entity("dimension", "位置", "dimension-doc", summary="小区与采样点位置")
    entity("business-object", "小区", "object-doc", summary="无线网络小区")
    entity("logical-model", "LTE MR Logical Model", "model-doc", summary="LTE 测量报告逻辑模型", **{
        "classification.layer": "ODS", "topic_domain": "性能", "topic": "无线覆盖", "primary_objects": ["小区"]})
    entity("physical-model", "LTE_PERIODIC_MR", "asset-doc", summary="周期测量报告", metrics=["RSRP"], dimensions=["位置"],
        grain=["用户", "小区", "时间"], important_fields=[{"name": "CELL_ID"}, {"name": "SCELL_RSRP"}, {"name": "EVENT_TIME"}],
        references=[("implements_logical_model", "LTE MR Logical Model", "logical-model"), ("provides_metric", "RSRP", "metric")],
        **{"classification.layer": "ODS", "topic_domain": "性能", "topic": "无线覆盖", "primary_objects": ["小区"]})
    entity("physical-model", "LTE_MR_NEW", "new-asset", summary="新增测量报告", technology="LTE", metrics=["RSRP"], dimensions=["位置"], **{"classification.layer": "ODS"})
    entity("physical-model", "UNKNOWN_MODEL", "unknown-asset", summary="语义尚未交付", **{"classification.layer": "ODS"})
    entity("physical-model", "BILLING_EVENTS", "billing-asset", summary="账单明细", **{"classification.layer": "ODS", "topic_domain": "计费", "topic": "账单"})
    return rows


def sample_config():
    return {"version": "synthetic-organization/v1", "confidence_threshold": .8,
            "hierarchy_enabled": True, "inference_enabled": True, "llm_enabled": False,
            "taxonomy": [{"id": "coverage", "view": "domain", "kind": "topic", "label": "无线覆盖", "features": {"metrics": ["RSRP"]}},
                         {"id": "billing", "view": "domain", "kind": "topic", "label": "账单", "features": {"metrics": ["AMOUNT"]}}],
            "rules": [{"id": "synthetic-lte-rsrp/v1", "selected": "coverage", "when": {"technology": "LTE", "metrics": ["RSRP"]}, "confidence": .95}]}
