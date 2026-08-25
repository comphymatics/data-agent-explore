from pathlib import Path
from openpyxl import Workbook
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.runtime import from_compiled
from explore_agent import ExploreAgent

tmp=Path("generated/demo_input.xlsx")
tmp.parent.mkdir(parents=True,exist_ok=True)
wb=Workbook()
ws=wb.active; ws.title="KPI"
ws.append(["指标名称","指标描述","公式","维度","数据源"])
ws.append(["RSRP","无线信号强度","AVG(RSRP)","Cell,Grid","LTE Periodic MR"])
wb.save(tmp)

wb2=Workbook()
ws=wb2.active; ws.title="Models"
ws.append(["模型名称","模型描述","分层","主题","粒度"])
ws.append(["LTE Periodic MR","LTE周期MR明细","ODS","Wireless Coverage","Subscriber,Cell,Time"])
m=Path("generated/demo_model.xlsx"); wb2.save(m)

compiled=ContextCompiler().compile([
    {"id":"demo-kpi","path":str(tmp),"type":"kpi_definition"},
    {"id":"demo-model","path":str(m),"type":"asset_catalog"},
])
runtime=from_compiled(compiled)
bundle=ExploreAgent(runtime.retrieval).explore("RSRP 有哪些现有模型可以提供？")
print(bundle)
