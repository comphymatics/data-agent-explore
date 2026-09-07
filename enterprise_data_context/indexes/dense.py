"""Local trained dense embeddings. No page text leaves this process.

Install the ``dense`` extra; DATA_CONTEXT_DENSE_MODEL can override the multilingual
default. Model loading is lazy; an unavailable model leaves lexical retrieval
usable with an explicit warning. Concept hashing is only an evaluation ablation.
"""
import os
from importlib.metadata import version

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class DisabledDenseEncoder:
    version = "dense/unconfigured"
    channel = "dense"

    def encode(self, texts):
        raise RuntimeError("Configure DATA_CONTEXT_DENSE_MODEL and install the dense extra")


class FastEmbedEncoder:
    channel = "dense"

    def __init__(self, model_name, cache_dir=None, local_files_only=False):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.local_files_only = local_files_only
        self._model = None
        self.version = "fastembed:" + model_name

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir,
                                        local_files_only=self.local_files_only, threads=2)
            self.version = "fastembed:" + version("fastembed") + ":" + self.model_name
        return self._model

    def encode(self, texts):
        return [v.tolist() for v in self._load().passage_embed(texts, batch_size=32)]

    def encode_query(self, query):
        return next(iter(self._load().query_embed(query))).tolist()


def configured_encoder():
    model = os.environ.get("DATA_CONTEXT_DENSE_MODEL", DEFAULT_MODEL)
    return (FastEmbedEncoder(model, os.environ.get("FASTEMBED_CACHE_PATH"),
                             os.environ.get("DATA_CONTEXT_DENSE_LOCAL_ONLY") == "1")
            if model and model != "disabled" else DisabledDenseEncoder())
