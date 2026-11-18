import hashlib
import json

import pytest

import scripts.package_task8 as package_task8


def model_dir(tmp_path, monkeypatch):
    model = tmp_path / 'model.onnx'
    tokenizer = tmp_path / 'tokenizer.json'
    model.write_bytes(b'onnx')
    tokenizer.write_bytes(b'tokenizer')
    model_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    tokenizer_hash = hashlib.sha256(tokenizer.read_bytes()).hexdigest()
    monkeypatch.setattr(package_task8, 'MODEL_SHA256', model_hash)
    prefix = 'query prefix'
    (tmp_path / 'reference.json').write_text(json.dumps({
        'revision': package_task8.MODEL_REVISION,
        'prefix': prefix,
    }))
    (tmp_path / 'assessment.json').write_text(json.dumps({
        'revision': package_task8.MODEL_REVISION,
        'parity_passed': True,
        'imported_torch': False,
    }))
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'model': f'BAAI/bge-small-zh-v1.5@{package_task8.MODEL_REVISION}',
        'prefix': prefix,
        'files': {'model.onnx': model_hash, 'tokenizer.json': tokenizer_hash},
    }))
    (tmp_path / 'tokenizer_config.json').write_text('{}')
    return tmp_path


def test_private_package_includes_runtime_manifest_and_verified_artifacts(tmp_path, monkeypatch):
    artifacts = package_task8.load_model_artifacts(model_dir(tmp_path, monkeypatch))

    assert 'model/manifest.json' in artifacts
    assert hashlib.sha256(artifacts['model/model.onnx']).hexdigest() == package_task8.MODEL_SHA256


def test_private_package_rejects_model_artifact_that_disagrees_with_runtime_manifest(tmp_path, monkeypatch):
    root = model_dir(tmp_path, monkeypatch)
    (root / 'tokenizer.json').write_bytes(b'tampered')

    with pytest.raises(ValueError, match='model manifest checksum mismatch: tokenizer.json'):
        package_task8.load_model_artifacts(root)
