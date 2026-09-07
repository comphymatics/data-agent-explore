"""Query generation receives only a public anchor, never candidate Gold/relations."""
from string import Formatter

TEMPLATES={
    "metric_to_model":"指标「{anchor}」由哪些模型提供？请列出指标和模型。",
    "purpose_to_data":"分析目的「{anchor}」需要哪些指标、维度、模型和字段？请列出能够确定的实体。",
    "model_to_analysis":"模型「{anchor}」支持哪些分析目的和指标？请列出模型及相关实体。",
    "model_to_business":"模型「{anchor}」对应哪些业务对象？请列出模型和业务对象。",
    "field_discovery":"模型「{anchor}」包含哪些字段？请列出模型及完整字段名。",
    "lineage_impact":"模型「{anchor}」的{direction}关联模型有哪些？请列出相关模型。",
}


def generate_query(category,anchor,profile,direction="",paraphraser=None):
    template=profile.query_templates.get(category,TEMPLATES[category])
    fields={name for _,name,_,_ in Formatter().parse(template) if name}
    if fields-{"anchor","direction"}: raise ValueError("query templates may use only anchor and direction")
    query=template.format(anchor=anchor,direction=direction)
    original=query
    if paraphraser is not None:
        query=paraphraser(query)
        if not isinstance(query,str) or not query.strip(): raise ValueError("query paraphraser must return a nonempty string")
    return query,{"method":"query_only_paraphrase" if paraphraser else "template", "original":original,
                  "meaning_preservation":"human review required"}
