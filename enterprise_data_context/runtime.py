from dataclasses import dataclass
from .retrieval import ContextRetrievalService

@dataclass
class Runtime:
    compiled: dict
    retrieval: ContextRetrievalService

def from_compiled(compiled):
    return Runtime(compiled, ContextRetrievalService(compiled))
