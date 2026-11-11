"""Read-only, reviewed-document comparison. No LLM, vector model or writes."""
import hashlib
import re
from sqlalchemy import text, bindparam
from app.comparison_query import parse_comparison
from app.evidence_comparison import compare_evidence

SOURCE_SHA='841a3271cddd0e0e6bf9d60e39bda69fa48de13c67300c313395d849bddfa588'
CONTRACTS={
    'parent':dict(metric='002475-2026H1-p63-s4',title='002475-2026H1-p62-fulltext-line117',
                  page=63,title_page=62,label='2、母公司资产负债表',
                  values=('5313841643.82','5620343695.37')),
    'consolidated':dict(metric='002475-2026H1-p60-s20',title='002475-2026H1-p60-s8',
                  page=60,title_page=60,label='1、合并资产负债表',
                  values=('47666294604.50','48438796114.12')),
}


def compare_rows(question,rows):
    rejected=dict(status='needs_review',claim_true=None,evidence_ids=[],
                  reason='missing_or_unverified_evidence')
    plan=parse_comparison(question)
    if plan['status']!='parsed':
        return {**rejected,'reason':plan['reason']}
    if (plan['current_period'],plan['previous_period'])!=('2026-06-30','2025-12-31'):
        return {**rejected,'reason':'period_not_reviewed'}
    contract=CONTRACTS[plan['scope']]
    selected={}
    try:
        for key,page in [('metric',contract['page']),('title',contract['title_page'])]:
            matches=[r for r in rows if r['chunk_id']==contract[key]]
            if len(matches)!=1:
                return rejected
            row=matches[0]; p=row['provenance']; content=p['text']
            if (hashlib.sha256(content.encode('utf-8')).hexdigest()!=row['text_sha256'] or
                p['document_sha256']!=SOURCE_SHA or p['company_code']!='002475' or
                p['period']!='2026H1' or p['document_id']!='002475-2026H1' or
                p['page']!=page or p['statement_scope']!=plan['scope'] or
                p['scope_evidence_id']!=contract['title']):
                return rejected
            selected[key]=p
        if ''.join(selected['title']['text'].split())!=contract['label']:
            return rejected
        lines=[s.strip().replace(',','') for s in selected['metric']['text'].splitlines() if s.strip()]
        if len(lines)!=3 or lines[0]!='应收账款' or any(
            not re.fullmatch(r'\d+\.\d{2}',s) for s in lines[1:]):
            return rejected
        # Reviewed values prevent a self-consistent but substituted source payload.
        if tuple(lines[1:])!=contract['values']:
            return rejected
    except (KeyError,TypeError,AttributeError):
        return rejected
    base=dict(company=plan['company'],metric=plan['metric'],unit='CNY',scope=plan['scope'],
              evidence_ids=[contract['metric'],contract['title']])
    result=compare_evidence(dict(base,value=lines[1],period=plan['current_period']),
        dict(base,value=lines[2],period=plan['previous_period']),relation=plan['relation'])
    return {**result,'company_code':plan['company'],'statement_scope':plan['scope'],
        'current_period':plan['current_period'],'previous_period':plan['previous_period'],
        'current_value':lines[1],'previous_value':lines[2],'relation':plan['relation'],
        'source_sha256':SOURCE_SHA,'data_mode':'reviewed_real_pdf',
        'evidence':[dict(chunk_id=contract[k],page=selected[k]['page']) for k in ('metric','title')],
        'limitations':['restricted_query_grammar','dates_and_unit_from_reviewed_document_contract']}


def compare_persisted(engine,question):
    plan=parse_comparison(question)
    if plan['status']!='parsed' or (plan.get('current_period'),plan.get('previous_period'))!=('2026-06-30','2025-12-31'):
        return compare_rows(question,[])
    if engine.dialect.name!='postgresql':
        raise RuntimeError('PostgreSQL evidence required')
    contract=CONTRACTS[plan['scope']]
    query=text('SELECT chunk_id,text_sha256,provenance FROM document_chunk_embeddings WHERE chunk_id IN :ids').bindparams(bindparam('ids',expanding=True))
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        rows=conn.execute(query,dict(ids=[contract['metric'],contract['title']])).mappings().all()
        result=compare_rows(question,rows)
        conn.rollback()
    return result
