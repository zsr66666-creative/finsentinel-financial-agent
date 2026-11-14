"""Small loopback encoder client; the API never imports torch/onnxruntime."""
import math
import os
import threading
import requests

MODEL_ID = 'BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620'
_slots = threading.BoundedSemaphore(1)


class QueryServiceError(Exception):
    def __init__(self, message='encoder unavailable', *, status_code=503):
        super().__init__(message)
        self.status_code = status_code


def validate_embedding(body):
    vector = body.get('vector')
    duration = body.get('encoding_ms')
    if (body.get('model') != MODEL_ID or not isinstance(vector, list) or len(vector) != 512
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
            or not 0.99 <= sum(value * value for value in vector) <= 1.01
            or type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
        raise QueryServiceError('invalid encoder response')
    return vector, duration


def encode_online_query(query):
    if os.getenv('QUERY_ENCODER_ENABLED') != '1':
        raise QueryServiceError('encoder disabled')
    if not _slots.acquire(blocking=False):
        raise QueryServiceError('encoder busy', status_code=429)
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post('http://127.0.0.1:8081/encode', json={'query': query}, timeout=(1, 8))
            if response.status_code == 429:
                raise QueryServiceError('encoder busy', status_code=429)
            response.raise_for_status()
            if len(response.content) > 65536:
                raise QueryServiceError('encoder response too large')
            return validate_embedding(response.json())
    except QueryServiceError:
        raise
    except Exception as exc:
        raise QueryServiceError() from exc
    finally:
        _slots.release()
