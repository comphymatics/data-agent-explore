# AGENTS.md

## Mandatory architecture rules

1. This repository implements Data Agent Explore capability.
2. Enterprise Data Context and Explore Agent are separate logical modules with stable contracts.
3. Enterprise Data Context is a Context Engine, not an answering agent.
4. Explore Agent is read-only and returns Context Bundles.
5. This system is NOT an ontology.
6. Backend Graph is machine-facing only.
7. Never implement node-by-node LLM graph traversal.
8. Rich Context Page is the primary LLM-facing information unit.
9. Context Bundle is the primary retrieval/output unit.
10. Prefer few rich reads over many sparse hops.
11. Word/Excel structural parsing must be deterministic.
12. Use Parser-first, LLM-assisted, Agent-evolved extraction.
13. Do not make Code Agent the per-document runtime parser.
14. Extract Context Fragments before Canonical Fusion.
15. Canonical Resolution must precede multi-source fusion.
16. Fusion is section-level and policy-driven; never blind overwrite.
17. Preserve evidence, ambiguity and conflicts.
18. Typed forward references are primary; backrefs are derived.
19. Initial retrieval uses Page-level indexes; field/counter retrieval is focused expansion.
20. Explore may only use data_search/data_read/data_expand/data_source plus an optional Environment Binding adapter.
21. SID and modeling standards are semantic references, not the main Context hierarchy.
22. Physical model/field -> business object/attribute/topic mapping is first-class.
23. source-materials is partial by default.
24. Absence of evidence MUST NOT be treated as evidence of absence.
25. Missing context must be explicit.
26. Major derived content must be traceable to evidence.
27. Environment-specific physical model adaptation is not a global-context responsibility.
28. Keep the end-to-end path runnable.
29. Do not replace this architecture with generic chunk-RAG.
30. Do not redesign contracts without updating schemas, producers, consumers and tests together.
