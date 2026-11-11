import pytest
from scripts.scope_supplement import verify_restored


def test_readback_checks_vector_hash_and_all_provenance():
    row=dict(chunk_id='x',text='source',embedding=[1.0]+[0.0]*511,page=62)
    actual=dict(model='model',dimensions=512,text_sha256='hash',
                embedding=__import__('json').dumps(row['embedding']),provenance={k:v for k,v in row.items() if k!='embedding'})
    verify_restored(row,actual,'model','hash')
    for field,value in [('text_sha256','wrong'),('provenance',{}),('embedding','[0.0,1.0]')]:
        with pytest.raises(ValueError):
            verify_restored(row,{**actual,field:value},'model','hash')
