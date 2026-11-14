import pytest
from app.online_query import MODEL_ID
from app.query_encoder_service import Encoder


class Tokenizer:
    def encode(self, text):
        self.text = text
        return type('Tokens', (), dict(ids=[101, 5, 102], attention_mask=[1, 1, 1], type_ids=[0, 0, 0]))()


def test_encoder_prefix_inputs_and_busy_rejection():
    import numpy as np
    import threading
    instance = Encoder.__new__(Encoder)
    instance.np = np
    instance.tokenizer = Tokenizer()
    instance.lock = threading.Lock()
    class Session:
        def run(self, outputs, inputs):
            assert set(inputs) == {'input_ids', 'attention_mask', 'token_type_ids'}
            assert inputs['input_ids'].shape == (1, 3)
            assert inputs['input_ids'].dtype == np.int64
            return [np.array([[1.] + [0.] * 511])]
    instance.session = Session()
    value = instance.encode('应收账款')
    assert value['model'] == MODEL_ID
    assert len(value['vector']) == 512
    assert instance.tokenizer.text == '为这个句子生成表示以用于检索相关文章：应收账款'
    instance.lock.acquire()
    try:
        assert instance.encode('ignored') is None
    finally:
        instance.lock.release()


def test_encoder_releases_slot_on_failure():
    import numpy as np
    import threading
    instance = Encoder.__new__(Encoder)
    instance.np = np
    instance.tokenizer = Tokenizer()
    instance.lock = threading.Lock()
    class Session:
        def run(self, *args):
            raise RuntimeError('failure')
    instance.session = Session()
    with pytest.raises(RuntimeError):
        instance.encode('问题')
    assert instance.lock.acquire(False)
