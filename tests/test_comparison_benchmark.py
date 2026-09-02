from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.benchmark.adapters.base import RetrievalAdapter
from evaluation.benchmark.adapters.opencode_explore import OpenCodeExploreAdapter
from evaluation.benchmark.adapters.openviking_http import OpenVikingHTTPAdapter
from evaluation.benchmark.corpus import materialize_corpus
from evaluation.benchmark.models import RetrievalResult
from evaluation.benchmark.openviking_import import import_corpus
from evaluation.benchmark.runner import run_benchmark
from evaluation.benchmark.scoring import aggregate_scores, score_result
from evaluation.benchmark.tokens import extract_telemetry_tokens


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "evaluation" / "examples"


def test_materialized_corpus_is_deterministic_and_gold_free(tmp_path):
    corpus_dir = tmp_path / "corpus"
    manifest = materialize_corpus(EXAMPLES, corpus_dir)
    assert manifest["record_count"] == 8
    assert manifest["gold_fields_included"] is False
    pages = sorted(corpus_dir.glob("evidence-pages/**/*.md"))
    assert len(pages) == 8
    combined = "\n".join(path.read_text(encoding="utf-8") for path in pages)
    assert "EVIDENCE_ID: ev-table-mr-cell-hour-field-avg-rsrp" in combined
    assert "ASSERTION_STATUS: CANDIDATE" in combined
    assert "required_evidence" not in combined
    assert "allowed_relevant_evidence" not in combined
    assert "forbidden_evidence" not in combined
    assert "design_oracle" not in combined

    with pytest.raises(ValueError, match="must be empty"):
        materialize_corpus(EXAMPLES, corpus_dir)


def test_scoring_uses_required_allowed_and_forbidden_sets():
    case = json.loads((EXAMPLES / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0])
    result = RetrievalResult(
        system="demo",
        case_id=case["case_id"],
        query_id="base",
        query=case["query"],
        repeat=1,
        evidence_ids=[
            case["required_evidence"][0],
            case["allowed_relevant_evidence"][0],
            case["forbidden_evidence"][0],
        ],
        query_tokens=100,
        token_details={"complete": True},
    )
    known = set(case["required_evidence"] + case["allowed_relevant_evidence"] + case["forbidden_evidence"])
    score = score_result(result, case, known)
    assert score.evidence_recall == pytest.approx(0.25)
    assert score.evidence_precision == pytest.approx(2 / 3)
    assert score.returned_forbidden == case["forbidden_evidence"]
    assert score.token_complete is True
    summary = aggregate_scores([score])["demo"]
    assert summary["token_complete_runs"] == 1


def test_opencode_event_parser_requires_traced_explore_child():
    events = [
        {
            "type": "tool_use",
            "part": {
                "tool": "task",
                "state": {
                    "input": {"subagent_type": "explore"},
                    "metadata": {"sessionId": "ses_child"},
                },
            },
        },
        {"type": "step_finish", "part": {"tokens": {"total": 123}}},
        {"type": "text", "part": {"text": 'EVIDENCE_IDS_JSON=["EV-ONE","ev-two"]'}},
    ]
    stdout = "\n".join(json.dumps(event) for event in events)
    parsed, child_ids, parent_tokens, texts = OpenCodeExploreAdapter._parse_events(stdout)
    evidence_ids, error = OpenCodeExploreAdapter._parse_final_ids(texts)
    assert len(parsed) == 3
    assert child_ids == ["ses_child"]
    assert parent_tokens == 123
    assert evidence_ids == ["ev-one", "ev-two"]
    assert error is None


def test_opencode_uses_private_copy_and_invalidates_mutation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "ev-one.md").write_text("EVIDENCE_ID: ev-one\n", encoding="utf-8")

    class MutatingAdapter(OpenCodeExploreAdapter):
        def _retrieve_in_dir(self, case, query, query_id, repeat, execution_dir):
            (execution_dir / "ev-one.md").write_text("changed\n", encoding="utf-8")
            return RetrievalResult(
                system=self.name,
                case_id=case["case_id"],
                query_id=query_id,
                query=query,
                repeat=repeat,
                evidence_ids=["ev-one"],
            )

    adapter = MutatingAdapter({"primary_agent": "plan"}, source)
    result = adapter.retrieve(
        {"case_id": "case-one", "context_token_budget": 2048},
        "问题",
        "base",
        1,
    )
    assert result.valid is False
    assert result.diagnostics["corpus_mutated"] is True
    assert "modified its private retrieval-corpus copy" in result.error
    assert (source / "ev-one.md").read_text(encoding="utf-8") == "EVIDENCE_ID: ev-one\n"


class StubOpenViking(OpenVikingHTTPAdapter):
    def _request(self, method, path, body=None):
        if path == "/health":
            return {"status": "ok"}
        return {
            "status": "ok",
            "result": {
                "resources": [
                    {"uri": "viking://resources/eval/one", "content": "EVIDENCE_ID: ev-one\n事实一"},
                    {"uri": "viking://resources/eval/two", "content": "EVIDENCE_ID: ev-two\n事实二"},
                ]
            },
            "telemetry": {
                "summary": {"tokens": {"llm": {"input": 7, "output": 3, "total": 10}}}
            },
        }


def test_openviking_adapter_extracts_ids_budget_and_native_tokens(tmp_path):
    adapter = StubOpenViking(
        {"target_uri": "viking://resources/eval", "mode": "search"},
        tmp_path,
    )
    case = {"case_id": "case-one", "context_token_budget": 2048}
    result = adapter.retrieve(case, "问题", "base", 1)
    assert result.valid is True
    assert result.evidence_ids == ["ev-one", "ev-two"]
    assert result.token_details["native_model_tokens"] == 10
    assert result.query_tokens > 10
    assert result.token_details["complete"] is True
    assert result.diagnostics["context_truncated"] is False
    assert extract_telemetry_tokens({"telemetry": {"summary": {"tokens": {"llm": {"input": 4}}}}}) == 4


def test_openviking_import_uses_temp_upload_then_versioned_resource(monkeypatch, tmp_path):
    corpus_dir = tmp_path / "corpus"
    materialize_corpus(EXAMPLES, corpus_dir)
    calls = []

    def fake_request(base_url, method, path, headers, timeout_seconds, **kwargs):
        calls.append((base_url, method, path, headers, timeout_seconds, kwargs))
        if path.endswith("temp_upload"):
            assert kwargs["raw_body"].startswith(b"------data-context-eval-")
            assert "multipart/form-data" in kwargs["content_type"]
            return {"status": "ok", "result": {"temp_file_id": "tmp-123"}}
        return {"status": "ok", "result": {"root_uri": "viking://resources/eval-v1"}}

    module = __import__("evaluation.benchmark.openviking_import", fromlist=["request_json"])
    monkeypatch.setattr(module, "request_json", fake_request)
    result = import_corpus(
        corpus_dir,
        {
            "base_url": "http://127.0.0.1:1933",
            "target_uri": "viking://resources/eval-v1",
            "timeout_seconds": 60,
        },
    )
    assert [call[2] for call in calls] == [
        "/api/v1/resources/temp_upload",
        "/api/v1/resources",
    ]
    add_body = calls[1][5]["body"]
    assert add_body["temp_file_id"] == "tmp-123"
    assert add_body["to"] == "viking://resources/eval-v1"
    assert add_body["preserve_structure"] is True
    assert result["target_uri"] == "viking://resources/eval-v1"


class FakeAdapter(RetrievalAdapter):
    name = "fake"

    def preflight(self):
        return {"fake": True}

    def retrieve(self, case, query, query_id, repeat):
        return RetrievalResult(
            system=self.name,
            case_id=case["case_id"],
            query_id=query_id,
            query=query,
            repeat=repeat,
            evidence_ids=list(case["required_evidence"]),
            query_tokens=42,
            token_details={"complete": True},
        )


def test_runner_writes_resumable_reports(monkeypatch, tmp_path):
    corpus_dir = tmp_path / "corpus"
    materialize_corpus(EXAMPLES, corpus_dir)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"opencode_explore": {"enabled": True}}),
        encoding="utf-8",
    )

    class NamedFake(FakeAdapter):
        name = "opencode_explore"

    monkeypatch.setitem(
        __import__("evaluation.benchmark.runner", fromlist=["ADAPTERS"]).ADAPTERS,
        "opencode_explore",
        NamedFake,
    )
    output_dir = tmp_path / "run"
    summary = run_benchmark(
        dataset_dir=EXAMPLES,
        corpus_dir=corpus_dir,
        config_path=config_path,
        output_dir=output_dir,
        systems=["opencode_explore"],
    )
    assert summary["overall"]["opencode_explore"]["evidence_recall_macro"] == 1.0
    assert (output_dir / "summary.md").is_file()
    assert len((output_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 2

    resumed = run_benchmark(
        dataset_dir=EXAMPLES,
        corpus_dir=corpus_dir,
        config_path=config_path,
        output_dir=output_dir,
        systems=["opencode_explore"],
        resume=True,
    )
    assert resumed["overall"] == summary["overall"]
    assert len((output_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 2
