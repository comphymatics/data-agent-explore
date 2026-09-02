from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


BINDING_POLICY_VERSION = "environment-binding/v1"


class AvailabilityState(str, Enum):
    FOUND = "FOUND"
    PARTIAL = "PARTIAL"
    NOT_FOUND_CONFIRMED = "NOT_FOUND_CONFIRMED"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"
    TRUNCATED = "TRUNCATED"


@dataclass(frozen=True)
class CapabilitySnapshot:
    provider: str
    environment_id: str | None
    capability_revision: str
    operations: tuple[str, ...]
    asset_types: tuple[str, ...] = ()
    snapshot_token: str | None = None
    captured_at: str | None = None
    warnings: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["operations"] = list(self.operations)
        row["asset_types"] = list(self.asset_types)
        row["warnings"] = list(self.warnings)
        return row


@dataclass
class EnvironmentSearchPage:
    state: AvailabilityState
    assets: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    cursor: str | None = None
    truncated: bool = False
    complete: bool = False
    snapshot_token: str | None = None
    captured_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "assets": self.assets,
            "coverage": self.coverage,
            "warnings": self.warnings,
            "cursor": self.cursor,
            "truncated": self.truncated,
            "complete": self.complete,
            "snapshot_token": self.snapshot_token,
            "captured_at": self.captured_at,
        }


@dataclass
class EnvironmentReadResult:
    state: AvailabilityState
    asset: dict[str, Any] | None = None
    related_assets: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "asset": self.asset,
            "related_assets": self.related_assets,
            "relations": self.relations,
            "warnings": self.warnings,
            "truncated": self.truncated,
        }


@dataclass
class EnvironmentExpansionResult:
    state: AvailabilityState
    assets: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "assets": self.assets,
            "relations": self.relations,
            "coverage": self.coverage,
            "warnings": self.warnings,
            "truncated": self.truncated,
        }


@dataclass
class EnvironmentBindingResult:
    required: bool
    state: AvailabilityState
    capabilities: CapabilitySnapshot | None = None
    assets: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    cursor: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        capabilities = self.capabilities.to_dict() if self.capabilities else None
        return {
            "binding_required": self.required,
            "binding_status": _binding_status(self.required, self.state),
            "availability_state": self.state.value,
            "provider": capabilities.get("provider") if capabilities else None,
            "environment_id": capabilities.get("environment_id") if capabilities else None,
            "capability_revision": capabilities.get("capability_revision") if capabilities else None,
            "snapshot_token": capabilities.get("snapshot_token") if capabilities else None,
            "captured_at": capabilities.get("captured_at") if capabilities else None,
            "operations": capabilities.get("operations", []) if capabilities else [],
            "asset_types": capabilities.get("asset_types", []) if capabilities else [],
            "matched_assets": self.assets,
            "coverage": self.coverage,
            "warnings": self.warnings + (capabilities.get("warnings", []) if capabilities else []),
            "cursor": self.cursor,
            "truncated": self.truncated,
        }


class EnvironmentBindingAdapter(Protocol):
    def resolve(self, requirements: dict[str, Any]) -> EnvironmentBindingResult: ...


class McpToolClient(Protocol):
    """Minimal client port; concrete stdio/HTTP transports stay outside the domain."""

    def list_tools(self) -> list[dict[str, Any]]: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class NullEnvironmentBindingAdapter:
    def resolve(self, requirements: dict[str, Any]) -> EnvironmentBindingResult:
        required = bool(requirements.get("required", True))
        return EnvironmentBindingResult(
            required=required,
            state=AvailabilityState.UNSUPPORTED,
            warnings=[{
                "code": "environment_adapter_not_configured",
                "message": "No environment metadata adapter is configured.",
            }],
        )


class MetaOneMcpAdapter:
    """Capability-negotiated anti-corruption layer over a changing MetaOne MCP."""

    OPERATION_ALIASES = {
        "capabilities": (
            "data_catalog_get_capabilities",
            "metaone_get_capabilities",
            "catalog_capability_snapshot",
        ),
        "search": (
            "data_catalog_search_assets",
            "metaone_search_assets",
            "catalog_find_assets",
        ),
        "read": (
            "data_catalog_get_asset_context",
            "metaone_get_asset",
            "catalog_read_asset",
        ),
        "expand": (
            "metaone_expand_assets",
            "data_catalog_expand_assets",
        ),
    }

    TYPE_MAP = {
        "PHYSICAL_TABLE": "physical-model",
        "PHYSICAL_MODEL": "physical-model",
        "PHYSICAL_COLUMN": "field",
        "FIELD": "field",
        "LOGICAL_ENTITY": "logical-model",
        "LOGICAL_MODEL": "logical-model",
        "LOGICAL_ATTRIBUTE": "business-attribute",
        "AGGREGATE_MODEL": "aggregate-model",
        "SID_ABE": "business-object",
        "SID_BE": "business-object",
        "DIMENSION": "dimension",
        "DIMENSION_LEVEL": "dimension-level",
        "DIMENSION_ATTRIBUTE": "dimension-attribute",
        "MEASURE": "measure",
        "INDICATOR": "metric",
        "METRIC": "metric",
    }

    COVERAGE_TYPES = {
        "metrics": {"metric", "measure"},
        "models": {"logical-model", "physical-model", "aggregate-model"},
        "dimensions": {"dimension", "dimension-level", "dimension-attribute"},
        "fields": {"field", "business-attribute", "dimension-attribute"},
        "business_object": {"business-object", "logical-model"},
    }

    def __init__(
        self,
        client: McpToolClient,
        *,
        environment_id: str | None = None,
        provider: str = "metaone",
        max_results: int = 20,
    ):
        self.client = client
        self.environment_id = environment_id
        self.provider = provider
        self.max_results = max_results
        self._tools: list[dict[str, Any]] | None = None
        self._operations: dict[str, dict[str, Any]] | None = None
        self._capabilities: CapabilitySnapshot | None = None

    def describe_capabilities(self, *, refresh: bool = False) -> CapabilitySnapshot:
        if self._capabilities is not None and not refresh:
            return self._capabilities
        if refresh:
            self._tools = None
            self._operations = None
        tools = self._list_tools()
        operations = self._discover_operations(tools)
        payload: dict[str, Any] = {}
        warnings: list[dict[str, Any]] = []
        descriptor = operations.get("capabilities")
        if descriptor:
            try:
                payload = self._call(descriptor, {})
            except Exception as exc:
                warnings.append(_warning_for_exception(exc, "capability_discovery_failed"))

        revision = _first(payload, "capabilityRevision", "capability_revision")
        if not revision:
            revision = "tools-" + hashlib.sha256(
                json.dumps(
                    [
                        {
                            "name": tool.get("name"),
                            "inputSchema": tool.get("inputSchema", tool.get("input_schema", {})),
                        }
                        for tool in sorted(tools, key=lambda item: str(item.get("name", "")))
                    ],
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]

        environment_value = (
            _first(payload, "environmentId", "environment_id", "tenantId")
            or self.environment_id
        )
        self._capabilities = CapabilitySnapshot(
            provider=str(_first(payload, "provider", "providerName") or self.provider),
            environment_id=str(environment_value) if environment_value else None,
            capability_revision=str(revision),
            operations=tuple(sorted(operations)),
            asset_types=tuple(str(value) for value in _list_value(payload, "assetTypes", "asset_types")),
            snapshot_token=_optional_string(
                _first(payload, "snapshotToken", "snapshot_token", "datasetVersion", "version")
            ),
            captured_at=_optional_string(
                _first(payload, "capturedAt", "captured_at", "generatedAt")
            ) or _now(),
            warnings=tuple(warnings),
        )
        return self._capabilities

    def search_assets(
        self,
        requirements: dict[str, Any],
        capabilities: CapabilitySnapshot | None = None,
    ) -> EnvironmentSearchPage:
        capabilities = capabilities or self.describe_capabilities()
        descriptor = self._operations_or_discover().get("search")
        if not descriptor:
            return EnvironmentSearchPage(
                state=AvailabilityState.UNSUPPORTED,
                warnings=[{
                    "code": "environment_search_unsupported",
                    "message": "The MCP server exposes no compatible asset search operation.",
                }],
            )

        arguments = self._search_arguments(descriptor, requirements, capabilities)
        try:
            payload = self._call(descriptor, arguments)
        except Exception as exc:
            return EnvironmentSearchPage(
                state=AvailabilityState.UNAVAILABLE,
                warnings=[_warning_for_exception(exc, "environment_search_failed")],
            )

        records = _records(payload)
        assets: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for record in records:
            normalized = self._normalize_asset(record, capabilities)
            if normalized is None:
                warnings.append({
                    "code": "invalid_environment_asset",
                    "message": "Ignored one environment record without a stable id, name or type.",
                })
            else:
                assets.append(normalized)

        truncated = bool(_first(payload, "truncated", "isTruncated", "hasMore"))
        cursor = _optional_string(_first(payload, "nextCursor", "next_cursor", "cursor"))
        total = _first(payload, "total", "totalCount", "total_count")
        explicitly_complete = _first(payload, "complete", "isComplete")
        complete = bool(explicitly_complete) if explicitly_complete is not None else total is not None and not truncated
        if truncated or cursor:
            state = AvailabilityState.TRUNCATED
        elif assets:
            state = AvailabilityState.FOUND if complete else AvailabilityState.PARTIAL
        elif complete and _as_int(total, default=0) == 0:
            state = AvailabilityState.NOT_FOUND_CONFIRMED
        else:
            state = AvailabilityState.TRUNCATED
            truncated = True
            warnings.append({
                "code": "environment_search_completeness_unknown",
                "message": "An empty response without total/complete metadata cannot confirm absence.",
            })

        inferred_coverage = {
            key: any(asset.get("type") in types for asset in assets)
            for key, types in self.COVERAGE_TYPES.items()
        }
        provider_coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
        coverage = {
            **inferred_coverage,
            **{
                str(key): bool(value)
                for key, value in provider_coverage.items()
                if isinstance(value, bool)
            },
        }
        # Lineage is relation coverage and cannot be inferred merely from finding a model.
        coverage.setdefault("lineage", False)
        return EnvironmentSearchPage(
            state=state,
            assets=assets,
            coverage=coverage,
            warnings=warnings,
            cursor=cursor,
            truncated=truncated,
            complete=complete,
            snapshot_token=_optional_string(
                _first(payload, "snapshotToken", "snapshot_token", "datasetVersion", "version", "indexVersion")
            ),
            captured_at=_optional_string(
                _first(payload, "capturedAt", "captured_at", "generatedAt")
            ),
        )

    def read_asset(
        self,
        asset_id: str,
        *,
        depth: int = 2,
        max_nodes: int = 50,
    ) -> EnvironmentReadResult:
        capabilities = self.describe_capabilities()
        descriptor = self._operations_or_discover().get("read")
        if not descriptor:
            return EnvironmentReadResult(
                state=AvailabilityState.UNSUPPORTED,
                warnings=[{
                    "code": "environment_read_unsupported",
                    "message": "The MCP server exposes no compatible asset read operation.",
                }],
            )
        arguments = self._arguments_for(
            descriptor,
            {"id": asset_id, "assetId": asset_id, "depth": depth, "maxNodes": max_nodes},
            required_fallback={"id": asset_id},
        )
        try:
            payload = self._call(descriptor, arguments)
        except Exception as exc:
            return EnvironmentReadResult(
                state=AvailabilityState.UNAVAILABLE,
                warnings=[_warning_for_exception(exc, "environment_read_failed")],
            )
        context = payload.get("context") if isinstance(payload.get("context"), dict) else payload
        raw_focus = context.get("focus") if isinstance(context.get("focus"), dict) else context.get("asset")
        if not isinstance(raw_focus, dict) and all(key in context for key in ("id", "type", "name")):
            raw_focus = context
        asset = self._normalize_asset(raw_focus, capabilities) if isinstance(raw_focus, dict) else None
        related_assets = []
        for raw in context.get("nodes") or context.get("relatedAssets") or []:
            if not isinstance(raw, dict):
                continue
            normalized = self._normalize_asset(raw, capabilities)
            if normalized and (not asset or normalized["id"] != asset["id"]):
                related_assets.append(normalized)
        truncated = bool(_first(context, "truncated", "isTruncated"))
        warnings = []
        if asset is None:
            warnings.append({
                "code": "invalid_environment_asset_detail",
                "message": "Asset detail did not contain a normalizable focus asset.",
            })
        relations = []
        for raw_relation in context.get("edges") or context.get("relations") or []:
            relation = self._normalize_relation(raw_relation, capabilities)
            if relation is None:
                warnings.append({
                    "code": "invalid_environment_relation",
                    "message": "Ignored one relation without source, target or predicate.",
                })
            else:
                relations.append(relation)
        return EnvironmentReadResult(
            state=(
                AvailabilityState.TRUNCATED
                if truncated
                else AvailabilityState.FOUND if asset else AvailabilityState.PARTIAL
            ),
            asset=asset,
            related_assets=related_assets,
            relations=relations,
            warnings=warnings,
            truncated=truncated,
        )

    def expand_assets(
        self,
        asset_ids: list[str],
        *,
        relations: list[str] | None = None,
        limit: int = 50,
    ) -> EnvironmentExpansionResult:
        descriptor = self._operations_or_discover().get("expand")
        if descriptor:
            arguments = self._arguments_for(
                descriptor,
                {
                    "ids": asset_ids,
                    "assetIds": asset_ids,
                    "relations": relations or [],
                    "limit": limit,
                    "maxNodes": limit,
                },
            )
            try:
                payload = self._call(descriptor, arguments)
            except Exception as exc:
                return EnvironmentExpansionResult(
                    state=AvailabilityState.UNAVAILABLE,
                    warnings=[_warning_for_exception(exc, "environment_expand_failed")],
                )
            values = _records(payload)
            capabilities = self.describe_capabilities()
            normalized = [self._normalize_asset(value, capabilities) for value in values]
            assets = [value for value in normalized if value is not None]
            warnings = []
            normalized_relations = []
            raw_relations = payload.get("relations") or payload.get("edges") or []
            for raw_relation in raw_relations:
                relation = self._normalize_relation(raw_relation, capabilities)
                if relation is None:
                    warnings.append({
                        "code": "invalid_environment_relation",
                        "message": "Ignored one relation without source, target or predicate.",
                    })
                else:
                    normalized_relations.append(relation)
            truncated = bool(_first(payload, "truncated", "isTruncated", "hasMore"))
            provider_coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
            return EnvironmentExpansionResult(
                state=(
                    AvailabilityState.TRUNCATED
                    if truncated
                    else AvailabilityState.FOUND
                    if assets or normalized_relations
                    else AvailabilityState.PARTIAL
                ),
                assets=assets,
                relations=normalized_relations,
                coverage={
                    str(key): bool(value)
                    for key, value in provider_coverage.items()
                    if isinstance(value, bool)
                },
                warnings=warnings,
                truncated=truncated,
            )
        if "read" in self._operations_or_discover():
            results = [self.read_asset(asset_id, max_nodes=limit) for asset_id in asset_ids]
            assets = []
            normalized_relations = []
            warnings = [{
                "code": "environment_expand_fallback_to_read",
                "message": "The provider has no focused expand operation; bounded asset reads were used.",
            }]
            truncated = False
            for result in results:
                if result.asset:
                    assets.append(result.asset)
                assets.extend(result.related_assets)
                normalized_relations.extend(result.relations)
                warnings.extend(result.warnings)
                truncated = truncated or result.truncated
            return EnvironmentExpansionResult(
                state=AvailabilityState.TRUNCATED if truncated else AvailabilityState.FOUND,
                assets=assets,
                relations=normalized_relations,
                warnings=warnings,
                truncated=truncated,
            )
        return EnvironmentExpansionResult(
            state=AvailabilityState.UNSUPPORTED,
            warnings=[{
                "code": "environment_expand_unsupported",
                "message": "The MCP server exposes no compatible expand or read operation.",
            }],
        )

    def resolve(self, requirements: dict[str, Any]) -> EnvironmentBindingResult:
        try:
            capabilities = self.describe_capabilities()
        except Exception as exc:
            return EnvironmentBindingResult(
                required=bool(requirements.get("required", True)),
                state=AvailabilityState.UNAVAILABLE,
                warnings=[_warning_for_exception(exc, "capability_discovery_failed")],
            )
        page = self.search_assets(requirements, capabilities)
        if page.snapshot_token or page.captured_at:
            capabilities = replace(
                capabilities,
                snapshot_token=page.snapshot_token or capabilities.snapshot_token,
                captured_at=page.captured_at or capabilities.captured_at,
            )
        return EnvironmentBindingResult(
            required=bool(requirements.get("required", True)),
            state=page.state,
            capabilities=capabilities,
            assets=page.assets,
            coverage=page.coverage,
            warnings=page.warnings,
            cursor=page.cursor,
            truncated=page.truncated,
        )

    def _list_tools(self) -> list[dict[str, Any]]:
        if self._tools is None:
            values = self.client.list_tools()
            if not isinstance(values, list):
                raise ValueError("MCP tools/list must return a list")
            self._tools = [value for value in values if isinstance(value, dict) and value.get("name")]
        return self._tools

    def _operations_or_discover(self) -> dict[str, dict[str, Any]]:
        if self._operations is None:
            self._operations = self._discover_operations(self._list_tools())
        return self._operations

    def _discover_operations(self, tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        discovered: dict[str, dict[str, Any]] = {}
        for operation in self.OPERATION_ALIASES:
            ranked = sorted(
                ((_operation_score(operation, tool, self.OPERATION_ALIASES[operation]), tool) for tool in tools),
                key=lambda pair: pair[0],
                reverse=True,
            )
            if ranked and ranked[0][0] > 0:
                discovered[operation] = ranked[0][1]
        self._operations = discovered
        return discovered

    def _search_arguments(
        self,
        descriptor: dict[str, Any],
        requirements: dict[str, Any],
        capabilities: CapabilitySnapshot,
    ) -> dict[str, Any]:
        coverage = requirements.get("required_coverage") or []
        supported_types = set(capabilities.asset_types)
        requested_types = sorted(
            raw
            for raw in supported_types
            if self.TYPE_MAP.get(raw.upper(), raw.lower().replace("_", "-"))
            in {
                canonical_type
                for key in coverage
                for canonical_type in self.COVERAGE_TYPES.get(str(key), set())
            }
        )
        limit = min(int(requirements.get("limit") or self.max_results), self.max_results)
        query = str(requirements.get("query", "")).strip()
        values = {
            "query": query,
            "q": query,
            "keyword": query,
            "searchText": query,
            "types": requested_types,
            "assetTypes": requested_types,
            "domain": requirements.get("scope", {}).get("topic_domain"),
            "limit": limit,
            "pageSize": limit,
            "cursor": requirements.get("cursor"),
        }
        return self._arguments_for(descriptor, values, required_fallback={"query": query})

    @staticmethod
    def _arguments_for(
        descriptor: dict[str, Any],
        values: dict[str, Any],
        required_fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = descriptor.get("inputSchema", descriptor.get("input_schema", {})) or {}
        properties = schema.get("properties") or {}
        if properties:
            return {key: values[key] for key in properties if key in values and values[key] not in (None, [], "")}
        return dict(required_fallback or {})

    def _call(self, descriptor: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
        raw = self.client.call_tool(str(descriptor["name"]), arguments)
        payload = _unwrap_mcp_result(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"MCP tool {descriptor['name']} returned a non-object payload")
        return payload

    def _normalize_asset(
        self,
        record: dict[str, Any],
        capabilities: CapabilitySnapshot,
    ) -> dict[str, Any] | None:
        raw = record.get("asset") if isinstance(record.get("asset"), dict) else record
        asset_id = _first(raw, "id", "assetId", "qualifiedName")
        name = _first(raw, "name", "displayName", "code")
        raw_type = _first(raw, "type", "assetType", "kind")
        if not asset_id or not name or not raw_type:
            return None
        canonical_type = self.TYPE_MAP.get(str(raw_type).upper(), str(raw_type).lower().replace("_", "-"))
        known = {
            "id", "assetId", "qualifiedName", "name", "displayName", "code", "type",
            "assetType", "kind", "description", "aliases", "domain", "attributes",
            "evidenceRefs", "evidence", "score", "matchedBy",
        }
        attributes = dict(raw.get("attributes") or {})
        attributes.update({key: value for key, value in raw.items() if key not in known})
        evidence = [{
            "provider": capabilities.provider,
            "environment_id": capabilities.environment_id,
            "captured_at": capabilities.captured_at or _now(),
            "snapshot_token": capabilities.snapshot_token,
            "provider_refs": list(raw.get("evidenceRefs") or []),
        }]
        return {
            "id": str(asset_id),
            "type": canonical_type,
            "provider_type": str(raw_type),
            "code": str(_first(raw, "code", "qualifiedName") or asset_id),
            "name": str(name),
            "description": str(raw.get("description") or ""),
            "aliases": [str(value) for value in raw.get("aliases", [])],
            "domain": _optional_string(raw.get("domain")),
            "attributes": attributes,
            "score": float(record.get("score", raw.get("score", 0.0)) or 0.0),
            "matched_by": list(record.get("matchedBy", raw.get("matchedBy", [])) or []),
            "knowledge_layer": "ENVIRONMENT",
            "assertion_status": "EXPLICIT",
            "evidence": evidence,
        }

    def _normalize_relation(
        self,
        raw: Any,
        capabilities: CapabilitySnapshot,
    ) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        source_id = _first(raw, "sourceId", "source_id", "fromId", "from")
        target_id = _first(raw, "targetId", "target_id", "toId", "to")
        predicate = _first(raw, "predicate", "relation", "relationType", "edgeType")
        if not source_id or not target_id or not predicate:
            return None
        relation_id = _first(raw, "id", "relationId", "edgeId") or "relation:" + hashlib.sha256(
            f"{source_id}|{predicate}|{target_id}".encode("utf-8")
        ).hexdigest()[:16]
        return {
            "id": str(relation_id),
            "source_id": str(source_id),
            "predicate": str(predicate),
            "target_id": str(target_id),
            "knowledge_layer": "ENVIRONMENT",
            "assertion_status": "EXPLICIT",
            "evidence": [{
                "provider": capabilities.provider,
                "environment_id": capabilities.environment_id,
                "captured_at": capabilities.captured_at or _now(),
                "snapshot_token": capabilities.snapshot_token,
                "provider_refs": [str(value) for value in raw.get("evidenceRefs", [])],
            }],
        }


def coerce_binding_result(value: Any, *, required: bool) -> EnvironmentBindingResult:
    """Compatibility bridge for older adapters returning ``list[dict]``."""
    if isinstance(value, EnvironmentBindingResult):
        return value
    if isinstance(value, list):
        return EnvironmentBindingResult(
            required=required,
            state=AvailabilityState.FOUND if value else AvailabilityState.PARTIAL,
            assets=[item for item in value if isinstance(item, dict)],
            warnings=[{
                "code": "legacy_environment_adapter",
                "message": "Adapter returned an unversioned legacy asset list.",
            }],
        )
    raise TypeError("environment adapter must return EnvironmentBindingResult or list[dict]")


def _binding_status(required: bool, state: AvailabilityState) -> str:
    if not required:
        return "not_required"
    return {
        AvailabilityState.FOUND: "resolved",
        AvailabilityState.PARTIAL: "partial",
        AvailabilityState.NOT_FOUND_CONFIRMED: "not_found_confirmed",
        AvailabilityState.UNSUPPORTED: "unsupported",
        AvailabilityState.UNAVAILABLE: "unavailable",
        AvailabilityState.TRUNCATED: "truncated",
    }[state]


def _operation_score(operation: str, tool: dict[str, Any], aliases: tuple[str, ...]) -> int:
    name = str(tool.get("name", "")).lower()
    description = str(tool.get("description", "")).lower()
    schema = tool.get("inputSchema", tool.get("input_schema", {})) or {}
    properties = {str(key).lower() for key in (schema.get("properties") or {})}
    if name in aliases:
        return 100
    text = f"{name} {description}"
    if operation == "capabilities" and any(token in text for token in ("capabil", "能力")):
        return 60
    if operation == "search" and any(token in text for token in ("search", "find", "查询", "检索")):
        return 60 + (10 if properties & {"query", "q", "keyword", "searchtext"} else 0)
    if operation == "read" and any(token in text for token in ("get_asset", "read_asset", "asset context", "资产详情")):
        return 60 + (10 if properties & {"id", "assetid"} else 0)
    if operation == "expand" and any(token in text for token in ("expand", "neighbor", "关联扩展")):
        return 60
    return 0


def _unwrap_mcp_result(raw: Any) -> Any:
    if isinstance(raw, dict) and "result" in raw and isinstance(raw["result"], dict):
        raw = raw["result"]
    if isinstance(raw, dict) and raw.get("isError"):
        raise RuntimeError(_text_content(raw) or "MCP tool returned isError=true")
    if isinstance(raw, dict) and isinstance(raw.get("structuredContent"), dict):
        return raw["structuredContent"]
    if isinstance(raw, dict) and isinstance(raw.get("structured_content"), dict):
        return raw["structured_content"]
    if isinstance(raw, dict) and "content" in raw:
        text = _text_content(raw)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("MCP text content is not valid JSON") from exc
    return raw


def _text_content(raw: dict[str, Any]) -> str:
    for item in raw.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            return str(item["text"])
    return ""


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("records", "hits", "assets", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _list_value(mapping: dict[str, Any], *keys: str) -> list[Any]:
    value = _first(mapping, *keys)
    return value if isinstance(value, list) else []


def _optional_string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _warning_for_exception(exc: Exception, fallback_code: str) -> dict[str, Any]:
    if isinstance(exc, PermissionError):
        code = "environment_unauthorized"
    elif isinstance(exc, TimeoutError):
        code = "environment_timeout"
    elif isinstance(exc, (ConnectionError, OSError)):
        code = "environment_unavailable"
    elif isinstance(exc, NotImplementedError):
        code = "environment_operation_unsupported"
    else:
        code = fallback_code
    return {"code": code, "message": str(exc) or exc.__class__.__name__}
