from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from importlib import resources
from pathlib import Path
import json
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .classification import classify_model
from .models import ContextFragment, Evidence, SourceLocation, TypedReference


class TemplateInputError(ValueError):
    """Raised when a parser delivery file is malformed or unsupported."""


def load_template_inputs(path: str | Path):
    """
    Load the agreed parser delivery JSON formats and normalize them to internal IR.

    Files whose names contain ``Schema`` are shape documentation and are not data.
    The JSON content is treated as data only; strings inside it are never executed as
    instructions. Every data file is validated against the packaged delivery contract
    before dispatching to a shape-specific adapter.
    """
    root = Path(path)
    files = [root] if root.is_file() else sorted(root.glob("*.json"))
    if not files:
        raise TemplateInputError(f"no JSON template inputs found: {root}")

    fragments: list[ContextFragment] = []
    sources: list[dict[str, Any]] = []
    loaded_files: list[dict[str, Any]] = []
    for file_path in files:
        if "schema" in file_path.name.lower():
            continue
        try:
            raw = file_path.read_bytes()
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TemplateInputError(f"invalid JSON template input {file_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise TemplateInputError(f"template input must be a JSON object: {file_path}")

        _validate_template_payload(payload, file_path)
        source_id = f"template:{file_path.stem}"
        kind, generated = _dispatch(payload, source_id, file_path)
        fingerprint = sha256(raw).hexdigest()
        fragments.extend(generated)
        sources.append({"id": source_id, "path": str(file_path), "type": kind, "fingerprint": fingerprint})
        loaded_files.append({"path": str(file_path), "kind": kind, "fragment_count": len(generated)})

    if not loaded_files:
        raise TemplateInputError(f"no data files found after excluding Schema templates: {root}")
    _assert_unique_fragment_ids(fragments)
    return {"fragments": fragments, "sources": sources, "files": loaded_files}


@lru_cache(maxsize=1)
def _template_validator():
    schema_text = resources.files("contracts").joinpath("template-input.schema.json").read_text(
        encoding="utf-8"
    )
    schema = json.loads(schema_text)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_template_payload(payload, path):
    errors = list(_template_validator().iter_errors(payload))
    if not errors:
        return
    nested = [item for root in errors for item in _flatten_schema_errors(root)]
    error = max(
        nested,
        key=lambda item: (len(item.absolute_path), len(item.absolute_schema_path)),
    )
    location = "/" + "/".join(_pointer(part) for part in error.absolute_path)
    raise TemplateInputError(
        f"template delivery schema validation failed at {location} in {path}: {error.message}"
    )


def _flatten_schema_errors(error):
    yield error
    for child in error.context:
        yield from _flatten_schema_errors(child)


def _dispatch(payload, source_id, path):
    keys = set(payload)
    if "apps" in keys:
        return "presales_usecases", _from_apps(payload, source_id, path)
    if {"metric_summaries", "counter_summaries", "dimension"} <= keys:
        return "kpi_kqi", _from_kpi_kqi(payload, source_id, path)
    if "tables" in keys:
        return "asset_catalog", _from_tables(payload, source_id, path)
    if "analysis_groups" in keys:
        return "modeling_documents", _from_modeling(payload, source_id, path)
    if {"metadata", "domains"} <= keys:
        return "sid_standard", _from_sid(payload, source_id, path)
    raise TemplateInputError(f"unsupported template input shape in {path}: top-level keys={sorted(keys)}")


def _from_apps(payload, source_id, path):
    apps = _list(payload, "apps", path)
    out = []
    for ai, app in enumerate(apps):
        app = _object(app, f"apps[{ai}]", path)
        app_name = _name(app, "app_name", f"apps[{ai}]", path)
        app_ptr = f"/apps/{ai}"
        features = _list(app, "features", path, app_ptr)
        scenario_names = [_name(x, "feature_name", f"{app_ptr}/features/{fi}", path) for fi, x in enumerate(features)]
        out += _context_fragments(
            source_id, path, "topic", app_name, app_ptr, "presales_usecases",
            sections={"scenarios": scenario_names},
        )
        for fi, feature in enumerate(features):
            feature = _object(feature, f"{app_ptr}/features/{fi}", path)
            ptr = f"{app_ptr}/features/{fi}"
            name = _name(feature, "feature_name", ptr, path)
            metric_names = _string_list(
                _object(feature.get("feature_description", {}), f"{ptr}/feature_description", path).get("metric_name", []),
                f"{ptr}/feature_description/metric_name", path,
            )
            refs = [_ref("part_of", app_name, "topic", source_id, path, ptr)]
            refs += [_ref("uses_metric", metric, "metric", source_id, path, f"{ptr}/feature_description/metric_name") for metric in metric_names]
            sections = {
                "summary": feature.get("feature_summary"),
                "customer_value": feature.get("customer_value"),
                "metrics": metric_names,
            }
            out += _context_fragments(
                source_id, path, "scenario", name, ptr, "presales_usecases",
                sections=sections, references=refs, features={"topic": app_name},
            )
    return out


def _from_kpi_kqi(payload, source_id, path):
    out = []
    for si, summary in enumerate(_list(payload, "metric_summaries", path)):
        ptr = f"/metric_summaries/{si}"
        summary = _object(summary, ptr, path)
        for mi, metric in enumerate(_list(summary, "metrics", path, ptr)):
            mptr = f"{ptr}/metrics/{mi}"
            metric = _object(metric, mptr, path)
            name = _name(metric, "metric_name", mptr, path)
            counters = _string_list(metric.get("related_counters", []), f"{mptr}/related_counters", path)
            dimensions = _string_list(metric.get("related_dimensions", []), f"{mptr}/related_dimensions", path)
            refs = [_ref("calculated_from", x, "metric", source_id, path, f"{mptr}/related_counters") for x in counters]
            refs += [_ref("grouped_by", x, "dimension", source_id, path, f"{mptr}/related_dimensions") for x in dimensions]
            sections = {
                "summary": metric.get("description"),
                "formula": metric.get("calculation_formula"),
                "related_sdr_field_formula": metric.get("related_sdr_field_formula"),
                "metrics": counters,
                "dimensions": dimensions,
                "unit": metric.get("unit"),
                "interface": metric.get("interface"),
                "metric_group": metric.get("metric_group"),
                "metric_type": metric.get("metric_type") or summary.get("summary_type"),
            }
            out += _context_fragments(
                source_id, path, "metric", name, mptr, "kpi_definition",
                sections=sections, references=refs,
            )

    for si, summary in enumerate(_list(payload, "counter_summaries", path)):
        ptr = f"/counter_summaries/{si}"
        summary = _object(summary, ptr, path)
        for ci, counter in enumerate(_list(summary, "counters", path, ptr)):
            cptr = f"{ptr}/counters/{ci}"
            counter = _object(counter, cptr, path)
            name = _name(counter, "counter_name", cptr, path)
            alias = str(counter.get("counter_name_en") or "").strip()
            dimensions = _string_list(counter.get("related_dimensions", []), f"{cptr}/related_dimensions", path)
            field = _object(counter.get("field", {}), f"{cptr}/field", path)
            field_payload = [field] if any(v not in (None, "", [], {}) for v in field.values()) else []
            refs = [_ref("grouped_by", x, "dimension", source_id, path, f"{cptr}/related_dimensions") for x in dimensions]
            sections = {
                "summary": counter.get("description") or counter.get("field_description"),
                "formula": counter.get("counter_formula"),
                "important_fields": field_payload,
                "dimensions": dimensions,
                "record_sources": counter.get("sources"),
                "application": summary.get("application"),
                "metric_type": "counter",
            }
            out += _context_fragments(
                source_id, path, "metric", name, cptr, "kpi_definition",
                sections=sections, references=refs,
                aliases=[alias] if alias and alias != name else [],
            )

    for di, dimension in enumerate(_list(payload, "dimension", path)):
        ptr = f"/dimension/{di}"
        dimension = _object(dimension, ptr, path)
        name = _name(dimension, "dimension_name", ptr, path)
        sdr_name = str(dimension.get("sdr_name") or "").strip()
        refs = [_ref("provided_by", sdr_name, "physical-model", source_id, path, ptr)] if sdr_name else []
        sections = {
            "summary": dimension.get("description") or dimension.get("field_definition"),
            "important_fields": [x for x in [dimension.get("field_name")] if x],
            "data_type": dimension.get("data_type"),
            "physical_models": [sdr_name] if sdr_name else [],
        }
        out += _context_fragments(source_id, path, "dimension", name, ptr, "kpi_definition", sections=sections, references=refs)
    return out


def _from_tables(payload, source_id, path):
    out = []
    for ti, table in enumerate(_list(payload, "tables", path)):
        ptr = f"/tables/{ti}"
        table = _object(table, ptr, path)
        name = _name(table, "table_name", ptr, path)
        columns = [_object(x, f"{ptr}/columns/{ci}", path) for ci, x in enumerate(_list(table, "columns", path, ptr))]
        field_rows = []
        metric_names, dimension_names = [], []
        refs = []
        for ci, column in enumerate(columns):
            cptr = f"{ptr}/columns/{ci}"
            column_name = _name(column, "column_name", cptr, path)
            field_rows.append({k: column.get(k) for k in (
                "column_name", "column_description", "data_type", "content_decription",
                "catagory", "corresponding_counter_or_dim", "unit", "source_columns",
                "processing_logic", "supported_scenarios",
            ) if column.get(k) not in (None, "", [], {})})
            category = str(column.get("catagory") or "").lower()
            target = str(column.get("corresponding_counter_or_dim") or "").strip()
            if target and any(x in category for x in ("指标", "度量", "counter", "metric")):
                metric_names.append(target)
                refs.append(_ref("implements_metric", target, "metric", source_id, path, cptr))
            if target and any(x in category for x in ("维度", "dimension")):
                dimension_names.append(target)
                refs.append(_ref("implements_dimension", target, "dimension", source_id, path, cptr))
        source = _object(table.get("source", {}), f"{ptr}/source", path)
        upstream = _string_list(source.get("source_tables", []), f"{ptr}/source/source_tables", path)
        refs += [_ref("upstream_model", x, "physical-model", source_id, path, f"{ptr}/source/source_tables") for x in upstream]
        logical_name = str(table.get("logic_model_name") or "").strip()
        if logical_name:
            refs.append(_ref("implements_logical_model", logical_name, "logical-model", source_id, path, ptr))
        classification = classify_model(table.get("layer"), table.get("domain"), table.get("topic"))
        layer = classification["layer"]
        domain = classification["topic_domain"]
        topic = classification["topic"]
        sections = {
            "summary": table.get("table_description"),
            "classification.layer_raw": layer["raw"],
            "classification.topic_domain_raw": domain["raw"],
            "classification.topic_raw": topic["raw"],
            "classification.taxonomy_version": classification["taxonomy_version"],
            "classification.status": classification["status"],
            "classification.issues": classification["issues"],
            "model_type": table.get("model_type"),
            "grain": [table.get("granularity")] if table.get("granularity") else [],
            "storage": table.get("storage"),
            "applications": [table.get("app_name")] if table.get("app_name") else [],
            "lineage.upstream": upstream,
            "processing_logic": source.get("processing_logic"),
            "important_fields": field_rows,
            "metrics": list(dict.fromkeys(metric_names)),
            "dimensions": list(dict.fromkeys(dimension_names)),
        }
        section_statuses = {"metrics": "DERIVED", "dimensions": "DERIVED"}
        for section, result in (
            ("classification.layer", layer), ("topic_domain", domain), ("topic", topic),
        ):
            if result["canonical"]:
                sections[section] = result["canonical"]
                if result["status"] in {"ALIAS", "APPROXIMATE_ALIAS"}:
                    section_statuses[section] = "DERIVED"
            elif result["raw"]:
                sections[section] = result["raw"]
                section_statuses[section] = "CANDIDATE"
        governed_sections = {
            "classification.layer", "topic_domain", "topic",
            "classification.taxonomy_version", "classification.status", "classification.issues",
        }
        standard_evidence = _modeling_standard_evidence()
        out += _context_fragments(
            source_id, path, "physical-model", name, ptr, "asset_catalog",
            sections=sections, references=refs,
            identity_hints={"physical_name": name},
            section_statuses=section_statuses,
            section_source_types={"important_fields": "data_dictionary"},
            section_evidence={section: standard_evidence for section in governed_sections},
        )
    return out


def _from_modeling(payload, source_id, path):
    out = []
    for gi, group in enumerate(_list(payload, "analysis_groups", path)):
        gptr = f"/analysis_groups/{gi}"
        group = _object(group, gptr, path)
        group_name = _name(group, "analysis_name", gptr, path)
        summaries = _list(group, "analysis_summaries", path, gptr)
        purpose_names = [_name(x, "analysis_type", f"{gptr}/analysis_summaries/{si}", path) for si, x in enumerate(summaries)]
        out += _context_fragments(source_id, path, "topic", group_name, gptr, "modeling_documents", sections={"analysis_purposes": purpose_names})
        for si, summary in enumerate(summaries):
            sptr = f"{gptr}/analysis_summaries/{si}"
            summary = _object(summary, sptr, path)
            purpose_name = _name(summary, "analysis_type", sptr, path)
            metrics = []
            metric_rows = []
            for ti, table in enumerate(_list(summary, "calculation_metric_tables", path, sptr)):
                tptr = f"{sptr}/calculation_metric_tables/{ti}"
                table = _object(table, tptr, path)
                table_name = str(table.get("table_name") or "").strip()
                for mi, metric in enumerate(_list(table, "calculation_metrics", path, tptr)):
                    mptr = f"{tptr}/calculation_metrics/{mi}"
                    metric = _object(metric, mptr, path)
                    metric_name = _name(metric, "metric_name", mptr, path)
                    metrics.append(metric_name)
                    metric_rows.append({"name": metric_name, "table": table_name})
                    dimensions = [metric.get("dimensions")] if metric.get("dimensions") else []
                    out += _context_fragments(
                        source_id, path, "metric", metric_name, mptr, "modeling_documents",
                        sections={
                            "formula": metric.get("calculation_formula"),
                            "measurement_point": metric.get("measurement_point"),
                            "interfaces": [metric.get("interfaces")] if metric.get("interfaces") else [],
                            "probes": [metric.get("probes")] if metric.get("probes") else [],
                            "dimensions": dimensions,
                        },
                        references=[_ref("used_by", purpose_name, "analysis-purpose", source_id, path, mptr)],
                    )
            refs = [_ref("part_of", group_name, "topic", source_id, path, sptr)]
            refs += [_ref("uses_metric", name, "metric", source_id, path, sptr) for name in metrics]
            out += _context_fragments(
                source_id, path, "analysis-purpose", purpose_name, sptr, "modeling_documents",
                sections={"summary": summary.get("description"), "metrics": list(dict.fromkeys(metrics)), "metric_catalog": metric_rows},
                references=refs, features={"topic": group_name},
            )
    return out


def _from_sid(payload, source_id, path):
    domains = _object(payload.get("domains"), "/domains", path)
    out = []
    for domain_name, domain in domains.items():
        dptr = f"/domains/{_pointer(domain_name)}"
        domain = _object(domain, dptr, path)
        abes = _object(domain.get("abes"), f"{dptr}/abes", path)
        for abe_name, abe in abes.items():
            aptr = f"{dptr}/abes/{_pointer(abe_name)}"
            abe = _object(abe, aptr, path)
            bes = _object(abe.get("bes"), f"{aptr}/bes", path)
            for be_name, be in bes.items():
                bptr = f"{aptr}/bes/{_pointer(be_name)}"
                be = _object(be, bptr, path)
                source_table = str(be.get("source_table") or "").strip()
                refs = [_ref("represented_by", source_table, "physical-model", source_id, path, bptr)] if source_table else []
                out += _context_fragments(
                    source_id, path, "business-object", be_name, bptr, "sid_standard",
                    sections={
                        "summary": be.get("description"),
                        "attributes": _list(be, "attributes", path, bptr),
                        "semantic_reference.sid_domain": domain_name,
                        "semantic_reference.sid_abe": abe_name,
                        "sid_source": be.get("source"),
                        "source_table": source_table,
                        "gb922_predefined": be.get("gb922_predefined"),
                    },
                    references=refs,
                )
    return out


def _context_fragments(
    source_id, path, context_type, name, pointer, source_type, *, sections,
    references=None, aliases=None, identity_hints=None, features=None,
    section_statuses=None, section_source_types=None, section_evidence=None,
):
    evidence = _evidence(source_id, path, pointer)
    common = dict(
        context_type=context_type, candidate_name=name,
        aliases=list(aliases or []), identity_hints=dict(identity_hints or {}),
        features=dict(features or {}), source_type=source_type,
        confidence=1.0, status="EXPLICIT",
    )
    out = [ContextFragment(
        fragment_id=_fragment_id(source_id, pointer, context_type, name, "identity"),
        section_type="identity", payload={"name": name}, evidence=evidence, **common,
    )]
    for section, value in sections.items():
        if value in (None, "", [], {}):
            continue
        section_status = (section_statuses or {}).get(section, "EXPLICIT")
        evidence_for_section = evidence + list((section_evidence or {}).get(section, []))
        section_source_type = (section_source_types or {}).get(section, source_type)
        out.append(ContextFragment(
            fragment_id=_fragment_id(source_id, pointer, context_type, name, section),
            section_type=section, payload=value, evidence=evidence_for_section,
            **{**common, "status": section_status, "source_type": section_source_type},
        ))
    if references:
        out.append(ContextFragment(
            fragment_id=_fragment_id(source_id, pointer, context_type, name, "references"),
            section_type="references", payload=[], references=list(references), evidence=evidence, **common,
        ))
    return out


def _ref(relation, raw_target, target_type, source_id, path, pointer):
    return TypedReference(
        relation=relation, raw_target=str(raw_target), target_type=target_type,
        status="UNRESOLVED", confidence=0.0,
        evidence=_evidence(source_id, path, pointer),
    )


def _evidence(source_id, path, pointer):
    return [Evidence(SourceLocation(source_id=source_id, path=str(path), section=pointer), note="parser-output JSON path")]


def _modeling_standard_evidence():
    return [Evidence(
        SourceLocation(
            source_id="modeling-standard:3.1",
            path="source-materials/数据模型设计和开发规范3.1.md",
            section="模型分层分域规范 / 统一命名规范",
        ),
        note="modeling-classification-3.1 governed normalization",
    )]


def _fragment_id(source_id, pointer, context_type, name, section):
    raw = "\x1f".join((source_id, pointer, context_type, name, section))
    return f"tpl-{sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _assert_unique_fragment_ids(fragments: Iterable[ContextFragment]):
    seen = set()
    for fragment in fragments:
        if fragment.fragment_id in seen:
            raise TemplateInputError(f"duplicate fragment id generated: {fragment.fragment_id}")
        seen.add(fragment.fragment_id)


def _object(value, location, path):
    if not isinstance(value, dict):
        raise TemplateInputError(f"expected object at {location} in {path}")
    return value


def _list(container, key, path, location=""):
    value = container.get(key)
    if not isinstance(value, list):
        where = f"{location}/{key}" if location else f"/{key}"
        raise TemplateInputError(f"expected array at {where} in {path}")
    return value


def _name(container, key, location, path):
    container = _object(container, location, path)
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TemplateInputError(f"expected non-empty string at {location}/{key} in {path}")
    return value.strip()


def _string_list(value, location, path):
    if value in (None, ""):
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise TemplateInputError(f"expected string array at {location} in {path}")
    return [x.strip() for x in value if x.strip()]


def _pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")
