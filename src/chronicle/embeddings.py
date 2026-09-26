from pathlib import Path
from threading import Lock

from chronicle import config

_model = None
_model_lock = Lock()


def embed_text(text: str) -> list[float]:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(
                    model_name=config.EMBED_MODEL,
                    cache_dir=str(Path.home() / ".chronicle" / "models"),
                    lazy_load=True,
                )

    embedding = next(iter(_model.embed([text])))
    return embedding.tolist()
