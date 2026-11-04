"""Local embeddings for reference passages (fastembed, ONNX on the CPU; no API, no GPU).
Vectors are L2-normalised float32 so a dot product is the cosine similarity. The model downloads once
into data/models. Nothing here changes passage text: vectors only help find the printed passage."""
from functools import lru_cache

import numpy as np
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ReferenceChunk

BATCH = 64


def model_name() -> str:
    return (get_settings().reference_embed_model or "").strip()


@lru_cache(maxsize=1)
def _model(name: str):
    from fastembed import TextEmbedding
    return TextEmbedding(name, cache_dir=str(get_settings().data_path / "models"))


def available() -> bool:
    if not model_name():
        return False
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def embed(texts: list[str]) -> np.ndarray:
    vectors = np.asarray(list(_model(model_name()).embed(texts, batch_size=BATCH)), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def embed_missing(db: Session, progress=None) -> int:
    """Embed every passage without a vector from the current model; returns how many were embedded."""
    name = model_name()
    if not available():
        return 0
    done = 0
    while True:
        rows = (db.query(ReferenceChunk)
                .filter((ReferenceChunk.embedding.is_(None)) | (ReferenceChunk.embedding_model != name))
                .order_by(ReferenceChunk.id).limit(BATCH * 8).all())
        if not rows:
            return done
        for chunk, vector in zip(rows, embed([c.text for c in rows])):
            chunk.embedding, chunk.embedding_model = to_blob(vector), name
        db.commit()
        done += len(rows)
        if progress:
            progress(done)
