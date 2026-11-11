"""Audit complete physical PDF pages 60..63; keep source PDF private."""
import argparse
import hashlib
import json
from pathlib import Path
import pymupdf
from app.contiguous_scope import annotate_complete_pages


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    digest=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if digest != '841a3271cddd0e0e6bf9d60e39bda69fa48de13c67300c313395d849bddfa588':
        raise ValueError('source PDF checksum mismatch')
    with pymupdf.open(args.pdf) as doc:
        pages=[dict(page=n, text=doc[n-1].get_text(), complete=True) for n in range(60,64)]
    rows=annotate_complete_pages('002475-2026H1',pages)
    hits=[r for r in rows if r['text']=='应收账款']
    assert [(r['page'],r['statement_scope']) for r in hits]==[(60,'consolidated'),(63,'parent')]
    result=dict(pdf_sha256=digest,pages=[60,61,62,63],hits=hits,
        limitations=['text extraction checked, not visual/human verified','not integrated into production'])
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: 2 scope anchors checked across 4 complete physical pages')


if __name__=='__main__':
    main()
