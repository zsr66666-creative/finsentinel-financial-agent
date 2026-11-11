"""Conservative balance-sheet scope gate around frozen experimental ranking.

Input MUST preserve source reading order per document/page. No cross-page
propagation is allowed on sparsely extracted documents. Candidates are not answers.
"""
import re
from datetime import date
from app.exact_metric_experiment import exact_search

def title_scope(content):
    label=re.sub(r'\s','',content)
    label=re.sub(r'^[一二三四五六七八九十\d]+[、.．]','',label)
    if label in ('合并资产负债表','合并资产负债表（续）','合并资产负债表(续)'):
        return 'consolidated'
    if label in ('母公司资产负债表','母公司资产负债表（续）','母公司资产负债表(续)'):
        return 'parent'
    # A mention in prose is never a scope anchor. Any other standalone table
    # title invalidates balance-sheet context on the rest of this page.
    if re.fullmatch(r'(合并|母公司)?(利润表|现金流量表|所有者权益变动表|资产负债表)([（(]续[）)])?',label):
        return 'unknown'
    return None

def annotate_scope(rows):
    contexts={};result=[]
    for row in rows:
        # Do not infer document identity from a chunk-ID naming convention.
        key=(row.get('company_code'),row.get('period'),row.get('document_id'),row.get('page'))
        valid_identity=row.get('document_id') is not None and row.get('page') is not None
        marker=title_scope(row.get('text',''))
        if valid_identity and marker is not None:
            contexts[key]=(marker,row['chunk_id'])
        scope,anchor=contexts.get(key,('unknown',None)) if valid_identity else ('unknown',None)
        result.append({**row,'statement_scope':scope,'scope_evidence_id':anchor,
                       'explicit_consolidated_page':scope=='consolidated'})
    return result

def scoped_search(rows,question,*,company_code,period,top_k=5,as_of=None):
    if not company_code or not period or type(top_k) is not int or not 1<=top_k<=20:
        raise ValueError('company, period and top_k 1..20 required')
    if as_of: date.fromisoformat(as_of)
    wants_parent='母公司' in question
    wants_consolidated='合并' in question
    conflict=wants_parent and wants_consolidated
    requested='parent' if wants_parent else ('consolidated' if wants_consolidated else None)
    result=dict(items=[],status='needs_review',requested_scope=requested,
                answer_verified=False,retrieval_mode='scope_guarded_exact_metric',warnings=[])
    if conflict:
        result['warnings']=['multiple_statement_scopes_require_separate_queries']
        return result
    # Scope context is derived before candidate filtering so title anchors are
    # not accidentally dropped. Caller must supply source rows, not scored hits.
    annotated=annotate_scope(rows)
    scoped=[r for r in annotated if r['company_code']==company_code and r['period']==period
            and (not as_of or (r.get('published_at') and r['published_at']<=as_of))]
    unknown=any(r['statement_scope']=='unknown' for r in scoped)
    if requested:
        scoped=[r for r in scoped if r['statement_scope']==requested]
    if not scoped:
        result['warnings']=['statement_scope_unverified' if requested and unknown else 'no_matching_scope_or_period']
        return result
    ranked=exact_search(scoped,question,company_code=company_code,period=period,top_k=top_k)
    # Only exact metric rows are admitted for explicit balance-sheet scope.
    # Lexical near matches can be useful leads, but are not scoped metric hits.
    items=ranked['items']
    if requested:
        items=[r for r in items if r.get('exact_label')]
    result['items']=items
    result['duration_ms']=ranked['duration_ms']
    if items:
        if requested:
            result['status']='candidates'
        else:
            result['warnings']=['statement_scope_not_requested_or_unverified']
    else:
        result['warnings']=['no_exact_metric_in_verified_scope']
    return result
