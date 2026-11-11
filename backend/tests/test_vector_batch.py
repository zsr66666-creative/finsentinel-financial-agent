import copy
import pytest
from scripts.vector_batch import validate, digest, MODEL, REVISION

def batch():
    return dict(model=MODEL, revision=REVISION, rows=[dict(chunk_id='source-p1-s0',
        text='source', text_sha256=digest(b'source'), source_url='local://report.pdf',
        document_sha256='a'*64, page=1, embedding=[1.0]+[0.0]*511)])

def test_valid_batch_and_invalid_numeric_vectors():
    validate(batch())
    for vector in ([1.0], [float('nan')]*512, [0.0]*512):
        value=batch(); value['rows'][0]['embedding']=vector
        with pytest.raises(ValueError): validate(value)

def test_hash_provenance_and_duplicate_validation():
    for key,value in [('text_sha256','bad'),('source_url',''),('page',0)]:
        package=batch(); package['rows'][0][key]=value
        with pytest.raises(ValueError): validate(package)
    package=batch(); package['rows'].append(copy.deepcopy(package['rows'][0]))
    with pytest.raises(ValueError): validate(package)
