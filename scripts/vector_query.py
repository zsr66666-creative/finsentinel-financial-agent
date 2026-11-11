"""Export private query vectors locally; run scoped Top-K on the server."""
import argparse
import json
import os
from pathlib import Path
from scripts.vector_batch import MODEL, REVISION, digest

PREFIX = '为这个句子生成表示以用于检索相关文章：'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['export','search','hybrid'])
    p.add_argument('--disable-vector',action='store_true')
    p.add_argument('--file',required=True)
    p.add_argument('--question',default='立讯精密半年度报告中，董事会对报告真实性作出了什么声明？')
    p.add_argument('--company',default='002475')
    p.add_argument('--period',default='2026H1')
    p.add_argument('--top-k',type=int,default=5)
    p.add_argument('--as-of')
    p.add_argument('--sha256')
    args=p.parse_args()
    path=Path(args.file)
    if args.mode=='export':
        from sentence_transformers import SentenceTransformer
        model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True,device='cpu')
        vector=model.encode([PREFIX+args.question],normalize_embeddings=True)[0].tolist()
        package=dict(model=f'{MODEL}@{REVISION}',question=args.question,query_prefix=PREFIX,
                     embedding=vector,company_code=args.company,period=args.period)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(package,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(sha256=digest(path.read_bytes()),dimensions=len(vector))))
    else:
        from sqlalchemy import create_engine
        from app.pgvector_search import search_vectors
        if not args.sha256 or digest(path.read_bytes())!=args.sha256:
            raise ValueError('query package checksum mismatch')
        package=json.loads(path.read_text(encoding='utf-8'))
        if package['model']!=f'{MODEL}@{REVISION}':
            raise ValueError('query model mismatch')
        engine=create_engine(os.environ['DATABASE_URL'])
        try:
            search=search_vectors
            positional=[package['embedding']]
            if args.mode=='hybrid':
                from app.persisted_hybrid import search_persisted
                search=search_persisted
                positional=[package['question'],None if args.disable_vector else package['embedding']]
            result=search(engine,*positional,model=package['model'],
                company_code=args.company,period=args.period,top_k=args.top_k,as_of=args.as_of)
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:
            engine.dispose()

if __name__=='__main__':
    main()
