# Governed LLM Semantic Inference

## 1. Purpose and boundary

LLM inference complements deterministic extraction and mapping when explicit relations
are missing. It proposes reviewable links from APP Features and modeling analyses to
metrics, SID business objects, logical models and physical models.

It does **not** manufacture a complete enterprise fact graph. Every LLM result is a
`CANDIDATE`, even when the target name resolves exactly. Candidate references do not
enter confirmed Backrefs, hierarchy edges or the machine-facing Graph before review.

The inference stage is offline and bounded. It consumes Rich Context Pages from one
immutable snapshot; it never asks an LLM to walk the backend graph node by node.

## 2. Pipeline

```text
immutable Context snapshot
        |
        v
deterministic candidate retrieval
        |  source Rich Page + bounded target Rich Pages
        v
Evidence Pack
        |  SID pages + model pages + modeling-classification catalog
        v
structured LLM completion
        |
        v
schema / target / relation / Evidence validation
        |
        +--> rejected proposal + reason
        |
        v
CANDIDATE ContextFragment + TypedReference
        |
        v
optional candidate-only snapshot -> Review Queue
```

Supported candidate relations:

| Source | Relation | Required target |
|---|---|---|
| APP Feature / modeling analysis | `uses_metric` | `metric` |
| APP Feature / modeling analysis | `analyzes_business_object` | `business-object` |
| APP Feature / modeling analysis | `supported_by_logical_model` | `logical-model` |
| APP Feature / modeling analysis | `supported_by_physical_model` | `physical-model` |

The direct scenario-to-physical-model candidate is useful for retrieval, but its
rationale should normally be supported by the intermediate metric/object/logical-model
pages when those pages are available.

## 3. Fail-closed validation

The model may select only paths present in the bounded `candidate_targets` list and
may cite only paths present in `evidence_catalog`. Each proposal must cite the source
scenario/analysis Page. Unknown paths, relation/target-type mismatches and out-of-pack
Evidence are rejected and recorded.

The model's numeric confidence is descriptive, not an approval decision. A high score
cannot promote a proposal. Promotion requires a separate review workflow or an
approved deterministic rule with its own Evidence.

`PARTIAL` or `UNKNOWN` snapshot coverage remains explicit in every run. Missing target
pages in such a snapshot are missing context, not evidence that no suitable model exists.

## 4. Configuration and secrets

`config/llm-inference.example.json` defines the supported configuration. Only the
environment-variable name is stored in JSON; the API key itself must never be written
to the repository or inference report.

The first provider implementation uses an OpenAI-compatible `/chat/completions`
endpoint and JSON object response mode. Provider/model, prompt version, base snapshot
version and inference run ID are retained with every candidate.

## 5. Outputs and versioning

`scripts/build_semantic_candidates.py` writes:

- `inference-report.json`, validated by
  `contracts/semantic-inference-run.schema.json`;
- `candidate-fragments.jsonl`, compatible with the internal ContextFragment contract;
- optionally, a new immutable candidate snapshot through `--enriched-out`.

The enriched snapshot persists `inference-runs.json`. Its manifest counts inference
runs and candidate references. Snapshot identity includes source fingerprints and the
coverage declaration in addition to canonical Page content.

## 6. Review requirements

Review should display source, target, relation, rationale, confidence, Evidence paths,
provider/model, prompt version and base IndexVersion. Approval and rejection records
are separate governance events. This implementation intentionally stops at candidate
generation; it does not silently implement automatic approval.
