from __future__ import annotations

from dataclasses import asdict, dataclass


REQUIREMENTS = {
    "metric_to_models": ("metrics", "models"),
    "analysis_data_requirement": ("purpose", "metrics", "dimensions", "models"),
    "model_understanding": ("business_meaning", "business_object", "fields", "grain"),
    "impact_analysis": ("models", "lineage"),
    "generic": ("business_meaning",),
}

EXPANSION = {
    "fields": ["fields"],
    "grain": ["grain"],
    "lineage": ["lineage"],
    "business_object": ["business_mapping"],
    "dimensions": ["dimensions"],
    "metrics": ["metrics"],
    "formula": ["formula"],
    "constraints": ["constraints"],
}


POLICY_DEFAULTS = {
    "metric_to_models": {"top_k": 4, "bundle_k": 8, "token_budget": 1600},
    "analysis_data_requirement": {"top_k": 6, "bundle_k": 12, "token_budget": 2800},
    "model_understanding": {"top_k": 4, "bundle_k": 8, "token_budget": 2200},
    "impact_analysis": {"top_k": 4, "bundle_k": 8, "token_budget": 2200},
    "generic": {"top_k": 4, "bundle_k": 8, "token_budget": 1400},
}


@dataclass(frozen=True)
class ContextPolicy:
    intent: str
    required_coverage: tuple[str, ...]
    top_k: int
    bundle_k: int
    token_budget: int
    max_contexts_per_type: int = 3
    read_content: str = "auto"
    expand_top_k: int = 20

    def to_dict(self):
        row = asdict(self)
        row["required_coverage"] = list(self.required_coverage)
        return row


class CoveragePlanner:
    def plan(self, intent, top_k=None, token_budget=None):
        name = intent if intent in REQUIREMENTS else "generic"
        defaults = POLICY_DEFAULTS[name]
        selected_top_k = defaults["top_k"] if top_k is None else top_k
        if selected_top_k < 1:
            raise ValueError("top_k must be positive")
        selected_budget = defaults["token_budget"] if token_budget is None else token_budget
        if selected_budget < 1:
            raise ValueError("token_budget must be positive")
        return ContextPolicy(
            intent=name,
            required_coverage=REQUIREMENTS[name],
            top_k=selected_top_k,
            bundle_k=max(selected_top_k, defaults["bundle_k"]),
            token_budget=selected_budget,
        )

    def evaluate(self, policy_or_intent, coverage):
        if isinstance(policy_or_intent, ContextPolicy):
            required = policy_or_intent.required_coverage
        else:
            required = REQUIREMENTS.get(policy_or_intent, REQUIREMENTS["generic"])
        if coverage and all(isinstance(row, dict) for row in coverage.values()):
            missing = list(dict.fromkeys(row["aspect"] for row in coverage.values() if row["status"] != "SATISFIED"))
        else:
            missing = [key for key in required if not coverage.get(key, False)]
        expand = []
        for m in missing:
            expand += EXPANSION.get(m,[])
        return missing, list(dict.fromkeys(expand))
