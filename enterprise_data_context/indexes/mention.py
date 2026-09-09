"""Query-driven mentions over the existing Page/Element exact dictionaries.

The trie stores vocabulary only. Targets and parent metadata remain owned by the
existing indexes; no second entity or element search index is created.
"""
import re
from bisect import bisect_left
from collections.abc import MutableSet
import unicodedata
from itertools import islice
from time import perf_counter

VERSION = "exact-mention/v1.2"
SYMBOL = re.compile(r"[a-z0-9_]+(?:[.:/\-][a-z0-9_]+)*", re.I)


def normalize(value):
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


class StablePosting(MutableSet):
    """Sorted IDs make bounded prefixes reproducible across processes/reloads.

    Updates pay insertion cost offline; queries do not sort whole postings.
    This replaces the existing posting container, not the index semantics.
    """
    def __init__(self, values=()):
        self.ids = sorted(set(values))

    def __contains__(self, value):
        pos = bisect_left(self.ids, value)
        return pos < len(self.ids) and self.ids[pos] == value

    def __iter__(self):
        return iter(self.ids)

    def __len__(self):
        return len(self.ids)

    def add(self, value):
        pos = bisect_left(self.ids, value)
        if pos == len(self.ids) or self.ids[pos] != value:
            self.ids.insert(pos, value)

    def discard(self, value):
        pos = bisect_left(self.ids, value)
        if pos < len(self.ids) and self.ids[pos] == value:
            self.ids.pop(pos)


class MentionVocabulary:
    def __init__(self):
        self.root = {}
        self.counts = {}

    def add(self, key):
        key = normalize(key)
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] != 1 or not key or SYMBOL.fullmatch(key):
            return
        node = self.root
        for char in key:
            node = node.setdefault(char, {})
        node[None] = key

    def remove(self, key):
        key = normalize(key)
        count = self.counts[key] - 1
        if count:
            self.counts[key] = count
            return
        del self.counts[key]
        node, trail = self.root, []
        for char in key:
            if char not in node:
                return
            trail.append((node, char)); node = node[char]
        node.pop(None, None)
        for parent, char in reversed(trail):
            if parent[char]:
                break
            del parent[char]

    def is_current(self):
        expected = {k for k in self.counts if k and not SYMBOL.fullmatch(k)}
        actual, pending = set(), [self.root]
        while pending:
            node = pending.pop()
            if None in node:
                actual.add(node[None])
            pending.extend(child for key, child in node.items() if key is not None)
        return expected == actual

    def phrases(self, query):
        steps = 0
        for start in range(len(query)):
            node = self.root
            for end in range(start, len(query)):
                steps += 1
                node = node.get(query[end])
                if node is None:
                    break
                if None in node:
                    key = node[None]
                    # ASCII phrase endpoints must not match inside identifiers.
                    if (key[0].isascii() and key[0].isalnum() and start and
                            re.match(r"[a-z0-9_]", query[start-1])):
                        continue
                    if (key[-1].isascii() and key[-1].isalnum() and end+1 < len(query) and
                            re.match(r"[a-z0-9_]", query[end+1])):
                        continue
                    yield key
        self.last_steps = steps


class ExactMentionResolver:
    def __init__(self, page_index, element_index):
        self.indexes = (("page", page_index), ("element", element_index))

    def resolve(self, query, target_limit=100):
        started = perf_counter()
        q = normalize(query)
        candidates = {q}
        for match in SYMBOL.finditer(q):
            candidates.add(match.group())
            candidates.update(re.split(r"[.:/\-]", match.group()))
        for match in re.finditer(r'["“「](.*?)["”」]', q):
            candidates.add(match.group(1).strip())
        for _, index in self.indexes:
            candidates.update(index.mentions.phrases(q))
        candidates.discard("")
        mentions, lookups, targets, truncated = [], 0, 0, False
        for key in sorted(candidates, key=lambda s: (-len(s), s)):
            for source, index in self.indexes:
                lookups += 1
                ids = index.exact.get(key, ())
                if not ids or len(key) < 2 and key != q:
                    continue
                budget = max(0, target_limit-targets)
                chosen = sorted(islice(ids, budget))
                targets += len(chosen)
                truncated |= len(ids) > len(chosen)
                if not chosen:
                    continue
                rows = []
                for target in chosen:
                    if source == "page":
                        page = index.pages[target]
                        rows.append({"target_id": target, "parent_page": target,
                                     "entity_type": page.context_type, "element_type": None})
                    else:
                        row = index.records[target]
                        rows.append({"target_id": target, "parent_page": row["path"],
                                     "entity_type": row["kind"].lower(), "element_type": row["kind"]})
                mentions.append({"text": (match.group() if (match := re.search(re.escape(key), query, re.I)) else key), "normalized": key, "source": source,
                    "target_ids": chosen, "targets": rows, "confidence": 1.0,
                    "match_method": "exact_symbol" if SYMBOL.fullmatch(key) else "exact_alias"})
        return {"mentions": mentions, "diagnostics": {"version": VERSION, "query_length": len(query),
            "mention_candidates_count": len(candidates), "exact_lookups_count": lookups,
            "total_exact_keys": sum(len(index.exact) for _, index in self.indexes),
            "trie_steps": sum(getattr(index.mentions, "last_steps", 0) for _, index in self.indexes),
            "targets_examined": targets, "target_limit": target_limit, "truncated": truncated,
            "anchor_latency_ms": (perf_counter()-started)*1000}}
