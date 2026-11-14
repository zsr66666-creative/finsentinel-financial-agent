"""Export fixed BGE to ONNX and measure CPU parity in separate processes.
Artifacts stay private in outputs/. Run export locally, benchmark without torch.
"""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

MODEL = 'BAAI/bge-small-zh-v1.5'
REVISION = '7999e1d3359715c523056ef9478215996d62a620'
PREFIX = '为这个句子生成表示以用于检索相关文章：'
QUESTIONS = ['应收账款是多少？', '立讯精密母公司期末尚未收回的销售货款在哪里披露？', '合并报表中的应收账款余额是什么？', '董事会对报告真实性作出了什么声明？', '财报证据核对' * 100]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['export', 'benchmark'])
    parser.add_argument('--directory', default='outputs/task8-cpu')
    args = parser.parse_args()
    root = Path(args.directory); root.mkdir(parents=True, exist_ok=True)
    if args.mode == 'export':
        import torch
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL, revision=REVISION, local_files_only=True, device='cpu')
        backbone = model[0].auto_model
        backbone.set_attn_implementation('eager')
        class Encoder(torch.nn.Module):
            def __init__(self):
                super().__init__(); self.backbone = backbone
            def forward(self, input_ids, attention_mask, token_type_ids):
                hidden = self.backbone(input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids).last_hidden_state[:, 0]
                return torch.nn.functional.normalize(hidden, p=2, dim=1)
        encoder = Encoder().eval()
        sample = model.tokenizer([PREFIX + QUESTIONS[0]], return_tensors='pt')
        torch.onnx.export(encoder, tuple(sample[k] for k in ['input_ids','attention_mask','token_type_ids']), str(root/'model.onnx'),
            input_names=['input_ids','attention_mask','token_type_ids'], output_names=['embedding'],
            dynamic_axes={k:{0:'batch',1:'sequence'} for k in sample} | {'embedding':{0:'batch'}}, opset_version=17, dynamo=False)
        model.tokenizer.save_pretrained(root)
        references = model.encode([PREFIX+q for q in QUESTIONS], normalize_embeddings=True).tolist()
        (root/'reference.json').write_text(json.dumps(dict(model=MODEL,revision=REVISION,prefix=PREFIX,questions=QUESTIONS,vectors=references)),encoding='utf-8')
        print('Exported:', root.resolve())
    else:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        import psutil
        reference = json.loads((root/'reference.json').read_text(encoding='utf-8'))
        assert reference['revision'] == REVISION
        process = psutil.Process()
        started = perf_counter()
        options = ort.SessionOptions(); options.intra_op_num_threads=1; options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        session=ort.InferenceSession(str(root/'model.onnx'), sess_options=options,providers=['CPUExecutionProvider'])
        tokenizer=Tokenizer.from_file(str(root/'tokenizer.json'))
        tokenizer.enable_truncation(max_length=512)
        load_ms=(perf_counter()-started)*1000
        timings=[]; errors=[]; similarities=[]
        for question, expected in zip(reference['questions'],reference['vectors']):
            for repeat in range(4):
                started=perf_counter(); encoded=tokenizer.encode(PREFIX+question)
                inputs={name:np.array([value],dtype=np.int64) for name,value in [('input_ids',encoded.ids),('attention_mask',encoded.attention_mask),('token_type_ids',encoded.type_ids)]}
                actual=session.run(None,inputs)[0][0]
                timings.append((perf_counter()-started)*1000)
            expected=np.array(expected)
            errors.append(float(np.max(np.abs(actual-expected))))
            similarities.append(float(np.dot(actual,expected)/(np.linalg.norm(actual)*np.linalg.norm(expected))))
        memory=process.memory_info()
        peak=getattr(memory,'peak_wset',memory.rss)
        import sys
        if sys.platform.startswith('linux'):
            import resource
            peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        report=dict(model=MODEL,revision=REVISION,model_sha256=hashlib.sha256((root/'model.onnx').read_bytes()).hexdigest(),
            model_mib=(root/'model.onnx').stat().st_size/1024**2,load_ms=load_ms,rss_mib=memory.rss/1024**2,peak_mib=peak/1024**2,
            timings_ms=timings,max_abs_errors=errors,cosine_similarities=similarities,dimensions=len(actual),
            imported_torch=__import__('sys').modules.get('torch') is not None,
            parity_passed=min(similarities)>0.99999 and max(errors)<0.0001,
            platform=sys.platform, limitations=['Measurements describe this process and platform only','One inference thread; no concurrent load measurement'])
        (root/'assessment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        if not report['parity_passed']:raise SystemExit('parity failed')
if __name__ == '__main__':main()
