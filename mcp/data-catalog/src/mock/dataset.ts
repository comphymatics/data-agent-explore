import type { Asset, ContextEdge, Evidence, MetadataDataset } from "../domain/types.js";

const capturedAt = "2026-07-31T00:00:00Z";

function evidence(id: string, sourceType: Evidence["sourceType"], description: string): Evidence {
  return {
    id,
    sourceType,
    sourceUri: `mock-telecom://${id}`,
    capturedAt,
    description,
  };
}

function asset(
  id: string,
  type: Asset["type"],
  code: string,
  name: string,
  description: string,
  domain: string,
  aliases: string[] = [],
  attributes: Record<string, unknown> = {},
): Asset {
  return {
    id,
    type,
    code,
    name,
    description,
    aliases,
    domain,
    attributes,
    evidenceRefs: [`ev:${id}`],
  };
}

function edge(
  id: string,
  sourceId: string,
  predicate: ContextEdge["predicate"],
  targetId: string,
  assertionType: ContextEdge["assertionType"] = "explicit",
  confidence = 1,
): ContextEdge {
  return {
    id,
    sourceId,
    predicate,
    targetId,
    assertionType,
    confidence,
    status: confidence >= 0.85 ? "verified" : "candidate",
    evidenceRefs: [`ev:${id}`],
  };
}

const assets: Asset[] = [
  asset("sid-abe:customer", "SID_ABE", "Customer", "Customer ABE", "客户及客户关系标准语义集合", "Customer"),
  asset("sid-be:customer", "SID_BE", "Customer", "Customer", "获得通信服务的个人或组织", "Customer", ["客户", "用户"]),
  asset("sid-abe:product", "SID_ABE", "Product", "Product ABE", "产品与产品实例标准语义集合", "Product"),
  asset("sid-be:product", "SID_BE", "Product", "Product", "客户实际订购或使用的产品实例", "Product", ["产品实例"]),
  asset("sid-be:product-offering", "SID_BE", "ProductOffering", "Product Offering", "向市场提供的可销售产品方案", "Product", ["套餐", "产品资费"]),
  asset("sid-abe:service", "SID_ABE", "Service", "Service ABE", "客户服务与资源服务标准语义集合", "Service"),
  asset("sid-be:service", "SID_BE", "Service", "Service", "提供给客户的通信服务实例", "Service", ["业务实例"]),
  asset("sid-abe:resource", "SID_ABE", "Resource", "Resource ABE", "支撑服务的网络资源标准语义集合", "Resource"),
  asset("sid-be:resource", "SID_BE", "Resource", "Resource", "用于提供通信服务的逻辑或物理资源", "Resource", ["网络资源"]),
  asset("sid-abe:party", "SID_ABE", "Party", "Party ABE", "个人和组织参与方标准语义集合", "Customer"),
  asset("sid-be:individual", "SID_BE", "Individual", "Individual", "自然人参与方", "Customer", ["个人客户"]),

  asset("logical:customer", "LOGICAL_ENTITY", "Customer", "客户", "统一客户主实体", "Customer", ["用户", "订户"], { grain: "one row per customer" }),
  asset("logical:customer-id", "LOGICAL_ATTRIBUTE", "customerId", "客户标识", "企业级客户唯一标识", "Customer"),
  asset("logical:region-code", "LOGICAL_ATTRIBUTE", "regionCode", "归属地编码", "客户归属省市编码", "Customer"),
  asset("logical:product-instance", "LOGICAL_ENTITY", "ProductInstance", "产品实例", "客户订购后的产品实例", "Product", ["订购实例"], { grain: "one row per customer product instance" }),
  asset("logical:product-instance-id", "LOGICAL_ATTRIBUTE", "productInstanceId", "产品实例标识", "产品实例唯一标识", "Product"),
  asset("logical:offering-id", "LOGICAL_ATTRIBUTE", "productOfferingId", "产品套餐标识", "销售套餐唯一标识", "Product"),
  asset("logical:subscription-status", "LOGICAL_ATTRIBUTE", "subscriptionStatus", "订购状态", "在网、暂停或退订状态", "Product"),
  asset("logical:activation-date", "LOGICAL_ATTRIBUTE", "activationDate", "生效日期", "产品实例生效日期", "Product"),
  asset("logical:termination-date", "LOGICAL_ATTRIBUTE", "terminationDate", "退订日期", "产品实例失效或退订日期", "Product"),
  asset("logical:service", "LOGICAL_ENTITY", "CustomerFacingService", "客户服务", "面向客户交付的通信服务实例", "Service", ["CFS"]),
  asset("logical:service-id", "LOGICAL_ATTRIBUTE", "serviceId", "服务标识", "客户服务实例唯一标识", "Service"),
  asset("logical:resource", "LOGICAL_ENTITY", "NetworkResource", "网络资源", "基站小区、网元等服务支撑资源", "Resource", ["网元", "小区"]),
  asset("logical:cell-id", "LOGICAL_ATTRIBUTE", "cellId", "小区标识", "无线小区唯一标识", "Resource"),
  asset("logical:service-quality", "LOGICAL_ENTITY", "ServiceQualityEvent", "服务质量事件", "客户服务体验和网络质量测量事件", "Service", ["网络质量"], { grain: "one row per subscriber, cell and hour" }),
  asset("logical:drop-call-count", "LOGICAL_ATTRIBUTE", "dropCallCount", "掉话次数", "统计周期内掉话次数", "Service"),
  asset("logical:call-count", "LOGICAL_ATTRIBUTE", "callCount", "通话次数", "统计周期内通话尝试次数", "Service"),

  asset("physical:dim-customer", "PHYSICAL_TABLE", "dim_customer", "客户维表", "客户主数据维表", "Customer", [], { schema: "dw", layer: "DIM", grain: "customer_id" }),
  asset("column:dim-customer.customer-id", "PHYSICAL_COLUMN", "customer_id", "客户标识字段", "客户代理键", "Customer", [], { table: "dim_customer", dataType: "string", primaryKey: true }),
  asset("column:dim-customer.region-code", "PHYSICAL_COLUMN", "region_code", "归属地字段", "客户归属省市编码", "Customer", [], { table: "dim_customer", dataType: "string" }),
  asset("physical:dwd-product-subscription", "PHYSICAL_TABLE", "dwd_product_subscription", "产品订购明细", "客户产品实例及状态变化明细", "Product", ["订购表"], { schema: "dw", layer: "DWD", grain: "product_instance_id" }),
  asset("column:subscription.instance-id", "PHYSICAL_COLUMN", "product_instance_id", "产品实例字段", "产品实例唯一标识", "Product", [], { table: "dwd_product_subscription", dataType: "string", primaryKey: true }),
  asset("column:subscription.customer-id", "PHYSICAL_COLUMN", "customer_id", "订购客户字段", "订购产品的客户标识", "Product", [], { table: "dwd_product_subscription", dataType: "string" }),
  asset("column:subscription.offering-id", "PHYSICAL_COLUMN", "offering_id", "套餐字段", "订购的产品套餐标识", "Product", [], { table: "dwd_product_subscription", dataType: "string" }),
  asset("column:subscription.status", "PHYSICAL_COLUMN", "status_cd", "订购状态字段", "ACTIVE、SUSPENDED 或 TERMINATED", "Product", [], { table: "dwd_product_subscription", dataType: "string" }),
  asset("column:subscription.activation-date", "PHYSICAL_COLUMN", "activation_dt", "生效日期字段", "订购生效日期", "Product", [], { table: "dwd_product_subscription", dataType: "date" }),
  asset("column:subscription.termination-date", "PHYSICAL_COLUMN", "termination_dt", "退订日期字段", "订购退订日期", "Product", [], { table: "dwd_product_subscription", dataType: "date" }),
  asset("physical:dwd-service-instance", "PHYSICAL_TABLE", "dwd_service_instance", "服务实例明细", "产品实例关联的客户服务实例", "Service", [], { schema: "dw", layer: "DWD", grain: "service_id" }),
  asset("column:service.service-id", "PHYSICAL_COLUMN", "service_id", "服务标识字段", "服务实例唯一标识", "Service", [], { table: "dwd_service_instance", dataType: "string" }),
  asset("column:service.product-instance-id", "PHYSICAL_COLUMN", "product_instance_id", "服务产品实例字段", "服务对应的产品实例", "Service", [], { table: "dwd_service_instance", dataType: "string" }),
  asset("physical:dim-cell", "PHYSICAL_TABLE", "dim_cell", "无线小区维表", "网络小区与地理属性", "Resource", [], { schema: "dw", layer: "DIM", grain: "cell_id" }),
  asset("column:cell.cell-id", "PHYSICAL_COLUMN", "cell_id", "小区标识字段", "无线小区唯一标识", "Resource", [], { table: "dim_cell", dataType: "string" }),
  asset("physical:dws-service-quality-hourly", "PHYSICAL_TABLE", "dws_service_quality_hourly", "小时服务质量汇总", "按用户、小区和小时汇总的网络体验指标", "Service", ["网络质量小时表"], { schema: "dw", layer: "DWS", grain: "subscriber_id,cell_id,stat_hour" }),
  asset("column:quality.customer-id", "PHYSICAL_COLUMN", "subscriber_id", "质量事件用户字段", "发生网络行为的客户标识", "Service", [], { table: "dws_service_quality_hourly", dataType: "string" }),
  asset("column:quality.cell-id", "PHYSICAL_COLUMN", "cell_id", "质量事件小区字段", "承载服务的无线小区", "Service", [], { table: "dws_service_quality_hourly", dataType: "string" }),
  asset("column:quality.drop-count", "PHYSICAL_COLUMN", "drop_call_cnt", "掉话次数字段", "小时掉话次数", "Service", [], { table: "dws_service_quality_hourly", dataType: "bigint" }),
  asset("column:quality.call-count", "PHYSICAL_COLUMN", "call_cnt", "通话次数字段", "小时通话尝试次数", "Service", [], { table: "dws_service_quality_hourly", dataType: "bigint" }),

  asset("dimension:region", "DIMENSION", "Region", "地区维度", "按客户归属省市分析", "Customer", ["省份", "地市"], { levels: ["province", "city"] }),
  asset("dimension:product-offering", "DIMENSION", "ProductOffering", "产品套餐维度", "按产品套餐进行分析", "Product", ["套餐维度"]),
  asset("dimension:cell", "DIMENSION", "Cell", "小区维度", "按网络小区分析服务质量", "Resource", ["基站小区"]),
  asset("measure:active-subscriptions", "MEASURE", "active_subscription_count", "在网订购数", "统计时点状态为 ACTIVE 的产品实例数", "Product", [], { aggregation: "count_distinct" }),
  asset("measure:terminated-subscriptions", "MEASURE", "terminated_subscription_count", "退订数", "统计周期内退订的产品实例数", "Product", [], { aggregation: "count_distinct" }),
  asset("measure:drop-calls", "MEASURE", "drop_call_count", "掉话次数", "统计周期内掉话次数合计", "Service", [], { aggregation: "sum" }),
  asset("measure:calls", "MEASURE", "call_count", "通话次数", "统计周期内通话尝试次数合计", "Service", [], { aggregation: "sum" }),
  asset("indicator:churn-rate", "INDICATOR", "product_churn_rate", "产品退订率", "退订产品实例数除以期初在网产品实例数", "Product", ["流失率", "离网率"], { formula: "terminated_subscription_count / opening_active_subscription_count", unit: "%" }),
  asset("indicator:drop-call-rate", "INDICATOR", "drop_call_rate", "掉话率", "掉话次数除以通话次数", "Service", ["通话掉线率"], { formula: "drop_call_count / call_count", unit: "%" }),
  asset("purpose:churn-analysis", "ANALYSIS_PURPOSE", "ChurnAnalysis", "客户流失分析", "识别高退订风险的客户和产品套餐", "Product", ["离网分析"]),
  asset("purpose:network-quality", "ANALYSIS_PURPOSE", "NetworkQualityMonitoring", "网络质量监控", "按地区和小区监控服务体验与掉话问题", "Service", ["网络体验分析"]),
];

const edges: ContextEdge[] = [
  edge("edge:sid-customer-abe", "sid-be:customer", "BELONGS_TO", "sid-abe:customer"),
  edge("edge:sid-product-abe", "sid-be:product", "BELONGS_TO", "sid-abe:product"),
  edge("edge:sid-offering-abe", "sid-be:product-offering", "BELONGS_TO", "sid-abe:product"),
  edge("edge:sid-service-abe", "sid-be:service", "BELONGS_TO", "sid-abe:service"),
  edge("edge:sid-resource-abe", "sid-be:resource", "BELONGS_TO", "sid-abe:resource"),
  edge("edge:logical-customer-sid", "logical:customer", "ALIGNS_WITH", "sid-be:customer", "user_confirmed"),
  edge("edge:logical-product-sid", "logical:product-instance", "ALIGNS_WITH", "sid-be:product", "user_confirmed"),
  edge("edge:logical-service-sid", "logical:service", "ALIGNS_WITH", "sid-be:service", "user_confirmed"),
  edge("edge:logical-resource-sid", "logical:resource", "ALIGNS_WITH", "sid-be:resource", "user_confirmed"),
  edge("edge:table-customer-logical", "physical:dim-customer", "IMPLEMENTS", "logical:customer"),
  edge("edge:col-customer-id-logical", "column:dim-customer.customer-id", "IMPLEMENTS", "logical:customer-id"),
  edge("edge:col-region-logical", "column:dim-customer.region-code", "IMPLEMENTS", "logical:region-code"),
  edge("edge:table-sub-logical", "physical:dwd-product-subscription", "IMPLEMENTS", "logical:product-instance"),
  edge("edge:col-instance-logical", "column:subscription.instance-id", "IMPLEMENTS", "logical:product-instance-id"),
  edge("edge:col-offering-logical", "column:subscription.offering-id", "IMPLEMENTS", "logical:offering-id"),
  edge("edge:col-status-logical", "column:subscription.status", "IMPLEMENTS", "logical:subscription-status"),
  edge("edge:col-activation-logical", "column:subscription.activation-date", "IMPLEMENTS", "logical:activation-date"),
  edge("edge:col-termination-logical", "column:subscription.termination-date", "IMPLEMENTS", "logical:termination-date"),
  edge("edge:table-service-logical", "physical:dwd-service-instance", "IMPLEMENTS", "logical:service"),
  edge("edge:col-service-logical", "column:service.service-id", "IMPLEMENTS", "logical:service-id"),
  edge("edge:table-cell-logical", "physical:dim-cell", "IMPLEMENTS", "logical:resource"),
  edge("edge:col-cell-logical", "column:cell.cell-id", "IMPLEMENTS", "logical:cell-id"),
  edge("edge:table-quality-logical", "physical:dws-service-quality-hourly", "IMPLEMENTS", "logical:service-quality"),
  edge("edge:col-drop-logical", "column:quality.drop-count", "IMPLEMENTS", "logical:drop-call-count"),
  edge("edge:col-calls-logical", "column:quality.call-count", "IMPLEMENTS", "logical:call-count"),

  edge("edge:customer-has-id", "physical:dim-customer", "HAS_COLUMN", "column:dim-customer.customer-id"),
  edge("edge:customer-has-region", "physical:dim-customer", "HAS_COLUMN", "column:dim-customer.region-code"),
  edge("edge:sub-has-instance", "physical:dwd-product-subscription", "HAS_COLUMN", "column:subscription.instance-id"),
  edge("edge:sub-has-customer", "physical:dwd-product-subscription", "HAS_COLUMN", "column:subscription.customer-id"),
  edge("edge:sub-has-offering", "physical:dwd-product-subscription", "HAS_COLUMN", "column:subscription.offering-id"),
  edge("edge:sub-has-status", "physical:dwd-product-subscription", "HAS_COLUMN", "column:subscription.status"),
  edge("edge:sub-has-activation", "physical:dwd-product-subscription", "HAS_COLUMN", "column:subscription.activation-date"),
  edge("edge:sub-has-termination", "physical:dwd-product-subscription", "HAS_COLUMN", "column:subscription.termination-date"),
  edge("edge:service-has-id", "physical:dwd-service-instance", "HAS_COLUMN", "column:service.service-id"),
  edge("edge:service-has-product", "physical:dwd-service-instance", "HAS_COLUMN", "column:service.product-instance-id"),
  edge("edge:cell-has-id", "physical:dim-cell", "HAS_COLUMN", "column:cell.cell-id"),
  edge("edge:quality-has-customer", "physical:dws-service-quality-hourly", "HAS_COLUMN", "column:quality.customer-id"),
  edge("edge:quality-has-cell", "physical:dws-service-quality-hourly", "HAS_COLUMN", "column:quality.cell-id"),
  edge("edge:quality-has-drop", "physical:dws-service-quality-hourly", "HAS_COLUMN", "column:quality.drop-count"),
  edge("edge:quality-has-calls", "physical:dws-service-quality-hourly", "HAS_COLUMN", "column:quality.call-count"),

  edge("edge:region-based-on", "dimension:region", "BASED_ON", "logical:region-code"),
  edge("edge:offering-based-on", "dimension:product-offering", "BASED_ON", "logical:offering-id"),
  edge("edge:cell-based-on", "dimension:cell", "BASED_ON", "logical:cell-id"),
  edge("edge:active-based-on", "measure:active-subscriptions", "BASED_ON", "logical:subscription-status"),
  edge("edge:terminated-based-on", "measure:terminated-subscriptions", "BASED_ON", "logical:termination-date"),
  edge("edge:drop-based-on", "measure:drop-calls", "BASED_ON", "logical:drop-call-count"),
  edge("edge:calls-based-on", "measure:calls", "BASED_ON", "logical:call-count"),
  edge("edge:churn-computed-terminated", "indicator:churn-rate", "CALCULATED_FROM", "measure:terminated-subscriptions"),
  edge("edge:churn-computed-active", "indicator:churn-rate", "CALCULATED_FROM", "measure:active-subscriptions"),
  edge("edge:churn-by-region", "indicator:churn-rate", "ANALYZED_BY", "dimension:region"),
  edge("edge:churn-by-offering", "indicator:churn-rate", "ANALYZED_BY", "dimension:product-offering"),
  edge("edge:drop-rate-drop", "indicator:drop-call-rate", "CALCULATED_FROM", "measure:drop-calls"),
  edge("edge:drop-rate-calls", "indicator:drop-call-rate", "CALCULATED_FROM", "measure:calls"),
  edge("edge:drop-by-region", "indicator:drop-call-rate", "ANALYZED_BY", "dimension:region"),
  edge("edge:drop-by-cell", "indicator:drop-call-rate", "ANALYZED_BY", "dimension:cell"),
  edge("edge:purpose-churn-indicator", "purpose:churn-analysis", "USES", "indicator:churn-rate"),
  edge("edge:purpose-churn-about", "purpose:churn-analysis", "ABOUT", "sid-be:product"),
  edge("edge:purpose-quality-indicator", "purpose:network-quality", "USES", "indicator:drop-call-rate"),
  edge("edge:purpose-quality-about-service", "purpose:network-quality", "ABOUT", "sid-be:service"),
  edge("edge:purpose-quality-about-resource", "purpose:network-quality", "ABOUT", "sid-be:resource"),
];

const edgeEvidence = edges.map((item) =>
  evidence(
    `ev:${item.id}`,
    item.assertionType === "explicit" ? "metadata_api" : "business_definition",
    `${item.sourceId} ${item.predicate} ${item.targetId}`,
  ),
);

const assetEvidence = assets.map((item) =>
  evidence(`ev:${item.id}`, item.type.startsWith("SID_") ? "standard" : "metadata_api", `${item.name} 元数据定义`),
);

export const telecomDataset: MetadataDataset = {
  version: "telecom-demo-2026.07.31",
  generatedAt: capturedAt,
  assets,
  edges,
  evidence: [...assetEvidence, ...edgeEvidence],
};
