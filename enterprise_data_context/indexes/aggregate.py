"""Aggregate adapter over the existing PageIndex; no second retrieval algorithm."""
from dataclasses import asdict
import json

from .page import PageIndex
from .hierarchy import fingerprint
from ..hierarchy_contracts import VIEWS, AGGREGATE_INDEX_VERSION
from ..models import ContextPage


class CachedEncoder:
    """Only changed L0/L1 documents are re-encoded on PageIndex generations."""
    def __init__(self, encoder):
        self.encoder, self.cache = encoder, {}

    @property
    def version(self):
        return getattr(self.encoder, "version", "custom")

    @property
    def channel(self):
        return getattr(self.encoder, "channel", "dense")

    def encode(self, texts):
        missing = list(dict.fromkeys(t for t in texts if (self.version, t) not in self.cache))
        if missing:
            vectors = self.encoder.encode(missing)
            if len(vectors) != len(missing):
                raise ValueError("encoder returned wrong vector count")
            self.cache.update(((self.version, t), v) for t, v in zip(missing, vectors))
        return [self.cache[(self.version, t)] for t in texts]

    def encode_query(self, query):
        return self.encoder.encode_query(query) if hasattr(self.encoder, "encode_query") else self.encoder.encode([query])[0]


def index_page(page):
    view = page["hierarchy_view"]
    summary = page["views"][view]["L1"]
    # Never index candidate audit, full member lists, evidence or L2 relations.
    fields = {k: summary[k] for k in ("summary", "primary_objects", "core_metrics", "core_dimensions",
                                     "main_purposes", "logical_models", "physical_models")}
    fields.update(hierarchy_view=view, branch_id=page["path"], branch_name=page["name"],
                  aliases=page["aliases"], taxonomy_labels=page["taxonomy_labels"])
    return ContextPage(page["path"], page["path"], "aggregate-context", page["name"], page["aliases"],
                       {"hierarchy_view": view}, page["L0"], json.dumps(fields, ensure_ascii=False, sort_keys=True),
                       {}, [], {}, {})


class AggregatePageIndex:
    def __init__(self, encoder=None):
        from .dense import configured_encoder
        self.encoder = CachedEncoder(encoder if encoder is not None else configured_encoder())
        self.indexes = {view: PageIndex(self.encoder) for view in VIEWS}
        self.fingerprints = {}
        self.pages = {}
        self.last_changed = []
        self.last_warnings = []

    @property
    def manifest(self):
        return {"version": AGGREGATE_INDEX_VERSION, "documents": dict(sorted(self.fingerprints.items()))}

    def expected(self, pages):
        return {p: fingerprint(asdict(index_page(a))) for p, a in pages.items()
                if any(e["active"] and e["status"] in {"CONFIRMED", "DERIVED"}
                       for e in a["views"][a["hierarchy_view"]]["L2"]["relations"])}

    def sync(self, pages):
        expected = self.expected(pages)
        self.last_changed = sorted(p for p in set(expected) | set(self.fingerprints)
                                   if expected.get(p) != self.fingerprints.get(p))
        for path in self.last_changed:
            if path in self.pages:
                self.indexes[self.pages[path]["hierarchy_view"]].remove(path)
            if path in expected:
                self.indexes[pages[path]["hierarchy_view"]].add(index_page(pages[path]))
        self.fingerprints, self.pages = expected, dict(pages)

    def is_current(self, pages):
        expected = self.expected(pages)
        actual = {p: fingerprint(asdict(page)) for index in self.indexes.values() for p, page in index.pages.items()}
        return self.fingerprints == expected == actual

    def search(self, query, views, top_k=9, method="hybrid", scope=None):
        if not views or len(views) > 2 or any(v not in VIEWS for v in views):
            raise ValueError("invalid aggregate search views")
        rows = []
        self.last_warnings = []
        # Separate PageIndex per view guarantees filtering before channel recall.
        for view in views:
            index = self.indexes[view]
            # Scope symbol belongs to the direct anchor, not a branch identifier filter.
            facets = {"hierarchy_view": view}
            if method == "lexical":
                hits = index.baseline_search(query, top_k=top_k)
            else:
                hits = index.search(query, scope=facets, top_k=top_k, candidate_limit=256)
                if index.last_candidate_diagnostics["truncated"]:
                    self.last_warnings.append({"code":"aggregate_candidate_budget", "view":view,
                                               **index.last_candidate_diagnostics})
                self.last_warnings.extend(index.last_warnings)
            for hit in hits:
                page = self.pages[hit.path]; summary = page["views"][view]["L1"]
                breakdown = getattr(index, "last_score_breakdown", {}).get(hit.path, {}) if method == "hybrid" else {"bm25": hit.score}
                # A facet-only hit is not query relevance.
                if method == "hybrid" and not any(breakdown.get(k, 0) > 0 for k in ("exact", "bm25", "dense")):
                    continue
                counts = summary["placement_counts"]
                supported = counts["CONFIRMED"] + counts["DERIVED"]
                quality = supported / max(1, supported + counts["CANDIDATE"])
                score = hit.score * (.9 + .1 * quality)
                rows.append({"path": hit.path, "hierarchy_view": view, "score": score,
                    "score_breakdown": {k: breakdown.get(k, 0.) for k in ("exact", "bm25", "dense", "facet", "rrf")},
                    "dense_encoder": self.encoder.version, "dense_channel": self.encoder.channel,
                    "l0": hit.l0, "member_summary": {k: summary[k] for k in ("member_count", "model_counts", "environment_availability")},
                    "placement_quality": {k.lower(): v for k, v in counts.items()}})
        return sorted(rows, key=lambda r: (-r["score"], r["path"]))[:top_k]
