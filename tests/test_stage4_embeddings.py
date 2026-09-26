import math

from app.services.embedding_service import embed_passages, embed_query


class FakeModel:
    def __init__(self):
        self.calls = []

    def encode(self, values, **kwargs):
        self.calls.append((values, kwargs))
        return [[1.0 / math.sqrt(384)] * 384 for _ in values]


def test_e5_passage_prefix_and_normalized_dimension():
    model = FakeModel()
    vector = embed_passages(["hello"], model=model)[0]
    assert model.calls[0][0] == ["passage: hello"]
    assert model.calls[0][1]["normalize_embeddings"] is True
    assert len(vector) == 384
    assert math.isclose(sum(value * value for value in vector), 1.0, rel_tol=1e-6)


def test_e5_query_prefix():
    model = FakeModel()
    embed_query("find AI", model=model)
    assert model.calls[0][0] == ["query: find AI"]
