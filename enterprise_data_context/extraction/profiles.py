from dataclasses import dataclass, field

@dataclass
class ExtractorProfile:
    name: str
    source_types: list[str]
    context_type: str
    required: list[str]
    aliases: dict[str, list[str]]
    name_field: str
    sections: dict[str, str]
    refs: dict[str, tuple[str, str]] = field(default_factory=dict)

COMMON = {
    "model": ["model", "model name", "table", "table name", "模型", "模型名称", "表", "表名"],
    "field": ["field", "field name", "column", "column name", "字段", "字段名"],
    "description": ["description", "desc", "说明", "描述", "定义", "模型描述", "字段描述"],
    "layer": ["layer", "分层", "模型层级"],
    "topic_domain": ["topic domain", "domain", "主题域", "数据域"],
    "topic": ["topic", "subject", "主题", "业务主题"],
    "metric": ["metric", "metric name", "kpi", "kqi", "指标", "指标名称"],
    "formula": ["formula", "calculation", "公式", "计算公式", "计算逻辑"],
    "dimension": ["dimension", "dimensions", "维度"],
    "purpose": ["purpose", "analysis purpose", "分析目的", "分析项", "分析能力"],
    "scenario": ["scenario", "use case", "场景", "业务场景"],
    "source": ["source", "data source", "source table", "数据源", "源表", "来源"],
    "grain": ["grain", "粒度", "统计粒度"],
    "object": ["business object", "object", "业务对象"],
    "attribute": ["attribute", "object attribute", "对象属性", "属性"],
}

PROFILES = [
    ExtractorProfile(
        "asset_model", ["asset_catalog", "asset_catalogs", "data_dictionary", "data_dictionaries"],
        "physical-model", ["model"], COMMON, "model",
        {"description":"summary","layer":"classification.layer","topic_domain":"topic_domain","topic":"topic","grain":"grain"}
    ),
    ExtractorProfile(
        "metric", ["kpi_definition","kpi_kqi","kpi","metrics","modeling_documents","presales_usecases"],
        "metric", ["metric"], COMMON, "metric",
        {"description":"summary","formula":"formula","dimension":"dimensions","topic":"topic"},
        {"source":("supported_by","physical-model")}
    ),
    ExtractorProfile(
        "purpose", ["presales_usecases","application_documents","modeling_documents"],
        "analysis-purpose", ["purpose"], COMMON, "purpose",
        {"description":"summary","scenario":"scenarios","metric":"metrics","dimension":"dimensions"}
    ),
    ExtractorProfile(
        "business_object", ["standards","modeling_standards","sid"],
        "business-object", ["object"], COMMON, "object",
        {"description":"summary","attribute":"attributes","topic_domain":"topic_domain","topic":"topic"}
    ),
]
