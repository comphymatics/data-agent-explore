import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.inference import (
    LLMInferenceConfig,
    OpenAICompatibleProvider,
    SemanticInferencePipeline,
)
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation
from enterprise_data_context.persistence import load_compiled, save_compiled


ROOT = Path(__file__).parents[1]


def fragment(fragment_id, context_type, name, section, payload, source_id, status="EXPLICIT"):
    return ContextFragment(
        fragment_id=fragment_id,
        context_type=context_type,
        candidate_name=name,
        section_type=section,
        payload=payload,
        evidence=[Evidence(SourceLocation(source_id, f"{source_id}.json", section=fragment_id))],
        source_type="test",
        status=status,
    )


def inference_fragments():
    return [
        fragment("s-id", "scenario", "Railway Coverage", "identity", {"name": "Railway Coverage"}, "app"),
        fragment("s-role", "scenario", "Railway Coverage", "semantic_role", "app-feature", "app"),
        fragment("s-kind", "scenario", "Railway Coverage", "scenario.kind", "APP_FEATURE", "app"),
        fragment("s-summary", "scenario", "Railway Coverage", "summary", "Analyze railway cell coverage with RSRP", "app"),
        fragment("s-metrics", "scenario", "Railway Coverage", "metrics", ["RSRP"], "app"),
        fragment("m-id", "metric", "RSRP", "identity", {"name": "RSRP"}, "kpi"),
        fragment("m-summary", "metric", "RSRP", "summary", "Reference signal received power", "kpi"),
        fragment("o-id", "business-object", "Cell BE", "identity", {"name": "Cell BE"}, "sid"),
        fragment("o-summary", "business-object", "Cell BE", "summary", "SID cell business entity", "sid"),
        fragment("l-id", "logical-model", "Cell Coverage", "identity", {"name": "Cell Coverage"}, "model"),
        fragment("l-summary", "logical-model", "Cell Coverage", "summary", "Logical cell coverage model", "model"),
        fragment("p-id", "physical-model", "dws_cell_coverage", "identity", {"name": "dws_cell_coverage"}, "catalog"),
        fragment("p-summary", "physical-model", "dws_cell_coverage", "summary", "Physical RSRP coverage model", "catalog"),
    ]


class FakeProvider:
    def infer(self, *, system_prompt, payload):
        assert "CANDIDATE" in system_prompt
        source_path = payload["source_page"]["path"]
        targets = {
            row["context_type"]: row["path"]
            for rows in payload["candidate_targets"].values()
            for row in rows
        }
        return {
            "relationships": [
                {
                    "relation": "uses_metric",
                    "target_path": targets["metric"],
                    "confidence": 0.91,
                    "rationale": "The scenario explicitly lists RSRP.",
                    "evidence_paths": [source_path, targets["metric"]],
                },
                {
                    "relation": "supported_by_physical_model",
                    "target_path": targets["physical-model"],
                    "confidence": 0.72,
                    "rationale": "The model summary describes RSRP coverage.",
                    "evidence_paths": [source_path, targets["physical-model"]],
                },
                {
                    "relation": "uses_metric",
                    "target_path": targets["physical-model"],
                    "confidence": 0.8,
                    "rationale": "Wrong target type and must be rejected.",
                    "evidence_paths": [source_path, targets["physical-model"]],
                },
                {
                    "relation": "supported_by_logical_model",
                    "target_path": "data://logical-models/invented",
                    "confidence": 0.99,
                    "rationale": "Invented targets must be rejected.",
                    "evidence_paths": [source_path],
                },
            ]
        }


def config():
    return LLMInferenceConfig.from_mapping({
        "enabled": True,
        "provider": "openai-compatible",
        "base_url": "https://llm.example.test/v1",
        "model": "fixture-model",
        "candidate_limit_per_type": 5,
    })


def test_llm_config_rejects_embedded_secrets_and_invalid_limits():
    with pytest.raises(ValueError, match="never store the API key"):
        LLMInferenceConfig.from_mapping({
            "enabled": True,
            "base_url": "https://llm.example.test/v1",
            "model": "fixture-model",
            "api_key": "secret",
        })
    with pytest.raises(ValueError, match="environment variable name"):
        LLMInferenceConfig.from_mapping({
            "enabled": True,
            "base_url": "https://llm.example.test/v1",
            "model": "fixture-model",
            "api_key_env": "sk-test-secret",
        })
    with pytest.raises(ValueError, match="candidate_limit_per_type"):
        LLMInferenceConfig.from_mapping({
            "enabled": True,
            "base_url": "https://llm.example.test/v1",
            "model": "fixture-model",
            "candidate_limit_per_type": 0,
        })


def test_openai_compatible_provider_uses_env_secret_and_structured_response(monkeypatch):
    monkeypatch.setenv("FIXTURE_LLM_KEY", "test-secret")
    llm_config = LLMInferenceConfig.from_mapping({
        "enabled": True,
        "provider": "openai-compatible",
        "base_url": "https://llm.example.test/v1",
        "model": "fixture-model",
        "api_key_env": "FIXTURE_LLM_KEY",
        "max_retries": 0,
    })

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": '{"relationships": []}'}}]
            }).encode()

    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return Response()

    provider = OpenAICompatibleProvider(llm_config, opener=opener)
    result = provider.infer(system_prompt="candidate only", payload={"source_page": {}})

    assert result == {"relationships": []}
    assert calls[0][0].full_url == "https://llm.example.test/v1/chat/completions"
    assert calls[0][0].get_header("Authorization") == "Bearer test-secret"
    assert calls[0][1] == 60.0
    assert "test-secret" not in json.dumps(llm_config.public_metadata())


def test_governed_inference_rejects_unbounded_or_mistyped_targets(tmp_path):
    base = ContextCompiler().compile_fragments(inference_fragments())
    save_compiled(base, tmp_path / "base")
    compiled = load_compiled(tmp_path / "base")

    run = SemanticInferencePipeline(config(), FakeProvider()).run(compiled)

    assert run.report["status"] == "PARTIAL"
    assert run.report["proposal_count"] == 2
    assert run.report["rejection_count"] == 2
    assert {row["relation"] for row in run.report["proposals"]} == {
        "uses_metric", "supported_by_physical_model",
    }
    assert {row["reason"] for row in run.report["rejections"]} == {
        "relation_target_type_mismatch", "target_not_in_bounded_candidates",
    }
    assert all(fragment.status == "CANDIDATE" for fragment in run.fragments)
    assert all(
        reference.status == "CANDIDATE"
        for fragment in run.fragments for reference in fragment.references
    )
    schema = json.loads(
        (ROOT / "contracts" / "semantic-inference-run.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(run.report))


def test_candidate_inference_survives_recompile_without_entering_confirmed_graph(tmp_path):
    base = ContextCompiler().compile_fragments(inference_fragments())
    save_compiled(base, tmp_path / "base")
    compiled = load_compiled(tmp_path / "base")
    run = SemanticInferencePipeline(config(), FakeProvider()).run(compiled)
    enriched = ContextCompiler().compile_fragments([*compiled["fragments"], *run.fragments])
    enriched["inference_runs"] = [run.report]

    scenario = next(context for context in enriched["contexts"] if context.name == "Railway Coverage")
    candidate_refs = [reference for reference in scenario.references if reference.status == "CANDIDATE"]
    assert len(candidate_refs) == 2
    assert all(reference.target_path for reference in candidate_refs)
    assert not enriched["graph"].neighbors(scenario.path)
    assert enriched["association_report"]["references_by_status"] == {"CANDIDATE": 2}

    manifest = save_compiled(enriched, tmp_path / "enriched")
    reloaded = load_compiled(tmp_path / "enriched")
    assert manifest["schema_version"] == "1.3"
    assert manifest["counts"]["candidate_references"] == 2
    assert manifest["counts"]["inference_runs"] == 1
    assert reloaded["inference_runs"][0]["run_id"] == run.report["run_id"]
