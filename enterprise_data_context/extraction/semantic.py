from __future__ import annotations
from typing import Protocol
from enterprise_data_context.models import DocumentIR, ContextFragment

class SemanticProvider(Protocol):
    def extract_fragments(self, document: DocumentIR) -> list[ContextFragment]: ...

class NullSemanticProvider:
    def extract_fragments(self, document):
        return []

class SemanticExtractor:
    """
    Production contract for LLM-assisted extraction.
    It receives structured DocumentIR, never raw binary source files.
    Default provider is conservative and produces no guessed facts.
    """
    def __init__(self, provider=None):
        self.provider = provider or NullSemanticProvider()

    def extract(self, document):
        return self.provider.extract_fragments(document)
