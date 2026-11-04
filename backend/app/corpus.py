import json
from pathlib import Path


def load_corpus(store, path):
    """Load real corpus records without inventing metrics.

    Each JSONL record follows the ingestion contract: document id, company
    code, metadata, pages[{page,text,spans}], and optional metrics[].
    """
    count = 0
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        company_id = str(doc['company_code'])
        store.put('companies', {'id':company_id,'code':company_id,'name':doc.get('company_name',company_id),'industry':'消费电子/电子制造','exchange':'SH' if company_id.startswith('6') else 'SZ','data_mode':'real_corpus'})
        filing_id = str(doc['id'])
        store.put('filings', {'id':filing_id,'company_id':company_id,'title':doc.get('title',''),'document_type':doc.get('report_type','announcement'),'published_at':doc.get('published_at'),'source_url':doc.get('source_url'),'version':doc.get('sha256'),'data_mode':'real_corpus'})
        for page in doc.get('pages',[]):
            spans = page.get('spans') or [{'start':0,'end':len(page.get('text','')),'text':page.get('text','')}]
            for idx, span in enumerate(spans):
                eid = f'{filing_id}-p{page.get("page",0)}-s{idx}'
                payload = {'id':eid,'company_id':company_id,'filing_id':filing_id,'document_type':doc.get('report_type','announcement'),'date':doc.get('published_at'),'period':doc.get('report_period'),'page':page.get('page',0),'paragraph':idx+1,'text':span.get('text',''),'source_url':doc.get('source_url'),'data_mode':'real_corpus'}
                store.put('evidence_spans',payload)
                store.put('document_chunks',{**payload,'chunk_index':idx})
        for idx, metric in enumerate(doc.get('metrics',[])):
            source_ids = metric.get('source_ids') or []
            mid = f'{filing_id}-metric-{metric["metric"]}-{idx}'
            store.put('financial_metrics', {'id':mid,'company_id':company_id,'metric':metric['metric'],'value':metric['value'],'unit':metric.get('unit',''),'period':str(metric.get('period',doc.get('report_period'))),'source_ids':source_ids,'data_mode':'real_corpus'})
        count += 1
    return {'documents':count,'data_mode':'real_corpus'}
