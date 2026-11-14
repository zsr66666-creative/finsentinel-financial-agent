"""Administrator-only artifact -> verified selected-page vector publication."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import shutil
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.corpus_index import prepare_chunks, publish_chunks, verify_pdf_text
from app.online_query import MODEL_ID


@contextmanager
def exchange_directory(parent):
    parent = Path(parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / ('task9-exchange-' + uuid4().hex)
    directory.mkdir(mode=0o700 if os.name != 'nt' else 0o777)
    try:
        yield directory
    finally:
        if directory.resolve().parent != parent:
            raise ValueError('exchange directory changed unexpectedly')
        shutil.rmtree(directory)


def load_chunks(engine, artifact_id, artifact_root):
    root = Path(artifact_root).resolve(strict=True)
    with engine.connect() as conn:
        artifact = conn.execute(text('SELECT * FROM ingestion_artifacts WHERE id=:id'), {'id': artifact_id}).mappings().one()
    path = Path(artifact['artifact_path']).resolve(strict=True)
    if not path.is_relative_to(root / 'parsed'):
        raise ValueError('parsed artifact escapes ingestion root')
    parsed = json.loads(path.read_text(encoding='utf-8'))
    blob = (root / 'blobs' / (artifact['sha256'] + '.pdf')).resolve(strict=True)
    if not blob.is_relative_to(root / 'blobs'):
        raise ValueError('PDF blob escapes ingestion root')
    chunks = prepare_chunks(artifact, parsed, blob)
    verify_pdf_text(blob, parsed)
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-id', required=True)
    parser.add_argument('--artifact-root', required=True)
    parser.add_argument('--encoder-python', required=True)
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    engine = create_engine(os.environ['DATABASE_URL'])
    try:
        chunks = load_chunks(engine, args.artifact_id, args.artifact_root)
        with exchange_directory(Path(args.output).resolve().parent) as directory:
            source, target = Path(directory)/'chunks.json', Path(directory)/'vectors.json'
            source.write_text(json.dumps(chunks, ensure_ascii=False), encoding='utf-8')
            encoder_script = Path(__file__).with_name('task9_encode_documents.py')
            subprocess.run([args.encoder_python, str(encoder_script), '--input', str(source), '--output', str(target),
                            '--model-dir', args.model_dir], check=True, timeout=600)
            encoded = json.loads(target.read_text(encoding='utf-8'))
            if encoded['model'] != MODEL_ID:
                raise ValueError('document encoder model mismatch')
            report = publish_chunks(engine, chunks, encoded['vectors'])
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
