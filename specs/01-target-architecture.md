# Target Architecture

Current code-grounded V1.1 overview: [technical diagram](../docs/architecture/data-explore-v1.1-architecture.html)
and [architecture explanation](../docs/architecture/data-explore-v1.1-architecture.md).

```text
Source Materials
  -> Deterministic Parsers / agreed Template JSON Delivery
  -> Template Schema Gate + Shape Adapters
  -> Context Fragments
  -> Canonical Resolution
  -> Business Semantic Mapping + Section-level Fusion
  -> Typed Reference Resolution
  -> Canonical Context Entities
       |
       +-> Typed Relation Graph + Backrefs
       |     lineage / impact / relation completion (machines only)
       |
       +-> SemanticOrganizationBuilder (existing organization module)
             Explicit Backbone + Governed Rules + Bounded Candidate Overlay
             -> Analysis / Domain / Asset Views (multiple parents, sparse levels)
             -> Deterministic Aggregate Context Pages L0 / L1 / L2
             -> Incremental Hierarchy Branch Index
       |
       +-> Rich Context Pages + Exact / Hybrid / Element indexes
                   |
                   v
         Four read-only Context Tools
         Direct Anchor / Hierarchical / Hybrid (auto routing)
                   |
              Context Assembly
                   |
               Coverage Check
                   |
             Focused Expansion
                   |
              Context Bundle
```

Enterprise Data Context is a Context Engine, separate from the Explore Agent.
This is not an ontology. Rich Context Page is the LLM-facing entity unit; Aggregate
Context Page is a materialized organization view, and Context Bundle is the output
contract. Organization edges never become canonical business facts or graph edges.

Environment Binding remains independent: MetaOne supplies current-environment
assets and explicit relations; enterprise materials supply Reference semantics.
Aggregate availability is unknown until the current Binding V3 overlay verifies
specific member identities. Partial source coverage remains explicit.

New contracts, inference governance and incremental dependencies are specified in
[Semantic Hierarchy](semantic-hierarchy.md), disclosure in
[Progressive Disclosure](progressive-disclosure.md), and serving/ablation in
[Hierarchical Retrieval](hierarchical-retrieval.md).

Parser/Template contracts, Canonical IR, Hybrid Retrieval, Element Search, Coverage,
Binding, snapshot publication governance and the official E2E benchmark remain
independent. The hierarchy snapshot is an additive governed artifact, not a new
source of enterprise truth.
