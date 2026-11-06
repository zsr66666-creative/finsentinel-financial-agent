"""Optional local sentence-transformers embedding adapter."""

import time


class LocalSentenceTransformerEmbeddings:
    def __init__(self, model_name="BAAI/bge-small-zh-v1.5", model=None, cache_folder=None):
        self.model_name = model_name
        self.cache_folder = cache_folder
        self._model = model
        self._dimension = None
        self.last_call_ms = 0.0

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, cache_folder=self.cache_folder)
        return self._model

    def _encode(self, texts):
        started = time.perf_counter()
        vectors = self.model.encode(texts, normalize_embeddings=True)
        self.last_call_ms = (time.perf_counter() - started) * 1000
        values = vectors.tolist() if hasattr(vectors, "tolist") else vectors
        if values:
            self._dimension = len(values[0])
        return values

    def embed_documents(self, texts):
        return self._encode(list(texts))

    def embed_query(self, text):
        return self._encode([text])[0]

    @property
    def dimension(self):
        return self._dimension

    def metadata(self):
        return {"model_name": self.model_name, "dimension": self.dimension, "last_call_ms": round(self.last_call_ms, 3)}
