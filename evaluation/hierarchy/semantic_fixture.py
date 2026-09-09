"""Controlled semantic-channel fixture. Never imported by production code.

The vectors intentionally encode a synthetic bilingual semantic space; they prove
fusion wiring, not learned model quality, and must not be used as a real encoder.
"""
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation
from enterprise_data_context.indexes.aggregate import AggregatePageIndex

SEMANTIC_CASES = [("用户移动过程中网络体验如何分析？", "Mobility"),
                  ("哪里存在信号差、覆盖不足？", "Wireless Coverage")]


class FixtureSemanticEncoder:
    version = "synthetic-bilingual-channel-fixture/v1"
    channel = "dense"

    def encode(self, texts):
        vectors = []
        for text in texts:
            text = text.casefold()
            vectors.append([float("mobility" in text or "移动" in text),
                            float("wireless coverage" in text or "信号差" in text), .01])
        return vectors


def build_semantic_fixture():
    fragments = []
    for i, purpose in enumerate(("Mobility", "Wireless Coverage", "Billing")):
        evidence = [Evidence(SourceLocation("synthetic-catalog", "fixtures/semantic-channel.json", row=i+1))]
        for section, payload in (("identity", {"name": "DATA_" + str(i)}), ("analysis_purposes", [purpose])):
            fragments.append(ContextFragment(f"semantic-{i}-{section}", "physical-model", "DATA_" + str(i), section, payload, evidence=evidence))
    compiled = ContextCompiler(hierarchy_config={"version": "semantic-channel-fixture/v1", "inference_enabled": False}).compile_fragments(fragments)
    index = compiled["hierarchy"]
    index.aggregate_index = AggregatePageIndex(FixtureSemanticEncoder())
    index.aggregate_index.sync(index.aggregate_pages)
    return compiled
