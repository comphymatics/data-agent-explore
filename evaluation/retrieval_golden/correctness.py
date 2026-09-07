"""Retrieval correctness oracles. Synthetic source facts, no semantic provider."""
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation
from explore_agent.coverage import requirement
from explore_agent.evaluation import EvaluationCase
from .fixtures import corpus as original_corpus, cases as original_cases, FixtureEnvironment, environment

MODEL = "data://physical-models/typed-catalog"
POLICY = "data://metrics/stored-counter"


def corpus():
    base = original_corpus()
    ev = [Evidence(SourceLocation("correctness-fixture", "correctness.json", row=1))]
    rows = list(base["fragments"])
    for name, typ, section, value in [
        ("Typed Catalog", "physical-model", "summary", "Governed measurement catalog"),
        ("Typed Catalog", "physical-model", "important_fields", [
            {"name":"subscriber_key","description":"Subscriber identifier"},
            {"name":"other_field","description":"A note mentioning ghost_field"},
            {"name":"unapproved_field","status":"CANDIDATE"}]),
        ("Typed Catalog", "physical-model", "attributes", [{"name":"customer_age"}]),
        ("Typed Catalog", "physical-model", "formula", "COUNT(subscriber_key)"),
        ("Typed Catalog", "physical-model", "metric_catalog", [{"code":"C_RADIO_001","name":"Radio attempts"}]),
        ("Typed Catalog", "physical-model", "joins", [{"source_field":"subscriber_key","target_field":"customer_id"}]),
        ("Stored Counter", "metric", "summary", "Externally measured counter"),
        ("Stored Counter", "metric", "formula", {"coverage_status":"NOT_APPLICABLE","authoritative":True,
            "reason":"Directly measured counter has no derived formula"}),
        ("Stored Counter", "metric", "constraints", {"coverage_status":"MISSING","authoritative":True,
            "complete":True,"reason":"Fixture inventory exhaustively enumerates this counter's constraints"}),
        ("Stable Model", "physical-model", "summary", "Stable identified environment reference"),
        ("Stable Model", "physical-model", "identity", "Stable Model"),
        ("Strong Model", "physical-model", "summary", "Fully qualified environment reference"),
        ("Strong Model", "physical-model", "identity", "Strong Model"),
    ]:
        rows.append(ContextFragment("correctness-"+str(len(rows)),typ,name,section,value,evidence=ev))
    compiled=ContextCompiler().compile_fragments(rows)
    # Keep the historical conflict oracle explicit, independent of compiler fusion policy.
    for item in [*compiled["pages"],*compiled["contexts"]]:
        if item.name=="Conflicted Model":
            item.conflicts.append({"section":"grain","kept":["Cell"],"discarded":["Subscriber"]})
    # Fixture of already-governed identity metadata; Compiler behavior is not changed.
    for context in compiled["contexts"]:
        if context.name in {"Stable Model","Strong Model"}:
            key="stable_id" if context.name=="Stable Model" else "strong_key"
            context.identity_hints.update(identity_namespace="fixture-catalog",environment_id="env-golden")
            context.identity_hints[key]="tenant.schema."+context.name.lower().replace(" ","_")
    return compiled


class CorrectnessEnvironment(FixtureEnvironment):
    def __init__(self):
        self.tool_call_count=0

    def resolve(self, request):
        self.tool_call_count+=1
        for name,key in [("Stable Model","stable_id"),("Strong Model","strong_key")]:
            if name in request["query"]:
                env=environment()
                env.assets[0].update(name=name,attributes={"identity_namespace":"fixture-catalog",key:"tenant.schema."+name.lower().replace(" ","_")})
                if "stale" in request["query"]:
                    env.assets[0]["evidence"][0]["snapshot_token"]="old-snapshot"
                if "ambiguous" in request["query"]:
                    env.assets.append({**env.assets[0],"id":"env:duplicate"})
                return env
        if "Logical Alias" in request["query"]:
            env=environment()
            env.assets[0].update(type="logical-model",name="Radio Model")
            return env
        return super().resolve(request)


def cases():
    rows=original_cases()
    for aspect, selector, kind in [("fields","subscriber_key","Field"),
        ("attributes","customer_age","Attribute"),("formula","COUNT(subscriber_key)","Formula"),
        ("counters","C_RADIO_001","Counter"),("join_keys","customer_id","JoinKey")]:
        req=requirement(MODEL,aspect,name="Typed Catalog",selector=selector)
        rows.append(EvaluationCase("typed-"+kind,"Typed Catalog "+selector,
            expected_contexts=[MODEL],expected_anchors=[MODEL],relevant_contexts=[MODEL],
            expected_elements=[{"parent_path":MODEL,"kind":kind,"identifier":selector}],
            expected_coverage={req["id"]:"SATISFIED"},
            explore_options={"top_k":1,"requirements":[req],"token_budget":5000},max_tool_calls=2,max_token_cost=14000))
    for suffix,entity,aspect,selector,status in [
        ("description-not-identifier",MODEL,"fields","ghost_field","UNKNOWN"),
        ("candidate-field",MODEL,"fields","unapproved_field","UNKNOWN"),
        ("wrong-explicit-path","data://physical-models/does-not-exist","fields","subscriber_key","UNKNOWN"),
        ("not-applicable",POLICY,"formula",None,"NOT_APPLICABLE"),
        ("complete-reference-absence",POLICY,"constraints",None,"MISSING"),
    ]:
        name="Stored Counter" if entity==POLICY else "Typed Catalog"
        req=requirement(entity,aspect,name=name,selector=selector)
        expected=POLICY if entity==POLICY else MODEL
        rows.append(EvaluationCase(suffix,name+" "+(selector or aspect),expected_contexts=[expected],
            expected_anchors=[expected],relevant_contexts=[expected],expected_coverage={req["id"]:status},
            explore_options={"top_k":1,"requirements":[req],"token_budget":5000},max_tool_calls=2,max_token_cost=14000))
    rows.append(EvaluationCase("cross-type-crosswalk","当前环境 Radio Model Logical Alias",
        expected_contexts=["Radio Model","RSRP"],expected_anchors=["Radio Model"],relevant_contexts=["Radio Model","RSRP"],
        expected_bindings=[],explore_options={"top_k":1},max_tool_calls=3,max_token_cost=10000))
    # Even when no page fits hydration, anchor ranking remains separately measurable.
    rows.append(EvaluationCase("anchor-before-hydration","RSRP",expected_contexts=[],relevant_contexts=[],
        expected_anchors=["RSRP"],explore_options={"top_k":1,"token_budget":1},max_tool_calls=1,max_token_cost=2000))
    for name in ("Stable Model","Strong Model"):
        path="data://physical-models/"+name.lower().replace(" ","-")
        for variant in ("verified","stale","ambiguous"):
            rows.append(EvaluationCase(name.lower().replace(" ","-")+"-"+variant,"当前环境 "+name+" "+variant,
                expected_contexts=[path],relevant_contexts=[path],expected_anchors=[path],
                expected_bindings=[["env:radio",path]] if variant=="verified" else [],
                explore_options={"top_k":1},max_tool_calls=3,max_token_cost=10000))
    return rows
