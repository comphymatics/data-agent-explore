from __future__ import annotations

import json
from dataclasses import asdict

from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.environment import (
    AvailabilityState,
    CapabilitySnapshot,
    EnvironmentBindingResult,
    MetaOneMcpAdapter,
)
from enterprise_data_context.models import (
    ContextFragment,
    Evidence,
    SourceLocation,
    TypedReference,
)
from enterprise_data_context.runtime import from_compiled
from explore_agent import ExploreAgent


class FixtureMcpClient:
    def __init__(self, tools, responses):
        self.tools = tools
        self.responses = responses
        self.calls = []

    def list_tools(self):
        return self.tools

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        value = self.responses[name]
        if isinstance(value, Exception):
            raise value
        return value(arguments) if callable(value) else value


def sample_tools():
    return [
        {
            "name": "data_catalog_get_capabilities",
            "description": "Return capabilities",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "data_catalog_search_assets",
            "description": "Search data assets",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "types": {"type": "array"},
                    "domain": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
        {
            "name": "data_catalog_get_asset_context",
            "description": "Get asset context",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "depth": {"type": "integer"},
                    "maxNodes": {"type": "integer"},
                },
            },
        },
    ]


def environment_asset(name="LTE Periodic MR"):
    return {
        "id": "physical:lte-periodic-mr",
        "type": "PHYSICAL_TABLE",
        "code": "LTE_PERIODIC_MR",
        "name": name,
        "description": "current environment table",
        "aliases": ["LTE Periodic MR"],
        "domain": "Resource",
        "attributes": {"layer": "ODS"},
        "evidenceRefs": ["metaone:asset:1"],
    }


def test_metaone_adapter_normalizes_current_sample_contract():
    client = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {
            "structuredContent": {
                "provider": "telecom-mock",
                "environmentId": "env-a",
                "datasetVersion": "capability-snapshot-old",
                "assetTypes": ["PHYSICAL_TABLE", "INDICATOR"],
            },
            "isError": False,
        },
        "data_catalog_search_assets": {
            "structuredContent": {
                "records": [{"asset": environment_asset(), "score": 0.97, "matchedBy": ["exact_name"]}],
                "total": 1,
                "version": "telecom-demo-1",
            },
            "isError": False,
        },
        "data_catalog_get_asset_context": {"focus": environment_asset(), "nodes": [], "edges": []},
    })
    result = MetaOneMcpAdapter(client, environment_id="fallback-env").resolve({
        "required": True,
        "query": "RSRP 有哪些现有模型可以提供？",
        "scope": {},
        "required_coverage": ["metrics", "models"],
        "limit": 4,
    })

    assert result.state is AvailabilityState.FOUND
    assert result.capabilities.provider == "telecom-mock"
    assert result.capabilities.environment_id == "env-a"
    assert result.capabilities.snapshot_token == "telecom-demo-1"
    assert {"capabilities", "search", "read"} <= set(result.capabilities.operations)
    assert result.coverage["models"] is True
    assert result.assets[0]["type"] == "physical-model"
    assert result.assets[0]["knowledge_layer"] == "ENVIRONMENT"
    assert result.assets[0]["evidence"][0]["environment_id"] == "env-a"
    search_call = next(call for call in client.calls if call[0] == "data_catalog_search_assets")
    assert search_call[1]["query"].startswith("RSRP")
    assert "PHYSICAL_TABLE" in search_call[1]["types"]
    schema = json.loads(
        open("contracts/environment-binding.schema.json", encoding="utf-8").read()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result.to_dict())

    detail = MetaOneMcpAdapter(client, environment_id="fallback-env").read_asset(
        "physical:lte-periodic-mr"
    )
    assert detail.state is AvailabilityState.FOUND
    assert detail.asset["type"] == "physical-model"
    assert detail.asset["knowledge_layer"] == "ENVIRONMENT"


def test_adapter_discovers_renamed_tools_and_parameter_aliases():
    tools = [
        {
            "name": "catalog_capability_snapshot",
            "description": "Metadata capability snapshot",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "catalog_find_assets",
            "description": "Find environment metadata",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "searchText": {"type": "string"},
                    "assetTypes": {"type": "array"},
                    "pageSize": {"type": "integer"},
                },
            },
        },
    ]
    client = FixtureMcpClient(tools, {
        "catalog_capability_snapshot": {
            "providerName": "metaone-fixture",
            "capabilityRevision": "cap-7",
            "snapshotToken": "snapshot-9",
        },
        "catalog_find_assets": {
            "items": [{
                "assetId": "metric:drop-rate",
                "assetType": "INDICATOR",
                "displayName": "掉话率",
            }],
            "totalCount": 1,
        },
    })
    result = MetaOneMcpAdapter(client, environment_id="tenant-b").resolve({
        "required": True,
        "query": "掉话率",
        "required_coverage": ["metrics"],
    })

    assert result.state is AvailabilityState.FOUND
    assert result.assets[0]["type"] == "metric"
    assert result.capabilities.capability_revision == "cap-7"
    assert client.calls[-1] == (
        "catalog_find_assets",
        {"searchText": "掉话率", "pageSize": 20},
    )


def test_adapter_supports_metaone_surface_and_relation_coverage():
    tools = [
        {
            "name": "metaone_get_capabilities",
            "description": "MetaOne capabilities",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "metaone_search_assets",
            "description": "Search MetaOne assets",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "types": {"type": "array"},
                    "limit": {"type": "integer"},
                },
            },
        },
        {
            "name": "metaone_expand_assets",
            "description": "Expand deterministic relationships",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {"type": "array"},
                    "relations": {"type": "array"},
                    "limit": {"type": "integer"},
                },
            },
        },
    ]
    client = FixtureMcpClient(tools, {
        "metaone_get_capabilities": {
            "provider": "metaone-fixture",
            "assetTypes": ["AGGREGATE_MODEL", "DIMENSION_LEVEL"],
        },
        "metaone_search_assets": {
            "records": [{
                "id": "aggregate:model-1",
                "type": "AGGREGATE_MODEL",
                "name": "用户日汇聚模型",
            }],
            "total": 1,
            "coverage": {"models": True, "lineage": False},
        },
        "metaone_expand_assets": {
            "records": [{
                "id": "physical:source-1",
                "type": "PHYSICAL_TABLE",
                "name": "用户明细表",
            }],
            "relations": [{
                "id": "relation:aggregate-source",
                "sourceId": "aggregate:model-1",
                "predicate": "USES",
                "targetId": "physical:source-1",
                "evidenceRefs": ["metaone:aggregate-source:1"],
            }],
            "coverage": {"lineage": True},
        },
    })
    result = MetaOneMcpAdapter(client).resolve({
        "required": True,
        "query": "用户日汇聚模型",
        "required_coverage": ["models", "lineage"],
    })

    assert result.assets[0]["type"] == "aggregate-model"
    assert result.coverage["models"] is True
    assert result.coverage["lineage"] is False
    assert "expand" in result.capabilities.operations

    expanded = MetaOneMcpAdapter(client).expand_assets(
        ["aggregate:model-1"], relations=["USES"]
    )
    assert expanded.state is AvailabilityState.FOUND
    assert expanded.assets[0]["type"] == "physical-model"
    assert expanded.relations[0]["predicate"] == "USES"
    assert expanded.relations[0]["assertion_status"] == "EXPLICIT"
    assert expanded.coverage["lineage"] is True


def test_adapter_never_upgrades_unknown_or_failure_to_confirmed_absence():
    unknown = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {},
        "data_catalog_search_assets": {"records": []},
        "data_catalog_get_asset_context": {},
    })
    unknown_result = MetaOneMcpAdapter(unknown).resolve({"required": True, "query": "missing"})
    assert unknown_result.state is AvailabilityState.TRUNCATED
    assert unknown_result.truncated is True

    timeout = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {},
        "data_catalog_search_assets": TimeoutError("fixture timeout"),
        "data_catalog_get_asset_context": {},
    })
    timeout_result = MetaOneMcpAdapter(timeout).resolve({"required": True, "query": "missing"})
    assert timeout_result.state is AvailabilityState.UNAVAILABLE
    assert timeout_result.warnings[0]["code"] == "environment_timeout"

    unauthorized = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {},
        "data_catalog_search_assets": PermissionError("fixture unauthorized"),
        "data_catalog_get_asset_context": {},
    })
    unauthorized_result = MetaOneMcpAdapter(unauthorized).resolve({
        "required": True, "query": "missing"
    })
    assert unauthorized_result.state is AvailabilityState.UNAVAILABLE
    assert unauthorized_result.warnings[0]["code"] == "environment_unauthorized"

    paged = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {},
        "data_catalog_search_assets": {
            "records": [{"asset": environment_asset()}],
            "nextCursor": "page-2",
        },
        "data_catalog_get_asset_context": {},
    })
    paged_result = MetaOneMcpAdapter(paged).resolve({"required": True, "query": "paged"})
    assert paged_result.state is AvailabilityState.TRUNCATED
    assert paged_result.cursor == "page-2"

    confirmed = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {},
        "data_catalog_search_assets": {"records": [], "total": 0},
        "data_catalog_get_asset_context": {},
    })
    confirmed_result = MetaOneMcpAdapter(confirmed).resolve({"required": True, "query": "missing"})
    assert confirmed_result.state is AvailabilityState.NOT_FOUND_CONFIRMED


def test_missing_search_capability_is_unsupported():
    client = FixtureMcpClient(sample_tools()[:1], {
        "data_catalog_get_capabilities": {"provider": "metaone-fixture"},
    })
    result = MetaOneMcpAdapter(client).resolve({"required": True, "query": "RSRP"})
    assert result.state is AvailabilityState.UNSUPPORTED


def test_explore_builds_dual_layer_overlay_and_versions():
    evidence = [Evidence(SourceLocation("reference", "reference.json", row=1))]
    compiled = ContextCompiler().compile_fragments([
        ContextFragment(
            "metric", "metric", "RSRP", "summary", "无线信号强度",
            evidence=evidence, source_type="kpi_definition",
            references=[TypedReference(
                "supported_by", "LTE Periodic MR", "physical-model", evidence=evidence
            )],
        ),
        ContextFragment(
            "model", "physical-model", "LTE Periodic MR", "summary", "LTE MR 明细",
            evidence=evidence, source_type="asset_catalog",
        ),
    ])
    client = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {
            "provider": "metaone-fixture",
            "environmentId": "env-1",
            "datasetVersion": "snapshot-1",
        },
        "data_catalog_search_assets": {
            "records": [{"asset": environment_asset(), "score": 1.0}],
            "total": 1,
        },
        "data_catalog_get_asset_context": {},
    })
    bundle = ExploreAgent(
        from_compiled(compiled).retrieval,
        environment_adapter=MetaOneMcpAdapter(client),
    ).explore("RSRP 有哪些现有模型可以提供？")

    assert bundle.environment["availability_state"] == "FOUND"
    assert bundle.environment["provider"] == "metaone-fixture"
    assert bundle.reference_index_version == bundle.index_version
    assert bundle.binding_policy_version == "environment-binding/v2"
    assert bundle.binding_overlay["environment_facts"]
    assert bundle.binding_overlay["reference_semantics"]
    assert not bundle.binding_overlay["derived_bindings"]
    assert bundle.binding_overlay["candidate_bindings"]
    assert bundle.binding_overlay["reference_only_assets"]
    schema = json.loads(
        open("contracts/context-bundle.schema.json", encoding="utf-8").read()
    )
    Draft202012Validator(schema).validate(asdict(bundle))


def test_reference_only_candidates_require_confirmed_absence():
    evidence = [Evidence(SourceLocation("reference", "reference.json", row=1))]
    compiled = ContextCompiler().compile_fragments([
        ContextFragment(
            "model", "physical-model", "Reference Model", "summary", "reference only",
            evidence=evidence, source_type="asset_catalog",
        ),
    ])
    capabilities = CapabilitySnapshot(
        provider="fixture",
        environment_id="env-1",
        capability_revision="cap-1",
        operations=("search",),
    )

    class ConfirmedAbsentAdapter:
        def resolve(self, requirements):
            return EnvironmentBindingResult(
                required=True,
                state=AvailabilityState.NOT_FOUND_CONFIRMED,
                capabilities=capabilities,
            )

    bundle = ExploreAgent(
        from_compiled(compiled).retrieval,
        environment_adapter=ConfirmedAbsentAdapter(),
    ).explore("Reference Model 有哪些现有模型可以提供？")
    assert bundle.binding_overlay["reference_only_assets"]
    assert any(item.get("reason") == "environment_absence_confirmed" for item in bundle.candidates)
    assert "environment_assets" in bundle.missing_context


def test_environment_only_hit_is_not_reported_as_no_context():
    evidence = [Evidence(SourceLocation("reference", "reference.json", row=1))]
    compiled = ContextCompiler().compile_fragments([
        ContextFragment(
            "unrelated", "scenario", "地铁弱覆盖", "summary", "unrelated reference",
            evidence=evidence, source_type="app_feature",
        ),
    ])
    client = FixtureMcpClient(sample_tools(), {
        "data_catalog_get_capabilities": {
            "provider": "metaone-fixture",
            "environmentId": "env-1",
            "assetTypes": ["PHYSICAL_TABLE"],
        },
        "data_catalog_search_assets": {
            "records": [{"asset": environment_asset("Environment Only Model"), "score": 1.0}],
            "total": 1,
            "version": "snapshot-env-only",
        },
        "data_catalog_get_asset_context": {},
    })
    bundle = ExploreAgent(
        from_compiled(compiled).retrieval,
        environment_adapter=MetaOneMcpAdapter(client),
    ).explore("UNKNOWN_METRIC 有哪些现有模型可以提供？")

    assert bundle.primary_contexts == []
    assert bundle.binding_overlay["environment_facts"]
    assert bundle.environment["snapshot_token"] == "snapshot-env-only"
    assert bundle.confidence > 0
    assert bundle.stop_reason != "no_context_found"


def test_focused_resolve_propagates_scoped_absence_and_pins_snapshots():
    client=FixtureMcpClient(sample_tools(),{
        "data_catalog_get_capabilities":{"provider":"fixture","environmentId":"env-a","snapshotToken":"old"},
        "data_catalog_search_assets":{"records":[environment_asset()],"total":1,"snapshotToken":"search-v2",
            "requirement_coverage":[{"entity":"missing field","aspect":"fields","status":"MISSING","complete":True,"authoritative":True,"evidence":[{"ref":"inventory"}]}]},
        "data_catalog_get_asset_context":{"snapshotToken":"other-v3","asset":environment_asset()},
    })
    adapter=MetaOneMcpAdapter(client)
    result=adapter.resolve({"required":True,"query":"LTE Periodic MR","intent":"model_understanding","focused_expansion":True})
    assert result.capabilities.snapshot_token=="search-v2"
    assert result.assets[0]["evidence"][0]["snapshot_token"]=="search-v2"
    assert result.requirement_coverage[0]["status"]=="MISSING"
    assert result.truncated
    assert any(w["code"]=="environment_snapshot_mismatch" for w in result.warnings)
    assert adapter.tool_call_count==4
