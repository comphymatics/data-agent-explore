"""Conservative generic extraction for semi-structured tables not covered by a named profile."""
import re, uuid
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation

MODEL_HINTS = ("table","model","模型","表名")
FIELD_HINTS = ("field","column","字段")
METRIC_HINTS = ("metric","kpi","kqi","指标")

class HeuristicExtractor:
    def extract(self, doc):
        # Deliberately conservative: only infer table kind, not business facts.
        out = []
        for elem in doc.elements:
            if elem.type != "table" or not elem.headers:
                continue
            joined = " ".join(str(x).lower() for x in elem.headers)
            if not any(x in joined for x in MODEL_HINTS + METRIC_HINTS):
                continue
            # Generic extraction is intentionally left to named profiles when a stable name column exists.
        return out
