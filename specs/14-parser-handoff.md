# Parser Template Delivery Contract

The real-document parser/extractor is an external producer. Its stable delivery is
a directory containing one or more JSON data files conforming to the five structures
demonstrated in `source-materials/templates/`:

1. presales APP features;
2. KPI/KQI definitions;
3. physical tables and fields;
4. modeling analysis definitions;
5. the SID business-object knowledge base.

The machine-valid union contract is `contracts/template-input.schema.json`.
Files whose names contain `Schema` document shapes only; they are not facts and are
not interpreted as instructions.

## Producer responsibility

The parser team owns:

- deterministic Word/Excel structural parsing;
- producing one of the five agreed JSON shapes without adding guessed facts;
- retaining source-level identifiers and values required by the agreed shape;
- delivering a complete batch directory rather than `ContextFragment` JSON/JSONL;
- keeping unknown, ambiguous and absent input explicit instead of inventing values.

The producer does not need to know the internal Canonical Context, Rich Context Page,
index, graph or Explore contracts.

## Consumer entrypoint

The production entrypoint is:

```python
compiled = ContextCompiler().compile_template_inputs(delivery_directory)
```

or:

```bash
python scripts/build_template_inputs.py \
  --input parser-delivery-directory \
  --out generated
```

`load_template_inputs()` performs the schema gate, identifies the matching delivery
shape, and converts it into evidence-bearing internal `ContextFragment` IR. Fragment
creation is therefore a consumer-side normalization responsibility.

`ContextCompiler.compile_fragments()` and `scripts/build_fragments.py` remain internal
and backward-compatible APIs. They are not the cross-team contract.

## Consumer responsibility

Downstream owns:

- validating every delivered data file against the Template union schema;
- deterministic shape-specific normalization into internal Context Fragments;
- canonical resolution and ambiguity preservation;
- section-level authority fusion and conflicts;
- business semantic mapping;
- typed reference resolution and derived backrefs;
- Rich Context Page materialization;
- page/element indexes and the machine-only graph;
- immutable `IndexVersion` publication and runtime loading;
- `data_search`, `data_read`, `data_expand`, `data_source`;
- Explore Context Bundle assembly and golden evaluation.

The consumer never reopens the producer's raw Word or Excel file.

## Internal provenance rules

Template adapters must attach JSON-pointer Evidence to every internal Fragment.
Internally, `EXPLICIT` and evidence-complete `DERIVED` content may enter canonical
sections. `INFERRED` and `CANDIDATE` content remains in `candidate_sections` and may
not enter normal indexes, Backrefs or Machine Graph.

## Governed model classification

The formal model layers are `ODS`, `SDL`, `ODI`, and `ADS`. `DWD` and `DWS`
are accepted input aliases and deterministically normalize to `SDL` and `ODI`;
the raw value remains in `classification.layer_raw` and the canonical section is
marked `DERIVED` with modeling-standard Evidence.

SDL topic domains/topics and ODI object domains/subobjects are validated against
the versioned `modeling-classification-3.1` catalog. Unknown declared values remain
in raw sections and `candidate_sections`, produce quality warnings, and never enter
canonical retrieval facets. ODS source-type classification and ADS application
classification remain open as required by the standard.

SID Domain/ABE are semantic references (`semantic_reference.sid_domain` and
`semantic_reference.sid_abe`), not model topic domains.
