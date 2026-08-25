DEFAULT_AUTHORITY = {
    "summary": ["data_dictionary","data_dictionaries","modeling_documents","kpi_definition","kpi_kqi","presales_usecases"],
    "formula": ["kpi_definition","kpi_kqi","metrics"],
    "classification.layer": ["asset_catalog","asset_catalogs","modeling_documents","modeling_standards"],
    "topic_domain": ["modeling_documents","modeling_standards","asset_catalog","asset_catalogs"],
    "topic": ["modeling_documents","modeling_standards","asset_catalog","asset_catalogs"],
    "important_fields": ["data_dictionary","data_dictionaries","runtime_metadata"],
    "lineage.upstream": ["etl","runtime_lineage"],
    "lineage.downstream": ["etl","runtime_lineage"],
    "analysis_purposes": ["presales_usecases","application_documents","modeling_documents"],
}

class SourceAuthorityPolicy:
    def rank(self, section, source_type):
        order = DEFAULT_AUTHORITY.get(section, [])
        try:
            return len(order) - order.index(source_type)
        except ValueError:
            return 0
