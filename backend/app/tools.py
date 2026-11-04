from decimal import Decimal
import math
import re


def calc_growth(current, previous):
    current, previous = Decimal(str(current)), Decimal(str(previous))
    if previous == 0:
        raise ValueError('previous value is zero; growth is undefined')
    return (current - previous) / abs(previous) * Decimal('100')


def detect_anomaly(metric_series, rule):
    if len(metric_series) < 2:
        return {'triggered':False,'reason':'insufficient_data','growth':None}
    growth = float(calc_growth(metric_series[-1], metric_series[-2]))
    if rule not in ('decline_10pct','increase_20pct'):
        raise ValueError('unknown risk rule')
    return {'triggered':growth <= -10 if rule=='decline_10pct' else growth>=20, 'growth':growth, 'rule':rule}


class Tools:
    def __init__(self, store):
        self.store = store

    def get_metric(self, company_id, metric, period):
        record = self.store.get('financial_metrics', f'{company_id}-{period}-annual-{metric}')
        if not record:
            raise ValueError('metric not found')
        return {**record,'calculation':'disclosed value (synthetic fixture)','confidence':1.0}

    def calc_growth(self, company_id, metric, periods):
        if len(periods) != 2:
            raise ValueError('exactly two periods required, previous then current')
        previous, current = [self.get_metric(company_id, metric, p) for p in periods]
        value = float(calc_growth(current['value'], previous['value']))
        return {'value':value,'unit':'%','period':periods[-1],'source_ids':previous['source_ids']+current['source_ids'],'calculation':f"({current['value']} - {previous['value']}) / abs({previous['value']}) × 100",'confidence':1.0}

    def compare_peers(self, company_ids, metric, period):
        values = [self.get_metric(c,metric,period) for c in company_ids]
        return {'value':[{'company_id':r['company_id'],'value':r['value']} for r in sorted(values,key=lambda r:r['value'],reverse=True)],'unit':values[0]['unit'] if values else '', 'period':period,'source_ids':[s for r in values for s in r['source_ids']],'calculation':'descending peer comparison','confidence':1.0}

    def detect_anomaly(self, metric_series, rule):
        return detect_anomaly(metric_series, rule)

    def search_evidence(self, company_id, date_range, document_type, query, limit=5):
        tokens = re.findall(r'[a-z_]+|[\u4e00-\u9fff]', query.lower())
        records = [r for r in self.store.all('evidence_spans') if r['company_id']==company_id and (not document_type or r['document_type']==document_type) and (not date_range or date_range[0]<=r['date']<=date_range[1])]
        # Transparent lexical baseline; does not pretend hash vectors are semantic embeddings.
        ranked = sorted(records,key=lambda r:sum(r['text'].lower().count(t) for t in tokens),reverse=True)
        return {'value':ranked[:limit],'unit':'documents','period':None,'source_ids':[r['id'] for r in ranked[:limit]],'calculation':'filtered lexical term-frequency ranking (demo)','confidence':0.8}

    def build_chart_data(self, company_id, metrics, period_range):
        rows = [r for r in self.store.all('financial_metrics') if r['company_id']==company_id and r['metric'] in metrics and period_range[0]<=r['period']<=period_range[1]]
        return {'value':rows,'unit':'mixed; see row unit','period':period_range,'source_ids':[s for r in rows for s in r['source_ids']],'calculation':'period ordered observations','confidence':1.0}
