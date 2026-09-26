from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from chronicle import embeddings


embed_text = embeddings.embed_text


def test_import_does_not_import_fastembed():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import chronicle.embeddings; print('fastembed' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_first_concurrent_calls_construct_model_once(monkeypatch):
    constructions = []

    class FakeVector:
        def tolist(self):
            return [1.0]

    class SlowTextEmbedding:
        def __init__(self, **kwargs):
            constructions.append(kwargs)
            time.sleep(0.1)

        def embed(self, texts):
            return iter([FakeVector()])

    monkeypatch.setitem(
        sys.modules,
        "fastembed",
        SimpleNamespace(TextEmbedding=SlowTextEmbedding),
    )
    monkeypatch.setattr(embeddings, "_model", None)
    callers_ready = threading.Barrier(2)

    def call_embed():
        callers_ready.wait()
        return embed_text("hello")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: call_embed(), range(2)))

    assert results == [[1.0], [1.0]]
    assert len(constructions) == 1


def test_embed_text_returns_768_floats():
    vector = embed_text("hello world")
    assert len(vector) == 768
    assert all(isinstance(v, float) for v in vector)


def test_embed_text_differs_for_different_input():
    a = embed_text("the qdrant collection stores vectors")
    b = embed_text("the weather today is sunny and warm")
    assert a != b
