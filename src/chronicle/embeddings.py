import os
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
                # Windows without Developer Mode can't create symlinks, so the
                # Hugging Face cache falls back to copies (a bit more disk) and
                # warns about it; that's harmless, so don't alarm anyone.
                os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
                from fastembed import TextEmbedding

                _model = TextEmbedding(
                    model_name=config.EMBED_MODEL,
                    cache_dir=str(Path.home() / ".chronicle" / "models"),
                    lazy_load=True,
                )

    embedding = next(iter(_model.embed([text])))
    return embedding.tolist()


def embed_or_empty(text: str) -> list[float]:
    """embed_text, but [] (no model download, no work) when semantic search is
    off; the NullVectorIndex ignores the empty vector."""
    return embed_text(text) if config.semantic_enabled() else []
