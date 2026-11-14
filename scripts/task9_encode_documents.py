"""Bounded offline document encoding; never run beside the resident encoder."""
import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter

from app.query_encoder_service import Encoder, MODEL_ID


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model-dir', required=True)
    args = parser.parse_args()
    chunks = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if not 0 < len(chunks) <= 10000:
        raise ValueError('document chunk count out of bounds')
    started = perf_counter()
    encoder = Encoder(args.model_dir)
    vectors = []
    for chunk in chunks:
        result = encoder.encode_document(chunk['text'])
        if result is None:
            raise ValueError('unexpected concurrent encoding')
        vectors.append(result['vector'])
    if 'torch' in sys.modules:
        raise ValueError('unexpected torch runtime')
    # The administrator owns the temporary exchange directory, not public git.
    Path(args.output).write_text(json.dumps(dict(model=MODEL_ID, vectors=vectors), allow_nan=False), encoding='utf-8')
    import psutil
    peak = getattr(psutil.Process().memory_info(), 'peak_wset', psutil.Process().memory_info().rss)
    if sys.platform.startswith('linux'):
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    print(json.dumps(dict(chunks=len(chunks), elapsed_ms=round((perf_counter()-started)*1000, 1),
                          peak_mib=round(peak/1024**2, 1), imported_torch=False, document_query_prefix=False)))
    if peak > 384 * 1024**2:
        raise SystemExit('document encoding memory exceeds 384 MiB acceptance budget')


if __name__ == '__main__':
    main()
