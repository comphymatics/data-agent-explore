from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation, TypedReference
from enterprise_data_context.environment import EnvironmentBindingResult, AvailabilityState, CapabilitySnapshot
from explore_agent.evaluation import EvaluationCase
from explore_agent.coverage import requirement


def corpus():
    evidence = [Evidence(SourceLocation("golden-fixture", "fixture.json", row=1))]
    rows = []
    def add(name, typ, section, value, refs=None, status="EXPLICIT"):
        rows.append(ContextFragment(str(len(rows)), typ, name, section, value, evidence=evidence,
                    source_type="asset_catalog", references=refs or [], status=status))
    add("RSRP", "metric", "summary", "无线信号强度")
    add("RSRP", "metric", "formula", "AVG(RSRP)")
    add("RSRP", "metric", "references", [], [TypedReference("supported_by", "Radio Model", "physical-model", evidence=evidence)])
    add("Radio Model", "physical-model", "summary", "小区测量明细")
    add("Radio Model", "physical-model", "important_fields", ["CELL_ID", "RSRP", "subscriber_key"])
    add("Radio Model", "physical-model", "grain", ["Cell", "Time"])
    add("Incomplete Model", "physical-model", "summary", "待补充的数据模型")
    add("Latency", "metric", "summary", "网络时延")
    add("FORBIDDEN_ASSET_Z9", "physical-model", "summary", "无线信号强度", status="CANDIDATE")
    for name in ("Same Name Model", "Absent Model", "Offline Model", "Conflicted Model"):
        add(name,"physical-model","summary",name+" reference description")
    add("Conflicted Model","physical-model","grain",["Cell"])
    add("Conflicted Model","physical-model","grain",["Subscriber"])
    compiled = ContextCompiler().compile_fragments(rows)
    # Historical concept-vector ablation. Production defaults never use this fixture encoder.
    from enterprise_data_context.indexes.hybrid import LocalConceptEncoder
    compiled["page_index"].encoder = LocalConceptEncoder()
    for item in [*compiled["pages"], *compiled["contexts"]]:
        if item.name=="Conflicted Model":
            item.conflicts.append({"section":"grain","kept":["Cell"],"discarded":["Subscriber"],"reason":"fixture unresolved source disagreement"})
    return compiled


def environment():
    return EnvironmentBindingResult(required=True, state=AvailabilityState.FOUND,
        capabilities=CapabilitySnapshot("fixture", "env-golden", "cap-v1", ("search",), snapshot_token="snapshot-v1"),
        assets=[{"id": "env:radio", "type": "physical-model", "name": "Radio Model", "code": "radio",
                 "knowledge_layer": "ENVIRONMENT", "assertion_status": "EXPLICIT",
                 "attributes": {"reference_path": "data://physical-models/radio-model"},
                 "evidence": [{"provider": "fixture", "environment_id": "env-golden", "snapshot_token": "snapshot-v1"}]}])


class FixtureEnvironment:
    def resolve(self, requirements):
        query=requirements["query"]
        if "Absent Model" in query:
            return EnvironmentBindingResult(required=True,state=AvailabilityState.NOT_FOUND_CONFIRMED,
                requirement_coverage=[{"entity":"Absent Model","aspect":"models","status":"MISSING",
                    "complete":True,"authoritative":True,"evidence":[{"snapshot":"absence-v1","scope":"Absent Model"}]}])
        if "Offline Model" in query:
            return EnvironmentBindingResult(required=True,state=AvailabilityState.UNAVAILABLE)
        if "Same Name Model" in query:
            result=environment()
            result.assets[0].update(name="Same Name Model",attributes={})
            return result
        return environment()


class FixtureSemanticProvider:
    """Deterministic contract fixture. This is not a live LLM quality measurement."""
    def complete(self, *, task, payload, **kwargs):
        if task == "route":
            query = payload["query"]
            intent = "metric_to_models" if "提供" in query else "model_understanding" if "字段" in query else "generic"
            return {"output": {"intent": intent, "entities": [], "aspects": []}, "usage": {"total_tokens": 60}}
        records = payload["evidence"]
        return {"output": {"observations": [{"evidence_id": r["evidence_id"], "excerpt": r["text"][:100]} for r in records[:1]]},
                "usage": {"total_tokens": 120}}


def cases():
    metric = "data://metrics/rsrp"
    model = "data://physical-models/radio-model"
    incomplete = "data://physical-models/incomplete-model"
    return [
        EvaluationCase("exact-anchor", "RSRP", expected_contexts=["RSRP", "Radio Model"],
            expected_anchors=["RSRP"], relevant_contexts=["RSRP", "Radio Model"],
            expected_coverage={"REFERENCE|RSRP|business_meaning": "SATISFIED"},
            explore_options={"top_k": 1}, max_tool_calls=2, max_token_cost=10000),
        EvaluationCase("cross-language-semantic", "signal strength", expected_contexts=["RSRP", "Radio Model"],
            expected_anchors=["RSRP"], relevant_contexts=["RSRP", "Radio Model"],
            explore_options={"top_k": 1}, max_tool_calls=2, max_token_cost=10000),
        EvaluationCase("metric-model-relation", "RSRP 有哪些模型提供？", expected_contexts=["RSRP", "Radio Model"],
            expected_anchors=["RSRP"], relevant_contexts=["RSRP", "Radio Model"],
            expected_bindings=[["env:radio", model]],
            expected_coverage={"REFERENCE|RSRP|models": "SATISFIED", "ENVIRONMENT|RSRP|models": "UNKNOWN"},
            explore_options={"top_k": 1}, max_tool_calls=3, max_token_cost=10000),
        EvaluationCase("focused-field", "Radio Model 的 subscriber_key 字段", expected_contexts=["Radio Model"],
            expected_anchors=["Radio Model"], relevant_contexts=["Radio Model"],
            expected_elements=["subscriber_key"],
            expected_coverage={"REFERENCE|Radio Model|fields": "SATISFIED"},
            explore_options={"top_k": 1, "requirements": [requirement(model,"fields",name="Radio Model",selector="subscriber_key")]},
            max_tool_calls=3, max_token_cost=10000),
        EvaluationCase("entity-isolation", "Radio Model 与 Incomplete Model 的字段", expected_contexts=["Radio Model", "Incomplete Model"],
            anchor_k=2,
            expected_anchors=["Radio Model", "Incomplete Model"], relevant_contexts=["Radio Model", "Incomplete Model"],
            expected_coverage={"REFERENCE|Radio Model|fields": "SATISFIED", "REFERENCE|Incomplete Model|fields": "UNKNOWN"},
            explore_options={"top_k": 2,"requirements": [requirement(model,"fields",name="Radio Model"), requirement(incomplete,"fields",name="Incomplete Model")]},
            max_tool_calls=3, max_token_cost=10000),
        EvaluationCase("name-is-not-identity", "当前环境 Same Name Model", expected_contexts=["Same Name Model"],
            relevant_contexts=["Same Name Model"], expected_anchors=["Same Name Model"], expected_bindings=[],
            explore_options={"top_k":1}, max_tool_calls=3,max_token_cost=10000),
        EvaluationCase("scoped-authoritative-absence", "当前环境 Absent Model", expected_contexts=["Absent Model"],
            relevant_contexts=["Absent Model"],expected_anchors=["Absent Model"],expected_bindings=[],
            expected_coverage={"ENVIRONMENT|Absent Model|models":"MISSING"},
            explore_options={"top_k":1,"requirements":[requirement("absent","models","ENVIRONMENT","Absent Model")]},
            max_tool_calls=3,max_token_cost=10000),
        EvaluationCase("unavailable-is-unknown", "当前环境 Offline Model", expected_contexts=["Offline Model"],
            relevant_contexts=["Offline Model"],expected_anchors=["Offline Model"],expected_bindings=[],
            expected_coverage={"ENVIRONMENT|Offline Model|models":"UNKNOWN"},
            explore_options={"top_k":1,"requirements":[requirement("offline","models","ENVIRONMENT","Offline Model")]},
            max_tool_calls=3,max_token_cost=10000),
        EvaluationCase("conflict-is-partial", "Conflicted Model 粒度", expected_contexts=["Conflicted Model"],
            relevant_contexts=["Conflicted Model"],expected_anchors=["Conflicted Model"],
            expected_coverage={"REFERENCE|Conflicted Model|grain":"PARTIAL"},
            explore_options={"top_k":1,"requirements":[requirement("data://physical-models/conflicted-model","grain",name="Conflicted Model")]},
            max_tool_calls=3,max_token_cost=10000),
        EvaluationCase("candidate-excluded", "FORBIDDEN_ASSET_Z9", expected_contexts=[], relevant_contexts=[],
            expected_bindings=[], explore_options={"top_k": 1}, max_tool_calls=1, max_token_cost=10000),
    ]
