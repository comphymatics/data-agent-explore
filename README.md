# Data Agent Explore — Complete Reference Implementation

This repository contains a complete, runnable implementation of two logical modules:

1. **Enterprise Data Context** — compiles partial enterprise Word/Excel/JSON/Markdown/SQL sources into traceable Rich Context Pages, indexes, references and a machine-side graph.
2. **Explore Agent** — understands a query, retrieves a Context Bundle, checks coverage, performs focused expansion, and returns reusable data context.

## Core rules

- Graph for machines; Pages for LLMs.
- Parser-first, LLM-assisted, Agent-evolved.
- Source materials are allowed to be incomplete.
- Absence of evidence is never evidence of absence.
- Explore Agent never reads raw Word/Excel and never traverses raw graph nodes.
- Environment-specific physical-model binding is an adapter boundary, not part of the global context model.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e .[dev]
pytest -q
python scripts/demo.py
```

## Build context from a source directory

```bash
python scripts/build_context.py --source-dir source-materials --out generated
```

## Main runtime API

```python
from enterprise_data_context.runtime import load_runtime
from explore_agent import ExploreAgent

runtime = load_runtime("generated")
agent = ExploreAgent(runtime.retrieval)

bundle = agent.explore("RSRP 有哪些现有模型可以提供？")
print(bundle)
```
