"""Opt-in scope extraction from COMPLETE, consecutively extracted PDF pages.

This does not accept sparse-span corpora as proof of page completeness.
"""
from app.statement_scope import title_scope

def annotate_complete_pages(document_id,pages):
    result=[];previous=None;scope='unknown';anchor=None
    for page in pages:
        n=page['page']
        if previous is not None and n<=previous:
            raise ValueError('pages must be unique and ascending')
        if previous is None or n!=previous+1 or not page.get('complete'):
            scope='unknown';anchor=None
        if not page.get('complete'):
            result.append(dict(document_id=document_id,page=n,text=page['text'],statement_scope='unknown',scope_title_page=None))
            previous=n
            continue
        for index,line in enumerate(page['text'].splitlines()):
            marker=title_scope(line)
            if marker is not None:
                scope=marker;anchor=n if marker!='unknown' else None
            result.append(dict(document_id=document_id,page=n,line=index,text=line.strip(),
                statement_scope=scope,scope_title_page=anchor))
        previous=n
    return result
