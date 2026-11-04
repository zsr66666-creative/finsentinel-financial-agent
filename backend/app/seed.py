"""Synthetic fixtures. Company names are real, all financial facts are invented."""
from datetime import datetime, timezone

COMPANIES = [('002475','立讯精密'),('002241','歌尔股份'),('601138','工业富联'),('002600','领益智造'),('002456','欧菲光'),('002273','水晶光电'),('300433','蓝思科技'),('300207','欣旺达'),('002384','东山精密'),('002938','鹏鼎控股'),('300408','三环集团'),('002463','沪电股份'),('002916','深南电路'),('300136','信维通信'),('300115','长盈精密'),('002351','漫步者'),('002055','得润电子'),('002635','安洁科技'),('300735','光弘科技'),('002681','奋达科技'),('002402','和而泰'),('300679','电连技术'),('002947','恒铭达'),('603160','汇顶科技')]


def seed(store):
    if store.all('companies'):
        return
    for i, (code, name) in enumerate(COMPANIES):
        store.put('companies', {'id':code, 'code':code, 'name':name, 'industry':'消费电子/电子制造', 'exchange':'SH' if code.startswith('6') else 'SZ', 'data_mode':'synthetic_demo'})
        for year in ('2024','2025'):
            fid = f'{code}-{year}-annual'
            store.put('filings', {'id':fid,'company_id':code,'title':f'{name} {year} 年度演示财报','document_type':'annual_report','published_at':f'{int(year)+1}-04-25','source_url':None,'source_label':'人工构造的教学演示数据，非真实披露','version':'demo-v1','data_mode':'synthetic_demo'})
            values = {'revenue':1000+i*80, 'net_profit':100+i*5, 'gross_margin':25+i%8, 'inventory':180+i*12, 'receivables':160+i*10, 'operating_cash_flow':90+i*4}
            if year == '2025':
                values = {k: round(v * ({'revenue':.82,'net_profit':.68,'gross_margin':.88,'inventory':1.30,'receivables':1.28,'operating_cash_flow':.60}[k] if i%3 == 0 else 1.08),2) for k,v in values.items()}
            for j, (metric,value) in enumerate(values.items()):
                eid = f'{fid}-{metric}'
                text = f'{name}{year}年{metric}为{value}{"%" if metric=="gross_margin" else "百万元"}。演示数据。'
                evidence = {'id':eid,'company_id':code,'filing_id':fid,'document_type':'annual_report','date':f'{int(year)+1}-04-25','period':year,'page':12+j,'paragraph':1,'text':text,'source_url':None,'data_mode':'synthetic_demo'}
                store.put('evidence_spans', evidence)
                store.put('document_chunks', {**evidence,'chunk_index':j})
                store.put('financial_metrics', {'id':eid,'company_id':code,'metric':metric,'value':value,'unit':'%' if metric=='gross_margin' else '百万元','period':year,'source_ids':[eid],'data_mode':'synthetic_demo'})
        if i % 3 == 0:
            eid = f'{code}-2025-annual-net_profit'
            store.put('alerts', {'id':f'alert-{code}-profit','company_id':code,'company_name':name,'title':'净利润与经营现金流同步下降','category':'profitability','severity':'high','status':'pending','period':'2025','summary':'演示财务数据中净利润同比下降 32%，经营现金流同比下降 40%，建议人工复核。','metrics':[{'metric':'net_profit_growth','value':-32,'unit':'%'},{'metric':'operating_cash_flow_growth','value':-40,'unit':'%'}],'calculation':'(68 - 100) / abs(100) × 100 = -32%（首家样本；其他公司采用同等比例）','evidence_ids':[eid,f'{code}-2024-annual-net_profit',f'{code}-2025-annual-operating_cash_flow',f'{code}-2024-annual-operating_cash_flow'],'created_at':'2026-04-26T09:00:00Z','data_mode':'synthetic_demo'})
            store.put('alerts', {'id':f'alert-{code}-working-capital','company_id':code,'company_name':name,'title':'存货及应收账款增速高于收入','category':'working_capital','severity':'medium','status':'pending','period':'2025','summary':'存货同比增长 30%、应收账款增长 28%，收入同比下降 18%。','metrics':[{'metric':'inventory_growth','value':30,'unit':'%'},{'metric':'receivables_growth','value':28,'unit':'%'}],'calculation':'(本期值 − 上期值) / abs(上期值) × 100','evidence_ids':[f'{code}-{year}-annual-{metric}' for metric in ['inventory','receivables','revenue'] for year in ['2024','2025']],'created_at':'2026-04-26T09:00:00Z','data_mode':'synthetic_demo'})
        if i % 6 == 0:
            eid = f'{code}-2025-litigation'
            store.put('evidence_spans', {'id':eid,'company_id':code,'filing_id':f'{code}-2025-annual','document_type':'announcement','date':'2026-03-10','period':'2025','page':1,'paragraph':2,'text':f'{name}演示公告：涉及未决诉讼，尚无法确定最终损失。此内容完全为教学构造。','source_url':None,'data_mode':'synthetic_demo'})
            store.put('alerts', {'id':f'alert-{code}-event','company_id':code,'company_name':name,'title':'未决诉讼事项待跟踪','category':'announcement_event','severity':'medium','status':'pending','period':'2025','summary':'演示公告提及未决诉讼，损失金额尚不确定。','metrics':[],'calculation':None,'evidence_ids':[eid],'created_at':'2026-03-10T09:00:00Z','data_mode':'synthetic_demo'})
    store.put('prompt_versions', {'id':'evidence-v1','version':'evidence-v1','system_prompt':'仅使用工具返回的数值与来源，引用不足时停止输出。','status':'active'})
    for i, (code, _) in enumerate(COMPANIES[:20]):
        for metric in ['revenue','net_profit']:
            evidence_id = f'{code}-2025-annual-{metric}'
            expected = store.get('financial_metrics', evidence_id)['value']
            store.put('eval_cases', {'id':f'gold-{i}-{metric}','company_id':code,'question':f'2025 年 {metric} 是多少？','metric':metric,'period':'2025','expected_value':expected,'tolerance':0.01,'required_evidence_ids':[evidence_id],'source':'synthetic_gold','status':'approved'})
