from dataclasses import dataclass
from .retrieval import ContextRetrievalService
from .persistence import load_compiled

@dataclass
class Runtime:
    compiled: dict
    retrieval: ContextRetrievalService

def from_compiled(compiled):
    return Runtime(compiled, ContextRetrievalService(compiled))

def load_runtime(path, index_version=None):
    return from_compiled(load_compiled(path, index_version=index_version))
