"""Per-run tool accounting. Estimates are explicitly distinct from provider token usage."""
import json
from enterprise_data_context.retrieval import _estimate_tokens


def estimate(value):
    return _estimate_tokens(json.dumps(value, ensure_ascii=False, default=str))


class MeteredTools:
    def __init__(self, tools, max_calls=20):
        self.tools = tools
        self.max_calls = max_calls
        self.calls = []

    def __getattr__(self, name):
        if name not in self.tools.ALLOWED:
            raise AttributeError(name)
        def call(*args, **kwargs):
            if len(self.calls) >= self.max_calls:
                raise ValueError("context tool call budget exhausted")
            row = {"tool": name, "input_tokens_estimated": estimate([args, kwargs]),
                   "output_tokens_estimated": 0, "status": "ERROR"}
            self.calls.append(row)
            result = getattr(self.tools, name)(*args, **kwargs)
            row.update(output_tokens_estimated=estimate(result), status="OK")
            return result
        return call

    def report(self):
        return {"tool_calls": len(self.calls), "tool_trace": self.calls,
                "tool_tokens_estimated": sum(r["input_tokens_estimated"]+r["output_tokens_estimated"] for r in self.calls),
                "token_measurement": "unicode-aware estimate; provider usage tracked separately"}
