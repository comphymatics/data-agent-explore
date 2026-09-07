"""Page-level BM25/exact/vector fusion. Encoders never receive candidates or Graph."""
from collections import Counter, defaultdict
import hashlib
import math
import re

# Versioned local concept features are an offline encoder, not a trained embedding model.
CONCEPTS = (
    ("signal strength", "无线信号强度", "接收信号功率", "rsrp"),
    ("weak coverage", "弱覆盖", "覆盖不足"),
    ("subscriber", "用户", "订户"),
    ("latency", "时延", "延迟"),
    ("throughput", "吞吐量", "传输速率"),
    ("packet loss", "丢包率", "丢包"),
)


class LocalConceptEncoder:
    version = "local-concept-subword/v1"
    channel = "vector"  # fixture ablation, never reported as trained dense

    def encode(self, texts):
        vectors = []
        for text in texts:
            text = str(text).casefold()
            vector = [0.0] * 512
            for i, words in enumerate(CONCEPTS):
                if any(word in text for word in words):
                    vector[i] = 4.0
            words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text)
            for word in set(words):
                slot = 32 + int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 480
                vector[slot] += 0.25
            vectors.append(vector)
        return vectors


def cosine(a, b):
    if len(a) != len(b) or not a or not all(math.isfinite(x) for x in (*a, *b)):
        raise ValueError("encoder returned invalid or incompatible vectors")
    denom = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    if not denom:
        raise ValueError("encoder returned a zero vector")
    return sum(x*y for x, y in zip(a, b))/denom


def hybrid_search(index, query, types=None, scope=None, top_k=8):
    from .page import toks, FACET_ALIASES, CLASSIFICATION_FILTERS, facet_matches
    from enterprise_data_context.models import SearchHit
    if top_k < 1:
        raise ValueError("top_k must be positive")
    eligible = []
    for path in index.docs:
        page = index.pages[path]
        if types and page.context_type not in types:
            continue
        # Governed facets are hard filters, including relation completion later.
        if any(FACET_ALIASES.get(k, k) in CLASSIFICATION_FILTERS and
               not facet_matches(page.facets.get(FACET_ALIASES.get(k, k)), v)
               for k, v in (scope or {}).items()
               if page.context_type in {"physical-model", "logical-model"}):
            continue
        eligible.append(path)
    identifier=(scope or {}).get("symbol")
    if not identifier and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:[_:.][A-Za-z0-9]+)+",query.strip()):
        identifier=query.strip()
    if identifier:
        token=str(identifier).casefold()
        # A named parent Page can contain a focused counter/field query whose symbol
        # deliberately lives only in ElementIndex. Keep that explicit Page anchor.
        def explicit_parent(path):
            page=index.pages[path]
            return any(key and re.search(r"(?<!\w)"+re.escape(str(key).casefold())+r"(?!\w)",query.casefold())
                       for key in [page.name,*page.aliases])
        eligible=[p for p in eligible if token in index.docs[p] or token in
                  {str(k).casefold() for k in [index.pages[p].name,index.pages[p].canonical_id,*index.pages[p].aliases]} or explicit_parent(p)]
    n = max(1, len(index.docs))
    avgdl = sum(sum(tf.values()) for tf in index.docs.values()) / n or 1
    lexical, exact, facets, vectors = {}, {}, {}, {}
    q = Counter(toks(query))
    qnorm = query.casefold().strip()
    for path in eligible:
        tf = index.docs[path]
        dl = sum(tf.values())
        lexical[path] = sum(
            math.log(1 + (n-index.df[t]+0.5)/(index.df[t]+0.5)) *
            (tf[t]*2.2)/(tf[t]+1.2*(0.25+0.75*dl/avgdl))
            for t in q if tf[t]
        )
        page = index.pages[path]
        keys = [page.name, page.canonical_id, *page.aliases]
        for key in keys:
            key = str(key).casefold().strip()
            if key and (key == qnorm or re.search(r"(?<![\w])"+re.escape(key)+r"(?![\w])", qnorm)):
                exact[path] = 1.0
        facets[path] = sum(facet_matches(page.facets.get(FACET_ALIASES.get(k, k)), v)
                           for k, v in (scope or {}).items())
    index.last_warnings = []
    try:
        if not eligible:
            return []
        generation=(index.generation,getattr(index.encoder,"version","custom"))
        if index.vector_generation != generation:
            paths = sorted(index.docs)
            encoded = index.encoder.encode([index.pages[p].l0+"\n"+index.pages[p].l1 for p in paths])
            if len(encoded) != len(paths):
                raise ValueError("encoder returned wrong vector count")
            for vector in encoded:
                cosine(vector, vector)
            index.vectors = dict(zip(paths, encoded))
            index.vector_generation = (index.generation, getattr(index.encoder,"version","custom"))
        query_vector = (index.encoder.encode_query(query) if hasattr(index.encoder,"encode_query")
                        else index.encoder.encode([query])[0])
        vectors = {p: cosine(query_vector, index.vectors[p]) for p in eligible}
        vectors = {p: score for p, score in vectors.items() if score >= 0.25}
    except Exception as exc:
        index.last_warnings = [{"code": "vector_retrieval_unavailable", "message": type(exc).__name__,
                                "encoder": getattr(index.encoder,"version","custom")}]
    scores, reasons = defaultdict(float), defaultdict(list)
    for channel, values, weight in (("exact", exact, 3), ("bm25", lexical, 1),
                                    (getattr(index.encoder,"channel","dense"), vectors, 1), ("facet", facets, 0.25)):
        ranked = sorted((p for p, value in values.items() if value > 0), key=lambda p: (-values[p], p))
        for rank, path in enumerate(ranked, 1):
            scores[path] += weight/(60+rank)
            reasons[path].append(channel)
    ranked = sorted(scores, key=lambda p: (-scores[p], p))[:top_k]
    return [SearchHit(p, index.pages[p].context_type, index.pages[p].name, scores[p],
                      reasons[p], index.pages[p].l0, index.pages[p].l1) for p in ranked]
