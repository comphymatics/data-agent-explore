from __future__ import annotations


class DataContextTools:
    """Platform-neutral, read-only tool surface consumed by Explore."""

    ALLOWED = {"data_search", "data_read", "data_expand", "data_source"}

    def __init__(self, retrieval):
        self.retrieval = retrieval

    def data_search(
        self,
        query,
        scope=None,
        types=None,
        top_k=8,
        bundle_k=None,
        token_budget=None,
        seen_context_ids=None,
        read_content=None,
        max_per_type=None,
        intent=None,
        mode="auto",
        hierarchy=None,
    ):
        return self.retrieval.data_search(
            query=query,
            scope=scope,
            types=types,
            top_k=top_k,
            bundle_k=bundle_k,
            token_budget=token_budget,
            seen_context_ids=seen_context_ids,
            read_content=read_content,
            max_per_type=max_per_type,
            intent=intent,
            mode=mode,
            hierarchy=hierarchy,
        )

    def data_read(self, path, level="L1", sections=None):
        return self.retrieval.data_read(path=path, level=level, sections=sections)

    def data_expand(self, paths, expand, top_k=20, query=None, intent=None, token_budget=None):
        if not isinstance(paths, list) or not paths:
            raise ValueError("paths must be a non-empty list")
        if not isinstance(expand, list) or not expand:
            raise ValueError("expand must be a non-empty list")
        return self.retrieval.data_expand(paths=paths, expand=expand, top_k=top_k, query=query, intent=intent, token_budget=token_budget)

    def data_source(self, path, section=None):
        return self.retrieval.data_source(path=path, section=section)

    def call(self, name, arguments):
        if name not in self.ALLOWED:
            raise ValueError(f"unsupported data context tool: {name}")
        return getattr(self, name)(**dict(arguments or {}))
