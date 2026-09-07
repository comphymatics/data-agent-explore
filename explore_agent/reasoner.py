class JointReasoner:
    """
    Deterministic joint-reasoning baseline. An LLM reasoner can replace this contract,
    but Explore never receives raw documents or raw graph storage.
    """
    def __init__(self, provider=None, limits=None):
        from .bounded import BoundedInference
        self.semantic = BoundedInference(provider, limits)
        self.observations = []

    def reason(self, query, hits, expansions, coverage, environment_assets=None):
        import json
        from hashlib import sha256
        records = []
        for hit in hits:
            # Only rendered rich-page text and governed sections, never graph storage.
            if hit.get("support"):
                records.append({"path": hit["path"], "layer": "REFERENCE", "text": hit.get("content") or hit.get("l1", ""),
                                "evidence": [p["evidence"] for p in hit["support"]]})
            for key in ("fields", "formula", "grain", "business_mapping", "constraints"):
                expanded = expansions.get(hit["path"], {})
                if expanded.get(key) and expanded.get("support"):
                    records.append({"path": hit["path"], "layer": "REFERENCE", "text": json.dumps(expanded[key], ensure_ascii=False),
                                    "evidence": [p["evidence"] for p in expanded["support"]]})
        for asset in environment_assets or []:
            if asset.get("assertion_status") == "EXPLICIT" and asset.get("evidence"):
                records.append({"path": asset["id"], "layer": "ENVIRONMENT", "text": asset.get("description") or asset["name"], "evidence": asset["evidence"]})
        for record in records:
            record["evidence_id"] = "e-"+sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
        by_id = {r["evidence_id"]: r for r in records}
        def validate(value):
            if set(value) != {"observations"} or not isinstance(value["observations"], list) or len(value["observations"]) > 8:
                raise ValueError("invalid joint reasoning response")
            output = []
            for observation in value["observations"]:
                if set(observation) != {"evidence_id", "excerpt"}:
                    raise ValueError("unsupported reasoning assertion")
                record = by_id.get(observation["evidence_id"])
                excerpt = observation["excerpt"]
                if not record or not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 500 or excerpt not in record["text"]:
                    raise ValueError("ungrounded reasoning assertion")
                output.append({**observation, "path": record["path"], "knowledge_layer": record["layer"], "evidence": record["evidence"]})
            return output
        self.observations = self.semantic.invoke("joint_reason", {
            "query": query, "requirements": [{k:v for k,v in r.items() if k != "evidence"} for r in coverage.values()],
            "evidence": records}, validate) or []
        base = self.summarize(query, hits, expansions, environment_assets)
        return base + ("; " + "; ".join(o["knowledge_layer"]+": "+o["excerpt"] for o in self.observations) if self.observations else "")

    def summarize(self,query,hits,expansions,environment_assets=None):
        by_type={}
        for h in hits:
            by_type.setdefault(h["context_type"],[]).append(h["name"])
        parts=[]
        for typ,names in by_type.items():
            parts.append(f"reference/{typ}: {', '.join(names[:5])}")
        environment_by_type={}
        for asset in environment_assets or []:
            environment_by_type.setdefault(asset.get("type","asset"),[]).append(asset.get("name",asset.get("id","unknown")))
        for typ,names in environment_by_type.items():
            parts.append(f"environment/{typ}: {', '.join(str(name) for name in names[:5])}")
        return "; ".join(parts) if parts else "No relevant Context Page was found in currently available sources."
