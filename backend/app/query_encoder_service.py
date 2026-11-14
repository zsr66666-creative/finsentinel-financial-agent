"""Single-session FP32 BGE CPU service; loopback only, no torch dependency."""
import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter

MODEL_ID = 'BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620'
PREFIX = '为这个句子生成表示以用于检索相关文章：'


class Encoder:
    def __init__(self, directory):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        root = Path(directory)
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['model'] != MODEL_ID or manifest['prefix'] != PREFIX:
            raise ValueError('model contract mismatch')
        for name in ('model.onnx', 'tokenizer.json'):
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != manifest['files'][name]:
                raise ValueError('model artifact checksum mismatch')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(root / 'model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(root / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=512)
        self.lock = threading.Lock()

    def encode(self, query):
        return self._encode(PREFIX + query)

    def encode_document(self, content):
        """Administrator batch use only; documents must not carry query instructions."""
        return self._encode(content, reject_truncation=True)

    def _encode(self, content, reject_truncation=False):
        if not self.lock.acquire(blocking=False):
            return None
        try:
            started = perf_counter()
            tokens = self.tokenizer.encode(content)
            if reject_truncation and getattr(tokens, 'overflowing', []):
                raise ValueError('document chunk exceeds token budget')
            inputs = {name: self.np.array([value], dtype=self.np.int64) for name, value in (
                ('input_ids', tokens.ids), ('attention_mask', tokens.attention_mask), ('token_type_ids', tokens.type_ids))}
            vector = self.session.run(None, inputs)[0][0].tolist()
            return dict(vector=vector, model=MODEL_ID, encoding_ms=round((perf_counter() - started) * 1000, 3))
        finally:
            self.lock.release()


def main():
    encoder = Encoder(os.environ['QUERY_ENCODER_MODEL_DIR'])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log query text or vector contents.

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def send_json(self, status, body):
            data = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != '/health':
                return self.send_json(404, {'error': 'not_found'})
            self.send_json(200, dict(status='ok', model=MODEL_ID, dimensions=512, runtime='onnx_cpu_fp32', concurrency=1))

        def do_POST(self):
            if self.path != '/encode':
                return self.send_json(404, {'error': 'not_found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    return self.send_json(413, {'error': 'invalid_body_size'})
                body = json.loads(self.rfile.read(length))
                query = body.get('query')
                if not isinstance(query, str) or not query.strip() or len(query) > 500:
                    return self.send_json(422, {'error': 'invalid_query'})
                result = encoder.encode(query.strip())
                if result is None:
                    return self.send_json(429, {'error': 'busy'})
                self.send_json(200, result)
            except (ValueError, TypeError, AttributeError):
                self.send_json(422, {'error': 'invalid_request'})
            except Exception:
                self.send_json(503, {'error': 'encoder_unavailable'})

    server = ThreadingHTTPServer(('127.0.0.1', 8081), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == '__main__':
    main()
